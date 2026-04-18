"""
加密工具（插件 auth_header 加密 / 解密）
"""
import os
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("PLUGIN_ENCRYPT_KEY", "")
    if not key:
        raise RuntimeError("PLUGIN_ENCRYPT_KEY 環境變數未設定")
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """加密敏感字串，回傳 base64 encoded 密文"""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """解密，若 token 無效則拋出 ValueError"""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("無法解密：token 無效或金鑰錯誤") from e
