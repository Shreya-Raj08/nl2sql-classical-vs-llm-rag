"""SQL extraction from LLM output, result comparison and the significance test."""
from evaluate import mcnemar, prf, results_match, tables_in
from src.llm import extract_sql


def test_extract_sql_from_code_block():
    raw = "Here you go:\n```sql\nSELECT name\nFROM student;\n```\nHope this helps."
    assert extract_sql(raw) == "SELECT name FROM student"


def test_extract_sql_plain_text():
    assert extract_sql("SQL: SELECT count(*) FROM course; -- done") == "SELECT count(*) FROM course"


def test_results_match_unordered_and_column_order():
    assert results_match([(1, "a"), (2, "b")], [(2, "b"), (1, "a")], ordered=False)
    assert results_match([("a", 1)], [(1, "a")], ordered=False)        # different column order
    assert not results_match([(1,), (2,)], [(2,), (1,)], ordered=True)  # ORDER BY matters
    assert results_match([(3.0,)], [(3,)], ordered=False)               # 3.0 == 3


def test_tables_and_prf():
    assert tables_in("SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.ID = T2.ID") == {"student", "takes"}
    p, r, f1 = prf({"student", "department"}, {"student"})
    assert (p, r) == (0.5, 1.0) and round(f1, 3) == 0.667


def test_mcnemar():
    a = {i: 1 for i in range(20)}
    b = {i: (1 if i < 2 else 0) for i in range(20)}
    only_a, only_b, p = mcnemar(a, b)
    assert (only_a, only_b) == (18, 0) and p < 0.001
    assert mcnemar(a, a)[2] == 1.0
