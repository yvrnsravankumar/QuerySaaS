import xml.etree.ElementTree as ET
import pytest
import requests
from querysaas import bip

class Response:
    def __init__(self,status=200,body=b"<root/>"):
        self.status_code=status; self.content=body; self.text=body.decode("utf-8","replace"); self.ok=200<=status<300
class Session:
    def __init__(self,response=None,error=None): self.response=response; self.error=error; self.calls=[]
    def post(self,url,**kwargs):
        self.calls.append((url,kwargs))
        if self.error: raise self.error
        return self.response
class Connection:
    url="https://fusion.example.com"; auth_header="Bearer secret"; timeout=9; verify_ssl=True
    def __init__(self,session): self.session=session

def fault(reason="Unable to find ReportObject"):
    return f'''<soap:Envelope xmlns:soap="{bip.SOAP_NS}"><soap:Body><soap:Fault><soap:Code><soap:Value>soap:Receiver</soap:Value></soap:Code><soap:Reason><soap:Text>{reason}</soap:Text></soap:Reason></soap:Fault></soap:Body></soap:Envelope>'''.encode()

def test_soap12_headers_endpoint_and_auth_not_returned():
    session=Session(Response())
    bip._transport(Connection(session),"downloadReportObject",[("reportAbsolutePath","/Custom/X.xdm")])
    url,kw=session.calls[0]
    assert url.endswith("/xmlpserver/services/ExternalReportWSSService")
    assert kw["headers"]["Content-Type"]=="application/soap+xml; charset=UTF-8"
    assert kw["headers"]["Accept"]=="application/soap+xml, text/xml"
    assert kw["headers"]["Authorization"]=="Bearer secret"

def test_http500_fault_parsed_before_http_error():
    with pytest.raises(bip.BIPSOAPFaultError) as info:
        bip._transport(Connection(Session(Response(500,fault()))),"downloadReportObject",[])
    assert info.value.status_code==500
    assert info.value.operation=="downloadReportObject"
    assert "secret" not in str(info.value)

def test_raw_http500_is_http_error():
    with pytest.raises(bip.BIPHTTPError) as info:
        bip._transport(Connection(Session(Response(500,b"plain error"))),"op",[])
    assert info.value.status_code==500

def test_invalid_success_xml():
    with pytest.raises(bip.BIPInvalidResponseError): bip._transport(Connection(Session(Response(200,b"bad"))),"op",[])
@pytest.mark.parametrize("status,error",[(401,bip.BIPAuthenticationError),(403,bip.BIPAuthorizationError)])
def test_auth_errors(status,error):
    with pytest.raises(error): bip._transport(Connection(Session(Response(status,b""))),"op",[])
def test_timeout_and_connection():
    with pytest.raises(bip.BIPTimeoutError): bip._transport(Connection(Session(error=requests.Timeout())),"op",[])
    with pytest.raises(bip.BIPConnectionError): bip._transport(Connection(Session(error=requests.ConnectionError())),"op",[])

def test_schedule_service_constants():
    assert bip.SCHEDULE_REPORT_SERVICE_PATH.endswith("ScheduleReportWSSService")
    assert bip.SCHEDULE_REPORT_NS.endswith("ScheduleReportService")