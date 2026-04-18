"""One-time script: set admin user password"""
import bcrypt
import psycopg2

pw = b"admin123456"
h = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
conn = psycopg2.connect(
    host="postgres", port=5432,
    dbname="ai_kb", user="ai_kb_user",
    password="changeme_strong_password"
)
cur = conn.cursor()
cur.execute("UPDATE users SET password=%s WHERE email=%s", (h, "admin@local"))
conn.commit()
print(f"Updated rows: {cur.rowcount}, hash prefix: {h[:20]}")
conn.close()
