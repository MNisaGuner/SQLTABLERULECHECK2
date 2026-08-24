"""
DataItem.TermId bos olan (hic terimle eslesmemis) kolonlar icin bilgilendirme
amacli terim onerisi uretir.

Bu tamamen BILGI AMACLIDIR -- ONAY/IADE karar mekanizmasina hic karismaz,
modele (LLM) hic gonderilmez. Token maliyeti olmasin diye saf Python +
RapidFuzz ile hesaplanir.

Katman 0 (en guvenilir): ayni kolon adi kataloğun BASKA bir yerinde daha
once bir terime baglanmissa, string benzerligine bakmadan direkt o terim
onerilir. Bu, kisaltma <-> aciklayici isim arasinda hicbir metinsel benzerlik
olmayan durumlar icin gerekli (orn. "TCKN" hicbir zaman "Kimlik Numarasi"
ile fuzzy eslesmez, ama ayni "TCKN" kolonu baska bir tabloda zaten bu terime
baglanmissa bu en guclu sinyaldir).

Katman 1-2 (Term sozlugune karsi birebir + fuzzy), kurumun
TermMatchFromExcel/matcher.py projesindeki yaklasimla tutarlidir: fuzzy skor
icin max(fuzz.token_sort_ratio, fuzz.partial_ratio).
"""

import re
from typing import Any

from rapidfuzz import fuzz

from config import MAX_TERM_SUGGESTIONS, TERM_SUGGESTION_THRESHOLD

_NORMALIZE_RE = re.compile(r"[\s_]+")


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("", name).lower()


def build_historical_index(historical_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    """[{"ColumnName":..., "TermName":...}, ...] listesinden, normalize edilmis
    kolon adi -> o isimle kataloğda eslesmis TUM terim adlari (tekil, siralanmis)
    index'ini olusturur."""
    index: dict[str, set[str]] = {}
    for row in historical_rows:
        column_name = row.get("ColumnName")
        term_name = row.get("TermName")
        if not column_name or not term_name:
            continue
        key = _normalize(column_name)
        index.setdefault(key, set()).add(term_name)
    return {key: sorted(names) for key, names in index.items()}


def suggest_term(
    column_name: str | None,
    terms: list[dict[str, Any]],
    historical_index: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """column_name icin oneri dondurur.

    Donen format: [{"term_name": str, "match_type": "HISTORICAL"|"EXACT"|"FUZZY", "score": float|None}]
    - Katman 0: ayni kolon adi kataloğda baska yerde eslesmisse, o terim(ler)
      TEK kaynak olarak doner (Term sozlugune bakilmaz).
    - Katman 1: Term sozlugunde birebir (normalize edilmis) ad eslesmesi
      varsa TEK sonuc doner.
    - Katman 2: yoksa skoru TERM_SUGGESTION_THRESHOLD ve uzerinde olan en iyi
      MAX_TERM_SUGGESTIONS terim, skora gore azalan sirada doner.
    - Hic eslesme yoksa bos liste doner.
    """
    if not column_name:
        return []

    normalized_column = _normalize(column_name)

    if historical_index:
        historical_matches = historical_index.get(normalized_column)
        if historical_matches:
            return [
                {"term_name": name, "match_type": "HISTORICAL", "score": None}
                for name in historical_matches
            ]

    if not terms:
        return []

    for term in terms:
        for name_field in ("Name", "EnglishName"):
            term_value = term.get(name_field)
            if term_value and _normalize(term_value) == normalized_column:
                return [{"term_name": term_value, "match_type": "EXACT", "score": None}]

    scored: list[dict[str, Any]] = []
    seen_term_names: set[str] = set()
    for term in terms:
        best_score = 0.0
        best_name: str | None = None
        for name_field in ("Name", "EnglishName"):
            term_value = term.get(name_field)
            if not term_value:
                continue
            score = max(
                fuzz.token_sort_ratio(column_name, term_value),
                fuzz.partial_ratio(column_name, term_value),
            )
            if score > best_score:
                best_score = score
                best_name = term_value

        if best_name and best_score >= TERM_SUGGESTION_THRESHOLD and best_name not in seen_term_names:
            seen_term_names.add(best_name)
            scored.append({"term_name": best_name, "match_type": "FUZZY", "score": round(best_score, 1)})

    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:MAX_TERM_SUGGESTIONS]
