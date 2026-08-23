"""FastAPI uygulamasi: MSSQL sorgu sonuclarini LLM ile kural denetiminden gecirir."""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from config import PROJECT_ROOT

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from auth import authenticate
from config import MAX_CONCURRENT_MODEL_CALLS, REQUIRED_COLUMNS, TERM_MATCH_COLUMN_KEY
from db import DatabaseError, fetch_main_rows, fetch_term_reference_data
from providers.base import ModelProvider, ModelProviderError
from providers.claude_provider import ClaudeProvider
from providers.local_provider import LocalProvider
from rules_loader import RulesFileNotFoundError, load_rules
from script_parser import parse_column_changes

SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY")
if not SESSION_SECRET_KEY:
    raise RuntimeError(
        "SESSION_SECRET_KEY .env dosyasinda tanimli olmali "
        "(oturum cookie'lerini imzalamak icin, bkz. .env.example)."
    )

app = FastAPI(title="SQL Table Rule Check")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    max_age=60 * 60 * 8,  # 8 saat
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def require_auth(request: Request) -> None:
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Oturum bulunamadı, giriş yapın.")


class RunCheckRequest(BaseModel):
    provider: str = "claude"


class LoginRequest(BaseModel):
    username: str
    password: str


def get_provider(name: str) -> ModelProvider:
    if name == "claude":
        return ClaudeProvider()
    if name == "local":
        return LocalProvider()
    raise HTTPException(status_code=400, detail=f"Bilinmeyen model saglayici: {name}")


def _split_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Bir satiri zorunlu kolonlar ve ek veri (denetlenecek kolonlar) olarak ayirir."""
    required = {k: row.get(k) for k in REQUIRED_COLUMNS}
    extra = {k: v for k, v in row.items() if k not in REQUIRED_COLUMNS}
    return required, extra


async def _process_row(
    row: dict[str, Any],
    rules_text: str,
    reference_data: list[dict[str, Any]],
    provider: ModelProvider,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    required, extra = _split_row(row)
    label = (
        f"{required['id']}-{required['LocationName']}-"
        f"{required['DatabaseName']}-{required['SchemaName']}-{required['TableName']}"
    )

    # TumKolonlar sadece ekranda tam baglam icin kullanilir, modele GONDERILMEZ.
    tum_kolonlar = extra.pop("TumKolonlar", [])
    # OnayBekleyenKolonlar (DataItem.StatusId=5) extra icinde kalir; kural
    # denetiminin TEK kolon kaynagidir, provider.check_row'a bununla gidilir.

    # Script'in hangi kolona ADD/ALTER/DROP yaptigini kendi metninden cikar
    # (StatusId bunu ayirt etmiyor, ozellikle DROP icin hic kod yok).
    degisen_kolonlar = parse_column_changes(
        extra.get("ScriptText"),
        required["DatabaseName"],
        required["SchemaName"],
        required["TableName"],
    )

    auto_approved = False
    if not degisen_kolonlar:
        # Script tek basina ana tabloya dokunmuyor (sadece audit/arsiv
        # companion script'i) -- kullanici karar verirken bunlara bakmiyor,
        # sadece ana tablo degisikligine odaklaniyor. Model cagrisi atlanir.
        auto_approved = True
        karar = "ONAY"
        gerekce = (
            "Bu script ana tabloyu "
            f"({required['DatabaseName']}.{required['SchemaName']}.{required['TableName']}) "
            "hedeflemiyor (audit/arşiv companion script'i); ana tablo dışı "
            "script'ler ayrıca kural denetiminden geçirilmiyor, otomatik "
            "onaylandı."
        )
        hata = None
        term_status = None
    else:
        async with semaphore:
            try:
                karar_result = await provider.check_row(extra, rules_text)
                karar = karar_result["karar"]
                gerekce = karar_result["gerekce"]
                hata = None
            except ModelProviderError as exc:
                karar = "HATA"
                gerekce = ""
                hata = str(exc)

            term_status = None
            column_name = extra.get(TERM_MATCH_COLUMN_KEY)
            if column_name:
                try:
                    term_status = await provider.check_term_match(str(column_name), reference_data)
                except ModelProviderError as exc:
                    term_status = {"durum": "hata", "terim": None, "oneriler": [], "hata": str(exc)}

    return {
        **required,
        "label": label,
        "karar": karar,
        "gerekce": gerekce,
        "hata": hata,
        "term_status": term_status,
        "script_text": extra.get("ScriptText"),
        "table_description": extra.get("TableDescription"),
        "columns": tum_kolonlar,
        "changed_columns": degisen_kolonlar,
        "auto_approved": auto_approved,
    }


@app.post("/api/login")
async def login(body: LoginRequest, request: Request):
    try:
        user = authenticate(body.username, body.password)
    except DatabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if user is None:
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı.")

    request.session["user_id"] = user["UserId"]
    request.session["username"] = user["Username"]
    return {"username": user["Username"]}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
async def me(request: Request):
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Oturum yok.")
    return {"username": request.session.get("username")}


@app.post("/api/run-check", dependencies=[Depends(require_auth)])
async def run_check(body: RunCheckRequest):
    try:
        rules_text = load_rules()
    except RulesFileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        rows = fetch_main_rows()
        reference_data = fetch_term_reference_data()
    except DatabaseError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        provider = get_provider(body.provider)
    except ModelProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not rows:
        return {"summary": {"onay": 0, "iade": 0, "hata": 0}, "results": []}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_MODEL_CALLS)
    tasks = [_process_row(row, rules_text, reference_data, provider, semaphore) for row in rows]
    all_results = await asyncio.gather(*tasks)

    # Ana tabloya dokunmayan (sadece audit/arsiv companion) script'ler
    # sonuc listesine hic girmez -- kullanici bunlari ayri bir onay/iade
    # kalemi olarak gormek istemiyor.
    results = [r for r in all_results if not r["auto_approved"]]

    summary = {
        "onay": sum(1 for r in results if r["karar"] == "ONAY"),
        "iade": sum(1 for r in results if r["karar"] == "IADE"),
        "hata": sum(1 for r in results if r["karar"] == "HATA"),
    }
    return {"summary": summary, "results": results}


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/login")
async def serve_login():
    return FileResponse(os.path.join(FRONTEND_DIR, "login.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
