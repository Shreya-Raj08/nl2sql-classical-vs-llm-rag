"""RAG: dynamic few-shot example retrieval (as in DAIL-SQL and the DFE step of Nascimento et al.).

The example pool is Spider's training set (question -> SQL pairs). Retrieval uses sentence embeddings
(all-MiniLM-L6-v2) and a FAISS inner-product index over normalised vectors (= cosine similarity).

LEAKAGE GUARD (hard requirement): no test question may be in the pool.
  * Every database used for testing (all 20 Spider dev databases + the demo database college_2)
    is removed from the pool entirely.
  * Any pool question whose normalised text equals a test question (even on another database) is removed.
  * Any pool question that is a near-identical paraphrase of a test question (cosine >= 0.95) is removed.
  * check_leakage() re-verifies all three conditions and raises LeakageError if anything overlaps.
"""
import json
import re
from functools import lru_cache

import faiss
import numpy as np

import config
from src.spider_data import load_questions


NEAR_DUP_THRESHOLD = 0.95


class LeakageError(Exception):
    pass


def normalize(q):
    return " ".join(re.sub(r"[^\w\s]", " ", q.lower()).split())


def test_questions():
    """All questions that may ever be used for testing: Spider dev + every question on the demo DB."""
    dev = load_questions(config.SPIDER_DEV)
    demo = [q for q in load_questions(config.SPIDER_TRAIN) if q["db_id"] == config.DEMO_DB]
    return dev + demo


@lru_cache(maxsize=1)
def embedder():
    from sentence_transformers import SentenceTransformer
    try:
        return SentenceTransformer(config.EMBED_MODEL, device="cpu", local_files_only=True)  # cached copy
    except Exception:
        return SentenceTransformer(config.EMBED_MODEL, device="cpu")                       # first download


def embed(texts):
    return embedder().encode(texts, batch_size=64, normalize_embeddings=True,
                             show_progress_bar=False, convert_to_numpy=True).astype("float32")


def build_pool(force=False):
    out = config.RAG_INDEX_DIR
    if (out / "pool.json").exists() and not force:
        return
    out.mkdir(parents=True, exist_ok=True)
    tests = test_questions()
    test_dbs = sorted({q["db_id"] for q in tests})
    test_texts = {normalize(q["question"]) for q in tests}
    train = load_questions(config.SPIDER_TRAIN)
    pool = [q for q in train if q["db_id"] not in test_dbs and normalize(q["question"]) not in test_texts]
    vecs = embed([q["question"] for q in pool])
    # also drop near-identical paraphrases of any test question (even though they are on other databases)
    max_sim = (vecs @ embed([q["question"] for q in tests]).T).max(axis=1)
    keep = max_sim < NEAR_DUP_THRESHOLD
    n_near = int((~keep).sum())
    pool = [q for q, k in zip(pool, keep) if k]
    vecs = vecs[keep]
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(out / "pool.faiss"))
    with open(out / "pool.json", "w", encoding="utf-8") as f:
        json.dump(pool, f)
    manifest = {
        "train_questions": len(train),
        "pool_questions": len(pool),
        "removed_for_test_databases": sum(q["db_id"] in test_dbs for q in train),
        "removed_for_duplicate_text": sum(q["db_id"] not in test_dbs and normalize(q["question"]) in test_texts
                                          for q in train),
        f"removed_for_near_duplicate_cos>={NEAR_DUP_THRESHOLD}": n_near,
        "excluded_databases": test_dbs,
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


@lru_cache(maxsize=1)
def load_pool():
    build_pool()
    index = faiss.read_index(str(config.RAG_INDEX_DIR / "pool.faiss"))
    with open(config.RAG_INDEX_DIR / "pool.json", encoding="utf-8") as f:
        pool = json.load(f)
    return index, pool


def check_leakage(tests=None):
    """Verify zero overlap between the RAG pool and the test questions. Raises LeakageError on any overlap."""
    _, pool = load_pool()
    tests = tests if tests is not None else test_questions()
    pool_dbs = {q["db_id"] for q in pool}
    pool_texts = {normalize(q["question"]) for q in pool}
    db_overlap = sorted(pool_dbs & {q["db_id"] for q in tests})
    text_overlap = sorted(pool_texts & {normalize(q["question"]) for q in tests})
    report = {
        "test_questions_checked": len(tests),
        "pool_questions": len(pool),
        "database_overlap": len(db_overlap),
        "exact_question_overlap": len(text_overlap),
    }
    # Near-identical paraphrases (cosine similarity >= threshold) also count as leakage.
    index, _ = load_pool()
    sims, _ = index.search(embed([q["question"] for q in tests]), 1)
    near = int((sims[:, 0] >= NEAR_DUP_THRESHOLD).sum())
    report[f"near_duplicate_overlap_cos>={NEAR_DUP_THRESHOLD}"] = near
    if db_overlap or text_overlap or near:
        raise LeakageError(f"Test data found in RAG pool! databases={db_overlap[:5]} "
                           f"questions={text_overlap[:5]} near_duplicates={near}")
    report["status"] = "PASSED (zero overlap)"
    return report


def retrieve(question, db_id, k=None):
    """Top-k most similar pool questions (never from the question's own database)."""
    k = k or config.RAG_TOP_K
    index, pool = load_pool()
    sims, ids = index.search(embed([question]), k + 10)
    out = []
    for s, i in zip(sims[0], ids[0]):
        ex = pool[i]
        if ex["db_id"] == db_id or normalize(ex["question"]) == normalize(question):
            continue                                   # defence in depth: never return the test DB/question
        out.append({**ex, "similarity": round(float(s), 3)})
        if len(out) == k:
            break
    return out
