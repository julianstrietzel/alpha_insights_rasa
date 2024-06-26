from datetime import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.db_utils import DBHandler
from actions.utils.utils import get_bp_range, get_patient_details


class ActionGrundInfo(Action):
    def __init__(self):
        self.dbhandler = DBHandler()
        super().__init__()

    def name(self) -> Text:
        return "action_grund_info"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        patient_details = None
        user_id = tracker.get_slot("user_id")
        print(user_id)
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        try:
            patient_details = get_patient_details(user_id, force_reload=True)
            if patient_details:
                systolic_range, diastolic_range = get_bp_range(
                    patient_details["birthday"],
                    (patient_details["medical_preconditions"] not in ["", None]),
                )
                query = f"""
                    SELECT
                        user_id,
                        COUNT(CASE WHEN systolic BETWEEN {systolic_range[0]} AND {systolic_range[1]} THEN 1 END) AS systolic_in_range,
                        COUNT(CASE WHEN systolic < {systolic_range[0]} THEN 1 END) AS systolic_below_range,
                        COUNT(CASE WHEN systolic > {systolic_range[1]} THEN 1 END) AS systolic_above_range,
                        
                        COUNT(CASE WHEN diastolic BETWEEN {diastolic_range[0]} AND {diastolic_range[1]} THEN 1 END) AS diastolic_in_range,
                        COUNT(CASE WHEN diastolic < {diastolic_range[0]} THEN 1 END) AS diastolic_below_range,
                        COUNT(CASE WHEN diastolic > {diastolic_range[1]} THEN 1 END) AS diastolic_above_range,
                        
                        COUNT(CASE WHEN pulse BETWEEN 60 AND 100 THEN 1 END) AS pulse_in_range,
                        COUNT(CASE WHEN pulse < 60 THEN 1 END) AS pulse_below_range,
                        COUNT(CASE WHEN pulse > 100 THEN 1 END) AS pulse_above_range,
                        
                        COUNT(*) AS total,
                        COUNT(CASE WHEN systolic BETWEEN {systolic_range[0]} AND {systolic_range[1]} 
                                   AND diastolic BETWEEN {diastolic_range[0]} AND {diastolic_range[1]} 
                                   AND pulse BETWEEN 60 AND 100 THEN 1 END) AS all_normal
                    FROM 
                        bloodpressure
                    WHERE 
                        user_id = {user_id}
                        AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 MONTHS'
                    GROUP BY 
                        user_id;
                """
                sex = patient_details["sex"]
                pre_existing_conditions = patient_details["medical_preconditions"]
                result = self.dbhandler.execute_query(query)
                if not result or len(result) == 0:
                    dispatcher.utter_message(
                        "No blood pressure records found for the past three months for the provided user id."
                    )
                    return patient_details
                result = result[0]
                print(sex)

                total = result[10]
                systolic_in_range = result[1]
                systolic_below_range = result[2]
                systolic_above_range = result[3]

                diastolic_in_range = result[4]
                diastolic_below_range = result[5]
                diastolic_above_range = result[6]

                pulse_in_range = result[7]
                pulse_below_range = result[8]
                pulse_above_range = result[9]

                systolic_total_out_of_range = (
                    systolic_below_range + systolic_above_range
                )
                diastolic_total_out_of_range = (
                    diastolic_below_range + diastolic_above_range
                )
                pulse_total_out_of_range = pulse_below_range + pulse_above_range

                all_normal = result[11]

                age = (
                    datetime.today().year
                    - datetime.strptime(patient_details["birthday"], "%Y-%m-%d").year
                )
                bin_female = str(sex).lower() == "female"
                gender = "Die Patientin" if bin_female else "Der Patient"
                gender_de = "weiblich" if bin_female else "männlich"
                pre_conditions = (
                    f"mit bekannten Vorerkrankungen ({pre_existing_conditions})"
                    if pre_existing_conditions not in ["", None]
                    else "ohne bekannte Vorerkrankungen"
                )

                dispatcher.utter_message(
                    f"{gender} ({gender_de}, {age} Jahre alt) {pre_conditions} hat {(all_normal) / (total) * 100:.0f}% "
                    f"{'ihrer' if bin_female else 'seiner'} Blutdruckmessungen ausschließlich innerhalb des "
                    f"Zielbereichs.\n"
                )

                if systolic_total_out_of_range / total > 0.1:
                    dispatcher.utter_message(
                        f"Systolische Messungen:\t{systolic_above_range / total * 100:.0f}% darüber,\t{systolic_below_range / total * 100:.0f}% darunter.\n"
                    )
                if diastolic_total_out_of_range / total > 0.1:
                    dispatcher.utter_message(
                        f"Diastolische Messungen:\t{diastolic_above_range / total * 100:.0f}% darüber,\t{diastolic_below_range / total * 100:.0f}% darunter.\n"
                    )

                if pulse_total_out_of_range / total > 0.1:
                    dispatcher.utter_message(
                        f"{pulse_above_range / total * 100:.0f}% der Puls-Messungen liegen darüber, {pulse_below_range / total * 100:.0f}% darunter.\n"
                    )

            else:
                dispatcher.utter_message("No patient found with the given user ID.")

        except Exception as e:
            dispatcher.utter_message(f"An error occurred: {e}")
        slot_events = (
            [
                SlotSet(key, value)
                for key, value in patient_details.items()
                if value is not None
            ]
            if patient_details
            else []
        )
        dispatcher.utter_message(
            buttons=[
                {
                    "title": "Wendepunkte",
                    "payload": "Wendepunkte in den Blutdruckwerten anzeigen",
                },
                {
                    "title": "Werte außerhalb des Zielkorridors",
                    "payload": "Gab es hohe systolische Messungen im letzten Monat?",
                },
                {
                    "title": "Veränderungen über den Tag",
                    "payload": "Wie verhält sich mein Blutdruck über den Tag?",
                },
            ]
        )
        return slot_events
