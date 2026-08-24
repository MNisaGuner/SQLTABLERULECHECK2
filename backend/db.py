"""
MSSQL baglantisi ve sorgu calistirma (salt-okunur / SELECT amacli).

Bu modul sadece SELECT sorgulari calistirir. Baska bir SQL komutu
calistirmak icin fonksiyon bilerek sunulmamistir.
"""

import os
import time

import pyodbc

from config import (
    ALL_TERMS_QUERY,
    COLUMN_QUERY_TEMPLATE,
    COLUMN_STATUS_PENDING,
    HISTORICAL_TERM_MATCH_QUERY,
    MAIN_QUERY,
    REQUIRED_COLUMNS,
    TERM_CACHE_TTL_SECONDS,
    TERM_MATCH_QUERY,
    USER_LOOKUP_QUERY,
)
from term_suggester import build_historical_index, suggest_term


class DatabaseError(Exception):
    pass


def _build_connection_string() -> str:
    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    driver = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    missing = [
        name
        for name, value in [
            ("DB_SERVER", server),
            ("DB_DATABASE", database),
            ("DB_USER", user),
            ("DB_PASSWORD", password),
        ]
        if not value
    ]
    if missing:
        raise DatabaseError(
            "Eksik .env degiskenleri: " + ", ".join(missing) + ". "
            ".env dosyasini kontrol edin (bkz. .env.example)."
        )

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={password};"
        f"Encrypt=yes;TrustServerCertificate=yes;"
    )


def _get_connection() -> pyodbc.Connection:
    conn_str = _build_connection_string()
    try:
        conn = pyodbc.connect(conn_str, timeout=10)
    except pyodbc.Error as exc:
        raise DatabaseError(f"MSSQL baglanti hatasi: {exc}") from exc
    # Salt-okunur niyet: sadece SELECT calistirilacak, otomatik commit gerekmiyor.
    conn.autocommit = True
    return conn


def _run_select(conn: pyodbc.Connection, query: str) -> list[dict]:
    stripped = query.strip()
    if not stripped.upper().startswith("SELECT") and not stripped.upper().startswith("WITH"):
        raise DatabaseError("Sadece SELECT sorgularina izin verilmektedir.")

    try:
        cursor = conn.cursor()
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return rows
    except pyodbc.Error as exc:
        raise DatabaseError(f"SQL sorgu hatasi: {exc}") from exc


_term_cache: dict[str, object] = {"terms": None, "fetched_at": 0.0}


def fetch_all_terms() -> list[dict]:
    """DTG.Term sozlugunun tamamini ceker; TERM_CACHE_TTL_SECONDS boyunca
    bellek ici cache'den doner (her review'da tekrar sorgulamamak icin)."""
    now = time.monotonic()
    if _term_cache["terms"] is not None and (now - _term_cache["fetched_at"]) < TERM_CACHE_TTL_SECONDS:
        return _term_cache["terms"]

    conn = _get_connection()
    try:
        rows = _run_select(conn, ALL_TERMS_QUERY)
    finally:
        conn.close()

    _term_cache["terms"] = rows
    _term_cache["fetched_at"] = now
    return rows


_historical_index_cache: dict[str, object] = {"index": None, "fetched_at": 0.0}


def fetch_historical_term_index() -> dict[str, list[str]]:
    """Kataloğda ayni kolon adinin daha once hangi terim(ler)e baglandigini
    gosteren index'i doner (Katman 0, en guvenilir oneri kaynagi);
    TERM_CACHE_TTL_SECONDS boyunca bellek ici cache'den doner."""
    now = time.monotonic()
    if (
        _historical_index_cache["index"] is not None
        and (now - _historical_index_cache["fetched_at"]) < TERM_CACHE_TTL_SECONDS
    ):
        return _historical_index_cache["index"]

    conn = _get_connection()
    try:
        rows = _run_select(conn, HISTORICAL_TERM_MATCH_QUERY)
    finally:
        conn.close()

    index = build_historical_index(rows)
    _historical_index_cache["index"] = index
    _historical_index_cache["fetched_at"] = now
    return index


def _fetch_columns_for_datasets(
    conn: pyodbc.Connection, dataset_ids: list[int], only_pending: bool = False
) -> dict[int, list[dict]]:
    """Verilen DataSetId'ler icin kolon (DataItem+Term) listelerini ceker, DataSetId'ye gore gruplar.

    only_pending=True ise sadece DataItem.StatusId=COLUMN_STATUS_PENDING (5,
    "Bilgi Mimari Onayinda") olan kolonlar doner -- modele gidecek, kural
    denetiminin TEK kaynagi olan kucuk set. only_pending=False ise tabloya
    ait TUM kolonlar doner -- sadece ekranda tam baglam gostermek icin; bu
    modda ayrica TermId'si bos kolonlara bilgilendirme amacli terim onerisi
    ("TerimOnerisi") eklenir -- OnayBekleyenKolonlar'a EKLENMEZ, boylece
    modele hic gonderilmez.
    """
    if not dataset_ids:
        return {}

    placeholders = ", ".join("?" for _ in dataset_ids)
    status_filter = f"AND di.StatusId = {COLUMN_STATUS_PENDING}" if only_pending else ""
    query = COLUMN_QUERY_TEMPLATE.format(placeholders=placeholders, status_filter=status_filter)

    try:
        cursor = conn.cursor()
        cursor.execute(query, dataset_ids)
        columns = [col[0] for col in cursor.description]
        raw_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
    except pyodbc.Error as exc:
        raise DatabaseError(f"Kolon sorgusu hatasi: {exc}") from exc

    terms = fetch_all_terms() if not only_pending else None
    historical_index = fetch_historical_term_index() if not only_pending else None

    grouped: dict[int, list[dict]] = {}
    for r in raw_rows:
        entry = {
            "KolonAdi": r["ColumnName"],
            "Aciklama": r["ColumnDescription"],
            "VeriTipi": r["PhysicalType"],
            "BosBirakilabilir": r["NullableInfo"],
            "Identity": r["IdentityInfo"],
            "BirincilAnahtar": r["PrimaryKeyInfo"],
            "IsTerimi": r["TermName"],
        }
        if terms is not None and not r["TermName"]:
            entry["TerimOnerisi"] = suggest_term(r["ColumnName"], terms, historical_index)
        grouped.setdefault(r["DataSetId"], []).append(entry)
    return grouped


def fetch_main_rows() -> list[dict]:
    """Ana denetim sorgusunu calistirir ve zorunlu kolonlari dogrular."""
    conn = _get_connection()
    try:
        rows = _run_select(conn, MAIN_QUERY)

        dataset_ids = sorted({r["DataSetId"] for r in rows if r.get("DataSetId") is not None})
        all_columns_by_dataset = _fetch_columns_for_datasets(conn, dataset_ids, only_pending=False)
        pending_columns_by_dataset = _fetch_columns_for_datasets(conn, dataset_ids, only_pending=True)
    finally:
        conn.close()

    for row in rows:
        dataset_id = row.pop("DataSetId", None)
        row["TumKolonlar"] = all_columns_by_dataset.get(dataset_id, [])
        row["OnayBekleyenKolonlar"] = pending_columns_by_dataset.get(dataset_id, [])

    if rows:
        missing_required = [c for c in REQUIRED_COLUMNS if c not in rows[0]]
        if missing_required:
            raise DatabaseError(
                "Ana sorgu zorunlu kolonlari dondurmuyor: "
                + ", ".join(missing_required)
            )
    return rows


def fetch_term_reference_data() -> list[dict]:
    """Terim eslestirme referans verisini taze olarak ceker (cache'lenmez)."""
    conn = _get_connection()
    try:
        rows = _run_select(conn, TERM_MATCH_QUERY)
    finally:
        conn.close()
    return rows


def fetch_user_by_username(username: str) -> dict | None:
    """Login icin AppUser satirini ceker (SELECT, salt okunur). Bulunamazsa None doner."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(USER_LOOKUP_QUERY, username)
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))
    except pyodbc.Error as exc:
        raise DatabaseError(f"Kullanici sorgu hatasi: {exc}") from exc
    finally:
        conn.close()


def get_raw_connection() -> pyodbc.Connection:
    """Dogrudan pyodbc baglantisi dondurur -- SADECE admin/CLI script'leri icin
    (orn. scripts/create_user.py). Web uygulamasinin kendisi (main.py) bu
    fonksiyonu KULLANMAZ; run_check/login akislari yalnizca yukaridaki
    fetch_* (SELECT) fonksiyonlarindan gecer. Bu, bilerek disariya acik
    birakilmis tek yazma (INSERT) yolu."""
    return _get_connection()
