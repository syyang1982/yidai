#!/usr/bin/env python3
import duckdb
import os

db_dir = os.path.expanduser("~/.hermes/yidai/db")

for db_file in os.listdir(db_dir):
    if not db_file.endswith('.duckdb'):
        continue
    db_path = os.path.join(db_dir, db_file)
    print(f"\n=== {db_file} ===")
    try:
        con = duckdb.connect(db_path, read_only=True)
        tables = con.execute('SHOW TABLES').fetchall()
        for t in tables:
            tname = t[0]
            cnt = con.execute(f'SELECT COUNT(*) FROM "{tname}"').fetchone()[0]
            print(f"  {tname}: {cnt} rows")
            # Show columns
            cols = con.execute(f'DESCRIBE "{tname}"').fetchall()
            col_names = [c[0] for c in cols]
            print(f"    cols: {col_names}")
            # Sample recent rows for score-related tables
            if 'score' in tname.lower() or 'signal' in tname.lower():
                try:
                    rows = con.execute(f'SELECT * FROM "{tname}" ORDER BY 1 DESC LIMIT 3').fetchall()
                    for r in rows:
                        print(f"    >> {r}")
                except:
                    pass
        con.close()
    except Exception as e:
        print(f"  ERROR: {e}")