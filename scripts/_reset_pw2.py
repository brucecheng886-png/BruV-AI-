import bcrypt, psycopg2, sys

email = sys.argv[1] if len(sys.argv) > 1 else "123"
password = sys.argv[2] if len(sys.argv) > 2 else "admin123456"

conn = psycopg2.connect(
    host="postgres", port=5432, dbname="ai_kb",
    user="ai_kb_user", password="changeme_strong_password"
)
cur = conn.cursor()
h = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
cur.execute("UPDATE users SET password=%s WHERE email=%s", (h, email))
conn.commit()
print("OK: rowcount=", cur.rowcount, "email=", email)

# verify
cur.execute("SELECT password FROM users WHERE email=%s", (email,))
stored = cur.fetchone()[0]
ok = bcrypt.checkpw(password.encode(), stored.encode())
print("verify:", ok)

cur.close()
conn.close()
