import pytest
from querysaas import AiCancellationToken,AiCancelledError,AiRetryPolicy,AiUsageTelemetry,enterprise_profile,generate_enterprise_text,iter_sse_text
class R:
 ok=True;status_code=200;headers={}
 def __init__(self,data=None,lines=None): self.data=data or {};self.lines=lines or []
 def json(self): return self.data
 def iter_lines(self,decode_unicode=True): return iter(self.lines)
class S:
 def __init__(self,r): self.r=r
 def request(self,*a,**k): return self.r
def test_mistral_adapter():
 p=enterprise_profile("mistral","mistral-small",api_key="x")
 r=generate_enterprise_text(p,"hello",session=S(R({"choices":[{"message":{"content":"ok"}}]})))
 assert r.text=="ok" and r.provider=="mistral"
def test_anthropic_adapter():
 p=enterprise_profile("anthropic","claude",api_key="x")
 r=generate_enterprise_text(p,"hello",session=S(R({"content":[{"type":"text","text":"ok"}]})))
 assert r.text=="ok"
def test_cancel():
 t=AiCancellationToken();t.cancel()
 with pytest.raises(AiCancelledError): t.raise_if_cancelled()
def test_sse():
 r=R(lines=['data: {"choices":[{"delta":{"content":"A"}}]}','data: [DONE]'])
 assert list(iter_sse_text(r))==["A"]
def test_retry_policy_validation():
 with pytest.raises(ValueError): AiRetryPolicy(max_attempts=0)
def test_telemetry():
 x=AiUsageTelemetry();assert x.to_dict()["requests"]==0