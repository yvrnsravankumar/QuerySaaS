from getpass import getpass
from pathlib import Path
import csv
from querysaas import connect


def main():
    url = input('Fusion URL: ').strip()
    username = input('Fusion username: ').strip()
    password = getpass('Fusion password: ')
    out = Path(r'C:\QuerySaaS\exports\hz_cust_accounts_1000.csv')
    query = "SELECT CUST_ACCOUNT_ID, ACCOUNT_NUMBER, STATUS, CREATION_DATE, LAST_UPDATE_DATE FROM HZ_CUST_ACCOUNTS"
    with connect('oracle_fusion', url=url, username=username, password=password) as connection:
        result = connection.copy2file_parallel(query=query, filename=out, order_by='CUST_ACCOUNT_ID', max_rows=1000, chunk_size=200, max_workers=4)
    assert out.exists()
    with out.open('r', encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == result.rows
    ids = [int(row['CUST_ACCOUNT_ID']) for row in rows]
    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
    with out.open('r', encoding='utf-8-sig') as handle:
        assert sum(1 for line in handle if line.startswith('CUST_ACCOUNT_ID,')) == 1
    print(result.to_dict())


if __name__ == '__main__':
    main()
