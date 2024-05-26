from datetime import datetime
from typing import List, Tuple

import psycopg2

database_schema = """# Database Schema

## Table: bloodpressure

- id (bigint, max length: None, not nullable): Measurement identifier.
- user_id (bigint, max length: None, nullable): Patient identifier.
- systolic (integer, max length: None, nullable): Systolic blood pressure measures the pressure in your blood vessels when your heart beats. A normal systolic blood pressure is generally considered to be around 120 mmHg, but can vary depending on various factors such as age, lifestyle, and overall health. High systolic blood pressure (a reading of 130 mmHg or higher) may indicate a condition called systolic hypertension, which can increase the risk of cardiovascular disease if not managed properly.
- diastolic (integer, max length: None, nullable): It measures the pressure in the blood vessels when the heart is at rest between beats. A normal diastolic blood pressure is generally considered to be around 80 mmHg, but can vary depending on various factors such as age, lifestyle, and overall health. High diastolic blood pressure (a reading of 90 mmHg or higher) may indicate a condition called diastolic hypertension, which can increase the risk of cardiovascular disease if not managed properly..
- pulse (integer, max length: None, nullable): Description.
- recorded_at (character varying, max length: 255, nullable): Time of recording in YYYY-MM-DD HH24:MI:SS.US. These measurements are typically done once in the morning and once in the evening at similar times. 

## Table: geo_location

- id (bigint, max length: None, not nullable): Measurement identifier.
- user_id (bigint, max length: None, nullable): Patient identifier.
- longitude (real, max length: None, nullable): Longitude.
- latitude (real, max length: None, nullable): Latitude.
- accuracy (real, max length: None, nullable): Accuracy of the measurement.
- source_of_geolocation (character varying, max length: 255, nullable): Google .
- geofence_detailed_status (character varying, max length: 255, nullable): IN_GEOFENCE,STILL_JUST_LEFT_GEOFENCE,RETURNED_TO_GEOFENCE,JUST_LEFT_GEOFENCE,OUTSIDE_GEOFENCE -> Within geofence there usually is a known environment.
- just_left_geofence_time (character varying, max length: 255, nullable): Time when geofence was just left the last time.
- connected_to_trusted_wifi (boolean, max length: None, nullable): Description.
- recorded_at (character varying, max length: 255, nullable): Time of recording in YYYY-MM-DD HH24:MI:SS.US.

## Table: patient

- user_id (bigint, max length: None, nullable): patient identifier.
- nickname (character varying, max length: 255, nullable): Name.
- medical_preconditions (character varying, max length: 255, nullable): Known preconditions.
- health (character varying, max length: 255, nullable): general health level.
- birthday (character varying, max length: 255, nullable): for age calculations and has to be considered when reasoning about reference values..
- sex (character varying, max length: 255, nullable): gender.
- home_longitude (real, max length: None, nullable): Longitude of home.
- home_latitude (real, max length: None, nullable): Latitude of home.
"""


class DBHandler:
    conn = None
    cur = None

    def __init__(self):
        if DBHandler.conn is None:
            try:
                DBHandler.conn = psycopg2.connect(
                    host="localhost",
                    database="insights",
                    user="insights",
                    port="5432", )
            except psycopg2.OperationalError as e:
                raise ConnectionError("Please start the database for our client first!\nError message: " + str(e))
            DBHandler.cur = self.conn.cursor()

    def execute_query(self, query) -> [List[Tuple], str]:
        print("Executing query: ", query)
        try:
            self.cur.execute(query)
            results = self.cur.fetchall()
            return results
        except psycopg2.OperationalError as e:
            self.conn.rollback()
            print("Operational error: " + str(e))
        except psycopg2.ProgrammingError as e:
            self.conn.rollback()
            print("Programming error: " + str(e))
        except psycopg2.IntegrityError as e:
            self.conn.rollback()
            print("Integrity error: " + str(e))
        except psycopg2.DataError as e:
            self.conn.rollback()
            print("Data error: " + str(e))
        except psycopg2.InternalError as e:
            self.conn.rollback()
            print("Internal error: " + str(e))
        except psycopg2.InFailedSqlTransaction as e:
            self.conn.rollback()
            print("Transaction failed and was rolled back: ", e)
        return None

    def close(self):
        self.conn.close()

    def get_table_schema(self):
        self.cur.execute(
            "SELECT * FROM information_schema.columns WHERE table_schema = 'public' AND table_name NOT IN "
            "('databasechangelog', 'jhi_user_authority', 'user_activity', 'jhi_user', 'jhi_user_authority', "
            "'databasechangeloglock', 'jhi_authority') "
            "ORDER BY table_schema, table_name, ordinal_position")
        tables = self.cur.fetchall()
        tables_dict = []
        for table in tables:
            table_dict = {
                "table_name": table[2],
                "column_name": table[3],
                "data_type": table[7],
                "character_maximum_length": table[8],
                "is_nullable": table[10]
            }
            tables_dict.append(table_dict)
        tables_new = dict()
        for column in tables_dict:
            table_name = column["table_name"]
            column.pop("table_name")
            if table_name in tables_new:
                tables_new[table_name].append(column)
            else:
                tables_new[table_name] = [column]
        return tables_new

    @staticmethod
    # Function to generate Markdown formatted text from the schema dictionary
    def generate_markdown(schema):
        markdown_output = "# Database Schema\n\n"
        for table_name, columns in schema.items():
            markdown_output += f"## Table: {table_name}\n\n"
            for column in columns:
                nullable = "not nullable" if column["is_nullable"] == "NO" else "nullable"
                details = f"{column['data_type']}"
                if "character_maximum_length" in column:
                    details += f", max length: {column['character_maximum_length']}"
                markdown_output += f"- **{column['column_name']}** ({details}, {nullable}): Description.\n"
            markdown_output += "\n"
        return markdown_output


def get_blood_pressure_spans(tracker, user_id) -> Tuple[Tuple[int, int], Tuple[int, int], str]:
    birthday = datetime.strptime(tracker.get_slot("birthday"), "%Y-%m-%d") if tracker.get_slot(
        "birthday") is not None else None
    systolic_span, diastolic_span = None, None
    if not birthday:
        query = f"""SELECT birthday FROM patient WHERE user_id = {user_id};"""
        result = DBHandler().execute_query(query)[0]
        print(result)
        birthday = datetime.strptime(result[0], "%Y-%m-%d") if result else None
    if birthday:
        age = (datetime.now() - birthday).days // 365
        if age < 18:
            systolic_span = (90, 120)
            diastolic_span = (60, 80)
        elif age < 40:
            systolic_span = (110, 130)
            diastolic_span = (70, 85)
        elif age < 60:
            systolic_span = (120, 140)
            diastolic_span = (75, 90)
        else:
            systolic_span = (130, 150)
            diastolic_span = (80, 95)

    else:
        systolic_span = (120, 130)
        diastolic_span = (80, 85)
        age = "unknown"
    return systolic_span, diastolic_span, str(age)
