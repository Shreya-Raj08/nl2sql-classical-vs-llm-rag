"""Loading Spider: database schemas, foreign keys, questions and database file paths."""
import json
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

import config


@dataclass
class Column:
    table: str          # original table name, e.g. "student"
    name: str           # original column name, e.g. "tot_cred"
    natural: str        # Spider's natural-language name, e.g. "tot cred"
    type: str           # "text" | "number" | "time" | "boolean" | "others"
    is_pk: bool = False


@dataclass
class Schema:
    db_id: str
    tables: list                                   # original table names
    table_natural: dict                            # table -> natural name
    columns: list                                  # list[Column]
    foreign_keys: list = field(default_factory=list)  # (table1, col1, table2, col2)

    def columns_of(self, table):
        return [c for c in self.columns if c.table == table]

    def primary_key(self, table):
        pks = [c for c in self.columns_of(table) if c.is_pk]
        return pks[0] if pks else None

    def to_create_table_sql(self):
        """Schema as CREATE TABLE statements (the representation DAIL-SQL found works best for LLMs)."""
        out = []
        for t in self.tables:
            lines = []
            for c in self.columns_of(t):
                sql_type = {"number": "NUMBER", "time": "TIME", "boolean": "BOOLEAN"}.get(c.type, "TEXT")
                lines.append(f"  {c.name} {sql_type}{' PRIMARY KEY' if c.is_pk else ''}")
            for t1, c1, t2, c2 in self.foreign_keys:
                if t1 == t:
                    lines.append(f"  FOREIGN KEY ({c1}) REFERENCES {t2}({c2})")
            out.append(f"CREATE TABLE {t} (\n" + ",\n".join(lines) + "\n);")
        return "\n".join(out)


@lru_cache(maxsize=1)
def load_all_schemas():
    with open(config.SPIDER_TABLES, encoding="utf-8") as f:
        raw = json.load(f)
    schemas = {}
    for db in raw:
        tables = db["table_names_original"]
        cols = []
        col_lookup = {}
        pk_ids = set()
        for pk in db["primary_keys"]:
            pk_ids.update(pk if isinstance(pk, list) else [pk])
        for idx, ((t_idx, cname), (_, cnat), ctype) in enumerate(
                zip(db["column_names_original"], db["column_names"], db["column_types"])):
            if t_idx < 0:          # the special "*" column
                continue
            col = Column(tables[t_idx], cname, cnat, ctype, idx in pk_ids)
            cols.append(col)
            col_lookup[idx] = col
        fks = []
        for a, b in db["foreign_keys"]:
            if a in col_lookup and b in col_lookup:
                ca, cb = col_lookup[a], col_lookup[b]
                fks.append((ca.table, ca.name, cb.table, cb.name))
        schemas[db["db_id"]] = Schema(db["db_id"], tables,
                                      dict(zip(tables, db["table_names"])), cols, fks)
    return schemas


def get_schema(db_id):
    return load_all_schemas()[db_id]


def db_path(db_id):
    return config.SPIDER_DB_DIR / db_id / f"{db_id}.sqlite"


def load_questions(path):
    """Returns list of dicts: {db_id, question, query}."""
    with open(path, encoding="utf-8") as f:
        return [{"db_id": q["db_id"], "question": q["question"], "query": q["query"]} for q in json.load(f)]


def list_databases():
    return sorted(p.name for p in config.SPIDER_DB_DIR.iterdir() if (p / f"{p.name}.sqlite").exists())


def read_text_values(db_id, max_per_column=3000, max_len=60):
    """Distinct text values of every text column -> {(table, column): [values]} (used for value matching)."""
    schema = get_schema(db_id)
    values = {}
    con = sqlite3.connect(f"file:{db_path(db_id)}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", errors="ignore")
    try:
        for c in schema.columns:
            if c.type != "text":
                continue
            try:
                rows = con.execute(
                    f'SELECT DISTINCT "{c.name}" FROM "{c.table}" WHERE "{c.name}" IS NOT NULL LIMIT {max_per_column}'
                ).fetchall()
            except sqlite3.Error:
                continue
            vals = [str(r[0]).strip() for r in rows if r[0] is not None]
            vals = [v for v in vals if 0 < len(v) <= max_len]
            if vals:
                values[(c.table, c.name)] = vals
    finally:
        con.close()
    return values
