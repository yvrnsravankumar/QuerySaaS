"""Enterprise AI provider adapters for QuerySaaS 0.3.0."""
from dataclasses import dataclass
from typing import Any, Mapping
from .ai import AiProviderError, AiResponse, AiProviderProfile, _send, _join

ENTERPRISE_DEFAULTS={
 "anthropic":"https://api.anthropic.com",
 "mistral":"https://api.mistral.ai/v1",
 "cohere":"https://api.cohere.com/v2",
 "azure_openai":None,
 "microsoft_foundry":None,
 "ibm_ica":None,
}

def enterprise_profile(provider,model,*,base_url=None,api_key=None,timeout=120,headers=None):
 p=str(provider).lower().strip()
 if p not in ENTERPRISE_DEFAULTS: raise ValueError("Unsupported enterprise provider: "+p)
 url=base_url or ENTERPRISE_DEFAULTS[p]
 if not url: raise ValueError(f"{p} requires base_url.")
 # Reuse validated profile transport while retaining enterprise provider metadata.
 profile=AiProviderProfile(provider="openai_compatible",model=model,base_url=url,api_key=api_key,timeout=timeout,headers=headers or {})
 object.__setattr__(profile,"provider",p)
 return profile

def generate_enterprise_text(profile,prompt,*,system_prompt=None,temperature=None,session=None):
 p=profile.provider
 if p=="anthropic":
  url=_join(profile.base_url,"/v1/messages"); h=dict(profile.headers); h.setdefault("x-api-key",profile.api_key or ""); h.setdefault("anthropic-version","2023-06-01")
  proxy=AiProviderProfile(provider="openai_compatible",model=profile.model,base_url=profile.base_url,timeout=profile.timeout,headers=h)
  body={"model":profile.model,"max_tokens":2048,"messages":[{"role":"user","content":prompt}]}
  if system_prompt: body["system"]=system_prompt
  if temperature is not None: body["temperature"]=temperature
  response,data=_send(proxy,"POST",url,json_body=body,session=session)
  text="".join(x.get("text","") for x in data.get("content",[]) if x.get("type")=="text").strip(); usage=data.get("usage")
 elif p=="cohere":
  url=_join(profile.base_url,"/chat"); body={"model":profile.model,"messages":[]}
  if system_prompt: body["messages"].append({"role":"system","content":system_prompt})
  body["messages"].append({"role":"user","content":prompt})
  if temperature is not None: body["temperature"]=temperature
  response,data=_send(profile,"POST",url,json_body=body,session=session)
  text=(data.get("message") or {}).get("content",[{}])[0].get("text","").strip(); usage=data.get("usage")
 else:
  url=_join(profile.base_url,"/chat/completions"); body={"model":profile.model,"messages":[],"stream":False}
  if system_prompt: body["messages"].append({"role":"system","content":system_prompt})
  body["messages"].append({"role":"user","content":prompt})
  if temperature is not None: body["temperature"]=temperature
  response,data=_send(profile,"POST",url,json_body=body,session=session)
  text=data.get("choices",[{}])[0].get("message",{}).get("content","").strip(); usage=data.get("usage")
 if not text: raise AiProviderError(f"{p} response contained no text.")
 return AiResponse(provider=p,model=profile.model,text=text,request_id=response.headers.get("x-request-id"),usage=usage,raw=data)