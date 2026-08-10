"""FastAPI uygulamasi: MSSQL sorgu sonuclarini LLM ile kural denetiminden gecirir."""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from config import PROJECT_ROOT

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import MAX_CONCURRENT_MODEL_CALLS, REQUIRED_COLUMNS, TERM_MATCH_COLUMN_KEY
from db import DatabaseError, fetch_main_rows, fetch_term_reference_data
from providers.base import ModelProvider, ModelProviderError
from providers.claude_provider import ClaudeProvider
from providers.local_provider import LocalProvider
from rules_loader import RulesFileNotFoundError, load_rules

app = FastAPI(title="SQL Table Rule Check")

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


class RunCheckRequest(BaseModel):
    provider: str = "claude"


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
        "columns": extra.get("Kolonlar", []),
    }


@app.post("/api/run-check")
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
    results = await asyncio.gather(*tasks)

    summary = {
        "onay": sum(1 for r in results if r["karar"] == "ONAY"),
        "iade": sum(1 for r in results if r["karar"] == "IADE"),
        "hata": sum(1 for r in results if r["karar"] == "HATA"),
    }
    return {"summary": summary, "results": results}


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
