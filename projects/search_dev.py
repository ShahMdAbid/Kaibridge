import sqlite3

conn = sqlite3.connect(r'C:\Users\HP\OneDrive\Documents\EasyEDA-Pro\example-projects\Example_Quick Start.eprj')
c = conn.cursor()
dev_uuid = '5accf6ca06ad493fbeefcb192c785a14'
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
for t in tables:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
    conds = ' OR '.join([f'"{col}" LIKE "%{dev_uuid}%"' for col in cols])
    if conds:
        try:
            cnt = c.execute(f"SELECT count(*) FROM {t} WHERE {conds}").fetchone()[0]
            if cnt > 0:
                print(f"Found in table '{t}': {cnt} rows")
        except Exception as e:
            pass
