"""Tiny DB adapter so the same code runs on SQLite (test profile) and PostgreSQL (dev profile)."""
from __future__ import annotations

import os
import re
import sqlite3


class DB:
    def __init__(self, url: str):
        self.url = url
        if url.startswith("sqlite"):
            path = url.split("///", 1)[1]
            if path != ":memory:":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.dialect, self.ph = "sqlite", "?"
        else:
            import psycopg
            from psycopg.rows import dict_row

            self.conn = psycopg.connect(url, row_factory=dict_row)
            self.dialect, self.ph = "postgres", "%s"

    # -- helpers ---------------------------------------------------------
    def execute(self, sql: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(sql.replace("?", self.ph) if self.ph != "?" else sql, params)
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def columns(self, table: str) -> list[str]:
        cur = self.execute(f"SELECT * FROM {table} LIMIT 0")  # noqa: S608 (internal table names only)
        if self.dialect == "sqlite":
            return [d[0] for d in cur.description]
        return [d.name for d in cur.description]

    # -- dialect abstraction for the SQL models --------------------------
    _JSON_GET = re.compile(r"JSON_GET\(\s*(\w+)\s*,\s*'(\w+)'\s*\)")

    def render(self, sql: str) -> str:
        """Translate portable macros. JSON_GET(col,'key') -> engine specific JSON extraction."""
        if self.dialect == "sqlite":
            return self._JSON_GET.sub(r"json_extract(\1, '$.\2')", sql)
        return self._JSON_GET.sub(r"(\1 ->> '\2')", sql)


def connect(url: str) -> DB:
    return DB(url)
