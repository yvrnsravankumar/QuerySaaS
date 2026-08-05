"""QuerySaaS public API."""
from .oracle_fusion import FusionConnection, fusionconnect, build_auth_header, execute_query, provision_bip_report, CountQueryResult
from .registry import connect, SUPPORTED_PROVIDERS, PLANNED_PROVIDERS
from .pipeline import LocalFileCopyResult, copy_fusion_to_local, copy_fusion_to_local_parallel, install_pipeline_methods
from .fbdi import install_fbdi_methods
from .sql import OracleSqlPlanner, SqlPlan, count_query, limit_query, page_query, validate_query
from .exceptions import *
install_pipeline_methods(FusionConnection)
install_fbdi_methods(FusionConnection)
__version__ = "0.1.4"
__all__=['connect','FusionConnection','fusionconnect','build_auth_header','execute_query','provision_bip_report','SUPPORTED_PROVIDERS','PLANNED_PROVIDERS','OracleSqlPlanner','SqlPlan','CountQueryResult','LocalFileCopyResult','copy_fusion_to_local','copy_fusion_to_local_parallel','count_query','limit_query','page_query','validate_query']
# QUERYSAAS-BIP-BEGIN
from .bip import install_bip_methods
install_bip_methods(FusionConnection)
# QUERYSAAS-BIP-END