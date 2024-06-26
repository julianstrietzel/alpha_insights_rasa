from datetime import datetime
from typing import Text

from rasa_sdk import Action

from actions.utils.utils import (
    get_patient_details,
    get_bp_range,
    fetch_latest_bp_measurement,
    is_in_range,
)


class ActionAktuellerBDStatus(Action):
    def name(self) -> Text:
        return "action_aktueller_bd_status"

    def run(self, dispatcher, tracker, domain):
        # Fetch the most recent blood pressure measurement for the patient
        user_id = tracker.get_slot("user_id")
        if not user_id:
            dispatcher.utter_message("Ich konnte keine Benutzer-ID finden.")
            return []
        patient_details = get_patient_details(user_id)
        age = (
            datetime.today().year
            - datetime.strptime(patient_details["birthday"], "%Y-%m-%d").year
        )

        # This is a placeholder function, replace it with your actual function to fetch the data
        latest_measurement = fetch_latest_bp_measurement(user_id)
        if not latest_measurement:
            dispatcher.utter_message(
                f"Es wurden keine Messungen gefunden für die user_id {user_id} gefunden."
            )
            return []
        print("latest_measurement", latest_measurement)
        # Calculate the days since the latest measurement
        recorded_at = datetime.strptime(latest_measurement[4], "%Y-%m-%d %H:%M:%S.%f")
        days_since_latest = (datetime.now() - recorded_at).days
        if days_since_latest == 0:
            days_since_latest = 1
        if days_since_latest > 30:
            since_message = f"{days_since_latest // 30} Monaten"
        elif days_since_latest > 7:
            since_message = f"{days_since_latest // 7} Wochen"
        else:
            since_message = f"{days_since_latest} Tagen"

        # Determine if the measurement is within or outside the target range
        # This is a placeholder function, replace it with your actual function to check the range
        bp_range = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )
        in_range = is_in_range(latest_measurement[1], latest_measurement[2], bp_range)
        target_message = (
            "Beide Werte liegen innerhalb"
            if all(in_range)
            else (
                "Beide Werte liegen außerhalb"
                if not any(in_range)
                else (
                    (
                        "Der systolische Wert liegt innerhalb"
                        if in_range[0]
                        else "Der systolische Wert liegt außerhalb"
                    )
                    + (
                        " und der diastolische Wert liegt innerhalb"
                        if in_range[1]
                        else " und der diastolische Wert liegt außerhalb"
                    )
                )
            )
        )
        # Generate the required message
        message = (
            f"Die jüngste Messung wurde vor {since_message} aufgezeichnet: "
            f"{latest_measurement[1]} / {latest_measurement[2]} mmHg, Puls: {latest_measurement[3]}\n"
        )
        message += (
            f"{target_message} des Zielkorridors für "
            f"{'einen Patienten' if patient_details['sex'] != 'FEMALE' else 'eine Patientin'}"
            f" im Alter von {age} Jahren."
        )

        dispatcher.utter_message(
            message,
            buttons=[
                {
                    "title": "Mehr details zum aktuellen Blutdruck",
                    "payload": "Wie hat sich der BD verhalten?",
                },
                {"title": "Mehr details zur Person", "payload": "Patienteninformation"},
                {
                    "title": "Trends in den Blutdruckdaten",
                    "payload": "Welche Trends sind im Blutdruck des Nutzers zu erkennen?",
                },
            ],
        )

        return []
