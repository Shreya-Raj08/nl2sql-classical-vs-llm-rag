"""LLM-based SQL generation (Systems 2, 3 and the LLM+RAG baseline) with a local model via Ollama.

Prompt = schema (CREATE TABLE statements, the representation recommended by DAIL-SQL)
         + [NLP hints from the classical front-end]        (S2, S3)
         + [retrieved similar question->SQL examples]      (S3, baseline)
         + question
All three LLM systems use the same model, settings and one round of self-correction, so differences
between them come only from the NLP hints and/or the retrieved examples.
"""
import re

import ollama

import config
from src.spider_data import get_schema

SYSTEM_PROMPT = (
    "You are an expert SQLite developer. Translate the user's question into ONE SQLite SELECT query "
    "for the given database. Use only tables and columns that exist in the schema. "
    "Return only the SQL query, with no explanation."
)


def _fmt_value(v):
    return f"'{v}'" if isinstance(v, str) else str(v)


def nlp_hints(a):
    """Turn the classical front-end analysis into short textual hints for the LLM."""
    lines = []
    for m in a["matches"]:
        if m.kind == "table":
            lines.append(f'- "{m.text}" refers to table {m.table}' + (" (synonym)" if m.how == "synonym" else ""))
        elif m.kind == "column":
            lines.append(f'- "{m.text}" refers to column {m.table}.{m.column}')
        elif m.kind == "value":
            lines.append(f'- "{m.text}" is the stored value {_fmt_value(m.value)} in column {m.table}.{m.column} '
                         f"(use this exact spelling)")
    link = a["linking"]
    if link["tables"]:
        lines.append(f"- Tables likely needed: {', '.join(link['tables'])}")
    if link["joins"]:
        lines.append("- Join path: " + "; ".join(f"{t1}.{c1} = {t2}.{c2}" for t1, c1, t2, c2 in link["joins"]))
    it = a["intent"]
    cues = []
    if it["aggregate"]:
        cues.append(f"aggregation {it['aggregate']}")
    for c in it["comparisons"]:
        cues.append(f'condition "{c["phrase"]} {c["value"]}" ({c["op"]} {c["value"]})')
    if it["superlative"]:
        cues.append(f'superlative "{it["superlative"]["word"]}" (ORDER BY ... {it["superlative"]["dir"]} LIMIT '
                    f'{it["limit"] or 1}, or MAX/MIN)')
    if it["group_by"]:
        cues.append("grouping (GROUP BY)")
    if it["order"]:
        cues.append(f"ordering ({it['order']})")
    if it["distinct"]:
        cues.append("distinct values")
    if it["negation"]:
        cues.append("negation (consider NOT IN / EXCEPT)")
    if cues:
        lines.append("- Question cues: " + "; ".join(cues))
    return "\n".join(lines)


def build_prompt(question, db_id, analysis=None, examples=None):
    parts = ["### SQLite database schema", get_schema(db_id).to_create_table_sql()]
    if analysis is not None:
        hints = nlp_hints(analysis)
        if hints:
            parts += ["", "### Hints from NLP analysis of the question (may be incomplete)", hints]
    if examples:
        parts += ["", "### Examples of similar questions and their SQL (from OTHER databases)"]
        for ex in examples:
            parts += [f"Question: {ex['question']}", f"SQL: {ex['query']}", ""]
    parts += ["", "### Question", question, "", "SQL:"]
    return "\n".join(parts)


def extract_sql(text):
    m = re.search(r"```(?:sql|sqlite)?\s*(.*?)```", text, re.S | re.I)
    if m:
        text = m.group(1)
    m = re.search(r"\b(SELECT|WITH)\b.*", text, re.S | re.I)
    sql = m.group(0) if m else text
    sql = sql.split(";")[0]
    return " ".join(sql.split())


def chat(messages):
    resp = ollama.chat(model=config.LLM_MODEL, messages=messages, options=config.LLM_OPTIONS)
    return resp["message"]["content"]


def generate(question, db_id, analysis=None, examples=None, executor=None):
    """Generate SQL; if `executor(sql)` raises, send the error back once for self-correction.

    Returns dict(sql, prompt, raw, attempts, fix_error)."""
    prompt = build_prompt(question, db_id, analysis, examples)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
    raw = chat(messages)
    sql = extract_sql(raw)
    out = {"sql": sql, "prompt": prompt, "raw": raw, "attempts": 1, "fix_error": None}
    if executor is None:
        return out
    for _ in range(config.LLM_MAX_FIX_ATTEMPTS):
        try:
            executor(sql)
            break
        except Exception as e:                       # SQLite error, unsafe query or timeout
            out["fix_error"] = str(e)
            messages += [{"role": "assistant", "content": raw},
                         {"role": "user", "content": f"That query failed with this error: {e}\n"
                                                     "Fix it. Return only the corrected SQLite query."}]
            raw = chat(messages)
            sql = extract_sql(raw)
            out.update(sql=sql, raw=raw, attempts=out["attempts"] + 1)
    return out
