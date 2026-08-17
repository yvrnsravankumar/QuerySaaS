"""Structured QuerySaaS exceptions."""
from __future__ import annotations
from typing import Any

class QuerySaaSError(RuntimeError): pass
class SqlValidationError(QuerySaaSError): pass
class MultipleStatementsError(SqlValidationError): pass
class UnsupportedStatementError(SqlValidationError): pass
class FusionError(QuerySaaSError): pass
class FusionConnectionError(FusionError): pass
class FusionAuthenticationError(FusionConnectionError): pass
class FusionTimeoutError(FusionConnectionError): pass
class FusionQueryError(FusionError): pass
class BIPublisherError(FusionError): pass

class OracleSqlError(FusionQueryError):
    def __init__(self, message, *, oracle_code=None, oracle_message=None, sql=None, request_id=None, soap_fault=None, retryable=False):
        super().__init__(message); self.oracle_code=oracle_code; self.oracle_message=oracle_message; self.sql=sql; self.request_id=request_id; self.soap_fault=soap_fault; self.retryable=bool(retryable)
    def __str__(self):
        detail=f"{self.oracle_code}: {self.oracle_message}" if self.oracle_code else super().__str__()
        return f"Oracle SQL error: {detail} (retryable={self.retryable})"

class PipelineError(QuerySaaSError): pass
class PipelineCancelledError(PipelineError): pass
class PipelinePageError(PipelineError):
    def __init__(self, message, *, offset, limit, generated_sql, attempt=1, filename=None, original_exception=None):
        super().__init__(message); self.offset=offset; self.limit=limit; self.generated_sql=generated_sql; self.attempt=attempt; self.filename=filename; self.original_exception=original_exception
    def __str__(self): return f"{super().__str__()} [offset={self.offset}, limit={self.limit}, attempt={self.attempt}, filename={self.filename}]"
class PipelineSchemaError(PipelineError):
    def __init__(self, message, *, expected_columns, actual_columns, offset, limit, filename):
        super().__init__(message); self.expected_columns=tuple(expected_columns); self.actual_columns=tuple(actual_columns); self.offset=offset; self.limit=limit; self.filename=filename
    def __str__(self): return f"{super().__str__()} [offset={self.offset}, expected={self.expected_columns}, actual={self.actual_columns}, filename={self.filename}]"

# Canonical BI Publisher exception hierarchy.
_SENSITIVE_METADATA_TOKENS = (
    "token", "authorization", "password", "cookie", "secret", "api_key",
    "base64", "payload", "zipped", "archive", "object_zipped_data",
    "p_b64_content", "notification_to", "recipient",
)


def _sanitize_bip_metadata(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key)
            if any(token in name.casefold() for token in _SENSITIVE_METADATA_TOKENS):
                result[name] = "[REDACTED]"
            else:
                result[name] = _sanitize_bip_metadata(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_bip_metadata(item) for item in value]
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


class BIPOperationError(BIPublisherError):
    """Base class for BI Publisher failures with safe structured metadata."""

    def __init__(
        self,
        message,
        *,
        operation=None,
        report_absolute_path=None,
        status_code=None,
        soap_fault_code=None,
        soap_fault_reason=None,
        oracle_error_code=None,
        oracle_message=None,
        metadata=None,
    ):
        super().__init__(message)
        self.operation = operation
        self.report_absolute_path = report_absolute_path
        self.status_code = status_code
        self.soap_fault_code = soap_fault_code
        self.soap_fault_reason = soap_fault_reason
        self.oracle_error_code = oracle_error_code
        self.oracle_message = oracle_message
        self.metadata = dict(metadata or {})

    def to_dict(self):
        return _sanitize_bip_metadata({
            "type": type(self).__name__,
            "message": str(self),
            "operation": self.operation,
            "report_absolute_path": self.report_absolute_path,
            "status_code": self.status_code,
            "soap_fault_code": self.soap_fault_code,
            "soap_fault_reason": self.soap_fault_reason,
            "oracle_error_code": self.oracle_error_code,
            "oracle_message": self.oracle_message,
            "metadata": dict(self.metadata),
        })


class BIPAuthenticationError(BIPOperationError): pass
class BIPAuthorizationError(BIPOperationError): pass
class BIPConnectionError(BIPOperationError): pass
class BIPTimeoutError(BIPOperationError): pass
class BIPHTTPError(BIPOperationError): pass
class BIPSOAPFaultError(BIPOperationError): pass
class BIPInvalidResponseError(BIPOperationError): pass
class BIPCatalogError(BIPOperationError): pass
class BIPObjectNotFoundError(BIPCatalogError): pass
class BIPObjectAlreadyExistsError(BIPCatalogError): pass
class BIPUnsupportedObjectTypeError(BIPCatalogError): pass
class BIPInvalidBase64Error(BIPCatalogError): pass
class BIPUploadError(BIPCatalogError): pass
class BIPDeleteError(BIPCatalogError): pass
class BIPVerificationError(BIPCatalogError): pass
class BIPRestoreError(BIPCatalogError): pass
class BIPScheduleError(BIPOperationError): pass
class BIPReportExecutionError(BIPOperationError): pass


class BIPReplaceError(BIPCatalogError):
    """Replacement failure with rollback and restoration diagnostics."""

    def __init__(
        self,
        message,
        *,
        object_type=None,
        deleted=False,
        restore_attempted=False,
        restored=False,
        replacement_error=None,
        restoration_error=None,
        restoration_verification=None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.object_type = object_type
        self.deleted = bool(deleted)
        self.restore_attempted = bool(restore_attempted)
        self.restored = bool(restored)
        self.replacement_error = replacement_error
        self.restoration_error = restoration_error
        self.restoration_verification = restoration_verification

    def to_dict(self):
        result = super().to_dict()
        result.update(_sanitize_bip_metadata({
            "object_type": self.object_type,
            "deleted": self.deleted,
            "restore_attempted": self.restore_attempted,
            "restored": self.restored,
            "replacement_error": str(self.replacement_error) if self.replacement_error is not None else None,
            "restoration_error": str(self.restoration_error) if self.restoration_error is not None else None,
            "restoration_verification": self.restoration_verification,
        }))
        return result


class LocalDataError(QuerySaaSError):
    """Base local data library error."""

class LocalDataFolderError(LocalDataError): pass
class LocalDataFileError(LocalDataError): pass
class LocalDataSchemaError(LocalDataError): pass
class LocalDataTableNameError(LocalDataError): pass
class LocalDataReadOnlyError(LocalDataError): pass
class LocalDataSqlError(LocalDataError): pass
class LocalDataExportError(LocalDataError): pass
class LocalDataWriteBackError(LocalDataError): pass
