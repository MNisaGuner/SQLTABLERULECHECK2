"""
Kullanici adi/sifre kimlik dogrulamasi.

Sifreler asla duz metin saklanmaz/karsilastirilmaz -- bcrypt ile hash'lenir.
"""

import bcrypt

from db import fetch_user_by_username


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Bozuk/gecersiz hash formati -- dogrulama basarisiz sayilir.
        return False


def authenticate(username: str, password: str) -> dict | None:
    """Kullanici adi + sifreyi dogrular. Basarisizsa None doner (sebep ayirt edilmez)."""
    user = fetch_user_by_username(username)
    if user is None:
        return None
    if not verify_password(password, user["PasswordHash"]):
        return None
    return user
