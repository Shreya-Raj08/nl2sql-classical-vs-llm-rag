"""The safety guard must allow exactly one read-only SELECT and block everything else."""
import pytest

from src.safety import UnsafeQuery, check_safe


@pytest.mark.parametrize("sql", [
    "DROP TABLE student",
    "DELETE FROM student WHERE dept_name = 'Physics'",
    "UPDATE student SET name = 'x'",
    "INSERT INTO student VALUES (1, 'a', 'b', 0)",
    "PRAGMA table_info(student)",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT 1; DROP TABLE student",
    "",
])
def test_blocks_unsafe_queries(sql):
    with pytest.raises(UnsafeQuery):
        check_safe(sql)


@pytest.mark.parametrize("sql", [
    "SELECT count(*) FROM student",
    "SELECT name FROM student WHERE name = 'drop table'",          # keyword inside a string literal is fine
    "SELECT name FROM instructor WHERE ID NOT IN (SELECT ID FROM teaches)",
    "SELECT dept_name FROM student UNION SELECT dept_name FROM instructor",
    "SELECT count(*) FROM student;",                                # one trailing semicolon is allowed
])
def test_allows_select_queries(sql):
    assert check_safe(sql)
