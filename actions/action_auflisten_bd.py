from datetime import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.db_utils import DBHandler
from actions.utils.utils import (
    get_bp_range,
    get_patient_details,
    zeitspanne_to_timespan,
    at_the_last_prefix,
)


class ActionAuflistenBd(Action):
    def __init__(self):
        self.dbhandler = DBHandler()
        super().__init__()

    def name(self) -> Text:
        return "action_auflisten_bd"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        print(tracker.slots)
        print(tracker.latest_message)
        print(next(tracker.get_latest_entity_values("timespan"), "Fall back"))
        user_id = tracker.get_slot("user_id")
        zeitspanne = tracker.get_slot("timespan") or "Monat"
        timespan = zeitspanne_to_timespan.get(zeitspanne)

        typ = tracker.get_slot("type") or "systolischen"

        print("tracker timespan", timespan)
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Bitte geben Sie eine Benutzer-ID an.")
            return []

        patient_details = get_patient_details(user_id, tracker)
        systolic_range, diastolic_range = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )
        date_filter = (
            f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
        )
        date_range_message = at_the_last_prefix.get(zeitspanne)
        date_range_message = date_range_message[0].lower() + date_range_message[1:]

        query = f"""
                SELECT
                    systolic,
                    diastolic,
                    pulse,
                    recorded_at
                FROM 
                    bloodpressure
                WHERE 
                    user_id = {user_id}
                    {date_filter}
                ORDER BY recorded_at DESC
                LIMIT 30
            """

        results = self.dbhandler.execute_query(query)
        # map recorded at to date time
        results = [
            (
                systolic,
                diastolic,
                pulse,
                datetime.strptime(recorded_at, "%Y-%m-%d %H:%M:%S.%f"),
            )
            for systolic, diastolic, pulse, recorded_at in results
        ]
        if not results:
            dispatcher.utter_message(
                "Keine Blutdruckaufzeichnungen für den angegebenen Zeitraum gefunden."
            )
            return []
        print(results)

        systolic_values = [result[0] for result in results]
        diastolic_values = [result[1] for result in results]
        if typ == "systolisch":
            values = systolic_values
            range_values = systolic_range
        else:
            values = diastolic_values
            range_values = diastolic_range

        # Output a list of all values with the date
        message = f"Die {typ}en Blutdruckwerte {date_range_message} sind: \n"
        for i, value in enumerate(values):
            message += f"- {value} mmHg am {results[i][3].strftime('%d.%m.%Y %H:%M')}\n"
        dispatcher.utter_message(message)
        return []
