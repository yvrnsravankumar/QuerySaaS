"""Consistent retry support for QuerySaaS network-bound public methods."""
from __future__ import annotations

import functools
import inspect
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

_TRANSIENT_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_RETRY_PARAMETER_NAMES = (
    "max_retries",
    "retry_base_seconds",
    "retry_max_seconds",
)


def validate_retry_options(
    max_retries=3,
    retry_base_seconds=1.0,
    retry_max_seconds=30.0,
):
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries must be an integer.")
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to zero.")
    for name, value in (
        ("retry_base_seconds", retry_base_seconds),
        ("retry_max_seconds", retry_max_seconds),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be numeric.")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero.")
    if retry_max_seconds < retry_base_seconds:
        raise ValueError("retry_max_seconds cannot be less than retry_base_seconds.")
    return int(max_retries), float(retry_base_seconds), float(retry_max_seconds)


@dataclass(frozen=True)
class NetworkRetryPolicy:
    max_retries: int = 3
    retry_base_seconds: float = 1.0
    retry_max_seconds: float = 30.0

    def __post_init__(self):
        validate_retry_options(
            self.max_retries,
            self.retry_base_seconds,
            self.retry_max_seconds,
        )

    @property
    def max_attempts(self):
        return self.max_retries + 1

    def delay(self, retry_number):
        base = min(
            self.retry_base_seconds * (2 ** max(0, retry_number - 1)),
            self.retry_max_seconds,
        )
        return min(base + random.uniform(0.0, min(0.25, base * 0.1)), self.retry_max_seconds)


def _status_code(error):
    for value in (
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    ):
        if isinstance(value, int):
            return value
    match = re.search(r"\b(408|429|500|502|503|504)\b", str(error))
    return int(match.group(1)) if match else None


def is_retryable_network_error(error):
    status = _status_code(error)
    if status in _TRANSIENT_STATUS_CODES:
        return True
    if status in {400, 401, 403, 404}:
        return False
    if requests is not None and isinstance(
        error,
        (requests.Timeout, requests.ConnectionError),
    ):
        return True
    text = str(error).casefold()
    non_retryable = (
        "authentication",
        "authorization",
        "invalid sql",
        "protected",
        "invalid base64",
        "unsupported object type",
        "schema mismatch",
        "cancelled",
    )
    if any(token in text for token in non_retryable):
        return False
    transient = (
        "timed out",
        "timeout",
        "connection reset",
        "connection aborted",
        "temporary failure",
        "temporarily unavailable",
        "name resolution",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "too many requests",
        "missing reportbytes",
        "invalid soap response",
    )
    return any(token in text for token in transient)


def retry_network_call(
    operation,
    call,
    *,
    max_retries=3,
    retry_base_seconds=1.0,
    retry_max_seconds=30.0,
    sleep=time.sleep,
):
    policy = NetworkRetryPolicy(
        max_retries=max_retries,
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
    )
    last_error = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return call()
        except Exception as error:
            last_error = error
            if attempt >= policy.max_attempts or not is_retryable_network_error(error):
                metadata = getattr(error, "metadata", None)
                if isinstance(metadata, dict):
                    metadata.update(
                        {
                            "retry_operation": operation,
                            "attempts": attempt,
                            "max_retries": policy.max_retries,
                            "retry_base_seconds": policy.retry_base_seconds,
                            "retry_max_seconds": policy.retry_max_seconds,
                            "retry_exhausted": attempt >= policy.max_attempts,
                        }
                    )
                raise
            sleep(policy.delay(attempt))
    raise last_error  # pragma: no cover


def _public_signature(function):
    signature = inspect.signature(function)
    parameters = []
    seen = set()
    for parameter in signature.parameters.values():
        if parameter.name in _RETRY_PARAMETER_NAMES:
            default = {
                "max_retries": 3,
                "retry_base_seconds": 1.0,
                "retry_max_seconds": 30.0,
            }[parameter.name]
            parameters.append(parameter.replace(default=default))
            seen.add(parameter.name)
        else:
            parameters.append(parameter)
    variadic_index = next(
        (index for index, item in enumerate(parameters) if item.kind == inspect.Parameter.VAR_KEYWORD),
        len(parameters),
    )
    additions = []
    for name, default in (
        ("max_retries", 3),
        ("retry_base_seconds", 1.0),
        ("retry_max_seconds", 30.0),
    ):
        if name not in seen:
            additions.append(
                inspect.Parameter(
                    name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                )
            )
    parameters[variadic_index:variadic_index] = additions
    return signature.replace(parameters=parameters)


def wrap_retryable_network_function(function, operation=None):
    if getattr(function, "__querysaas_network_retry__", False):
        return function
    signature = inspect.signature(function)
    accepted = set(signature.parameters)
    operation_name = operation or function.__name__

    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        max_retries = kwargs.pop("max_retries", 3)
        retry_base_seconds = kwargs.pop("retry_base_seconds", 1.0)
        retry_max_seconds = kwargs.pop("retry_max_seconds", 30.0)
        validate_retry_options(max_retries, retry_base_seconds, retry_max_seconds)

        def invoke():
            call_kwargs = dict(kwargs)
            # Disable an older nested retry loop when the original function already
            # exposes retry settings. The shared retry policy becomes authoritative.
            if "max_retries" in accepted:
                call_kwargs["max_retries"] = 0
            if "retry_base_seconds" in accepted:
                call_kwargs["retry_base_seconds"] = retry_base_seconds
            if "retry_max_seconds" in accepted:
                call_kwargs["retry_max_seconds"] = retry_max_seconds
            return function(*args, **call_kwargs)

        return retry_network_call(
            operation_name,
            invoke,
            max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
        )

    wrapped.__signature__ = _public_signature(function)
    wrapped.__querysaas_network_retry__ = True
    wrapped.__querysaas_original__ = function
    return wrapped


_METHOD_NAMES = (
    "executequery",
    "copy2file",
    "copy2dd",
    "copy2dd_parallel",
    "syncquery2dd",
    "syncquery2dd_parallel",
    "get_folder_contents",
    "download_bip_object",
    "get_bip_object_xml",
    "bip_object_exists",
    "verify_bip_object",
    "refresh_fbdi_jobs",
    "get_fbdi_jobs",
    "monitor_ess_job",
)


def install_network_retry_methods(connection_class):
    for name in _METHOD_NAMES:
        method = getattr(connection_class, name, None)
        if callable(method):
            setattr(
                connection_class,
                name,
                wrap_retryable_network_function(method, name),
            )
    return connection_class

