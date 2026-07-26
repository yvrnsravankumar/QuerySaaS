"""Connector registry and provider-neutral QuerySaaS entry point."""
from .oracle_fusion import fusionconnect

SUPPORTED_PROVIDERS = ("oracle_fusion",)
PLANNED_PROVIDERS = ("salesforce", "oracle_atp", "workday", "netsuite", "sap")


def connect(provider, **kwargs):
    """Create a provider connection using a common QuerySaaS entry point."""
    normalized = str(provider).strip().lower().replace("-", "_").replace(" ", "_")

    if normalized in {"oracle_fusion", "fusion", "oracle_cloud_erp"}:
        return fusionconnect(
            url=kwargs.pop("url"),
            user=kwargs.pop("user", kwargs.pop("username", None)),
            password=kwargs.pop("password"),
            **kwargs,
        )

    if normalized in PLANNED_PROVIDERS:
        raise NotImplementedError(
            f"The {normalized!r} connector is planned but is not included in QuerySaaS 0.1.0."
        )

    raise ValueError(
        f"Unsupported provider {provider!r}. Supported providers: {', '.join(SUPPORTED_PROVIDERS)}."
    )
