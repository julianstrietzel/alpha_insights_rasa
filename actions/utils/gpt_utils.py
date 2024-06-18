import json

from openai import OpenAI
from openai.lib.streaming import AssistantEventHandler

from actions.utils.db_utils import DBHandler, database_schema


class GPTHandler:

    def __init__(self, basic_information: str = ""):
        # TODO if handed over a thread id this should not create but get the thread to continue even if multiple sessions are up
        self.client = OpenAI()
        self.thread = self.client.beta.threads.create()
        self.assistant = self.client.beta.assistants.create(
            name="PostgresSQL Data Extractor",
            instructions=f"""
You are an assistant that is able to extract data from a database. Therefore you have the tool of accessing a sql postgresql database. Your task is to answer the question of the user by querying the database. The database schema is provided below.
You can use the tool 'execute_sql_statement' to ask sql requests to the database. The tool has one parameter 'query' which is the sql query to be executed.
You are in the role of a junior doctor, that provides insights to a senior doctor that asks them questions about the patients.
Provide answers in professional medical langugage being precise and short, as the doctor hsa not much time. 
Everytime you run into problems, please just try your best and different approaches to solve the problem, get different views on the data and use sql functions to write stuff.
# Database Schema

"""
            + database_schema
            + "\nConsider information only related to the following user: "
            + basic_information
            + "Current date: 2024-05-29",
            model="gpt-4o",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "execute_sql_statement",
                        "description": "Use this tool to ask sql requests to the database.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The sql query to be executed",
                                }
                            },
                            "required": ["query"],
                        },
                    },
                }
            ],
        )

    async def execute_query(
        self, question: str, output_function: callable, stream: bool = True
    ):
        thread = self.thread
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=question,
        )
        if stream:
            with self.client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id=self.assistant.id,
                event_handler=EventHandler(
                    output_function=output_function, gpt_handler=self, stream=stream
                ),
            ) as stream:
                for text in stream.text_deltas:
                    if output_function:
                        output_function(text)
                    print(text, end="", flush=True)
                stream.until_done()
        else:
            run = self.client.beta.threads.runs.create_and_poll(
                thread_id=thread.id, assistant_id=self.assistant.id
            )
            event_handler = EventHandler(
                output_function=output_function, gpt_handler=self, stream=stream
            )
            if run.status != "completed":
                event_handler.handle_requires_action(run)
            messages = self.client.beta.threads.messages.list(thread_id=thread.id)

            for message in messages:
                # Assuming message.content is a list of TextContentBlock
                if message.role != "user":
                    output_function(message.content[0].text.value)
        return thread


class EventHandler(AssistantEventHandler):

    def __init__(
        self, output_function: callable = None, gpt_handler=None, stream: bool = True
    ):
        self.gpt_handler = gpt_handler if gpt_handler else GPTHandler()
        self.db_handler = DBHandler(
            silent=False, output_function=output_function, stringify_output=True
        )
        self.output_function = output_function
        self.stream = stream
        super().__init__()

    def on_event(self, event):
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == "thread.run.requires_action" or self.stream:
            self.handle_requires_action(event.data)

    def handle_requires_action(self, data):
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "execute_sql_statement":
                try:
                    result = self.db_handler.execute_query(
                        json.loads(tool.function.arguments)["query"]
                    )
                    tool_outputs.append({"tool_call_id": tool.id, "output": result})
                except Exception as e:
                    print(
                        "During execution of the database query the following error was rasied: "
                        + e
                    )
                    tool_outputs.append(
                        {
                            "tool_call_id": tool.id,
                            "output": "An error occurred during the execution of the query: "
                            + e,
                        }
                    )

        # Submit all tool_outputs at the same time
        self.submit_tool_outputs(tool_outputs, data)

    def submit_tool_outputs(self, tool_outputs, run: "Run" = None):
        # Use the submit_tool_outputs_stream helper
        print("Submitting tool outputs" + str(tool_outputs))
        if self.stream:
            with self.gpt_handler.client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=self.current_run.thread_id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
            ) as stream:
                for text in stream.text_deltas:
                    if self.output_function:
                        self.output_function(text)

                    print(text, end="", flush=True)
        else:
            self.gpt_handler.client.beta.threads.runs.submit_tool_outputs_and_poll(
                thread_id=run.thread_id,
                run_id=run.id,
                tool_outputs=tool_outputs,
            )
