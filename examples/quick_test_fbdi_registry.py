"""Read-only live smoke test for QuerySaaS FBDI job registry refresh."""
from getpass import getpass

from querysaas import connect


def main():
    fusion_url = input("Fusion URL: ").strip()
    fusion_username = input("Fusion username: ").strip()
    fusion_password = getpass("Fusion password: ")

    if not fusion_url.startswith("https://"):
        raise ValueError("Fusion URL must use HTTPS.")

    with connect(
        "oracle_fusion",
        url=fusion_url,
        username=fusion_username,
        password=fusion_password,
        provision=False,
        verify_ssl=True,
    ) as connection:
        print("Refreshing FBDI jobs from Oracle Fusion...")
        jobs = connection.refresh_fbdi_jobs(force=True)

        print("Source:", jobs.attrs.get("source"))
        print("Refreshed at:", jobs.attrs.get("refreshed_at"))
        print("Refresh error:", jobs.attrs.get("refresh_error"))
        print("Rows:", len(jobs))
        print("Columns:", list(jobs.columns))

        required = {
            "ERP_FAMILY",
            "APPLICATION_ID",
            "BUSINESS_OBJECT",
            "ERP_INTERFACE_OPTIONS_ID",
            "UCM_ACCOUNT",
            "DOCUMENT_ACCOUNT",
            "LOAD_JOB_NAME",
            "IMPORT_JOB_NAME",
            "CONTROL_FILE_NAME",
            "INTERFACE_TABLE_NAMES",
        }
        missing = sorted(required - set(jobs.columns))
        if missing:
            raise AssertionError(f"Missing required columns: {missing}")
        if jobs.empty:
            raise AssertionError("The FBDI registry returned no rows.")

        print("\nFirst 20 FBDI job rows:")
        print(jobs.head(20).to_string(index=False))

        print("\nProject Budget test:")
        project_budget = connection.get_fbdi_jobs(
            business_object="Project Budget",
        )
        print(project_budget.to_string(index=False))

        print("\nInterface table test:")
        project_table = connection.get_fbdi_jobs(
            interface_table="PJO_PLAN_VERSIONS_XFACE",
        )
        print(project_table.to_string(index=False))

        print("\nForce-refresh cache test:")
        refreshed_again = connection.refresh_fbdi_jobs(force=True)
        print("Rows after second refresh:", len(refreshed_again))
        print("New refresh timestamp:", refreshed_again.attrs.get("refreshed_at"))

        if jobs.attrs.get("source") != "oracle_fusion":
            raise AssertionError(
                "Live registry refresh did not succeed. "
                f"Fallback error: {jobs.attrs.get('refresh_error')}"
            )

        print("\nFBDI registry live smoke test passed.")


if __name__ == "__main__":
    main()
