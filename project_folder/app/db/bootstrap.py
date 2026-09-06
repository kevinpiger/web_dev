"""Startup schema bootstrap: apply db/schema/*.sql, diff against information_schema.

Rules (spec §5):
- file has column, DB doesn't -> ALTER TABLE ADD COLUMN
- DB has column, file doesn't -> WARN only, never drop
- both have it but type differs -> WARN only, never alter
Must be idempotent: a second run should produce zero changes, zero warnings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.session import engine

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).parent / "schema"

_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(?P<schema>\w+)\.(?P<table>\w+)\s*\((?P<body>.*?)\n\);",
    re.IGNORECASE | re.DOTALL,
)
_COLUMN_LINE_RE = re.compile(r"^\s*(?P<name>[a-z_][a-z0-9_]*)\s+(?P<type>[A-Z][A-Za-z0-9_() ]*)")
_CONSTRAINT_KEYWORDS = {"constraint", "primary", "unique", "check", "foreign"}


@dataclass
class BootstrapSummary:
    sql_files_run: int = 0
    tables_created: int = 0
    columns_added: int = 0
    warnings: list[str] = field(default_factory=list)

    def log(self) -> None:
        logger.info(
            "db bootstrap summary: files=%d tables_created=%d columns_added=%d warnings=%d",
            self.sql_files_run,
            self.tables_created,
            self.columns_added,
            len(self.warnings),
        )
        for warning in self.warnings:
            logger.warning(warning)


def _sql_files() -> list[Path]:
    return sorted(SCHEMA_DIR.rglob("*.sql"))


def _strip_sql_comments(sql: str) -> str:
    """Drop `--` and `/* */` comments.

    Without this, a column documented by a comment line above it is invisible to the
    column diff below (the comment becomes the head of the comma-separated chunk), so
    exactly the annotated columns — the schema augmentations — would never be added to
    an already-existing table. No schema file puts `--` inside a string literal, so a
    plain strip is safe here.
    """
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", sql)


def _parse_declared_columns(sql: str) -> dict[str, str]:
    """Extract column_name -> declared_type from a single CREATE TABLE IF NOT EXISTS body."""
    match = _CREATE_TABLE_RE.search(_strip_sql_comments(sql))
    if not match:
        return {}
    columns: dict[str, str] = {}
    depth = 0
    current = []
    for char in match.group("body"):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            _maybe_add_column(current, columns)
            current = []
        else:
            current.append(char)
    _maybe_add_column(current, columns)
    return columns


def _maybe_add_column(chars: list[str], columns: dict[str, str]) -> None:
    line = "".join(chars).strip()
    if not line:
        return
    first_word = line.split(None, 1)[0].lower()
    if first_word in _CONSTRAINT_KEYWORDS:
        return
    col_match = _COLUMN_LINE_RE.match(line)
    if not col_match:
        return
    columns[col_match.group("name").lower()] = col_match.group("type").strip()


async def _existing_columns(
    conn: AsyncConnection, schema: str, table: str
) -> dict[str, str]:
    result = await conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    )
    return {row.column_name: row.data_type for row in result}


async def _table_exists(conn: AsyncConnection, schema: str, table: str) -> bool:
    result = await conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    )
    return result.first() is not None


async def _reconcile_columns(
    conn: AsyncConnection, schema: str, table: str, declared: dict[str, str], summary: BootstrapSummary
) -> None:
    existing = await _existing_columns(conn, schema, table)

    for column_name, declared_type in declared.items():
        if column_name not in existing:
            ddl_type = declared_type.split()[0]
            await conn.execute(
                text(f'ALTER TABLE {schema}.{table} ADD COLUMN "{column_name}" {ddl_type}')
            )
            summary.columns_added += 1
            logger.info("added column %s.%s.%s (%s)", schema, table, column_name, ddl_type)

    for column_name in existing:
        if column_name not in declared:
            summary.warnings.append(
                f"{schema}.{table}.{column_name} exists in DB but not in schema file (not dropped)"
            )


async def run() -> BootstrapSummary:
    summary = BootstrapSummary()

    async with engine.begin() as conn:
        for sql_path in _sql_files():
            sql_text = sql_path.read_text(encoding="utf-8")
            match = _CREATE_TABLE_RE.search(sql_text)

            table_existed_before = (
                await _table_exists(conn, match.group("schema"), match.group("table"))
                if match
                else False
            )

            # Comments are stripped before splitting so a `;` inside one can't cut a
            # statement in half.
            executable = _strip_sql_comments(sql_text)
            for statement in filter(None, (s.strip() for s in executable.split(";"))):
                await conn.execute(text(statement))
            summary.sql_files_run += 1

            if not match:
                continue

            schema_name = match.group("schema")
            table_name = match.group("table")
            if not table_existed_before:
                summary.tables_created += 1

            declared_columns = _parse_declared_columns(sql_text)
            await _reconcile_columns(conn, schema_name, table_name, declared_columns, summary)

    summary.log()
    return summary
