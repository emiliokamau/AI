import sqlite3, json
conn = sqlite3.connect('chats.db')
cur = conn.cursor()
cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
data = [dict(zip(cols, r)) for r in rows]
print(json.dumps(data, default=str, indent=2))
conn.close()
