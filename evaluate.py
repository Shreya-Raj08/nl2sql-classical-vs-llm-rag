"""Evaluate the four systems on Spider.

Usage (from the project folder, with the venv active):
    python evaluate.py --testset dev --per-level 50            # 200 dev questions, 50 per difficulty level
    python evaluate.py --testset college_2 --all               # all 170 questions on the demo database
    python evaluate.py --testset dev --all --systems classical # all 1,034 dev questions, System 1 only
    python evaluate.py --testset dev --summarize-only          # rebuild tables/charts from predictions.csv

Metrics (per system, overall and per Spider difficulty level Easy/Medium/Hard/Extra):
  * Execution accuracy (EX): predicted SQL returns the same rows as the gold SQL.
  * Schema-linking precision/recall/F1 over the tables used (as in Table 2 of Nascimento et al., DKE 2026).
  * Average seconds per question, errors, self-corrections.
Results go to results/<testset>/ : predictions.csv, summary.csv, summary.md, charts.
The run is resumable: re-running skips questions already in predictions.csv.
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict

import sqlglot
from sqlglot import exp

import config
from src import nlp_frontend, pipeline, rag, safety
from src.spider_data import db_path, load_questions

sys.path.insert(0, str(config.SPIDER_EVAL_DIR))
LEVELS = ["easy", "medium", "hard", "extra"]


# ------------------------------------------------------------------------------------------------
def hardness(db_id, sql):
    """Spider's official difficulty label (uses the test-suite evaluation scripts)."""
    from evaluation import Evaluator
    from process_sql import Schema, get_schema as eval_schema, get_sql
    schema = Schema(eval_schema(str(db_path(db_id))))
    return Evaluator().eval_hardness(get_sql(schema, sql))


def tables_in(sql):
    try:
        return {t.name.lower() for t in sqlglot.parse_one(sql, read="sqlite").find_all(exp.Table)}
    except Exception:
        return set()


def prf(pred, gold):
    if not pred and not gold:
        return 1.0, 1.0, 1.0
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def mcnemar(ok_a, ok_b):
    """Exact (binomial) McNemar test on paired correct/incorrect outcomes. Returns (only_a, only_b, p)."""
    from math import comb
    ids = ok_a.keys() & ok_b.keys()
    only_a = sum(1 for i in ids if ok_a[i] and not ok_b[i])
    only_b = sum(1 for i in ids if ok_b[i] and not ok_a[i])
    n, k = only_a + only_b, min(only_a, only_b)
    p = min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2 ** n) if n else 1.0
    return only_a, only_b, p


def _norm_val(v):
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 4)
    return v


def results_match(pred_rows, gold_rows, ordered):
    p = [tuple(_norm_val(v) for v in r) for r in pred_rows]
    g = [tuple(_norm_val(v) for v in r) for r in gold_rows]
    if (p == g) if ordered else (Counter(p) == Counter(g)):
        return True
    # tolerate a different column order (e.g. SELECT name, age vs SELECT age, name)
    if len(p) == len(g) and p and len(p[0]) == len(g[0]):
        ps = [tuple(sorted(map(str, r))) for r in p]
        gs = [tuple(sorted(map(str, r))) for r in g]
        return (ps == gs) if ordered else (Counter(ps) == Counter(gs))
    return False


# ------------------------------------------------------------------------------------------------
def load_testset(name, per_level, use_all, seed):
    if name == "dev":
        items = load_questions(config.SPIDER_DEV)
    elif name == config.DEMO_DB:
        items = [q for q in load_questions(config.SPIDER_TRAIN) if q["db_id"] == config.DEMO_DB]
    else:
        raise SystemExit(f"Unknown test set {name}")
    for i, q in enumerate(items):
        q["idx"] = i
        try:
            q["level"] = hardness(q["db_id"], q["query"])
        except Exception:
            q["level"] = "unknown"
    if use_all:
        return items
    rng = random.Random(seed)
    picked = []
    for lvl in LEVELS:
        pool = [q for q in items if q["level"] == lvl]
        picked += rng.sample(pool, min(per_level, len(pool)))
    return sorted(picked, key=lambda q: q["idx"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testset", default="dev", help="dev | college_2")
    ap.add_argument("--per-level", type=int, default=50)
    ap.add_argument("--all", action="store_true", help="use every question instead of a stratified sample")
    ap.add_argument("--systems", default=",".join(config.SYSTEMS))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--summarize-only", action="store_true", help="rebuild tables/charts from predictions.csv")
    args = ap.parse_args()
    systems = [s.strip() for s in args.systems.split(",")]

    out_dir = config.RESULTS_DIR / (args.testset + ("_all" if args.all else ""))
    if args.summarize_only:
        return summarize(out_dir, systems)
    out_dir.mkdir(parents=True, exist_ok=True)
    tests = load_testset(args.testset, args.per_level, args.all, args.seed)
    print(f"Test set '{args.testset}': {len(tests)} questions, levels {dict(Counter(q['level'] for q in tests))}")

    # ---- Leakage check (hard requirement): must pass before anything runs ----
    report = rag.check_leakage(rag.test_questions())
    report["this_run_test_questions_checked"] = rag.check_leakage(tests)["test_questions_checked"]
    print("Leakage check PASSED:", json.dumps(report, indent=2))
    with open(out_dir / "leakage_check.json", "w") as f:
        json.dump(report, f, indent=2)

    pred_file = out_dir / "predictions.csv"
    fields = ["idx", "db_id", "level", "system", "question", "gold_sql", "pred_sql", "exec_match",
              "tab_p", "tab_r", "tab_f1", "frontend_tab_f1", "seconds", "error", "self_corrected"]
    done = set()
    if pred_file.exists():
        with open(pred_file, encoding="utf-8") as f:
            done = {(int(r["idx"]), r["system"]) for r in csv.DictReader(f)}
    new_file = not pred_file.exists()
    fh = open(pred_file, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=fields)
    if new_file:
        w.writeheader()

    for n, q in enumerate(tests, 1):
        todo = [s for s in systems if (q["idx"], s) not in done]
        if not todo:
            continue
        gold_cols, gold_rows = safety.execute(q["db_id"], q["query"], timeout=60)
        gold_tabs = tables_in(q["query"])
        analysis = nlp_frontend.analyze(q["question"], q["db_id"])
        fe_f1 = prf({t.lower() for t in analysis["linking"]["tables"]}, gold_tabs)[2]
        for s in todo:
            r = pipeline.run(s, q["question"], q["db_id"], analysis=analysis if s != "llm_rag" else None)
            ok = r["error"] is None and results_match(r["rows"], gold_rows, "order by" in q["query"].lower())
            p, rc, f1 = prf(tables_in(r["sql"] or ""), gold_tabs)
            w.writerow({"idx": q["idx"], "db_id": q["db_id"], "level": q["level"], "system": s,
                        "question": q["question"], "gold_sql": q["query"], "pred_sql": r["sql"],
                        "exec_match": int(ok), "tab_p": round(p, 3), "tab_r": round(rc, 3), "tab_f1": round(f1, 3),
                        "frontend_tab_f1": round(fe_f1, 3), "seconds": r["seconds"], "error": r["error"] or "",
                        "self_corrected": int(bool(r["fix_error"]))})
            fh.flush()
            print(f"[{n}/{len(tests)}] {s:12s} {'OK ' if ok else 'BAD'} {r['seconds']:5.1f}s  {q['question'][:60]}")
    fh.close()
    summarize(out_dir, systems)


# ------------------------------------------------------------------------------------------------
def summarize(out_dir, systems):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with open(out_dir / "predictions.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["system"] in systems]
    by = defaultdict(list)
    for r in rows:
        by[r["system"]].append(r)

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    summary = []
    for s in systems:
        rs = by[s]
        if not rs:
            continue
        row = {"system": config.SYSTEMS[s], "n": len(rs),
               "EX_all": round(100 * mean([int(r["exec_match"]) for r in rs]), 1)}
        for lvl in LEVELS:
            lr = [r for r in rs if r["level"] == lvl]
            row[f"EX_{lvl}"] = round(100 * mean([int(r["exec_match"]) for r in lr]), 1) if lr else None
        row.update({
            "table_P": round(mean([float(r["tab_p"]) for r in rs]), 3),
            "table_R": round(mean([float(r["tab_r"]) for r in rs]), 3),
            "table_F1": round(mean([float(r["tab_f1"]) for r in rs]), 3),
            "avg_seconds": round(mean([float(r["seconds"]) for r in rs]), 2),
            "errors": sum(1 for r in rs if r["error"]),
            "self_corrections": sum(int(r["self_corrected"]) for r in rs),
        })
        summary.append(row)
    if not summary:
        return
    # schema linking of the classical front-end alone (DANKE-like "Alternative 3")
    any_rows = next(iter(by.values()))
    fe = round(mean([float(r["frontend_tab_f1"]) for r in any_rows]), 3)

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    cols = list(summary[0].keys())
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols) + " |" for r in summary]
    md += ["", f"Schema-linking F1 of the classical NLP front-end alone (keyword matching, before any SQL "
               f"generation): {fe}"]
    ok = {s: {r["idx"]: int(r["exec_match"]) for r in by[s]} for s in systems if by[s]}
    pairs = [(a, b) for a, b in [("classical", "nlp_llm"), ("nlp_llm", "nlp_llm_rag"), ("llm_rag", "nlp_llm_rag"),
                                 ("llm_rag", "nlp_llm")] if a in ok and b in ok]
    if pairs:
        md += ["", "### Paired significance test (exact McNemar, execution match on the same questions)",
               "| comparison | only first right | only second right | p-value | significant (p<0.05) |",
               "|---|---|---|---|---|"]
    for a, b in pairs:
        only_a, only_b, p = mcnemar(ok[a], ok[b])
        md.append(f"| {config.SYSTEMS[a]} vs {config.SYSTEMS[b]} | {only_a} | {only_b} | {p:.4f} | "
                  f"{'yes' if p < 0.05 else 'no'} |")
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n" + "\n".join(md))

    # Chart 1: execution accuracy by difficulty
    fig, ax = plt.subplots(figsize=(9, 4.5))
    width = 0.8 / len(summary)
    for i, r in enumerate(summary):
        vals = [r[f"EX_{l}"] or 0 for l in LEVELS] + [r["EX_all"]]
        bars = ax.bar([x + i * width for x in range(5)], vals, width, label=r["system"])
        ax.bar_label(bars, fmt="%.0f", fontsize=7, padding=1)
    ax.set_xticks([x + width * (len(summary) - 1) / 2 for x in range(5)], ["Easy", "Medium", "Hard", "Extra", "All"])
    ax.set_ylabel("Execution accuracy (%)")
    ax.set_ylim(0, 100)
    ax.set_title(f"Execution accuracy by difficulty ({out_dir.name})")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "chart_execution_accuracy.png", dpi=150)

    # Chart 2: schema-linking F1 (mirrors Table 2 of Nascimento et al.)
    fig, ax = plt.subplots(figsize=(7, 4))
    names = ["NLP front-end only"] + [r["system"] for r in summary]
    vals = [fe] + [r["table_F1"] for r in summary]
    bars = ax.barh(names, vals)
    ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set_xlim(0, 1.1)
    ax.set_xlabel("Table-level F1")
    ax.set_title("Schema linking: did the system use the right tables?")
    fig.tight_layout()
    fig.savefig(out_dir / "chart_schema_linking.png", dpi=150)


if __name__ == "__main__":
    main()
