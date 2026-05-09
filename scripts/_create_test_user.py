import bcrypt, psycopg2

h = bcrypt.hashpw(b'admin123456', bcrypt.gensalt(12)).decode()
conn = psycopg2.connect(host='postgres', port=5432, dbname='ai_kb', user='ai_kb_user', password='BU4hOAHWOWzDptbM')
cur = conn.cursor()
cur.execute(
    "INSERT INTO users (id, email, password, role, created_at) "
    "VALUES (gen_random_uuid(), '123', %s, 'admin', NOW()) "
    "ON CONFLICT (email) DO UPDATE SET password=EXCLUDED.password",
    (h,)
)
conn.commit()
print('done, rowcount=', cur.rowcount)
cur.execute("SELECT email, role FROM users WHERE email='123'")
print('user:', cur.fetchone())
cur.close()
conn.close()
