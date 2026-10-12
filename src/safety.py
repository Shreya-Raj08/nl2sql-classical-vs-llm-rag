"""Safety guard + read-only SQL execution (ethics: the system can never modify or delete data)."""
import re
import sqlite3
import time

import sqlglot
from sqlglot import exp

import config
from src.spider_data import db_path

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b", re.I)


class UnsafeQuery(Exception):
    pass


def check_safe(sql):
    """Allow exactly one read-only SELECT statement (UNION/INTERSECT/EXCEPT of SELECTs is fine)."""
    if not sql or not sql.strip():
        raise UnsafeQuery("Empty query")
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise UnsafeQuery("Multiple statements are not allowed")
    if FORBIDDEN.search(re.sub(r"'[^']*'|\"[^\"]*\"", "''", stripped)):   # ignore keywords inside string literals
        raise UnsafeQuery("Only read-only SELECT queries are allowed")
    try:
        tree = sqlglot.parse_one(stripped, read="sqlite")
    except sqlglot.errors.ParseError as e:
        # Unparseable by sqlglot but it may still be valid SQLite; the keyword check above already passed.
        if not stripped.lower().lstrip("( ").startswith(("select", "with")):
            raise UnsafeQuery(f"Not a SELECT query ({e.__class__.__name__})")
        return stripped
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        raise UnsafeQuery(f"Only SELECT queries are allowed (got {type(tree).__name__})")
    return stripped


def execute(db_id, sql, max_rows=None, timeout=None):
    """Run a query on a read-only connection with a time limit. Returns (columns, rows). Raises on error."""
    sql = check_safe(sql)
    timeout = timeout or config.QUERY_TIMEOUT_SEC
    con = sqlite3.connect(f"file:{db_path(db_id)}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", errors="ignore")
    deadline = time.monotonic() + timeout
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)  # abort long queries
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows) if max_rows else cur.fetchall()
        return cols, rows
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise TimeoutError(f"Query exceeded {timeout}s time limit")
        raise
    finally:
        con.close()
