"""The leakage check must pass on a clean pool and fail on any overlap (database, exact text or paraphrase).

Uses a tiny fake pool and fake embeddings, so it needs neither Spider nor the embedding model.
"""
import faiss
import numpy as np
import pytest

from src import rag


def _vec(i, dim=8):
    v = np.zeros(dim, dtype="float32")
    v[i % dim] = 1.0
    return v


def _install_fake_pool(monkeypatch, pool, vectors):
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    monkeypatch.setattr(rag, "load_pool", lambda: (index, pool))


def _install_fake_embed(monkeypatch, mapping):
    monkeypatch.setattr(rag, "embed", lambda texts: np.stack([mapping[t] for t in texts]))


POOL = [{"db_id": "train_db_a", "question": "How many singers are there?", "query": "SELECT count(*) FROM singer"},
        {"db_id": "train_db_b", "question": "List all ships.", "query": "SELECT name FROM ship"}]
POOL_VECS = np.stack([_vec(0), _vec(1)])


def test_clean_pool_passes(monkeypatch):
    tests = [{"db_id": "test_db", "question": "What is the average age?", "query": "..."}]
    _install_fake_pool(monkeypatch, POOL, POOL_VECS)
    _install_fake_embed(monkeypatch, {"What is the average age?": _vec(5)})
    report = rag.check_leakage(tests)
    assert report["database_overlap"] == 0 and report["exact_question_overlap"] == 0
    assert report["status"].startswith("PASSED")


def test_database_overlap_fails(monkeypatch):
    tests = [{"db_id": "train_db_a", "question": "Something else entirely?", "query": "..."}]
    _install_fake_pool(monkeypatch, POOL, POOL_VECS)
    _install_fake_embed(monkeypatch, {"Something else entirely?": _vec(6)})
    with pytest.raises(rag.LeakageError):
        rag.check_leakage(tests)


def test_exact_question_overlap_fails(monkeypatch):
    tests = [{"db_id": "test_db", "question": "how many SINGERS are there", "query": "..."}]   # same after normalising
    _install_fake_pool(monkeypatch, POOL, POOL_VECS)
    _install_fake_embed(monkeypatch, {"how many SINGERS are there": _vec(6)})
    with pytest.raises(rag.LeakageError):
        rag.check_leakage(tests)


def test_near_duplicate_paraphrase_fails(monkeypatch):
    tests = [{"db_id": "test_db", "question": "Count the singers.", "query": "..."}]
    _install_fake_pool(monkeypatch, POOL, POOL_VECS)
    _install_fake_embed(monkeypatch, {"Count the singers.": _vec(0)})                     # cosine = 1.0
    with pytest.raises(rag.LeakageError):
        rag.check_leakage(tests)


def test_normalize():
    assert rag.normalize("How many Singers are there?") == "how many singers are there"
