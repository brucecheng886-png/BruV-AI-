"""
Rate Limiting 設定 — 共用 limiter 實例
讓 main.py（middleware 掛載）與各 router 都能 import 同一個 limiter，避免循環 import。
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings

# 全域預設限速（開發模式放寬 10 倍）
_global_limit = "600/minute" if settings.APP_ENV == "development" else "60/minute"

# /auth/login 嚴格限速
LOGIN_RATE_LIMIT = "50/minute" if settings.APP_ENV == "development" else "5/minute"

limiter = Limiter(key_func=get_remote_address, default_limits=[_global_limit])
