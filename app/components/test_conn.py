import pymssql

# Try different TDS versions
for version in ['7.0', '7.1', '7.2', '7.3', '7.4']:
    try:
        print(f"Trying TDS version {version}...")
        conn = pymssql.connect(
            server='15.207.206.3',
            port=1433,
            user='sa',
            password='Chanakya!315',
            database='LubricatingCloud',
            login_timeout=5,
            tds_version=version
        )
        print(f"SUCCESS with TDS version {version}!")
        conn.close()
        break
    except Exception as e:
        print(f"Failed: {str(e)[:80]}")