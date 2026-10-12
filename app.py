"""Simple web interface for the NL-to-SQL comparison.  Run:  python app.py   then open http://127.0.0.1:7860"""
import gradio as gr
import pandas as pd

import config
from src import nlp_frontend, pipeline, rag, safety
from src.spider_data import get_schema, list_databases, load_questions

CHOICES = list(config.SYSTEMS.values()) + ["Compare all"]
KEY_OF = {v: k for k, v in config.SYSTEMS.items()}
EXAMPLES = [
    "How many students are in the Comp. Sci. department?",
    "What are the names of instructors with a salary greater than 90000?",
    "Which department has the highest budget?",
    "What is the average salary of instructors in each department?",
    "List the titles of courses offered by the Physics department.",
    "Find the names of instructors who have not taught any course.",
]


def _df(res):
    if res["error"]:
        return pd.DataFrame({"error": [res["error"]]})
    return pd.DataFrame(res["rows"], columns=res["columns"]) if res["columns"] else pd.DataFrame()


def ask(question, db_id, choice):
    if not question.strip():
        return "", pd.DataFrame(), "", {}, "", ""
    systems = list(config.SYSTEMS) if choice == "Compare all" else [KEY_OF[choice]]
    analysis = nlp_frontend.analyze(question, db_id)
    results = [pipeline.run(s, question, db_id, analysis=analysis if s != "llm_rag" else None) for s in systems]
    main = results[-1] if len(results) == 1 else results[0]
    if len(results) > 1:
        lines = []
        for r in results:
            status = f"error: {r['error']}" if r["error"] else f"{len(r['rows'])} row(s)"
            fixed = "  (self-corrected)" if r["fix_error"] else ""
            more = len(r["rows"]) - 5
            table_md = "" if r["error"] else (_df(r).head(5).to_markdown(index=False)
                                              + (f"\n\n_… and {more} more row(s)_" if more > 0 else ""))
            lines.append(f"### {config.SYSTEMS[r['system']]}  ·  {r['seconds']} s  ·  {status}{fixed}\n"
                         f"```sql\n{r['sql'] or '-- no SQL generated'}\n```\n" + table_md)
        comparison = "\n\n".join(lines)
    else:
        comparison = ""
    examples = next((r["examples"] for r in results if r["examples"]), [])
    ex_md = "\n\n".join(f"**{e['similarity']}** · `{e['db_id']}` — {e['question']}\n```sql\n{e['query']}\n```"
                        for e in examples) or "_(this system does not use retrieval)_"
    # show the richest prompt (S3: hints + examples) when several systems ran
    shown = next((r for r in results if r["system"] == "nlp_llm_rag"), None) or next(
        (r for r in results if r["prompt"]), main)
    prompt_md = (f"Prompt of **{config.SYSTEMS[shown['system']]}**:\n```text\n{shown['prompt']}\n```"
                 if shown.get("prompt") else "_(System 1 uses no LLM)_")
    if len(results) > 1:     # Compare all: the side-by-side answers below replace the single SQL/result boxes
        status = f"Compare all · {round(sum(r['seconds'] for r in results), 1)} s in total"
        return ("", pd.DataFrame(), comparison, nlp_frontend.steps_for_display(analysis), ex_md,
                f"{prompt_md}\n\n{status}")
    status = (f"{config.SYSTEMS[main['system']]} · {main['seconds']} s"
              + (f" · first attempt failed, self-corrected ({main['fix_error']})" if main["fix_error"] else ""))
    return (main["sql"] or "", _df(main), comparison,
            nlp_frontend.steps_for_display(analysis), ex_md, f"{prompt_md}\n\n{status}")


def schema_md(db_id):
    return f"```sql\n{get_schema(db_id).to_create_table_sql()}\n```"


RESULT_SETS = ("dev", f"{config.DEMO_DB}_all", "dev_all")


def results_md():
    out = []
    for name in RESULT_SETS:
        f = config.RESULTS_DIR / name / "summary.md"
        if f.exists():
            out.append(f"## Test set: {name}\n\n" + f.read_text(encoding="utf-8"))
        lf = config.RESULTS_DIR / name / "leakage_check.json"
        if lf.exists():
            out.append("Leakage check:\n```json\n" + lf.read_text() + "\n```")
    return "\n\n".join(out) or "_No evaluation results yet. Run `python evaluate.py` first._"


def chart_paths():
    paths = []
    for name in RESULT_SETS:
        for c in ("chart_execution_accuracy.png", "chart_schema_linking.png"):
            p = config.RESULTS_DIR / name / c
            if p.exists():
                paths.append(str(p))
    return paths


def tables_overview(db_id):
    """Every table with its columns, keys and number of rows."""
    s = get_schema(db_id)
    lines = [f"**{db_id}** has {len(s.tables)} tables.", "",
             "| table | rows | columns (PK = primary key) | links to |", "|---|---|---|---|"]
    for t in s.tables:
        try:
            n = safety.execute(db_id, f'SELECT COUNT(*) FROM "{t}"')[1][0][0]
        except Exception:
            n = "?"
        cols = ", ".join(f"{c.name}{' (PK)' if c.is_pk else ''}" for c in s.columns_of(t))
        via = {}
        for t1, c1, t2, _ in s.foreign_keys:
            if t1 == t:
                via.setdefault(t2, []).append(c1)
        links = ", ".join(f"{t2} (via {', '.join(cs)})" for t2, cs in via.items()) or "—"
        lines.append(f"| **{t}** | {n} | {cols} | {links} |")
    return "\n".join(lines)


def table_preview(db_id, table, n=20):
    if not table:
        return pd.DataFrame()
    cols, rows = safety.execute(db_id, f'SELECT * FROM "{table}" LIMIT {int(n)}')
    return pd.DataFrame(rows, columns=cols)


def spider_questions(db_id, limit=25):
    """Sample questions written for this database in Spider (useful ideas for the demo), with difficulty."""
    import evaluate
    qs = [q for path in (config.SPIDER_TRAIN, config.SPIDER_DEV) for q in load_questions(path) if q["db_id"] == db_id]
    rows = []
    for q in qs[:limit]:
        try:
            level = evaluate.hardness(db_id, q["query"])
        except Exception:
            level = "?"
        rows.append([level, q["question"]])
    return pd.DataFrame(rows, columns=["difficulty", "question"])


def explorer(db_id):
    tables = get_schema(db_id).tables
    return (tables_overview(db_id), gr.update(choices=tables, value=tables[0]),
            table_preview(db_id, tables[0]), spider_questions(db_id), schema_md(db_id))


def build():
    try:
        print("RAG leakage check:", rag.check_leakage())
        leak_warning = ""
    except Exception as e:                       # only shown if the check fails
        leak_warning = f"\n\n**WARNING: RAG leakage check FAILED: {e}**"
    with gr.Blocks(title="NL to SQL") as demo:
        gr.Markdown("# Natural Language to SQL\nClassical NLP vs NLP + LLM vs NLP + LLM + RAG" + leak_warning)
        with gr.Tab("Ask a question"):
            with gr.Row():
                db = gr.Dropdown(list_databases(), value=config.DEMO_DB, label="Database", scale=1)
                system = gr.Radio(CHOICES, value=CHOICES[2], label="System", scale=3)
            question = gr.Textbox(label="Question", placeholder="e.g. How many students are in the Comp. Sci. department?")
            gr.Examples(EXAMPLES, inputs=question)
            go = gr.Button("Generate SQL", variant="primary")
            sql = gr.Code(label="Generated SQL", language="sql")
            table = gr.Dataframe(label="Result")
            comparison = gr.Markdown()
            with gr.Accordion("Show steps: classical NLP front-end (A1–A5)", open=False):
                steps = gr.JSON()
            with gr.Accordion("Show steps: retrieved examples (RAG)", open=False):
                examples = gr.Markdown()
            with gr.Accordion("Show steps: prompt sent to the LLM", open=False):
                prompt = gr.Markdown()
            go.click(ask, [question, db, system], [sql, table, comparison, steps, examples, prompt])
            question.submit(ask, [question, db, system], [sql, table, comparison, steps, examples, prompt])
        with gr.Tab("Database explorer"):
            gr.Markdown("Shows the database selected on the *Ask a question* tab.")
            overview = gr.Markdown()
            with gr.Row():
                table_pick = gr.Dropdown(label="Preview a table (first 20 rows)", scale=1)
            preview = gr.Dataframe(label="Table contents")
            with gr.Accordion("Example questions written for this database in Spider", open=False):
                sample_qs = gr.Dataframe(wrap=True)
            with gr.Accordion("Full schema (CREATE TABLE statements, as given to the LLM)", open=False):
                schema = gr.Markdown()
            outputs = [overview, table_pick, preview, sample_qs, schema]
            db.change(explorer, db, outputs)
            demo.load(explorer, db, outputs)
            table_pick.change(table_preview, [db, table_pick], preview)
        with gr.Tab("Evaluation results"):
            res = gr.Markdown(results_md())
            gallery = gr.Gallery(chart_paths(), columns=2, height="auto")
            gr.Button("Refresh").click(lambda: (results_md(), chart_paths()), None, [res, gallery])
    return demo


if __name__ == "__main__":
    # footer_links=[] and the CSS remove Gradio's footer ("Use via API", "Built with Gradio", "Settings")
    build().launch(inbrowser=True, footer_links=[], css="footer {display: none !important;}")
