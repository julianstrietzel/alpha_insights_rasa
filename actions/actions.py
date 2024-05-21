import json
from typing import Any, Text, Dict, List, Tuple, Optional

import psycopg2
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from openai import OpenAI

from openai import AssistantEventHandler


class ActionAskGPT(Action):
    def __init__(self):
        self.gpt_handler = GPTHandler()
        super().__init__()

    def name(self) -> Text:
        return "action_ask_gpt"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_input = tracker.latest_message.get('text')
        response = self.gpt_handler.execute_query(user_input)
        dispatcher.utter_message(response)
        return []


class ActionGetBasicUserDetails(Action):
    def name(self) -> Text:
        return "action_get_basic_user_details"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None:
            dispatcher.utter_message("Please provide a user id.")
            return []
        details, response = ActionGetBasicUserDetails.get_patient_details(user_id)
        print(details)
        if details is None:
            dispatcher.utter_message("No user found with the provided user id.")
            print(response)
            return []
        dispatcher.utter_message(f"User {user_id} has the following details: {response}")
        return []

    @staticmethod
    def get_patient_details(user_id) -> Tuple[Optional[Dict], str]:
        try:
            # Define the SQL query
            query = f"""SELECT id, health, geo, user_id, nickname, title, home_longitude, home_latitude, birthday, sex, 
            medical_preconditions FROM patient WHERE user_id = {user_id};"""

            result = DBHandler().execute_query(query)[0]
            # log result
            print(result)
            # log result datatype
            print(type(result))
            if result:
                patient_details = {
                    "health": result[1],
                    "geo": result[2],
                    "user_id": result[3],
                    "nickname": result[4],
                    "title": result[5],
                    "home_longitude": result[6],
                    "home_latitude": result[7],
                    "birthday": result[8],
                    "sex": result[9],
                    "medical_preconditions": result[10]
                }

                response = "\n"
                for detail_name, detail_value in [
                    ("ID", patient_details['user_id']),
                    ("Health", patient_details['health']),
                    ("Geo", patient_details['geo']),
                    ("Nickname", patient_details['nickname']),
                    ("Title", patient_details['title']),
                    ("Home Longitude", patient_details['home_longitude']),
                    ("Home Latitude", patient_details['home_latitude']),
                    ("Birthday", patient_details['birthday']),
                    ("Sex", patient_details['sex']),
                    ("Medical Preconditions", patient_details['medical_preconditions'])
                ]:
                    if detail_value is not None:
                        response += f"{detail_name}: {detail_value}\n"
            else:
                response = "No patient found with the given user ID."

            return patient_details, response
        except Exception as e:
            return None, f"An error occurred: {e}"


class DBHandler:
    conn = None
    cur = None

    def __init__(self):
        if DBHandler.conn is None:
            DBHandler.conn = psycopg2.connect(
                host="localhost",
                database="insights",
                user="insights",
                port="5432", )
            DBHandler.cur = self.conn.cursor()

    def execute_query(self, query) -> str:
        print("Executing query: ", query)
        try:
            self.cur.execute(query)
            results = self.cur.fetchall()
        except psycopg2.OperationalError as e:
            self.conn.rollback()
            return "Operational error: " + str(e)
        except psycopg2.ProgrammingError as e:
            self.conn.rollback()
            return "Programming error: " + str(e)
        except psycopg2.IntegrityError as e:
            self.conn.rollback()
            return "Integrity error: " + str(e)
        except psycopg2.DataError as e:
            self.conn.rollback()
            return "Data error: " + str(e)
        except psycopg2.InternalError as e:
            self.conn.rollback()
            return "Internal error: " + str(e)
        except psycopg2.InFailedSqlTransaction as e:
            self.conn.rollback()
            return "Transaction failed and was rolled back: " + str(e)
        return results

    def close(self):
        self.conn.close()

    def get_table_schema(self):
        self.cur.execute(
            "SELECT * FROM information_schema.columns WHERE table_schema = 'public' AND table_name NOT IN ('databasechangelog', 'jhi_user_authority', 'user_activity', 'jhi_user', 'jhi_user_authority', 'databasechangeloglock', 'jhi_authority') ORDER BY table_schema, table_name, ordinal_position")
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


class GPTHandler:

    def __init__(self):
        self.db_handler = DBHandler()
        db_schema = DBHandler.generate_markdown(self.db_handler.get_table_schema())
        self.client = OpenAI(api_key="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")
        self.thread = None
        self.assistant = self.client.beta.assistants.create(
            name="PostgresSQL Data Extractor",
            instructions=f"""
You are an assistant that is able to extract data from a database. Therefore you have the tool of accessing a sql postgresql database. Your task is to answer the question of the user by querying the database. The database schema is provided below.
You can use the tool 'execute_sql_statement' to ask sql requests to the database. The tool has one parameter 'query' which is the sql query to be executed.
the user of interest in this case is has the user_id 5504.
You are in the role of a junior doctor, that provides insights to a senior doctor that asks them questions about the patients.
Provide answers in professional medical langugage being precise and short, as the doctor hsa not much time. 
Everytime you run into problems, please just try your best and different approaches to solve the problem, get different views on the data and use sql functions to write stuff.
# Database Schema

""" + db_schema,
            model="gpt-3.5-turbo",
            tools=[
                {"type": "function",
                 "function": {
                     "name": "execute_sql_statement",
                     "description": "Use this tool to ask sql requests to the database.",
                     "parameters": {
                         "type": "object",
                         "properties": {
                             "query": {
                                 "type": "string",
                                 "description": "The sql query to be executed"
                             }
                         },
                         "required": ["query"]
                     }
                 }
                 }
            ]
        )

        def ask_question(question: str, gui=None):
            thread = self.thread or self.client.beta.threads.create()
            self.client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=question,
            )
            with self.client.beta.threads.runs.stream(
                    thread_id=thread.id,
                    assistant_id=self.assistant.id,
                    event_handler=EventHandler(gui=gui, gpt_handler=self)
            ) as stream:
                for text in stream.text_deltas:
                    if gui:
                        gui.add_text(text)
                    else:
                        print(text, end="", flush=True)
                stream.until_done()
            return thread


class EventHandler(AssistantEventHandler):

    def __init__(self, gui=None, gpt_handlers=None):
        self.gpt_handler = gpt_handlers if gpt_handlers else GPTHandler()
        self.gui = gui
        super().__init__()

    def on_event(self, event):
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id  # Retrieve the run ID from the event data
            self.handle_requires_action(event.data, run_id)

    def handle_requires_action(self, data, run_id):
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "execute_sql_statement":
                result = DBHandler().execute_query(json.loads(tool.function.arguments)["query"])
                tool_outputs.append({"tool_call_id": tool.id, "output": result})

        # Submit all tool_outputs at the same time
        self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        # Use the submit_tool_outputs_stream helper
        with self.gpt_handler.client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
        ) as stream:
            for text in stream.text_deltas:
                if self.gui:
                    self.gui.add_text(text)
                else:
                    print(text, end="", flush=True)
