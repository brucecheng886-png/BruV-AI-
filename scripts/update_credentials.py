"""一次性腳本：更新 admin 帳號的 email 和密碼"""
import asyncio, sys, bcrypt
sys.path.insert(0, '/app')
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config import settings

NEW_EMAIL = "123"
NEW_PASSWORD = "123"
OLD_EMAIL = "admin@local"

async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    pw_hash = bcrypt.hashpw(NEW_PASSWORD.encode(), bcrypt.gensalt()).decode()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET email = :new_email, password = :new_pw WHERE email = :old_email"),
            {"new_email": NEW_EMAIL, "new_pw": pw_hash, "old_email": OLD_EMAIL}
        )
        r = await conn.execute(text("SELECT email FROM users WHERE email = :e"), {"e": NEW_EMAIL})
        row = r.fetchone()
        print(f"OK: email={row[0]}" if row else "FAIL: user not found")
    await engine.dispose()

asyncio.run(main())
