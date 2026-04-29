"""One-time script: set admin user password.

Usage:
  docker exec bruv_ai_backend python scripts/update_admin_password.py <email> [new_password]

If email is omitted, reads ADMIN_EMAIL env var (default: admin@local).
If password is omitted, reads ADMIN_PASSWORD env var (default: admin123456).
"""
import bcrypt
import os
import sys
import psycopg2

email    = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ADMIN_EMAIL", "admin@local")
new_pw   = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("ADMIN_PASSWORD", "admin123456")

h = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
conn = psycopg2.connect(
    host=os.environ.get("POSTGRES_HOST", "postgres"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    dbname=os.environ.get("POSTGRES_DB", "ai_kb"),
    user=os.environ.get("POSTGRES_USER", "ai_kb_user"),
    password=os.environ.get("POSTGRES_PASSWORD", "changeme_strong_password"),
)
cur = conn.cursor()
cur.execute("UPDATE users SET password=%s WHERE email=%s", (h, email))
conn.commit()
print(f"Target email: {email}")
print(f"Updated rows: {cur.rowcount}, hash prefix: {h[:20]}")
if cur.rowcount == 0:
    print("WARNING: no rows updated — check that the email exists in DB.")
conn.close()
