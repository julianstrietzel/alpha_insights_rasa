from typing import Any, Text, Dict, List

from openai import OpenAI
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.defog_utils import DefogHandler
from actions.utils.utils import get_bp_range, get_patient_details


class ActionDefogFallback(Action):
    def __init__(self):
        self.defog = DefogHandler()
        self.client = OpenAI()

        super().__init__()

    def name(self) -> Text:
        return "action_defog_fallback"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_input = tracker.latest_message.get("text")
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        patient_details = get_patient_details(user_id, force_reload=False)
        systolic_range, diastolic_range = get_bp_range(
            patient_details["birthday"],
            (patient_details["medical_preconditions"] not in ["", None]),
        )
        background_info_string_for_llm = f"Patient Information: {str(patient_details)}, BP Target Range: {systolic_range}/{diastolic_range}"

        defog_result = self.defog.ask_query(
            user_input, user_id, background_info_string_for_llm
        )
        columns = defog_result["columns"]
        data = defog_result["data"]
        dispatcher.utter_message("SQL Query: " + defog_result["query_generated"])
        pretty_data = (
            "\t".join([header for header in columns])
            + "\n"
            + "\n".join(["\t".join([str(cell) for cell in row]) for row in data])
        )
        dispatcher.utter_message("Query Result:\n" + pretty_data)
        thread = self.client.beta.threads.create()
        instructions = (
            f"You are trying to answer the following question: '{user_input}'\n"
            f"You will be provided with data to answer the question."
            f"About the following user {patient_details}"
            f"'You will be provided with data to answer the question from the database "
            f"potentially containing blood pressure and geo location data."
            f"Do not use any external sources, only the data provided."
            f"Do not mirror the user input or patient details, but provide a "
            f"professional and short medical answer addressed to the doctor of the patient."
        )
        assistant = self.client.beta.assistants.create(
            model="gpt-4o",
            instructions=instructions,
        )
        self.client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="'\nThe result of the SQL query was:\n"
            + pretty_data
            + "\nPlease provide a professional medical answer to the provided question "
            "earlier based only on the provided data."
            "KEEP SHORT AND PROFESSIONAL OTHERWISE I'LL GET FIRED. DO NOT MAKE UP ANY UNKNOWN INFORMATION AND MAKE THE ANSWER SHORT AND INTERPRETABLE"
            "Answer in German to me as a healthcare professional in my language.",
        )
        self.client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id
        )
        messages = self.client.beta.threads.messages.list(thread_id=thread.id)
        for message in messages:
            if message.role != "user":
                dispatcher.utter_message(message.content[0].text.value)

        return []
