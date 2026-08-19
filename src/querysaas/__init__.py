"""QuerySaaS public API."""
from .oracle_fusion import FusionConnection, fusionconnect, build_auth_header, execute_query, provision_bip_report, CountQueryResult
from .registry import connect, SUPPORTED_PROVIDERS, PLANNED_PROVIDERS
from .pipeline import LocalFileCopyResult, copy_fusion_to_local, copy_fusion_to_local_parallel, install_pipeline_methods
from .fbdi import install_fbdi_methods
from .sql import OracleSqlPlanner, SqlPlan, count_query, limit_query, page_query, validate_query
from .exceptions import *
install_pipeline_methods(FusionConnection)
install_fbdi_methods(FusionConnection)
__version__ = "0.3.7"
__all__=['connect','FusionConnection','fusionconnect','build_auth_header','execute_query','provision_bip_report','SUPPORTED_PROVIDERS','PLANNED_PROVIDERS','OracleSqlPlanner','SqlPlan','CountQueryResult','LocalFileCopyResult','copy_fusion_to_local','copy_fusion_to_local_parallel','count_query','limit_query','page_query','validate_query']
# QUERYSAAS-BIP-BEGIN
from .bip import install_bip_methods
install_bip_methods(FusionConnection)
# QUERYSAAS-BIP-END
# QUERYSAAS-AI-FOUNDATION-BEGIN
from .ai import (
    AiError,
    AiConfigurationError,
    AiSecurityError,
    AiAuthenticationError,
    AiProviderError,
    AiProviderProfile,
    AiResponse,
    DEFAULT_AI_BASE_URLS,
    SUPPORTED_AI_PROVIDERS,
    normalize_ai_base_url,
    redact_ai_context,
    test_ai_connection,
    generate_ai_text,
)
# QUERYSAAS-AI-FOUNDATION-END
# QUERYSAAS-AI-SQL-SAFETY-BEGIN
from .ai_sql import (
    AiSqlError,
    AiSqlExtractionError,
    AiSqlSafetyError,
    AiSqlClassification,
    AiSqlResult,
    extract_sql,
    classify_sql,
    enforce_read_only_sql,
    build_oracle_sql_prompt,
    generate_oracle_sql,
)
# QUERYSAAS-AI-SQL-SAFETY-END
# QUERYSAAS-AI-PROFILES-CONTEXT-BEGIN
from .ai_context import (
    AiProfileError,
    AiCredentialError,
    AiContextError,
    AiCredentialReference,
    AiNamedProfile,
    AiProfileStore,
    OracleSchemaContext,
    AiRequestPreview,
    extract_referenced_tables,
    validate_sql_schema_context,
    preview_ai_sql_request,
)
# QUERYSAAS-AI-PROFILES-CONTEXT-END
# QUERYSAAS-AI-SQL-REPAIR-BEGIN
from .ai_repair import (
    AiSqlRepairError,
    OracleErrorContext,
    AiSqlExplanation,
    AiSqlRepairResult,
    parse_oracle_error,
    compare_sql,
    build_sql_explanation_prompt,
    explain_oracle_sql,
    build_sql_repair_prompt,
    repair_oracle_sql,
)
# QUERYSAAS-AI-SQL-REPAIR-END
# QUERYSAAS-AI-0.3.0-BEGIN
from .ai_repair import AiSqlRepairError, OracleErrorContext, AiSqlExplanation, AiSqlRepairResult, parse_oracle_error, compare_sql, explain_oracle_sql, repair_oracle_sql
from .ai_enterprise import ENTERPRISE_DEFAULTS, enterprise_profile, generate_enterprise_text
from .ai_runtime import AiCancelledError, AiCancellationToken, AiRetryPolicy, AiUsageTelemetry, generate_ai_text_resilient, iter_sse_text
# QUERYSAAS-AI-0.3.0-END
from .local_data import LocalDataFile, LocalSqlResult, LocalDataLibrary, open_data_library


from .network_retry import (
    NetworkRetryPolicy,
    install_network_retry_methods,
    retry_network_call,
    validate_retry_options,
    wrap_retryable_network_function,
)

# Apply retries only after pipeline, BI Publisher, and FBDI methods are registered.
install_network_retry_methods(FusionConnection)

# Preserve standalone public functions while exposing the same retry contract.
execute_query = wrap_retryable_network_function(execute_query, "execute_query")
copy_fusion_to_local = wrap_retryable_network_function(
    copy_fusion_to_local,
    "copy_fusion_to_local",
)
copy_fusion_to_local_parallel = wrap_retryable_network_function(
    copy_fusion_to_local_parallel,
    "copy_fusion_to_local_parallel",
)


from .parallel_parts import ParallelExecutionPlan, PartFileCopyResult, plan_parallel_execution, copy_fusion_query_to_parts
from .fusion_api import FusionModeDecision, LEGACY_METHOD_MAP, install_unified_fusion_methods
install_unified_fusion_methods(FusionConnection)


