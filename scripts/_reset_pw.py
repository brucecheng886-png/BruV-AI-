import bcrypt, psycopg2, os, sys

email = sys.argv[1] if len(sys.argv) > 1 else "123"
password = sys.argv[2] if len(sys.argv) > 2 else "admin123456"

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
h = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
cur.execute("UPDATE users SET password=%s WHERE email=%s", (h, email))
conn.commit()
print(f"OK: {cur.rowcount} row(s) updated. email={email}")
cur.close()
conn.close()
