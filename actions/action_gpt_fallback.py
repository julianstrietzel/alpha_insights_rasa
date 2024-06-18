from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.gpt_utils import GPTHandler
from actions.utils.utils import get_bp_range, get_patient_details


class ActionGptFallback(Action):
    def name(self) -> Text:
        return "action_gpt_fallback"

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
        background_info_string_for_llm = (
            f"Patient Information of user_id {user_id}: {str(patient_details)}"
            f"Target coridor for systolic {systolic_range}"
            f" and diastolic blood pressure: {diastolic_range}"
        )
        await GPTHandler(
            basic_information=background_info_string_for_llm
        ).execute_query(
            user_input, output_function=dispatcher.utter_message, stream=False
        )

        return []
