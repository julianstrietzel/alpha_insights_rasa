import json

from openai import OpenAI
from openai.lib.streaming import AssistantEventHandler

from actions.utils.db_utils import DBHandler


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

    def execute_query(self, question: str, output_function: callable = None):
        thread = self.thread or self.client.beta.threads.create()
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question,
        )
        with self.client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id=self.assistant.id,
                event_handler=EventHandler(output_function=output_function, gpt_handler=self)
        ) as stream:
            for text in stream.text_deltas:
                if output_function:
                    output_function(text)
                else:
                    print(text, end="", flush=True)
            stream.until_done()
        return thread


class EventHandler(AssistantEventHandler):

    def __init__(self, output_function:callable=None, gpt_handler=None):
        self.gpt_handler = gpt_handler if gpt_handler else GPTHandler()
        self.output_function = output_function
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
                if self.output_function:
                    self.output_function(text)
                else:
                    print(text, end="", flush=True)
