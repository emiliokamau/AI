import json
from db import db_connect

conn = db_connect()
cur = conn.cursor()
cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
rows = cur.fetchall()
print(json.dumps(rows, default=str, indent=2))
conn.close()
