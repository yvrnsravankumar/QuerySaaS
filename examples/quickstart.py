from getpass import getpass
from querysaas import connect

FUSION_URL = "https://your-host.oraclecloud.com"
FUSION_USERNAME = "your.username"
FUSION_PASSWORD = getpass("Oracle Fusion password: ")

with connect(
    "oracle_fusion",
    url=FUSION_URL,
    username=FUSION_USERNAME,
    password=FUSION_PASSWORD,
) as con:
    print(con.executequery("SELECT * FROM dual", all_varchar=True))
