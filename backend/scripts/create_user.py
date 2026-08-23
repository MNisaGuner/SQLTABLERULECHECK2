"""
DTG.AppUser tablosuna yeni bir kullanici ekler (CLI, manuel calistirilir).

Kullanim (backend/ dizininden):
    python scripts/create_user.py <kullanici_adi>

Sifre interaktif olarak (ekrana yazilmadan) sorulur.
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # backend/ kokune eris

from dotenv import load_dotenv

from config import PROJECT_ROOT

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from auth import hash_password
from db import DatabaseError, get_raw_connection


def create_user(username: str, password: str) -> None:
    conn = get_raw_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO DataGov.DTG.AppUser (Username, PasswordHash) VALUES (?, ?)",
            username,
            hash_password(password),
        )
    except Exception as exc:
        raise DatabaseError(f"Kullanici eklenemedi: {exc}") from exc
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="DTG.AppUser tablosuna yeni kullanici ekler.")
    parser.add_argument("username", help="Kullanici adi")
    args = parser.parse_args()

    password = getpass.getpass("Şifre: ")
    password_confirm = getpass.getpass("Şifre (tekrar): ")
    if password != password_confirm:
        print("Şifreler eşleşmiyor.")
        raise SystemExit(1)
    if not password:
        print("Şifre boş olamaz.")
        raise SystemExit(1)

    try:
        create_user(args.username, password)
    except DatabaseError as exc:
        print(f"Hata: {exc}")
        raise SystemExit(1)

    print(f"Kullanıcı '{args.username}' eklendi.")


if __name__ == "__main__":
    main()
