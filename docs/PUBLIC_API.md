# BI Publisher 0.3.2 Public API

```python
connection.get_folder_contents(folder_absolute_path="", item_type=None)
connection.download_bip_object(report_absolute_path, output_file=None, overwrite=False)
connection.upload_bip_object(report_object_absolute_path_url, object_type, object_zipped_data)
connection.extract_bip_object(object_zipped_data, output_directory=None, overwrite=False)
connection.get_bip_object_xml(report_absolute_path, member_name=None, include_non_xml=False)
connection.bip_object_exists(report_absolute_path)
connection.verify_bip_object(report_absolute_path, object_type=None, verification_mode="readable")
connection.delete_bip_object(report_absolute_path, *, missing_ok=False, verify=True, timeout=10, poll_interval=0.5)
connection.replace_bip_object(report_object_absolute_path_url, object_type, object_zipped_data, *, verify=True, timeout=10, poll_interval=0.5)
connection.plan_bip_object_copy(destination_connection, source_report_absolute_path, destination_absolute_path, object_type=None, overwrite=False)
connection.copy_bip_object(destination_connection, source_report_absolute_path, destination_absolute_path, object_type=None, *, overwrite=False, verify=True, dry_run=False, timeout=10, poll_interval=0.5)
connection.schedule_bip_report(report_absolute_path, *, output_format="csv", parameters=None, size_of_data_chunk_download=-1, notification_user_name=None, notification_to=None, notify_when_success=False, notify_when_failed=False, notify_when_skipped=False, notify_when_warning=False, save_data=True, save_output=True, schedule_public=True, job_name=None, user_job_desc=None)
```


## 0.3.2 correctness contract

- BI Publisher exceptions are canonical in `querysaas.exceptions`, accept structured metadata, and expose redacted `to_dict()` output.
- `verification_mode='readable'` is the only supported verification mode in 0.3.2. Oracle may repackage archives, so raw ZIP equality is not a migration-success criterion.
- CREATE and REPLACE poll for catalog visibility before readability verification. An ambiguous response or transport exception is treated as a warning when the committed target is readable.
- Scheduling uses `ScheduleReportWSSService` and the `ScheduleReportService` namespace. Notifications are opt-in. Enabling any notification event requires both `notification_to` and `notification_user_name`.
- `P_B64_CONTENT` is passed through as supplied and parameter values are excluded from public results.


## Local Data Library 0.3.4
```python
db = open_data_library(folder, database=None, recursive=True, read_only=False)
db.refresh(); db.list_files(); db.list_tables(); db.describe_table(name); db.preview(name); db.count(name)
db.query(sql, parameters=None); db.execute(sql, parameters=None); db.materialize(source, as_table=None, replace=False)
db.export_csv(source, output_file); db.export_tsv(source, output_file); db.export_parquet(source, output_file)
```


## Network retry parameters

The following public methods expose `max_retries=3`, `retry_base_seconds=1.0`, and `retry_max_seconds=30.0`:

- `execute_query`
- `FusionConnection.executequery`
- `copy_fusion_to_local`
- `copy_fusion_to_local_parallel`
- `copy2file`
- `copy2file_parallel`
- `copy2dd`
- `copy2dd_parallel`
- `syncquery2dd`
- `syncquery2dd_parallel`
- `get_folder_contents`
- `download_bip_object`
- `get_bip_object_xml`
- `bip_object_exists`
- `verify_bip_object`
- `refresh_fbdi_jobs`
- `get_fbdi_jobs`
- `monitor_ess_job`

The default allows one initial attempt plus three retries. Only recognized transient network and service failures are retried. Local-only methods do not expose these parameters.
