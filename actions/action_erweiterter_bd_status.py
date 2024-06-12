from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.db_utils import DBHandler
from actions.utils.utils import get_bp_range, get_patient_details


class ActionErweiterterBDStatus(Action):
    def __init__(self):
        self.dbhandler = DBHandler()
        super().__init__()

    def name(self) -> Text:
        return "action_erweiterter_bd_status"

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
        timespan = tracker.get_slot("timespan")
        change_date = tracker.get_slot("change_date")

        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Bitte geben Sie eine Benutzer-ID an.")
            return []

        patient_details = get_patient_details(user_id, tracker)
        systolic_range, diastolic_range = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )
        if next(tracker.get_latest_entity_values("timespan")):
            date_filter = (
                f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
            )
        elif change_date:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= '{change_date}'"
        else:
            date_filter = (
                f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
            )

        query = f"""
                SELECT
                    systolic,
                    diastolic,
                    pulse
                FROM 
                    bloodpressure
                WHERE 
                    user_id = {user_id}
                    {date_filter}
            """

        results = self.dbhandler.execute_query(query)
        if not results:
            dispatcher.utter_message(
                "Keine Blutdruckaufzeichnungen für den angegebenen Zeitraum gefunden."
            )
            return {}

        systolic_values = [result[0] for result in results]
        diastolic_values = [result[1] for result in results]

        if not systolic_values or not diastolic_values:
            dispatcher.utter_message("Keine Blutdruckdaten verfügbar.")
            return {}

        systolic_min = min(systolic_values)
        systolic_max = max(systolic_values)
        systolic_avg = sum(systolic_values) / len(systolic_values)

        diastolic_min = min(diastolic_values)
        diastolic_max = max(diastolic_values)
        diastolic_avg = sum(diastolic_values) / len(diastolic_values)

        systolic_in_range = len(
            [x for x in systolic_values if systolic_range[0] <= x <= systolic_range[1]]
        )
        diastolic_in_range = len(
            [
                x
                for x in diastolic_values
                if diastolic_range[0] <= x <= diastolic_range[1]
            ]
        )

        systolic_below_range = len(
            [x for x in systolic_values if x < systolic_range[0]]
        )
        diastolic_below_range = len(
            [x for x in diastolic_values if x < diastolic_range[0]]
        )

        systolic_above_range = len(
            [x for x in systolic_values if x > systolic_range[1]]
        )
        diastolic_above_range = len(
            [x for x in diastolic_values if x > diastolic_range[1]]
        )

        total_measurements = len(systolic_values)

        dispatcher.utter_message(
            f"Die Blutdruckmessungen lagen zwischen {systolic_min}/{diastolic_min} mmHg und {systolic_max}/{diastolic_max} mmHg "
            f"und hatten einen Durchschnitt von {systolic_avg:.1f}/{diastolic_avg:.1f} mmHg.\n\n"
        )
        systolic_in_range_percent = systolic_in_range / total_measurements * 100
        diastolic_in_range_percent = diastolic_in_range / total_measurements * 100
        dispatcher.utter_message(
            f"Innerhalb des Ziels: {systolic_in_range_percent:.1f}% systolisch, "
            f"{diastolic_in_range_percent:.1f}% diastolisch.\n"
        )
        if systolic_in_range_percent < 70:
            dispatcher.utter_message(
                f"Unterhalb des Ziels: {systolic_below_range / total_measurements * 100:.1f}% systolisch, "
                f"{diastolic_below_range / total_measurements * 100:.1f}% diastolisch.\n"
            )
        if diastolic_in_range_percent < 70:
            dispatcher.utter_message(
                f"Über dem Ziel: {systolic_above_range / total_measurements * 100:.1f}% systolisch, "
                f"{diastolic_above_range / total_measurements * 100:.1f}% diastolisch.\n"
            )

        # TODO Testing and completion of the following functionality
        # Obwohl wir eine starke Schwankung (20% über, 20% unter dem Ziel) im systolischen Blutdruck am Morgen sehen, sehen wir leicht erhöhte Werte (20% über) am Abend.
        # Der diastolische Blutdruck zeigt niedrige Werte am Morgen (30% unter dem Ziel) und erhöhte Werte am Abend (30% über dem Ziel).
        return []
