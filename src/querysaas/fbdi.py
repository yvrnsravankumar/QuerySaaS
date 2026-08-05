"""Oracle Fusion FBDI import and purge proof-of-concept pipelines."""
from __future__ import annotations
import base64, csv, json, re, tempfile, zipfile
from importlib.resources import files
from pathlib import Path
import duckdb
import requests

ENDPOINT='/fscmRestApi/resources/11.13.18.05/erpintegrations'
def _rows():
    p=files('querysaas').joinpath('data/fbdi_jobs.csv')
    with p.open('r',encoding='utf-8-sig',newline='') as h: return [{k.strip():(v or '').strip() for k,v in r.items()} for r in csv.DictReader(h)]
def _normalize_fbdi_selector(value):
    """Normalize a selector while preserving exact Oracle CSV output names."""
    if value is None:
        return ""
    name = Path(str(value).strip()).name
    if Path(name).suffix.casefold() in {".csv", ".ctl"}:
        name = Path(name).stem
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _singular_fbdi_selector(value):
    """Return a conservative singular normalized selector."""
    normalized = _normalize_fbdi_selector(value)
    if normalized.endswith("ies") and len(normalized) > 3:
        return normalized[:-3] + "y"
    if normalized.endswith("s") and len(normalized) > 1:
        return normalized[:-1]
    return normalized


def _configuration_key(row):
    """Return the logical Oracle FBDI submission configuration key."""
    return (
        row.get("ERP_INTERFACE_OPTIONS_ID", "").strip(),
        row.get("UCM_ACCOUNT", "").strip(),
        row.get("IMPORT_JOB_NAME", "").strip(),
        row.get("BUSINESS_OBJECT", "").strip(),
    )


def _score_row(selector, row):
    """Rank one registry row against a user-friendly selector."""
    requested = _normalize_fbdi_selector(selector)
    requested_singular = _singular_fbdi_selector(selector)
    if not requested:
        return None

    business = _normalize_fbdi_selector(row.get("BUSINESS_OBJECT", ""))
    control = _normalize_fbdi_selector(row.get("CONTROL_FILE_NAME", ""))
    tables = {
        _normalize_fbdi_selector(table_name)
        for table_name in row.get("INTERFACE_TABLE_NAMES", "").split(",")
        if table_name.strip()
    }

    if requested == business:
        return 100, "business_object_exact"
    if requested == control:
        return 90, "control_file_exact"
    if requested in tables:
        return 80, "interface_table_exact"

    if requested_singular and requested_singular == _singular_fbdi_selector(business):
        return 50, "business_object_friendly"
    if requested_singular and requested_singular == _singular_fbdi_selector(control):
        return 40, "control_file_friendly"
    if requested_singular and any(
        requested_singular == _singular_fbdi_selector(table_name)
        for table_name in tables
    ):
        return 30, "interface_table_friendly"

    return None


def _matching(selector):
    """Return only the highest-quality registry matches for a selector."""
    ranked = []
    for row in _rows():
        score = _score_row(selector, row)
        if score is None:
            continue
        matched = dict(row)
        matched["_QUERYSAAS_MATCH_SCORE"] = score[0]
        matched["_QUERYSAAS_MATCH_TYPE"] = score[1]
        ranked.append(matched)

    if not ranked:
        return []

    highest = max(row["_QUERYSAAS_MATCH_SCORE"] for row in ranked)
    return [row for row in ranked if row["_QUERYSAAS_MATCH_SCORE"] == highest]


def _format_configurations(configurations):
    return [
        {
            "erp_interface_options_id": key[0],
            "ucm_account": key[1],
            "import_job_name": key[2],
            "business_object": key[3],
        }
        for key in sorted(configurations)
    ]


def _resolve(selectors, interface_options_id=None):
    """Resolve all supplied selectors to one logical FBDI configuration."""
    selectors = [selector for selector in selectors if str(selector).strip()]
    if not selectors:
        raise ValueError("At least one FBDI selector is required.")

    required_option = None if interface_options_id is None else str(interface_options_id).strip()
    selector_configurations = []

    for selector in selectors:
        matches = _matching(selector)
        if required_option is not None:
            matches = [
                row for row in matches
                if row.get("ERP_INTERFACE_OPTIONS_ID", "").strip() == required_option
            ]

        if not matches:
            raise LookupError(f"No FBDI registry match for '{selector}'.")

        configurations = {_configuration_key(row) for row in matches}
        selector_configurations.append((selector, configurations))

    common = set(selector_configurations[0][1])
    for _, configurations in selector_configurations[1:]:
        common.intersection_update(configurations)

    if not common:
        details = {
            str(selector): _format_configurations(configurations)
            for selector, configurations in selector_configurations
        }
        raise LookupError(
            "The supplied FBDI selectors do not resolve to the same job: "
            f"{details}"
        )

    if len(common) > 1:
        raise LookupError(
            "FBDI selector is ambiguous. Use a more specific friendly name. "
            f"Matches: {_format_configurations(common)}"
        )

    selected_key = next(iter(common))
    registry_rows = [
        row for row in _rows()
        if _configuration_key(row) == selected_key
    ]
    first = registry_rows[0]

    document_account = first.get("DOCUMENT_ACCOUNT", "").strip()
    if not document_account:
        ucm_account = first.get("UCM_ACCOUNT", "").strip()
        if not ucm_account:
            raise ValueError("FBDI registry has no DOCUMENT_ACCOUNT or UCM_ACCOUNT.")
        document_account = ucm_account.strip("/").replace("/", "$/") + "$"

    import_job_name = first.get("IMPORT_JOB_NAME", "").strip().lstrip("/")
    if ";" in import_job_name:
        package_name, definition_name = import_job_name.rsplit(";", 1)
        import_job_name = f"{package_name},{definition_name}"

    return {
        "business_object": first.get("BUSINESS_OBJECT", "").strip(),
        "interface_options_id": first.get("ERP_INTERFACE_OPTIONS_ID", "").strip(),
        "document_account": document_account,
        "job_name": import_job_name,
        "rows": registry_rows,
    }


def _selector_row(selector, config):
    """Resolve a selector to exactly one Oracle control file in a job."""
    matches = [
        row for row in _matching(selector)
        if row.get("ERP_INTERFACE_OPTIONS_ID", "").strip()
        == config["interface_options_id"]
        and row.get("CONTROL_FILE_NAME", "").strip()
    ]

    control_names = {
        row["CONTROL_FILE_NAME"].strip()
        for row in matches
    }
    if len(control_names) != 1:
        raise LookupError(
            f"Selector '{selector}' does not identify one Oracle control file "
            f"for interface option {config['interface_options_id']}. "
            f"Matches: {sorted(control_names)}"
        )

    expected = next(iter(control_names))
    return next(row for row in matches if row["CONTROL_FILE_NAME"].strip() == expected)

def _params(values):
    if values is None:return '#NULL'
    if isinstance(values,str):return values.strip() or '#NULL'
    return ','.join('#NULL' if v is None else str(v) for v in values) or '#NULL'
def _post(self,payload):
    response=requests.post(self.url.rstrip('/')+ENDPOINT,headers={'Authorization':self.auth_header,'Content-Type':'application/vnd.oracle.adf.resourceitem+json','Accept':'application/json'},json=payload,timeout=self.timeout,verify=self.verify_ssl)
    try:data=response.json()
    except ValueError as exc: raise RuntimeError(f'Oracle Fusion returned non-JSON HTTP {response.status_code}: {(response.text or "")[:1000]}') from exc
    if not response.ok: raise RuntimeError(f'Oracle Fusion rejected FBDI request HTTP {response.status_code}: {json.dumps(data)[:2000]}')
    if not data.get('ReqstId'): raise RuntimeError('Oracle Fusion did not return ReqstId; do not automatically resubmit.')
    return data

def import_fbdi(self, source, business_object=None, interface_table=None, standard_file_name=None, parameter_list=None, callback_url='#NULL', notification_code='10', interface_options_id=None):
    path=Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower()!='.zip': raise ValueError('source must be an existing FBDI ZIP file.')
    with zipfile.ZipFile(path) as z: members=[Path(n).name for n in z.namelist() if n.lower().endswith('.csv')]
    selectors=[x for x in (business_object,interface_table,standard_file_name) if x]
    if not selectors: selectors=members
    config=_resolve(selectors,interface_options_id)
    payload={'OperationName':'importBulkData','DocumentContent':base64.b64encode(path.read_bytes()).decode('ascii'),'ContentType':'zip','FileName':path.name,'DocumentAccount':config['document_account'],'JobName':config['job_name'],'ParameterList':_params(parameter_list),'CallbackURL':callback_url or '#NULL','NotificationCode':str(notification_code or '10'),'JobOptions':f"InterfaceDetails={config['interface_options_id']},ImportOption=Y,PurgeOption=N,ExtractFileType=ALL"}
    data=_post(self,payload); return {'status':'SUBMITTED','request_id':str(data['ReqstId']),'zip_file':str(path),**{k:v for k,v in config.items() if k!='rows'},'response':data}

def csv2fbdi(self, source, zip_file=None, parameter_list=None, callback_url='#NULL', notification_code='10', interface_options_id=None):
    if isinstance(source,dict): pairs=[(Path(p).expanduser().resolve(),s) for p,s in source.items()]
    else:
        paths=[Path(source).expanduser().resolve()] if isinstance(source,(str,Path)) else [Path(p).expanduser().resolve() for p in source]
        pairs=[(p,p.name) for p in paths]
    config=_resolve([s for _,s in pairs],interface_options_id)
    for p,_ in pairs:
        if not p.is_file(): raise FileNotFoundError(p)
    name=zip_file or f"{config['business_object']}_FBDI.zip"; out=Path(name).expanduser(); out=out if out.suffix else out.with_suffix('.zip'); out=out.resolve(); out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        used=set()
        for p,s in pairs:
            oracle=Path(_selector_row(s,config)['CONTROL_FILE_NAME']).stem+'.csv'
            if oracle in used: raise ValueError(f'Duplicate Oracle CSV name: {oracle}')
            used.add(oracle); z.write(p,oracle)
    return import_fbdi(self,out,interface_options_id=config['interface_options_id'],parameter_list=parameter_list,callback_url=callback_url,notification_code=notification_code)

def duckdb2fbdi(self, duckdb_path, files, zip_file=None, parameter_list=None, callback_url='#NULL', notification_code='10', interface_options_id=None):
    config=_resolve(list(files),interface_options_id); total=0
    with tempfile.TemporaryDirectory(prefix='querysaas_fbdi_') as tmp:
        generated={}; con=duckdb.connect(str(Path(duckdb_path).expanduser().resolve()),read_only=True)
        try:
            for selector,query in files.items():
                frame=con.execute(query).fetch_df(); total+=len(frame); oracle=Path(_selector_row(selector,config)['CONTROL_FILE_NAME']).stem+'.csv'; p=Path(tmp)/oracle; frame.to_csv(p,index=False,header=False,encoding='utf-8',lineterminator='\n',na_rep=''); generated[p]=selector
        finally: con.close()
        result=csv2fbdi(self,generated,zip_file=zip_file,parameter_list=parameter_list,callback_url=callback_url,notification_code=notification_code,interface_options_id=config['interface_options_id'])
    result['source_rows']=total; result['source_type']='duckdb'; return result

def monitor_ess_job(
    self,
    request_id,
    finder="ESSExecutionDetailsRF",
):
    """Return normalized parent and child ESS execution details."""
    try:
        normalized_request_id = int(request_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("request_id must be a positive integer.") from exc
    if normalized_request_id <= 0:
        raise ValueError("request_id must be a positive integer.")

    if not isinstance(finder, str) or not finder.strip():
        raise ValueError("finder must be a non-empty string.")
    normalized_finder = finder.strip()
    if ";" in normalized_finder:
        raise ValueError(
            "finder must contain only the Oracle finder name. "
            "Do not include ';requestId=' in finder."
        )

    finder_expression = (
        f"{normalized_finder};requestId={normalized_request_id}"
    )
    endpoint = self.url.rstrip("/") + ENDPOINT
    headers = {
        "Authorization": self.auth_header,
        "Accept": "application/json",
        "Content-Type": "application/vnd.oracle.adf.resourceitem+json",
    }
    params = {"finder": finder_expression}
    sender = (
        getattr(getattr(self, "session", None), "get", None)
        or getattr(getattr(self, "_session", None), "get", None)
        or requests.get
    )
    try:
        response = sender(
            endpoint,
            headers=headers,
            params=params,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
    except requests.Timeout as exc:
        raise RuntimeError(
            f"Oracle Fusion ESS monitor timed out for request "
            f"{normalized_request_id}."
        ) from exc
    except requests.ConnectionError as exc:
        raise RuntimeError(
            f"Oracle Fusion ESS monitor connection failed for request "
            f"{normalized_request_id}."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Oracle Fusion ESS monitor returned a non-JSON response "
            f"(HTTP {response.status_code})."
        ) from exc

    if response.status_code == 401:
        raise RuntimeError("Oracle Fusion ESS monitor authentication failed.")
    if response.status_code == 403:
        raise RuntimeError("Oracle Fusion ESS monitor authorization failed.")
    if not response.ok:
        raise RuntimeError(
            "Oracle Fusion ESS monitor failed "
            f"(HTTP {response.status_code}): {json.dumps(data)[:2000]}"
        )

    items = data.get("items") or []
    if not items:
        return {
            "success": False,
            "found": False,
            "request_id": str(normalized_request_id),
            "finder": normalized_finder,
            "finder_expression": finder_expression,
            "status": None,
            "job_name": None,
            "job_path": None,
            "children": [],
            "terminal": False,
            "succeeded": False,
        }

    item = items[0]
    request_status = item.get("RequestStatus")
    if not request_status:
        raise RuntimeError(
            "Oracle Fusion ESS monitor response has no RequestStatus."
        )
    try:
        status_payload = (
            json.loads(request_status)
            if isinstance(request_status, str)
            else request_status
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Oracle Fusion ESS RequestStatus is not valid JSON."
        ) from exc

    job = status_payload.get("JOBS") or status_payload.get("jobs") or {}
    children_value = job.get("CHILD") or job.get("child") or []
    if isinstance(children_value, dict):
        children_value = [children_value]

    children = [
        {
            "request_id": str(child.get("REQUESTID"))
            if child.get("REQUESTID") is not None else None,
            "job_name": child.get("JOBNAME"),
            "job_path": child.get("JOBPATH"),
            "status": child.get("STATUS"),
        }
        for child in children_value
    ]
    status = job.get("STATUS")
    terminal_statuses = {
        "SUCCEEDED", "ERROR", "WARNING", "CANCELLED", "EXPIRED"
    }
    return {
        "success": True,
        "found": True,
        "operation": item.get("OperationName") or "getESSExecutionDetails",
        "request_id": str(job.get("REQUESTID") or item.get("ReqstId") or normalized_request_id),
        "finder": normalized_finder,
        "finder_expression": finder_expression,
        "job_name": job.get("JOBNAME"),
        "job_path": job.get("JOBPATH"),
        "status": status,
        "children": children,
        "child_count": len(children),
        "terminal": str(status or "").upper() in terminal_statuses,
        "succeeded": str(status or "").upper() == "SUCCEEDED",
        "raw_request_status": status_payload,
    }


def _normalize_ess_parameters(parameters):
    """Normalize Oracle ESS parameters to a comma-delimited string."""
    if parameters is None:
        return "#NULL"
    if isinstance(parameters, str):
        return parameters.strip() or "#NULL"
    if isinstance(parameters, (list, tuple)):
        return ",".join(
            "#NULL" if value is None else str(value)
            for value in parameters
        ) or "#NULL"
    raise TypeError("parameters must be None, a string, list, or tuple.")


def submit_ess_job(
    self,
    job_package_name,
    job_definition_name,
    parameters=None,
):
    """Submit an Oracle Fusion ESS job through erpintegrations."""
    if not isinstance(job_package_name, str) or not job_package_name.strip():
        raise ValueError("job_package_name cannot be empty.")
    if not isinstance(job_definition_name, str) or not job_definition_name.strip():
        raise ValueError("job_definition_name cannot be empty.")

    package_name = job_package_name.strip()
    definition_name = job_definition_name.strip()
    ess_parameters = _normalize_ess_parameters(parameters)
    payload = {
        "OperationName": "submitESSJobRequest",
        "JobPackageName": package_name,
        "JobDefName": definition_name,
        "ESSParameters": ess_parameters,
    }
    data = _post(self, payload)
    request_id = data.get("ReqstId")
    if request_id is None or not str(request_id).strip():
        raise RuntimeError(
            "Oracle Fusion did not return ReqstId for the ESS submission. "
            "The outcome is ambiguous and must not be automatically resubmitted."
        )
    return {
        "status": "SUBMITTED",
        "operation": "submitESSJobRequest",
        "request_id": str(request_id),
        "job_package_name": package_name,
        "job_definition_name": definition_name,
        "ess_parameters": ess_parameters,
        "response": data,
    }


def purge_fbdi(
    self,
    load_request_id=None,
    low_load_request_id=None,
    high_load_request_id=None,
    business_object=None,
    interface_table=None,
    standard_file_name=None,
    interface_options_id=None,
):
    """Submit InterfaceLoaderPurge for one load request or a request range."""
    single_mode = load_request_id is not None
    range_mode = (
        low_load_request_id is not None
        or high_load_request_id is not None
    )

    if single_mode and range_mode:
        raise ValueError(
            "Supply either load_request_id or low/high load request IDs, "
            "not both."
        )

    if not single_mode and not range_mode:
        raise ValueError(
            "Supply load_request_id, or both low_load_request_id and "
            "high_load_request_id."
        )

    if single_mode:
        try:
            normalized_load_id = int(load_request_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "load_request_id must be a positive integer."
            ) from exc

        if normalized_load_id <= 0:
            raise ValueError(
                "load_request_id must be a positive integer."
            )

        load_parameter = str(normalized_load_id)
        low_parameter = "#NULL"
        high_parameter = "#NULL"
        purge_mode = "single"

    else:
        if low_load_request_id is None or high_load_request_id is None:
            raise ValueError(
                "Both low_load_request_id and high_load_request_id are "
                "required for a range purge."
            )

        try:
            normalized_low_id = int(low_load_request_id)
            normalized_high_id = int(high_load_request_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "low_load_request_id and high_load_request_id must be "
                "positive integers."
            ) from exc

        if normalized_low_id <= 0 or normalized_high_id <= 0:
            raise ValueError(
                "low_load_request_id and high_load_request_id must be "
                "positive integers."
            )

        if normalized_low_id > normalized_high_id:
            raise ValueError(
                "low_load_request_id cannot be greater than "
                "high_load_request_id."
            )

        load_parameter = "#NULL"
        low_parameter = str(normalized_low_id)
        high_parameter = str(normalized_high_id)
        purge_mode = "range"

    if interface_options_id is None:
        selectors = [
            value
            for value in (
                business_object,
                interface_table,
                standard_file_name,
            )
            if value is not None and str(value).strip()
        ]

        if not selectors:
            raise ValueError(
                "Supply business_object, interface_table, "
                "standard_file_name, or interface_options_id."
            )

        resolved = _resolve(selectors)
        resolved_option_id = resolved["interface_options_id"]
        resolved_business_object = resolved["business_object"]
    else:
        try:
            normalized_option_id = int(interface_options_id)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "interface_options_id must be a positive integer."
            ) from exc

        if normalized_option_id <= 0:
            raise ValueError(
                "interface_options_id must be a positive integer."
            )

        resolved_option_id = str(normalized_option_id)
        resolved_business_object = None

    ess_parameters = ",".join(
        [
            str(resolved_option_id),
            load_parameter,
            low_parameter,
            high_parameter,
            "#NULL",
            "ORA_FBDI",
            "USER",
            "#NULL",
            "#NULL",
        ]
    )

    submission = self.submit_ess_job(
        job_package_name=(
            "/oracle/apps/ess/financials/commonModules/"
            "shared/common/interfaceLoader"
        ),
        job_definition_name="InterfaceLoaderPurge",
        parameters=ess_parameters,
    )

    return {
        "status": submission["status"],
        "operation": "purge_fbdi",
        "purge_mode": purge_mode,
        "purge_request_id": submission["request_id"],
        "load_request_id": (
            int(load_parameter)
            if load_parameter != "#NULL"
            else None
        ),
        "low_load_request_id": (
            int(low_parameter)
            if low_parameter != "#NULL"
            else None
        ),
        "high_load_request_id": (
            int(high_parameter)
            if high_parameter != "#NULL"
            else None
        ),
        "erp_interface_options_id": str(resolved_option_id),
        "business_object": resolved_business_object,
        "ess_parameters": ess_parameters,
        "response": submission["response"],
    }


def install_fbdi_methods(cls):
    cls.import_fbdi = import_fbdi
    cls.csv2fbdi = csv2fbdi
    cls.duckdb2fbdi = duckdb2fbdi
    cls.submit_ess_job = submit_ess_job
    cls.monitor_ess_job = monitor_ess_job
    cls.purge_fbdi = purge_fbdi
