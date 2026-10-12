# Error analysis: dev

## Why each system's wrong answers were wrong

| system | wrong answers | sql_error | wrong_tables | value_mismatch | wrong_logic |
|---|---|---|---|---|---|
| S1: Classical NLP | 142 | 0 | 52 | 0 | 90 |
| S2: NLP + LLM | 51 | 1 | 18 | 2 | 30 |
| S3: NLP + LLM + RAG | 55 | 5 | 14 | 7 | 29 |
| Baseline: LLM + RAG | 63 | 8 | 11 | 6 | 38 |

Categories:
- **sql_error**: SQL failed to run (syntax error / unknown column / unsafe)
- **wrong_tables**: Used the wrong set of tables (schema-linking error)
- **value_mismatch**: Right structure, but a literal value is spelt/cased differently from the database
- **wrong_logic**: Right tables, wrong logic (conditions, grouping, aggregation, nesting, ordering)

## Where adding RAG hurt: S2 correct, S3 wrong (17 questions)

Failure type of S3: NLP + LLM + RAG: wrong_logic = 6, value_mismatch = 5, wrong_tables = 4, sql_error = 2

**Q (medium):** what is the name and nation of the singer who have a song having 'Hey' in its name?
- Gold: `SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'`
- S2: NLP + LLM (correct): `SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'`
- S3: NLP + LLM + RAG (wrong, sql_error): `SELECT T1.Name, T1.Country FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.Singer_ID = T2.Singer_ID JOIN concert AS T3 ON T2.concert_ID = T3.concert_ID WHERE T3.Song_Name LIKE '%Hey%'`

**Q (medium):** What is the name and country of origin of every singer who has a song with the word 'Hey' in its title?
- Gold: `SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'`
- S2: NLP + LLM (correct): `SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT T1.Name, T1.Country FROM singer AS T1 JOIN singer_in_concert AS T2 ON T1.Singer_ID = T2.Singer_ID JOIN concert AS T3 ON T2.concert_ID = T3.concert_ID JOIN singer_in_concert AS T4 ON T3.concert_ID = T4.concert_ID JOIN singer AS T5 ON T4.Singer_ID = T5.Singer_ID WHERE T1.Song_Name LIKE '%Hey%'`

**Q (extra):** Find the first name of students who have cat or dog pet.
- Gold: `SELECT DISTINCT T1.Fname FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat' OR T3.pettype  =  'dog'`
- S2: NLP + LLM (correct): `SELECT DISTINCT Student.Fname FROM Student JOIN Has_Pet ON Student.StuID = Has_Pet.StuID JOIN Pets ON Has_Pet.PetID = Pets.PetID WHERE Pets.PetType IN ('cat', 'dog')`
- S3: NLP + LLM + RAG (wrong, value_mismatch): `SELECT DISTINCT T1.fname FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'Cat' OR T3.PetType = 'Dog'`

**Q (extra):** Find the major and age of students who do not have a cat pet.
- Gold: `SELECT major ,  age FROM student WHERE stuid NOT IN (SELECT T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat')`
- S2: NLP + LLM (correct): `SELECT Major, Age FROM Student WHERE StuID NOT IN (SELECT StuID FROM Has_Pet JOIN Pets ON Has_Pet.PetID = Pets.PetID WHERE PetType = 'cat')`
- S3: NLP + LLM + RAG (wrong, value_mismatch): `SELECT Major, Age FROM Student WHERE StuID NOT IN (SELECT StuID FROM Has_Pet WHERE PetID IN (SELECT PetID FROM Pets WHERE PetType = 'Cat'))`

**Q (hard):** What are the ids of the students who do not own cats as pets?
- Gold: `SELECT stuid FROM student EXCEPT SELECT T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat'`
- S2: NLP + LLM (correct): `SELECT StuID FROM Student EXCEPT SELECT StuID FROM Has_Pet JOIN Pets ON Has_Pet.PetID = Pets.PetID WHERE Pets.PetType = 'cat'`
- S3: NLP + LLM + RAG (wrong, value_mismatch): `SELECT StuID FROM Student EXCEPT SELECT StuID FROM Has_Pet WHERE PetID IN (SELECT PetID FROM Pets WHERE PetType = 'Cat')`

**Q (extra):** Find the first name and age of students who have a dog but do not have a cat as a pet.
- Gold: `SELECT T1.fname ,  T1.age FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'dog' AND T1.stuid NOT IN (SELECT T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pettype  =  'cat')`
- S2: NLP + LLM (correct): `SELECT T1.Fname, T1.Age FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'dog' AND T1.StuID NOT IN (SELECT T1.StuID FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'cat')`
- S3: NLP + LLM + RAG (wrong, value_mismatch): `SELECT fname, age FROM Student WHERE StuID IN (SELECT StuID FROM Has_Pet WHERE PetID IN (SELECT PetID FROM Pets WHERE PetType = 'Dog')) EXCEPT SELECT fname, age FROM Student WHERE StuID IN (SELECT StuID FROM Has_Pet WHERE PetID IN (SELECT PetID FROM Pets WHERE PetType = 'Cat'))`

**Q (hard):** What is the last name of the student who has a cat that is 3 years old?
- Gold: `SELECT T1.lname FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T3.petid  =  T2.petid WHERE T3.pet_age  =  3 AND T3.pettype  =  'cat'`
- S2: NLP + LLM (correct): `SELECT T1.LName FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'cat' AND T3.pet_age = 3`
- S3: NLP + LLM + RAG (wrong, value_mismatch): `SELECT T1.lname FROM Student AS T1 JOIN Has_Pet AS T2 ON T1.StuID = T2.StuID JOIN Pets AS T3 ON T2.PetID = T3.PetID WHERE T3.PetType = 'Cat' AND T3.pet_age = 3`

**Q (hard):** What is the car model with the highest mpg ?
- Gold: `select t1.model from car_names as t1 join cars_data as t2 on t1.makeid  =  t2.id order by t2.mpg desc limit 1;`
- S2: NLP + LLM (correct): `SELECT T1.Model FROM model_list AS T1 INNER JOIN car_names AS T2 ON T1.Model = T2.Model INNER JOIN cars_data AS T3 ON T2.MakeId = T3.Id ORDER BY T3.MPG DESC LIMIT 1`
- S3: NLP + LLM + RAG (wrong, sql_error): `SELECT T1.Model FROM model_list AS T1 JOIN car_names AS T2 ON T1.ModelId = T2.MakeId ORDER BY T2.MPG DESC LIMIT 1`

## Where adding RAG helped: S3 correct, S2 wrong (13 questions)

Failure type of S2: NLP + LLM: wrong_logic = 8, wrong_tables = 5

**Q (hard):** How many dog pets are raised by female students?
- Gold: `SELECT count(*) FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid JOIN pets AS T3 ON T2.petid  =  T3.petid WHERE T1.sex  =  'F' AND T3.pettype  =  'dog'`
- S3: NLP + LLM + RAG (correct): `SELECT COUNT(*) FROM Pets AS T1 JOIN Has_Pet AS T2 ON T1.PetID = T2.PetID JOIN Student AS T3 ON T2.StuID = T3.StuID WHERE T1.PetType = 'dog' AND T3.Sex = 'F'`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT COUNT(*) FROM Pets AS T1 JOIN Has_Pet AS T2 ON T1.PetID = T2.PetID JOIN Student AS T3 ON T2.StuID = T3.StuID WHERE T1.PetType = 'dog' AND T3.Sex = 'female'`

**Q (medium):** What is the number of car models that are produced by each maker and what is the id and full name of each maker?
- Gold: `SELECT Count(*) ,  T2.FullName ,  T2.id FROM MODEL_LIST AS T1 JOIN CAR_MAKERS AS T2 ON T1.Maker  =  T2.Id GROUP BY T2.id;`
- S3: NLP + LLM + RAG (correct): `SELECT COUNT(model_list.Model), car_makers.Id, car_makers.FullName FROM model_list JOIN car_makers ON model_list.Maker = car_makers.Id GROUP BY car_makers.Id, car_makers.FullName`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT car_makers.Maker, car_makers.FullName, COUNT(model_list.Model) AS NumberOfModels FROM model_list JOIN car_makers ON model_list.Maker = car_makers.Id GROUP BY car_makers.Maker, car_makers.FullName`

**Q (extra):** What is the airport code of the airport with the most flights?
- Gold: `SELECT T1.AirportCode FROM AIRPORTS AS T1 JOIN FLIGHTS AS T2 ON T1.AirportCode  =  T2.DestAirport OR T1.AirportCode  =  T2.SourceAirport GROUP BY T1.AirportCode ORDER BY count(*) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T2.AirportCode FROM flights AS T1 JOIN airports AS T2 ON T1.DestAirport = T2.AirportCode GROUP BY T2.AirportCode ORDER BY COUNT(*) DESC LIMIT 1`
- S2: NLP + LLM (wrong, wrong_tables): `SELECT DestAirport FROM flights GROUP BY DestAirport ORDER BY COUNT(*) DESC LIMIT 1`

**Q (medium):** Find all airlines that have at least 10 flights.
- Gold: `SELECT T1.Airline FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline HAVING count(*)  >  10`
- S3: NLP + LLM + RAG (correct): `SELECT T1.Airline FROM airlines AS T1 JOIN flights AS T2 ON T1.uid = T2.Airline GROUP BY T2.Airline HAVING COUNT(*) >= 10`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT T1.Airline, T1.Abbreviation FROM airlines AS T1 JOIN flights AS T2 ON T1.uid = T2.Airline GROUP BY T1.Airline HAVING COUNT(T2.FlightNo) >= 10`

**Q (easy):** What are flight numbers of flights arriving at Airport "APG"?
- Gold: `SELECT FlightNo FROM FLIGHTS WHERE DestAirport  =  "APG"`
- S3: NLP + LLM + RAG (correct): `SELECT FlightNo FROM flights WHERE DestAirport = 'APG'`
- S2: NLP + LLM (wrong, wrong_tables): `SELECT COUNT(flights.FlightNo) FROM flights JOIN airports ON flights.DestAirport = airports.AirportCode WHERE airports.AirportCode = 'APG'`

**Q (medium):** Give the flight numbers of flights arriving in Aberdeen.
- Gold: `SELECT T1.FlightNo FROM FLIGHTS AS T1 JOIN AIRPORTS AS T2 ON T1.DestAirport   =  T2.AirportCode WHERE T2.City  =  "Aberdeen"`
- S3: NLP + LLM + RAG (correct): `SELECT T1.FlightNo FROM flights AS T1 JOIN airports AS T2 ON T1.DestAirport = T2.AirportCode WHERE T2.City = 'Aberdeen'`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT COUNT(flights.FlightNo) FROM flights JOIN airports ON flights.DestAirport = airports.AirportCode WHERE airports.City = 'Aberdeen'`

**Q (extra):** What is the document id and name with greatest number of paragraphs?
- Gold: `SELECT T1.document_id ,  T2.document_name FROM Paragraphs AS T1 JOIN Documents AS T2 ON T1.document_id  =  T2.document_id GROUP BY T1.document_id ORDER BY count(*) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT p.Document_ID, d.Document_Name FROM Paragraphs p JOIN Documents d ON p.Document_ID = d.Document_ID GROUP BY p.Document_ID, d.Document_Name ORDER BY COUNT(*) DESC LIMIT 1`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT p.Document_ID, d.Document_Name, COUNT(p.Paragraph_ID) AS Paragraph_Count FROM Paragraphs p JOIN Documents d ON p.Document_ID = d.Document_ID GROUP BY p.Document_ID, d.Document_Name ORDER BY Paragraph_Count DESC LIMIT 1`

**Q (extra):** What is the name of the course with the most students enrolled?
- Gold: `SELECT  T1.course_name FROM Courses AS T1 JOIN Student_Enrolment_Courses AS T2 ON T1.course_id  =  T2.course_id GROUP BY T1.course_name ORDER BY count(*) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T1.course_name FROM Courses AS T1 JOIN Student_Enrolment_Courses AS T2 ON T1.course_id = T2.course_id GROUP BY T1.course_name ORDER BY COUNT(*) DESC LIMIT 1`
- S2: NLP + LLM (wrong, wrong_logic): `SELECT c.course_name FROM Courses c JOIN Student_Enrolment_Courses sec ON c.course_id = sec.course_id GROUP BY c.course_id ORDER BY COUNT(sec.student_course_id) DESC LIMIT 1`

## Where the NLP hints helped: S3 correct, LLM + RAG baseline wrong (14 questions)

Failure type of Baseline: LLM + RAG: wrong_logic = 7, sql_error = 4, wrong_tables = 3

**Q (hard):** What are the number of concerts that occurred in the stadium with the largest capacity ?
- Gold: `select count(*) from concert where stadium_id = (select stadium_id from stadium order by capacity desc limit 1)`
- S3: NLP + LLM + RAG (correct): `SELECT COUNT(*) FROM concert JOIN stadium ON concert.Stadium_ID = stadium.Stadium_ID WHERE stadium.Capacity = (SELECT MAX(Capacity) FROM stadium)`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT count(*) FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id = T2.stadium_id ORDER BY T2.capacity DESC LIMIT 1`

**Q (hard):** How many car makers are there in each continents? List the continent name and the count.
- Gold: `SELECT T1.Continent ,  count(*) FROM CONTINENTS AS T1 JOIN COUNTRIES AS T2 ON T1.ContId  =  T2.continent JOIN car_makers AS T3 ON T2.CountryId  =  T3.Country GROUP BY T1.Continent;`
- S3: NLP + LLM + RAG (correct): `SELECT c.Continent, COUNT(cm.Id) AS CarMakerCount FROM car_makers cm JOIN countries co ON cm.Country = co.CountryId JOIN continents c ON co.Continent = c.ContId GROUP BY c.Continent`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT T2.Continent, COUNT(T1.Id) FROM car_makers AS T1 JOIN countries AS T2 ON T1.Country = T2.CountryId JOIN continents AS T3 ON T2.Continent = T3.ContId GROUP BY T3.Continent`

**Q (medium):** What is the number of car models that are produced by each maker and what is the id and full name of each maker?
- Gold: `SELECT Count(*) ,  T2.FullName ,  T2.id FROM MODEL_LIST AS T1 JOIN CAR_MAKERS AS T2 ON T1.Maker  =  T2.Id GROUP BY T2.id;`
- S3: NLP + LLM + RAG (correct): `SELECT COUNT(model_list.Model), car_makers.Id, car_makers.FullName FROM model_list JOIN car_makers ON model_list.Maker = car_makers.Id GROUP BY car_makers.Id, car_makers.FullName`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT T1.Maker, T1.Id, T1.FullName, COUNT(T2.Model) AS ModelCount FROM car_makers AS T1 LEFT JOIN model_list AS T2 ON T1.Id = T2.Maker GROUP BY T1.Maker, T1.Id, T1.FullName`

**Q (extra):** What are the different models created by either the car maker General Motors or weighed more than 3500?
- Gold: `SELECT DISTINCT T2.Model FROM CAR_NAMES AS T1 JOIN MODEL_LIST AS T2 ON T1.Model  =  T2.Model JOIN CAR_MAKERS AS T3 ON T2.Maker  =  T3.Id JOIN CARS_DATA AS T4 ON T1.MakeId  =  T4.Id WHERE T3.FullName  =  'General Motors' OR T4.weight  >  3500;`
- S3: NLP + LLM + RAG (correct): `SELECT DISTINCT T3.Model FROM car_makers AS T1 JOIN model_list AS T2 ON T1.Id = T2.Maker JOIN car_names AS T3 ON T2.Model = T3.Model JOIN cars_data AS T4 ON T3.MakeId = T4.Id WHERE T1.FullName = 'General Motors' OR T4.Weight > 3500`
- Baseline: LLM + RAG (wrong, wrong_tables): `SELECT DISTINCT T1.Model FROM model_list AS T1 INNER JOIN car_names AS T2 ON T1.ModelId = T2.Model WHERE T2.Make = 'General Motors' OR T2.MakeId > 3500`

**Q (extra):** What is the airport code of the airport with the most flights?
- Gold: `SELECT T1.AirportCode FROM AIRPORTS AS T1 JOIN FLIGHTS AS T2 ON T1.AirportCode  =  T2.DestAirport OR T1.AirportCode  =  T2.SourceAirport GROUP BY T1.AirportCode ORDER BY count(*) DESC LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T2.AirportCode FROM flights AS T1 JOIN airports AS T2 ON T1.DestAirport = T2.AirportCode GROUP BY T2.AirportCode ORDER BY COUNT(*) DESC LIMIT 1`
- Baseline: LLM + RAG (wrong, wrong_tables): `SELECT DestAirport FROM flights GROUP BY DestAirport ORDER BY COUNT(*) DESC LIMIT 1`

**Q (extra):** Find the abbreviation and country of the airline that has fewest number of flights?
- Gold: `SELECT T1.Abbreviation ,  T1.Country FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline ORDER BY count(*) LIMIT 1`
- S3: NLP + LLM + RAG (correct): `SELECT T1.Abbreviation, T1.Country FROM airlines AS T1 JOIN flights AS T2 ON T1.uid = T2.Airline GROUP BY T1.Airline ORDER BY COUNT(*) ASC LIMIT 1`
- Baseline: LLM + RAG (wrong, wrong_logic): `SELECT T1.Abbreviation, T1.Country FROM airlines AS T1 JOIN flights AS T2 ON T1.uid = T2.Airline GROUP BY T1.uid ORDER BY count(*) LIMIT 1`

**Q (medium):** What are the distinct template type descriptions for the templates ever used by any document?
- Gold: `SELECT DISTINCT T1.template_type_description FROM Ref_template_types AS T1 JOIN Templates AS T2 ON T1.template_type_code  = T2.template_type_code JOIN Documents AS T3 ON T2.Template_ID  =  T3.template_ID`
- S3: NLP + LLM + RAG (correct): `SELECT DISTINCT T3.Template_Type_Description FROM Documents AS T1 INNER JOIN Templates AS T2 ON T1.Template_ID = T2.Template_ID INNER JOIN Ref_Template_Types AS T3 ON T2.Template_Type_Code = T3.Template_Type_Code`
- Baseline: LLM + RAG (wrong, sql_error): `SELECT DISTINCT T2.Template_Type_Description FROM Documents AS T1 INNER JOIN Templates AS T2 ON T1.Template_ID = T2.Template_ID`

**Q (hard):** Show the name of the teacher for the math course.
- Gold: `SELECT T3.Name FROM course_arrange AS T1 JOIN course AS T2 ON T1.Course_ID  =  T2.Course_ID JOIN teacher AS T3 ON T1.Teacher_ID  =  T3.Teacher_ID WHERE T2.Course  =  "Math"`
- S3: NLP + LLM + RAG (correct): `SELECT T2.Name FROM course_arrange AS T1 JOIN teacher AS T2 ON T1.Teacher_ID = T2.Teacher_ID JOIN course AS T3 ON T1.Course_ID = T3.Course_ID WHERE T3.Course = 'Math'`
- Baseline: LLM + RAG (wrong, sql_error): `SELECT T2.Name FROM course AS T1 JOIN course_arrange AS T2 ON T1.Course_ID = T2.Course_ID WHERE T1.Course = 'math'`

## Where the NLP hints hurt: baseline correct, S3 wrong (6 questions)

Failure type of S3: NLP + LLM + RAG: wrong_logic = 4, wrong_tables = 1, sql_error = 1

**Q (medium):** What is the average and maximum age for each pet type?
- Gold: `SELECT avg(pet_age) ,  max(pet_age) ,  pettype FROM pets GROUP BY pettype`
- Baseline: LLM + RAG (correct): `SELECT avg(Pet_age) , max(Pet_age) , PetType FROM Pets GROUP BY PetType`
- S3: NLP + LLM + RAG (wrong, wrong_tables): `SELECT AVG(Student.Age), MAX(Student.Age), Pets.PetType FROM Student JOIN Has_Pet ON Student.StuID = Has_Pet.StuID JOIN Pets ON Has_Pet.PetID = Pets.PetID GROUP BY Pets.PetType`

**Q (medium):** Find the name and membership level of the visitors whose membership level is higher than 4, and sort by their age from old to young.
- Gold: `SELECT name ,  Level_of_membership FROM visitor WHERE Level_of_membership  >  4 ORDER BY age DESC`
- Baseline: LLM + RAG (correct): `SELECT Name, Level_of_membership FROM visitor WHERE Level_of_membership > 4 ORDER BY Age DESC`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT Name, Level_of_membership FROM visitor WHERE Level_of_membership > 4 ORDER BY Age ASC`

**Q (medium):** Give the name, population, and head of state for the country that has the largest area.
- Gold: `SELECT Name ,  population ,  HeadOfState FROM country ORDER BY SurfaceArea DESC LIMIT 1`
- Baseline: LLM + RAG (correct): `SELECT T1.Name, T1.Population, T1.HeadOfState FROM country AS T1 ORDER BY T1.SurfaceArea DESC LIMIT 1`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT Name, Population, HeadOfState FROM country ORDER BY Region DESC LIMIT 1`

**Q (medium):** What are the names and areas of countries with the top 5 largest area?
- Gold: `SELECT Name ,  SurfaceArea FROM country ORDER BY SurfaceArea DESC LIMIT 5`
- Baseline: LLM + RAG (correct): `SELECT Name , SurfaceArea FROM country ORDER BY SurfaceArea DESC LIMIT 5`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT Name, Region FROM country ORDER BY Region DESC LIMIT 5`

**Q (hard):** What is the average grade of students who have friends?
- Gold: `SELECT avg(grade) FROM Highschooler WHERE id IN (SELECT T1.student_id FROM Friend AS T1 JOIN Highschooler AS T2 ON T1.student_id  =  T2.id)`
- Baseline: LLM + RAG (correct): `SELECT AVG(grade) FROM Highschooler WHERE ID IN (SELECT student_id FROM Friend)`
- S3: NLP + LLM + RAG (wrong, wrong_logic): `SELECT AVG(T1.grade) FROM Highschooler AS T1 JOIN Friend AS T2 ON T1.ID = T2.student_id`

**Q (extra):** Which owner has paid the largest amount of money in total for their dogs? Show the owner id and zip code.
- Gold: `SELECT T1.owner_id ,  T1.zip_code FROM Owners AS T1 JOIN Dogs AS T2 ON T1.owner_id  =  T2.owner_id JOIN Treatments AS T3 ON T2.dog_id  =  T3.dog_id GROUP BY T1.owner_id ORDER BY sum(T3.cost_of_treatment) DESC LIMIT 1`
- Baseline: LLM + RAG (correct): `SELECT T1.owner_id, T1.zip_code FROM Owners AS T1 JOIN Dogs AS T2 ON T1.owner_id = T2.owner_id JOIN Treatments AS T3 ON T2.dog_id = T3.dog_id GROUP BY T1.owner_id, T1.zip_code ORDER BY SUM(T3.cost_of_treatment) DESC LIMIT 1`
- S3: NLP + LLM + RAG (wrong, sql_error): `SELECT O.owner_id, O.zip_code, SUM(C.charge_amount) AS total_amount FROM Owners O JOIN Dogs D ON O.owner_id = D.owner_id JOIN Treatments T ON D.dog_id = T.dog_id JOIN Charges C ON T.charge_id = C.charge_id GROUP BY O.owner_id, O.zip_code ORDER BY total_amount DESC LIMIT 1`

## What the LLM fixes: S2 correct, classical S1 wrong (97 questions)

Failure type of S1: Classical NLP: wrong_logic = 68, wrong_tables = 29

**Q (extra):** Show the stadium name and capacity with most number of concerts in year 2014 or after.
- Gold: `SELECT T2.name ,  T2.capacity FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  >=  2014 GROUP BY T2.stadium_id ORDER BY count(*) DESC LIMIT 1`
- S2: NLP + LLM (correct): `SELECT s.Name, s.Capacity FROM stadium s JOIN concert c ON s.Stadium_ID = c.Stadium_ID JOIN singer_in_concert sic ON c.concert_ID = sic.concert_ID WHERE c.Year >= '2014' GROUP BY s.Stadium_ID ORDER BY COUNT(c.concert_ID) DESC LIMIT 1`
- S1: Classical NLP (wrong, wrong_tables): `SELECT COUNT(*) FROM stadium JOIN concert ON concert.Stadium_ID = stadium.Stadium_ID JOIN singer_in_concert ON singer_in_concert.concert_ID = concert.concert_ID JOIN singer ON singer_in_concert.Singer_ID = singer.Singer_ID WHERE singer.Song_release_year = '2014'`

**Q (hard):** What are the names of all stadiums that did not have a concert in 2014?
- Gold: `SELECT name FROM stadium EXCEPT SELECT T2.name FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.year  =  2014`
- S2: NLP + LLM (correct): `SELECT Name FROM stadium WHERE Stadium_ID NOT IN (SELECT T1.Stadium_ID FROM concert AS T1 JOIN singer_in_concert AS T2 ON T1.concert_ID = T2.concert_ID WHERE T1.Year = '2014')`
- S1: Classical NLP (wrong, wrong_tables): `SELECT stadium.Name FROM stadium JOIN concert ON concert.Stadium_ID = stadium.Stadium_ID JOIN singer_in_concert ON singer_in_concert.concert_ID = concert.concert_ID JOIN singer ON singer_in_concert.Singer_ID = singer.Singer_ID WHERE singer.Song_release_year = '2014'`

**Q (medium):** what is the name and nation of the singer who have a song having 'Hey' in its name?
- Gold: `SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'`
- S2: NLP + LLM (correct): `SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'`
- S1: Classical NLP (wrong, wrong_logic): `SELECT Country FROM singer`

**Q (medium):** What is the name and country of origin of every singer who has a song with the word 'Hey' in its title?
- Gold: `SELECT name ,  country FROM singer WHERE song_name LIKE '%Hey%'`
- S2: NLP + LLM (correct): `SELECT Name, Country FROM singer WHERE Song_Name LIKE '%Hey%'`
- S1: Classical NLP (wrong, wrong_logic): `SELECT Name, Country FROM singer GROUP BY Name`

**Q (extra):** Find the name and location of the stadiums which some concerts happened in the years of both 2014 and 2015.
- Gold: `SELECT T2.name ,  T2.location FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.Year  =  2014 INTERSECT SELECT T2.name ,  T2.location FROM concert AS T1 JOIN stadium AS T2 ON T1.stadium_id  =  T2.stadium_id WHERE T1.Year  =  2015`
- S2: NLP + LLM (correct): `SELECT s.Name, s.Location FROM stadium s JOIN concert c ON s.Stadium_ID = c.Stadium_ID JOIN singer_in_concert sic ON c.concert_ID = sic.concert_ID WHERE c.Year IN ('2014', '2015') GROUP BY s.Stadium_ID HAVING COUNT(DISTINCT c.Year) = 2`
- S1: Classical NLP (wrong, wrong_tables): `SELECT stadium.Location FROM stadium JOIN concert ON concert.Stadium_ID = stadium.Stadium_ID JOIN singer_in_concert ON singer_in_concert.concert_ID = concert.concert_ID JOIN singer ON singer_in_concert.Singer_ID = singer.Singer_ID WHERE singer.Song_release_year = '2014' AND concert.Year = '2015'`