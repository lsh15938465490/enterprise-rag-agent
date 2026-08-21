"""只允许单条 SELECT，禁止改数据、多语句和系统表。给 Agent 只读查库用。"""

import re

import sqlparse

FORBIDDEN = re.compile(r"\b(pg_|information_schema|pg_catalog)\b", re.I)


def assert_readonly_select(sql: str) -> str:
    cleaned = sql.strip()
    if not cleaned:
        raise ValueError("SQL 为空")
    if ";" in cleaned.rstrip(";"):
        raise ValueError("禁止多语句")
    statements = [s for s in sqlparse.parse(cleaned) if str(s).strip()]
    if len(statements) != 1:
        raise ValueError("禁止多语句")
    stmt = statements[0]
    if stmt.get_type() != "SELECT":
        raise ValueError("仅允许 SELECT")
    if FORBIDDEN.search(cleaned):
        raise ValueError("禁止访问系统表")
    return cleaned.rstrip(";")
