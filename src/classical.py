"""System 1: Classical NLP -> SQL using rules and templates (no LLM).

Uses only the outputs of the shared front-end (keyword matches, linked tables, join path, intent cues)
and fills a SQL template:  SELECT <select> FROM <tables + joins> WHERE <conditions>
                           GROUP BY <group> ORDER BY <order> LIMIT <n>
It handles simple questions well and is expected to fail on nested queries, set operations and complex
logic -- which is exactly the gap the LLM-based systems are compared against.
"""
from src.spider_data import get_schema

AGE_HINTS = {"oldest": "DESC", "youngest": "ASC", "old": "DESC", "young": "ASC"}


def _quote(v):
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _name_column(schema, table):
    """A human-readable column to show for a table (name/title), falling back to the primary key."""
    cols = schema.columns_of(table)
    for key in ("name", "title"):
        for c in cols:
            if key in c.name.lower() and not c.name.lower().endswith("id"):
                return c.name
    pk = schema.primary_key(table)
    return pk.name if pk else cols[0].name


def _nearest(cands, token, prefer_after=True):
    if not cands:
        return None
    if token is None:
        return cands[0]
    after = [m for m in cands if m.start > token]
    if prefer_after and after:
        return min(after, key=lambda m: m.start - token)
    return min(cands, key=lambda m: abs(m.start - token))


def generate(a):
    schema = get_schema(a["db_id"])
    matches, link, intent = a["matches"], a["linking"], a["intent"]
    col_type = {(c.table, c.name): c.type for c in schema.columns}
    columns = [m for m in matches if m.kind == "column"]
    numeric = [m for m in columns if col_type.get((m.table, m.column)) == "number"]
    used = set()
    where, order_by, group_by, limit = [], None, None, None
    select_expr = None
    extra_tables = []

    # 1) data values found in the question  ->  column = 'value'
    for m in matches:
        if m.kind == "value":
            where.append((m.table, m.column, "=", m.value))

    # 2) numeric comparisons ("more than 100 credits")  ->  column > 100
    for cmp in intent["comparisons"]:
        tgt = _nearest([m for m in numeric if id(m) not in used], cmp["token"], prefer_after=True)
        if tgt is None:
            cands = [c for t in link["tables"] for c in schema.columns_of(t) if c.type == "number" and not c.is_pk]
            if cands:
                where.append((cands[0].table, cands[0].name, cmp["op"], cmp["value"]))
            continue
        used.add(id(tgt))
        where.append((tgt.table, tgt.column, cmp["op"], cmp["value"]))

    # 3) aggregation over a numeric column ("average salary")
    agg = intent["aggregate"]
    agg_target = None
    if agg in ("AVG", "SUM", "MAX", "MIN"):
        agg_target = _nearest([m for m in numeric if id(m) not in used], intent["agg_token"])
        if agg_target:
            used.add(id(agg_target))

    # 4) grouping ("for each department")
    if intent["group_by"]:
        after = [m for m in matches if m.kind in ("column", "table") and m.start > intent["group_token"]]
        g = min(after, key=lambda m: m.start) if after else None
        if g is not None:
            group_by = (g.table, g.column or _name_column(schema, g.table))
            used.add(id(g))

    # 5) superlatives ("highest salary", "oldest", "department with the most students")
    sup = intent["superlative"]
    count_superlative = False
    if sup and not agg:
        tgt = _nearest([m for m in numeric if id(m) not in used], sup["token"])
        if tgt is None and sup["word"].lower() in AGE_HINTS:
            age = next((c for t in link["tables"] for c in schema.columns_of(t) if "age" in c.name.lower()), None)
            if age:
                order_by = (age.table, age.name, AGE_HINTS[sup["word"].lower()])
        elif tgt is not None:
            used.add(id(tgt))
            order_by = (tgt.table, tgt.column, sup["dir"])
        else:
            # "Which X has the most Y?"  ->  GROUP BY X ORDER BY COUNT(*) DESC LIMIT 1
            tables_mentioned = [m for m in matches if m.kind == "table"]
            if tables_mentioned:
                main = tables_mentioned[0].table
                group_by = group_by or (main, _name_column(schema, main))
                count_superlative = True
        limit = intent["limit"] or 1

    # 6) explicit ordering ("ordered by age")
    if intent["order"] and order_by is None:
        cand = [m for m in columns if id(m) not in used]
        if cand:
            o = cand[-1]
            used.add(id(o))
            order_by = (o.table, o.column, intent["order"])

    # 7) SELECT list
    where_cols = {(t, c) for t, c, _, _ in where}
    sel_cols = [(m.table, m.column) for m in columns
                if id(m) not in used and (m.table, m.column) not in where_cols]
    sel_cols = list(dict.fromkeys(sel_cols))
    if group_by and group_by in sel_cols:
        sel_cols.remove(group_by)

    tables = list(link["tables"])
    for t, c, *_ in where + ([order_by] if order_by else []) + ([group_by] if group_by else []):
        if t not in tables:
            extra_tables.append(t)
    multi = len(tables) + len(extra_tables) > 1

    def q(t, c):
        return f"{t}.{c}" if multi else c

    distinct = "DISTINCT " if intent["distinct"] else ""
    if agg == "COUNT":
        inner = f"COUNT(DISTINCT {q(*sel_cols[0])})" if intent["distinct"] and sel_cols else "COUNT(*)"
        select_expr = f"{q(*group_by)}, {inner}" if group_by else inner
        distinct = ""
    elif agg in ("AVG", "SUM", "MAX", "MIN") and agg_target:
        inner = f"{agg}({q(agg_target.table, agg_target.column)})"
        select_expr = f"{q(*group_by)}, {inner}" if group_by else inner
    elif count_superlative:
        select_expr = q(*group_by)
    elif group_by:
        select_expr = ", ".join([q(*group_by)] + [q(*c) for c in sel_cols]) if sel_cols else q(*group_by)
    elif sel_cols:
        select_expr = ", ".join(q(*c) for c in sel_cols)
    else:
        main = next((m.table for m in matches if m.kind == "table"), tables[0])
        select_expr = q(main, _name_column(schema, main))

    # 8) FROM + JOIN (join path from the foreign-key graph)
    from_sql = tables[0]
    joined = {tables[0]}
    for t1, c1, t2, c2 in link["joins"]:
        new = t2 if t1 in joined else t1
        from_sql += f" JOIN {new} ON {t1}.{c1} = {t2}.{c2}"
        joined.add(new)
    for t in tables[1:] + extra_tables:
        if t not in joined:          # not connected by a foreign key: fall back to a cross join
            from_sql += f", {t}"
            joined.add(t)

    sql = f"SELECT {distinct}{select_expr} FROM {from_sql}"
    if where:
        sql += " WHERE " + " AND ".join(f"{q(t, c)} {op} {_quote(v)}" for t, c, op, v in where)
    if group_by:
        sql += f" GROUP BY {q(*group_by)}"
    if count_superlative:
        sql += f" ORDER BY COUNT(*) {sup['dir']}"
    elif order_by:
        sql += f" ORDER BY {q(order_by[0], order_by[1])} {order_by[2]}"
    if limit:
        sql += f" LIMIT {limit}"
    return sql
