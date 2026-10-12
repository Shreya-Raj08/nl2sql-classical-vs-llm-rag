"""Classical NLP front-end: intent rules (needs only spaCy) and System 1 end-to-end (needs Spider)."""
from conftest import needs_spider
from src import classical, nlp_frontend as F, safety


def intent(q):
    return F.detect_intent(F.preprocess(q))


def test_intent_cues():
    assert intent("How many students are there?")["aggregate"] == "COUNT"
    assert intent("What is the average salary?")["aggregate"] == "AVG"
    cmp = intent("Find students with more than 100 credits.")["comparisons"]
    assert cmp and cmp[0]["op"] == ">" and cmp[0]["value"] == 100
    assert intent("Instructors earning greater than 90000")["comparisons"][0]["op"] == ">"   # "greater" lemma = "great"
    assert intent("Which department has the highest budget?")["superlative"]["dir"] == "DESC"
    assert intent("Average salary in each department")["group_by"]
    assert intent("Students who have not taken a course")["negation"]


def test_norm_value():
    assert F.norm_value("Comp. Sci.") == "comp sci"


@needs_spider
def test_value_and_synonym_matching():
    a = F.analyze("How many students are in the Comp. Sci. department?", "college_2")
    values = [m for m in a["matches"] if m.kind == "value"]
    assert values and values[0].value == "Comp. Sci."
    a = F.analyze("What is the salary of each teacher?", "college_2")
    assert any(m.kind == "table" and m.table == "instructor" and m.how == "synonym" for m in a["matches"])


@needs_spider
def test_system1_end_to_end():
    a = F.analyze("What are the names of instructors with a salary greater than 90000?", "college_2")
    sql = classical.generate(a)
    assert sql == "SELECT name FROM instructor WHERE salary > 90000"
    cols, rows = safety.execute("college_2", sql)
    gold = safety.execute("college_2", "SELECT name FROM instructor WHERE salary > 90000")[1]
    assert sorted(rows) == sorted(gold)
