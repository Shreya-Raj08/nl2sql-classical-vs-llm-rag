# Error analysis: college_2_all

## Why each system's wrong answers were wrong

| system | wrong answers | sql_error | wrong_tables | value_mismatch | wrong_logic |
|---|---|---|---|---|---|
| S1: Classical NLP | 142 | 0 | 94 | 0 | 48 |
| S2: NLP + LLM | 54 | 0 | 21 | 0 | 33 |
| S3: NLP + LLM + RAG | 38 | 1 | 6 | 0 | 31 |
| Baseline: LLM + RAG | 33 | 1 | 4 | 0 | 28 |

Categories:
- **sql_error**: SQL failed to run (syntax error / unknown column / unsafe)
- **wrong_tables**: Used the wrong set of tables (schema-linking error)
- **value_mismatch**: Right structure, but a literal value is spelt/cased differently from the database
- **wrong_logic**: Right tables, wrong logic (conditions, grouping, aggregation, nesting, ordering)

## Where adding RAG hurt: S2 correct, S3 wrong (6 questions)

Failure type of S3: NLP + LLM + RAG: wrong_tables = 3, wrong_logic = 2, sql_error = 1

**Q (medium):** What is the title, credit value, and department name for courses with more than one prerequisite?
- Gold: `SELECT T1.title ,  T1.credits , T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id  =  T2.course_id GROUP BY T2.course_id HAVING count(*)  >  1`
- S2: NLP + LLM (correct): `SELECT course.title, course.credits, course.dept_name FROM course JOIN prereq ON course.course_id = prereq.course_id GROUP BY course.course_id HAVING COUNT(prereq.prereq_id) > 1`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT T1.title, T1.credits, T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.prereq_id GROUP BY T1.course_id HAVING COUNT(*) > 1`

**Q (hard):** Find the id of the courses that do not have any prerequisite?
- Gold: `SELECT course_id FROM course EXCEPT SELECT course_id FROM prereq`
- S2: NLP + LLM (correct): `SELECT course_id FROM course EXCEPT SELECT T1.course_id FROM prereq AS T1 JOIN course AS T2 ON T1.prereq_id = T2.course_id`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT course_id FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (extra):** What are the names of students who have taken the prerequisite for the course International Finance?
- Gold: `SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.id  =  T2.id WHERE T2.course_id IN (SELECT T4.prereq_id FROM course AS T3 JOIN prereq AS T4 ON T3.course_id  =  T4.course_id WHERE T3.title  =  'International Finance')`
- S2: NLP + LLM (correct): `SELECT student.name FROM student JOIN takes ON student.ID = takes.ID JOIN section ON takes.course_id = section.course_id JOIN course ON section.course_id = course.course_id JOIN prereq ON course.course_id = prereq.prereq_id WHERE course.title = 'International Finance'`
- S3: NLP + LLM + RAG (wrong, sql_error): `SELECT T4.student_id FROM takes AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id JOIN course AS T3 ON T2.course_id = T3.course_id JOIN prereq AS T4 ON T3.course_id = T4.prereq_id WHERE T3.title = 'International Finance'`

**Q (hard):** Find the building, room number, semester and year of all courses offered by Psychology department sorted by course titles.
- Gold: `SELECT T2.building ,  T2.room_number ,  T2.semester ,  T2.year FROM course AS T1 JOIN SECTION AS T2 ON T1.course_id  =  T2.course_id WHERE T1.dept_name  =  'Psychology' ORDER BY T1.title`
- S2: NLP + LLM (correct): `SELECT T2.building, T2.room_number, T2.semester, T2.year FROM course AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id JOIN department AS T3 ON T1.dept_name = T3.dept_name WHERE T3.dept_name = 'Psychology' ORDER BY T1.title ASC`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T3.building , T3.room_number , T3.semester , T3.year FROM course AS T1 JOIN teaches AS T2 ON T1.course_id = T2.course_id JOIN section AS T3 ON T2.sec_id = T3.sec_id WHERE T1.dept_name = 'Psychology' ORDER BY T1.title`

**Q (extra):** Find courses that ran in Fall 2009 or in Spring 2010.
- Gold: `SELECT course_id FROM SECTION WHERE semester  =  'Fall' AND YEAR  =  2009 UNION SELECT course_id FROM SECTION WHERE semester  =  'Spring' AND YEAR  =  2010`
- S2: NLP + LLM (correct): `SELECT course_id FROM section WHERE semester = 'Fall' AND YEAR = 2009 UNION SELECT course_id FROM section WHERE semester = 'Spring' AND YEAR = 2010`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T1.title FROM course AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id WHERE T2.semester = 'Fall' AND T2.year = 2009 OR T2.semester = 'Spring' AND T2.year = 2010`

**Q (extra):** Find courses that ran in Fall 2009 but not in Spring 2010.
- Gold: `SELECT course_id FROM SECTION WHERE semester  =  'Fall' AND YEAR  =  2009 EXCEPT SELECT course_id FROM SECTION WHERE semester  =  'Spring' AND YEAR  =  2010`
- S2: NLP + LLM (correct): `SELECT course_id FROM section WHERE semester = 'Fall' AND YEAR = 2009 EXCEPT SELECT course_id FROM section WHERE semester = 'Spring' AND YEAR = 2010`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T1.title FROM course AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id WHERE T2.semester = 'Fall' AND T2.year = 2009 AND T2.course_id NOT IN (SELECT course_id FROM section WHERE semester = 'Spring' AND year = 2010)`

## Where adding RAG helped: S3 correct, S2 wrong (22 questions)

Failure type of S2: NLP + LLM: wrong_tables = 13, wrong_logic = 9

**Q (extra):** Count the number of courses without prerequisites.
- Gold: `SELECT count(*) FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S3: NLP + LLM + RAG (correct): `SELECT count(*) FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT COUNT(*) FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (hard):** Find the name of the courses that do not have any prerequisite?
- Gold: `SELECT title FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S3: NLP + LLM + RAG (correct): `SELECT title FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT title FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (hard):** What are the titles of courses without prerequisites?
- Gold: `SELECT title FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S3: NLP + LLM + RAG (correct): `SELECT title FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT title FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (hard):** Find the names of the top 3 departments that provide the largest amount of courses?
- Gold: `SELECT dept_name FROM course GROUP BY dept_name ORDER BY count(*) DESC LIMIT 3`
- S3: NLP + LLM + RAG (correct): `SELECT T3.dept_name FROM course AS T1 JOIN department AS T3 ON T1.dept_name = T3.dept_name GROUP BY T1.dept_name ORDER BY COUNT(*) DESC LIMIT 3`
- S2: NLP + LLM (wrong, wrong_tables): `SELECT T2.dept_name, COUNT(*) as course_count FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name GROUP BY T2.dept_name ORDER BY course_count DESC LIMIT 3`

**Q (hard):** What are the names of the 3 departments with the most courses?
- Gold: `SELECT dept_name FROM course GROUP BY dept_name ORDER BY count(*) DESC LIMIT 3`
- S3: NLP + LLM + RAG (correct): `SELECT T2.dept_name FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name GROUP BY T2.dept_name ORDER BY COUNT(*) DESC LIMIT 3`
- S2: NLP + LLM (wrong, wrong_tables): `SELECT T2.dept_name, COUNT(*) AS course_count FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name GROUP BY T2.dept_name ORDER BY course_count DESC LIMIT 3`

**Q (hard):** Find the name of the department that offers the highest total credits?
- Gold: `SELECT dept_name FROM course GROUP BY dept_name ORDER BY sum(credits) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T3.dept_name FROM course AS T1 JOIN department AS T3 ON T1.dept_name = T3.dept_name GROUP BY T1.dept_name ORDER BY sum(T1.credits) DESC LIMIT 1`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT T1.dept_name, SUM(T1.credits) AS total_credits FROM course AS T1 GROUP BY T1.dept_name ORDER BY total_credits DESC LIMIT 1`

**Q (hard):** What is the name of the department with the most credits?
- Gold: `SELECT dept_name FROM course GROUP BY dept_name ORDER BY sum(credits) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T3.dept_name FROM course AS T1 JOIN department AS T3 ON T1.dept_name = T3.dept_name GROUP BY T1.dept_name ORDER BY sum(T1.credits) DESC LIMIT 1`
- S2: NLP + LLM (wrong, wrong_tables): `SELECT T1.dept_name FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name ORDER BY T1.credits DESC LIMIT 1`

**Q (easy):** Given the titles of all courses, in order of titles and credits.
- Gold: `SELECT title FROM course ORDER BY title ,  credits`
- S3: NLP + LLM + RAG (correct): `SELECT title FROM course ORDER BY title, credits`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT title, credits FROM course ORDER BY title, credits ASC`

## Where the NLP hints helped: S3 correct, LLM + RAG baseline wrong (6 questions)

Failure type of Baseline: LLM + RAG: wrong_logic = 3, wrong_tables = 2, sql_error = 1

**Q (hard):** What is the name of the student who has the highest total credits in the History department.
- Gold: `SELECT name FROM student WHERE dept_name  =  'History' ORDER BY tot_cred DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T1.name FROM student AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name WHERE T2.dept_name = 'History' ORDER BY T1.tot_cred DESC LIMIT 1`
- Baseline: LLM + RAG (wrong, wrong_tables): `SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.id = T2.id WHERE T1.dept_name = 'History' GROUP BY T1.id ORDER BY sum(T1.tot_cred) DESC LIMIT 1`

**Q (hard):** Find the title of course that is provided by Statistics but not Psychology departments.
- Gold: `SELECT title FROM course WHERE dept_name  =  'Statistics' EXCEPT SELECT title FROM course WHERE dept_name  =  'Psychology'`
- S3: NLP + LLM + RAG (correct): `SELECT T1.title FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name WHERE T2.dept_name = 'Statistics' EXCEPT SELECT T1.title FROM course AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name WHERE T2.dept_name = 'Psychology'`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT title FROM course WHERE dept_name = 'Statistics' AND course_id NOT IN (SELECT course_id FROM course WHERE dept_name = 'Psychology')`

**Q (hard):** What are the titles of courses that are in the Statistics department but not the Psychology department?
- Gold: `SELECT title FROM course WHERE dept_name  =  'Statistics' EXCEPT SELECT title FROM course WHERE dept_name  =  'Psychology'`
- S3: NLP + LLM + RAG (correct): `SELECT title FROM course WHERE dept_name = 'Statistics' EXCEPT SELECT title FROM course WHERE dept_name = 'Psychology'`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT title FROM course WHERE dept_name = 'Statistics' AND course_id NOT IN (SELECT course_id FROM course WHERE dept_name = 'Psychology')`

**Q (extra):** Find the minimum salary for the departments whose average salary is above the average payment of all instructors.
- Gold: `SELECT min(salary) ,  dept_name FROM instructor GROUP BY dept_name HAVING avg(salary)  >  (SELECT avg(salary) FROM instructor)`
- S3: NLP + LLM + RAG (correct): `SELECT MIN(salary), dept_name FROM instructor GROUP BY dept_name HAVING AVG(salary) > (SELECT AVG(salary) FROM instructor)`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT MIN(salary) FROM instructor WHERE dept_name IN (SELECT dept_name FROM instructor GROUP BY dept_name HAVING AVG(salary) > (SELECT AVG(salary) FROM instructor))`

**Q (hard):** What is the name of the deparment with the highest enrollment?
- Gold: `SELECT dept_name FROM student GROUP BY dept_name ORDER BY count(*) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T2.dept_name FROM student AS T1 JOIN department AS T2 ON T1.dept_name = T2.dept_name GROUP BY T2.dept_name ORDER BY COUNT(*) DESC LIMIT 1`
- Baseline: LLM + RAG (wrong, wrong_tables): `SELECT T4.dept_name FROM SECTION AS T1 JOIN takes AS T2 ON T1.course_id = T2.course_id JOIN course AS T3 ON T1.course_id = T3.course_id JOIN department AS T4 ON T3.dept_name = T4.dept_name GROUP BY T3.dept_name ORDER BY count(*) DESC LIMIT 1`

**Q (extra):** Find the name of instructor who is the advisor of the student who has the highest number of total credits.
- Gold: `SELECT T2.name FROM advisor AS T1 JOIN instructor AS T2 ON T1.i_id  =  T2.id JOIN student AS T3 ON T1.s_id  =  T3.id ORDER BY T3.tot_cred DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T3.name FROM advisor AS T1 JOIN student AS T2 ON T1.s_ID = T2.ID JOIN instructor AS T3 ON T1.i_ID = T3.ID ORDER BY T2.tot_cred DESC LIMIT 1`
- Baseline: LLM + RAG (wrong, sql_error): `SELECT T4.name FROM student AS T1 JOIN advisor AS T2 ON T1.id = T2.s_id JOIN instructor AS T3 ON T2.i_id = T3.id JOIN instructor AS T4 ON T1.advisor = T4.id ORDER BY T1.tot_cred DESC LIMIT 1`

## Where the NLP hints hurt: baseline correct, S3 wrong (11 questions)

Failure type of S3: NLP + LLM + RAG: wrong_logic = 5, wrong_tables = 5, sql_error = 1

**Q (medium):** Find the title, credit, and department name of courses that have more than one prerequisites?
- Gold: `SELECT T1.title ,  T1.credits , T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id  =  T2.course_id GROUP BY T2.course_id HAVING count(*)  >  1`
- Baseline: LLM + RAG (correct): `SELECT T1.title, T1.credits, T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.course_id GROUP BY T1.course_id HAVING COUNT(*) > 1`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT T1.title, T1.credits, T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.prereq_id GROUP BY T1.course_id HAVING COUNT(*) > 1`

**Q (medium):** What is the title, credit value, and department name for courses with more than one prerequisite?
- Gold: `SELECT T1.title ,  T1.credits , T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id  =  T2.course_id GROUP BY T2.course_id HAVING count(*)  >  1`
- Baseline: LLM + RAG (correct): `SELECT T1.title , T1.credits , T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.course_id GROUP BY T1.course_id HAVING count(*) > 1`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT T1.title, T1.credits, T1.dept_name FROM course AS T1 JOIN prereq AS T2 ON T1.course_id = T2.prereq_id GROUP BY T1.course_id HAVING COUNT(*) > 1`

**Q (extra):** How many courses that do not have prerequisite?
- Gold: `SELECT count(*) FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- Baseline: LLM + RAG (correct): `SELECT count(*) FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT COUNT(*) FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (easy):** List the names of all courses ordered by their titles and credits.
- Gold: `SELECT title FROM course ORDER BY title ,  credits`
- Baseline: LLM + RAG (correct): `SELECT title FROM course ORDER BY title, credits`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT T1.title, T1.credits FROM course AS T1 ORDER BY T1.title, T1.credits`

**Q (hard):** Find the id of the courses that do not have any prerequisite?
- Gold: `SELECT course_id FROM course EXCEPT SELECT course_id FROM prereq`
- Baseline: LLM + RAG (correct): `SELECT course_id FROM course WHERE course_id NOT IN (SELECT course_id FROM prereq)`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT course_id FROM course WHERE course_id NOT IN (SELECT prereq_id FROM prereq)`

**Q (medium):** What is the title of the course that was offered at building Chandler during the fall semester in the year of 2010?
- Gold: `SELECT T1.title FROM course AS T1 JOIN SECTION AS T2 ON T1.course_id  =  T2.course_id WHERE building  =  'Chandler' AND semester  =  'Fall' AND YEAR  =  2010`
- Baseline: LLM + RAG (correct): `SELECT T1.title FROM course AS T1 JOIN SECTION AS T2 ON T1.course_id = T2.course_id WHERE T2.building = 'Chandler' AND T2.semester = 'Fall' AND T2.year = 2010`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T1.title FROM course AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id JOIN classroom AS T3 ON T2.building = T3.building WHERE T3.building = 'Chandler' AND T2.semester = 'Fall' AND T2.year = 2010`

**Q (medium):** Give the title of the course offered in Chandler during the Fall of 2010.
- Gold: `SELECT T1.title FROM course AS T1 JOIN SECTION AS T2 ON T1.course_id  =  T2.course_id WHERE building  =  'Chandler' AND semester  =  'Fall' AND YEAR  =  2010`
- Baseline: LLM + RAG (correct): `SELECT T1.title FROM course AS T1 JOIN SECTION AS T2 ON T1.course_id = T2.course_id WHERE T2.building = 'Chandler' AND T2.semester = 'Fall' AND T2.year = 2010`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T1.title FROM course AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id JOIN classroom AS T3 ON T2.building = T3.building WHERE T3.building = 'Chandler' AND T2.semester = 'Fall' AND T2.year = 2010`

**Q (extra):** What are the names of students who have taken the prerequisite for the course International Finance?
- Gold: `SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.id  =  T2.id WHERE T2.course_id IN (SELECT T4.prereq_id FROM course AS T3 JOIN prereq AS T4 ON T3.course_id  =  T4.course_id WHERE T3.title  =  'International Finance')`
- Baseline: LLM + RAG (correct): `SELECT T1.name FROM student AS T1 JOIN takes AS T2 ON T1.id = T2.id WHERE T2.course_id IN ( SELECT T4.prereq_id FROM course AS T3 JOIN prereq AS T4 ON T3.course_id = T4.course_id WHERE T3.title = 'International Finance' )`
- S3: NLP + LLM + RAG (wrong, sql_error): `SELECT T4.student_id FROM takes AS T1 JOIN section AS T2 ON T1.course_id = T2.course_id JOIN course AS T3 ON T2.course_id = T3.course_id JOIN prereq AS T4 ON T3.course_id = T4.prereq_id WHERE T3.title = 'International Finance'`

## What the LLM fixes: S2 correct, classical S1 wrong (88 questions)

Failure type of S1: Classical NLP: wrong_tables = 60, wrong_logic = 28

**Q (easy):** Find the buildings which have rooms with capacity more than 50.
- Gold: `SELECT DISTINCT building FROM classroom WHERE capacity  >  50`
- S2: NLP + LLM (correct): `SELECT DISTINCT building FROM classroom WHERE capacity > 50`
- S1: Classical NLP (wrong, wrong_logic): `SELECT building FROM classroom WHERE capacity > 50`

**Q (easy):** Count the number of rooms that are not in the Lamberton building.
- Gold: `SELECT count(*) FROM classroom WHERE building != 'Lamberton'`
- S2: NLP + LLM (correct): `SELECT COUNT(*) FROM classroom WHERE building != 'Lamberton'`
- S1: Classical NLP (wrong, wrong_logic): `SELECT COUNT(*) FROM classroom WHERE building = 'Lamberton'`

**Q (easy):** How many classrooms are not in Lamberton?
- Gold: `SELECT count(*) FROM classroom WHERE building != 'Lamberton'`
- S2: NLP + LLM (correct): `SELECT COUNT(*) FROM classroom WHERE building != 'Lamberton'`
- S1: Classical NLP (wrong, wrong_logic): `SELECT COUNT(*) FROM classroom WHERE building = 'Lamberton'`

**Q (extra):** What is the name and building of the departments whose budget is more than the average budget?
- Gold: `SELECT dept_name ,  building FROM department WHERE budget  >  (SELECT avg(budget) FROM department)`
- S2: NLP + LLM (correct): `SELECT dept_name, building FROM department WHERE budget > (SELECT AVG(budget) FROM department)`
- S1: Classical NLP (wrong, wrong_logic): `SELECT AVG(budget) FROM department`

**Q (extra):** Give the name and building of the departments with greater than average budget.
- Gold: `SELECT dept_name ,  building FROM department WHERE budget  >  (SELECT avg(budget) FROM department)`
- S2: NLP + LLM (correct): `SELECT dept_name, building FROM department WHERE budget > (SELECT AVG(budget) FROM department)`
- S1: Classical NLP (wrong, wrong_logic): `SELECT AVG(budget) FROM department`