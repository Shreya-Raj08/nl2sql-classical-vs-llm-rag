"""Runs one question through one of the four systems and returns the SQL, results and all intermediate steps."""
import time

import config
from src import classical, llm, nlp_frontend, rag, safety


def run(system, question, db_id, analysis=None):
    """system: 'classical' | 'nlp_llm' | 'nlp_llm_rag' | 'llm_rag'."""
    assert system in config.SYSTEMS, system
    t0 = time.perf_counter()
    res = {"system": system, "question": question, "db_id": db_id, "sql": None, "columns": [], "rows": [],
           "error": None, "steps": {}, "prompt": None, "examples": [], "fix_error": None}
    uses_nlp = system in ("classical", "nlp_llm", "nlp_llm_rag")
    uses_rag = system in ("nlp_llm_rag", "llm_rag")
    try:
        if uses_nlp:
            analysis = analysis or nlp_frontend.analyze(question, db_id)
            res["steps"] = nlp_frontend.steps_for_display(analysis)
        if uses_rag:
            res["examples"] = rag.retrieve(question, db_id)
        if system == "classical":
            res["sql"] = classical.generate(analysis)
        else:
            out = llm.generate(question, db_id,
                               analysis=analysis if uses_nlp else None,
                               examples=res["examples"] if uses_rag else None,
                               executor=lambda s: safety.execute(db_id, s, max_rows=1))
            res.update(sql=out["sql"], prompt=out["prompt"], fix_error=out["fix_error"])
        res["columns"], res["rows"] = safety.execute(db_id, res["sql"], max_rows=config.MAX_RESULT_ROWS)
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {e}"
    res["seconds"] = round(time.perf_counter() - t0, 2)
    return res
