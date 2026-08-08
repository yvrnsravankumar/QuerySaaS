"""Retry, cancellation, streaming helpers, and usage telemetry."""
from __future__ import annotations
import json,time
from dataclasses import dataclass,field
from typing import Any,Callable,Iterable,Mapping
from .ai import AiProviderError, AiResponse, generate_ai_text

class AiCancelledError(AiProviderError): pass
@dataclass
class AiCancellationToken:
 cancelled: bool=False
 def cancel(self): self.cancelled=True
 def raise_if_cancelled(self):
  if self.cancelled: raise AiCancelledError("AI request was cancelled.")
@dataclass(frozen=True)
class AiRetryPolicy:
 max_attempts:int=3; initial_delay:float=.25; multiplier:float=2.0; max_delay:float=4.0
 def __post_init__(self):
  if self.max_attempts<1: raise ValueError("max_attempts must be at least 1.")
@dataclass
class AiUsageTelemetry:
 requests:int=0; failures:int=0; retries:int=0; input_tokens:int=0; output_tokens:int=0; total_tokens:int=0; duration_ms:float=0
 def record(self,response,duration_ms):
  self.requests+=1; self.duration_ms+=duration_ms; u=dict(response.usage or {}); self.input_tokens+=int(u.get("prompt_tokens",u.get("input_tokens",0)) or 0); self.output_tokens+=int(u.get("completion_tokens",u.get("output_tokens",0)) or 0); self.total_tokens+=int(u.get("total_tokens",0) or 0)
 def to_dict(self): return dict(self.__dict__)

def generate_ai_text_resilient(profile,prompt,*,retry_policy=None,cancellation_token=None,telemetry=None,session=None,**kwargs):
 policy=retry_policy or AiRetryPolicy(); token=cancellation_token or AiCancellationToken(); stats=telemetry or AiUsageTelemetry(); delay=policy.initial_delay; last=None
 for attempt in range(1,policy.max_attempts+1):
  token.raise_if_cancelled(); started=time.perf_counter()
  try:
   result=generate_ai_text(profile,prompt,session=session,**kwargs); stats.record(result,(time.perf_counter()-started)*1000); return result
  except AiCancelledError: raise
  except Exception as exc:
   last=exc; stats.failures+=1
   if attempt>=policy.max_attempts: raise
   stats.retries+=1; token.raise_if_cancelled(); time.sleep(min(delay,policy.max_delay)); delay*=policy.multiplier
 raise last

def iter_sse_text(response,cancellation_token=None):
 token=cancellation_token or AiCancellationToken()
 for raw in response.iter_lines(decode_unicode=True):
  token.raise_if_cancelled()
  if not raw or not raw.startswith("data:"): continue
  data=raw[5:].strip()
  if data=="[DONE]": break
  payload=json.loads(data); delta=payload.get("choices",[{}])[0].get("delta",{}).get("content")
  if delta: yield delta