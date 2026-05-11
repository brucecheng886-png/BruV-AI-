"""
Migration: 新增 users.is_active 與 users.must_change_password 欄位
執行方式（在 Docker 容器外）：
    docker compose exec backend python scripts/migrate_user_roles.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from database import engine


async def migrate():
    async with engine.begin() as conn:
        # 新增 is_active（若不存在）
        await conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """))
        print("✅ users.is_active OK")

        # 新增 must_change_password（若不存在）
        await conn.execute(text("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE
        """))
        print("✅ users.must_change_password OK")

    print("Migration 完成。")


if __name__ == "__main__":
    asyncio.run(migrate())
