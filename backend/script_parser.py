"""
ScriptText'i (DataScript.ScriptText) regex ile parse edip, incelenen script'in
hedef tabloya ait hangi kolonlara ADD/ALTER/DROP islemi yaptigini cikarir.

DataItem.StatusId (onayda/canlida/vb.) sadece "hangi kolonlar su an onay
bekliyor" sorusunu cevaplar; script'in o kolonda ADD mi ALTER mi DROP mu
yaptigini ayirt etmez (ozellikle DROP icin hic kod yok). Bu yuzden degisiklik
tipi, script'in kendisinden cikarilir.

Ayni script blogu icinde ayni tabloya ait olmayan ifadeler (audit/archive
tablo guncellemeleri, trigger tanimlari) DatabaseName/SchemaName/TableName
ile TAM eslesme sarti sayesinde otomatik olarak yok sayilir.
"""

import re

_IDENT = r"\[?([A-Za-z0-9_]+)\]?"
_TARGET = rf"{_IDENT}\s*\.\s*{_IDENT}\s*\.\s*{_IDENT}"

_SKIP_PREFIXES = ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX")
_COL_TOKEN_RE = re.compile(r"^\[?([A-Za-z0-9_]+)\]?")

_CREATE_TABLE_RE = re.compile(
    rf"CREATE\s+TABLE\s+{_TARGET}\s*\((?P<body>.*?)\n[ \t]*\)",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_ADD_RE = re.compile(
    rf"ALTER\s+TABLE\s+{_TARGET}\s+ADD\s+(?!CONSTRAINT\b)(?P<body>.*?);",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_COLUMN_RE = re.compile(
    rf"ALTER\s+TABLE\s+{_TARGET}\s+ALTER\s+COLUMN\s+\[?(?P<column>[A-Za-z0-9_]+)\]?",
    re.IGNORECASE,
)
_DROP_COLUMN_RE = re.compile(
    rf"ALTER\s+TABLE\s+{_TARGET}\s+DROP\s+COLUMN\s+(?P<body>.*?);",
    re.IGNORECASE | re.DOTALL,
)


def _target_matches(
    groups: tuple[str, str, str],
    database_name: str | None,
    schema_name: str | None,
    table_name: str | None,
) -> bool:
    db, schema, table = groups
    return (
        db.lower() == (database_name or "").strip().lower()
        and schema.lower() == (schema_name or "").strip().lower()
        and table.lower() == (table_name or "").strip().lower()
    )


def _split_top_level(body: str) -> list[str]:
    """Body'yi ust seviye virgullerden boler; parantez ici virguller (orn. NUMERIC(10,2)) yok sayilir."""
    parts = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _extract_column_name(segment: str) -> str | None:
    segment = segment.strip()
    if not segment:
        return None
    if any(segment.upper().startswith(prefix) for prefix in _SKIP_PREFIXES):
        return None
    match = _COL_TOKEN_RE.match(segment)
    return match.group(1) if match else None


def parse_column_changes(
    script_text: str | None,
    database_name: str | None,
    schema_name: str | None,
    table_name: str | None,
) -> list[dict]:
    """ScriptText'i parse edip hedef tabloya ait kolon degisikliklerini dondurur.

    Donen liste: [{"column": "CustomerClassId", "change_type": "ALTER"}, ...]
    change_type: "ADD" | "ALTER" | "DROP"
    """
    if not script_text:
        return []

    changes: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _add(column: str | None, change_type: str) -> None:
        if not column:
            return
        key = (column.lower(), change_type)
        if key in seen:
            return
        seen.add(key)
        changes.append({"column": column, "change_type": change_type})

    for m in _CREATE_TABLE_RE.finditer(script_text):
        if not _target_matches(m.groups()[:3], database_name, schema_name, table_name):
            continue
        for segment in _split_top_level(m.group("body")):
            _add(_extract_column_name(segment), "ADD")

    for m in _ALTER_ADD_RE.finditer(script_text):
        if not _target_matches(m.groups()[:3], database_name, schema_name, table_name):
            continue
        for segment in _split_top_level(m.group("body")):
            _add(_extract_column_name(segment), "ADD")

    for m in _ALTER_COLUMN_RE.finditer(script_text):
        if not _target_matches(m.groups()[:3], database_name, schema_name, table_name):
            continue
        _add(m.group("column"), "ALTER")

    for m in _DROP_COLUMN_RE.finditer(script_text):
        if not _target_matches(m.groups()[:3], database_name, schema_name, table_name):
            continue
        for segment in _split_top_level(m.group("body")):
            _add(_extract_column_name(segment), "DROP")

    return changes
