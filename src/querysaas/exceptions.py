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
class BIPOperationError(BIPublisherError):
    """Base class for BI Publisher operational failures with safe metadata."""

    def __init__(self, message, *, operation=None, report_absolute_path=None,
                 status_code=None, soap_fault_code=None, soap_fault_reason=None,
                 oracle_error_code=None, oracle_message=None, metadata=None):
        super().__init__(message)
        self.operation = operation
        self.report_absolute_path = report_absolute_path
        self.status_code = status_code
        self.soap_fault_code = soap_fault_code
        self.soap_fault_reason = soap_fault_reason
        self.oracle_error_code = oracle_error_code
        self.oracle_message = oracle_message
        self.metadata = dict(metadata or {})


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


class BIPReplaceError(BIPCatalogError):
    def __init__(self, message, *, object_type=None, deleted=False,
                 restore_attempted=False, restored=False,
                 replacement_error=None, restoration_error=None,
                 restoration_verification=None, **kwargs):
        super().__init__(message, **kwargs)
        self.object_type = object_type
        self.deleted = bool(deleted)
        self.restore_attempted = bool(restore_attempted)
        self.restored = bool(restored)
        self.replacement_error = replacement_error
        self.restoration_error = restoration_error
        self.restoration_verification = restoration_verification


class BIPRestoreError(BIPCatalogError): pass
class BIPScheduleError(BIPOperationError): pass
class BIPReportExecutionError(BIPOperationError): pass
