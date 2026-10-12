"""Error analysis of evaluation results: why did each system fail?

Usage:  python error_analysis.py --testset dev        (reads results/<testset>/predictions.csv)
Writes results/<testset>/error_analysis.md
"""
import argparse
import csv
import re
from collections import Counter, defaultdict

import config

CATEGORIES = {
    "sql_error": "SQL failed to run (syntax error / unknown column / unsafe)",
    "wrong_tables": "Used the wrong set of tables (schema-linking error)",
    "value_mismatch": "Right structure, but a literal value is spelt/cased differently from the database",
    "wrong_logic": "Right tables, wrong logic (conditions, grouping, aggregation, nesting, ordering)",
}


def literals(sql):
    return {m.lower() for m in re.findall(r"'([^']*)'|\"([^\"]*)\"", sql or "") for m in m if m}


def literals_raw(sql):
    return {m for m in re.findall(r"'([^']*)'|\"([^\"]*)\"", sql or "") for m in m if m}


def categorize(r):
    if r["error"]:
        return "sql_error"
    if float(r["tab_f1"]) < 1.0:
        return "wrong_tables"
    p, g = literals_raw(r["pred_sql"]), literals_raw(r["gold_sql"])
    if p != g and {x.lower() for x in p} == {x.lower() for x in g}:
        return "value_mismatch"
    return "wrong_logic"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="dev")
    args = ap.parse_args()
    out_dir = config.RESULTS_DIR / args.testset
    with open(out_dir / "predictions.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_sys = defaultdict(list)
    by_q = defaultdict(dict)
    for r in rows:
        by_sys[r["system"]].append(r)
        by_q[r["idx"]][r["system"]] = r

    md = [f"# Error analysis: {args.testset}", "",
          "## Why each system's wrong answers were wrong", "",
          "| system | wrong answers | " + " | ".join(CATEGORIES) + " |",
          "|---|---|" + "---|" * len(CATEGORIES)]
    for s, label in config.SYSTEMS.items():
        wrong = [r for r in by_sys.get(s, []) if r["exec_match"] == "0"]
        if not by_sys.get(s):
            continue
        c = Counter(categorize(r) for r in wrong)
        md.append(f"| {label} | {len(wrong)} | " + " | ".join(str(c[k]) for k in CATEGORIES) + " |")
    md += ["", "Categories:"] + [f"- **{k}**: {v}" for k, v in CATEGORIES.items()]

    def pairs(a, b, title, limit=8):
        sel = [d for d in by_q.values() if a in d and b in d
               and d[a]["exec_match"] == "1" and d[b]["exec_match"] == "0"]
        out = ["", f"## {title} ({len(sel)} questions)", ""]
        cats = Counter(categorize(d[b]) for d in sel)
        out.append("Failure type of " + config.SYSTEMS[b] + ": " +
                   ", ".join(f"{k} = {v}" for k, v in cats.most_common()))
        for d in sel[:limit]:
            out += ["", f"**Q ({d[a]['level']}):** {d[a]['question']}",
                    f"- Gold: `{d[a]['gold_sql']}`",
                    f"- {config.SYSTEMS[a]} (correct): `{d[a]['pred_sql']}`",
                    f"- {config.SYSTEMS[b]} (wrong, {categorize(d[b])}): `{d[b]['pred_sql']}`"]
        return out

    md += pairs("nlp_llm", "nlp_llm_rag", "Where adding RAG hurt: S2 correct, S3 wrong")
    md += pairs("nlp_llm_rag", "nlp_llm", "Where adding RAG helped: S3 correct, S2 wrong")
    md += pairs("nlp_llm_rag", "llm_rag", "Where the NLP hints helped: S3 correct, LLM + RAG baseline wrong")
    md += pairs("llm_rag", "nlp_llm_rag", "Where the NLP hints hurt: baseline correct, S3 wrong")
    md += pairs("nlp_llm", "classical", "What the LLM fixes: S2 correct, classical S1 wrong", limit=5)
    (out_dir / "error_analysis.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
