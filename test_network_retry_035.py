import inspect
import pytest

from querysaas import (
    FusionConnection,
    copy_fusion_to_local,
    copy_fusion_to_local_parallel,
    execute_query,
)
from querysaas.network_retry import (
    NetworkRetryPolicy,
    retry_network_call,
    validate_retry_options,
)

EXPECTED_METHODS = (
    "executequery",
    "copy2file",
    "copy2file_parallel",
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


def test_retry_policy_defaults_and_validation():
    policy = NetworkRetryPolicy()
    assert policy.max_retries == 3
    assert policy.max_attempts == 4
    assert policy.retry_base_seconds == 1.0
    assert policy.retry_max_seconds == 30.0
    assert validate_retry_options(0, 0.1, 1.0) == (0, 0.1, 1.0)
    with pytest.raises(TypeError):
        validate_retry_options(True, 1.0, 30.0)
    with pytest.raises(ValueError):
        validate_retry_options(-1, 1.0, 30.0)
    with pytest.raises(ValueError):
        validate_retry_options(3, 10.0, 1.0)


def test_retry_call_three_retries_then_success():
    attempts = []
    sleeps = []

    def call():
        attempts.append(1)
        if len(attempts) < 4:
            raise RuntimeError("HTTP 503 service unavailable")
        return "ok"

    result = retry_network_call(
        "test",
        call,
        max_retries=3,
        retry_base_seconds=0.01,
        retry_max_seconds=0.1,
        sleep=sleeps.append,
    )
    assert result == "ok"
    assert len(attempts) == 4
    assert len(sleeps) == 3


def test_non_retryable_authentication_failure_is_not_retried():
    attempts = []

    def call():
        attempts.append(1)
        raise RuntimeError("HTTP 401 authentication failed")

    with pytest.raises(RuntimeError):
        retry_network_call("test", call, max_retries=3, sleep=lambda _: None)
    assert len(attempts) == 1


@pytest.mark.parametrize("method_name", EXPECTED_METHODS)
def test_fusion_method_exposes_retry_parameters(method_name):
    signature = inspect.signature(getattr(FusionConnection, method_name))
    assert signature.parameters["max_retries"].default == 3
    assert signature.parameters["retry_base_seconds"].default == 1.0
    assert signature.parameters["retry_max_seconds"].default == 30.0


@pytest.mark.parametrize(
    "function",
    [execute_query, copy_fusion_to_local, copy_fusion_to_local_parallel],
)
def test_standalone_function_exposes_retry_parameters(function):
    signature = inspect.signature(function)
    assert signature.parameters["max_retries"].default == 3
    assert signature.parameters["retry_base_seconds"].default == 1.0
    assert signature.parameters["retry_max_seconds"].default == 30.0


def test_local_data_methods_do_not_gain_network_retry_parameters():
    from querysaas import LocalDataLibrary

    signature = inspect.signature(LocalDataLibrary.query)
    assert "max_retries" not in signature.parameters
