from collections import defaultdict
from datetime import datetime
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions import ddp
from actions.utils.db_utils import DBHandler
from actions.utils.utils import (
    get_bp_range,
    get_patient_details,
    calculate_percentages,
    zeitspanne_to_timespan,
    at_the_last_prefix,
)


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
        zeitspanne = tracker.get_slot("timespan") or "Monat"
        change_date = tracker.get_slot("change_date") or None
        change_date_parsed = (
            ddp.get_date_data(change_date).date_obj if change_date else None
        )
        change_date = (
            change_date_parsed.strftime("%Y-%m-%d") if change_date_parsed else None
        )
        timespan = zeitspanne_to_timespan.get(zeitspanne)
        print("tracker timespan", timespan)
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Bitte geben Sie eine Benutzer-ID an.")
            return []

        patient_details = get_patient_details(user_id, tracker)
        systolic_range, diastolic_range = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )
        if next(tracker.get_latest_entity_values("timespan"), None):
            date_filter = (
                f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
            )
            date_range_message = at_the_last_prefix.get(zeitspanne)
            date_range_message = date_range_message[0].lower() + date_range_message[1:]
        elif change_date:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= '{change_date}'"
            date_range_message = "seit dem " + change_date_parsed.strftime("%d.%m.%Y")
        else:
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
            return {}
        print(results)

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

        # Calculate percentages for systolic values
        (
            systolic_below_range_percent,
            systolic_in_range_percent,
            systolic_above_range_percent,
        ) = calculate_percentages(systolic_values, systolic_range)

        # Calculate percentages for diastolic values
        (
            diastolic_below_range_percent,
            diastolic_in_range_percent,
            diastolic_above_range_percent,
        ) = calculate_percentages(diastolic_values, diastolic_range)

        dispatcher.utter_message(
            f"Die {len(results)} Blutdruckmessungen {date_range_message} lagen zwischen {systolic_min}/{diastolic_min} mmHg und {systolic_max}/{diastolic_max} mmHg "
            f"und hatten einen Durchschnitt von {systolic_avg:.1f}/{diastolic_avg:.1f} mmHg.\n\n"
        )
        # more above than below then string erhöht vs verringert if in_range percent is below 70 stark otherwise leicht
        dispatcher.utter_message(
            f"Der systolische Blutdruck is {'leicht' if systolic_in_range_percent >= 70 else 'deutlich'} "
            f"{'erhöht' if systolic_above_range_percent > systolic_below_range_percent else 'zu niedrig'}.\n"
        )

        dispatcher.utter_message(
            f"Der diastolische Blutdruck is {'leicht' if diastolic_in_range_percent >= 70 else 'deutlich'} "
            f"{'erhöht' if diastolic_above_range_percent > diastolic_below_range_percent else 'zu niedrig'}.\n"
        )

        # dispatcher.utter_message(
        #             f"Innerhalb des Ziels:\t{systolic_in_range_percent:.1f}% systolisch, "
        #             f"\t{diastolic_in_range_percent:.1f}% diastolisch.\n"
        #         )
        #         if systolic_in_range_percent < 70 or diastolic_in_range_percent < 70:
        #             dispatcher.utter_message(
        #                 f"Oberhalb des Ziels:\t{systolic_above_range_percent:.1f}% systolisch, "
        #                 f"\t{diastolic_above_range_percent:.1f}% diastolisch.\n"
        #                 f"Unterhalb des Ziels:\t{systolic_below_range_percent:.1f}% systolisch, "
        #                 f"\t{diastolic_below_range_percent:.1f}% diastolisch.\n"
        #             )

        # Step 1 & 2: Categorize readings into morning and evening
        morning_readings = defaultdict(list)
        evening_readings = defaultdict(list)

        for result in results:
            systolic, diastolic, _, recorded_at = result
            hour = recorded_at.hour
            if 6 <= hour < 12:  # Define your own time range for morning
                morning_readings["systolic"].append(systolic)
                morning_readings["diastolic"].append(diastolic)
            elif 18 <= hour < 24:  # Define your own time range for evening
                evening_readings["systolic"].append(systolic)
                evening_readings["diastolic"].append(diastolic)

        morning_systolic_percentages = calculate_percentages(
            morning_readings["systolic"], systolic_range
        )
        morning_diastolic_percentages = calculate_percentages(
            morning_readings["diastolic"], diastolic_range
        )

        evening_systolic_percentages = calculate_percentages(
            evening_readings["systolic"], systolic_range
        )
        evening_diastolic_percentages = calculate_percentages(
            evening_readings["diastolic"], diastolic_range
        )

        # Step 4: Generate messages
        def generate_message(bp_type, morning_percentages, evening_percentages):
            morning_message = (
                "keine Messungen"
                if sum(morning_percentages) == 0
                else (
                    "starke Schwankungen"
                    if morning_percentages[0] > 20 and morning_percentages[2] > 20
                    else (
                        "niedrige Werte"
                        if morning_percentages[0] > 25
                        else (
                            "erhöhte Werte"
                            if morning_percentages[2] > 25
                            else "normale Werte"
                        )
                    )
                )
            )

            morning_perc_message = (
                "("
                + (
                    f"{morning_percentages[0]:.1f}% unter, "
                    if morning_percentages[0] > 0
                    else ""
                )
                + (
                    f"{morning_percentages[1]:.1f}% in, "
                    if morning_percentages[1] > 0
                    else ""
                )
                + (
                    f"{morning_percentages[2]:.1f}% über"
                    if morning_percentages[2] > 0
                    else ""
                )
                + " dem Ziel) "
                if morning_percentages[0] > 10 or morning_percentages[2] > 10
                else ""
            )

            evening_message = (
                "keine Messungen"
                if sum(evening_percentages) == 0
                else (
                    "starke Schwankungen"
                    if evening_percentages[0] > 20 and evening_percentages[2] > 20
                    else (
                        "niedrige Werte"
                        if evening_percentages[0] > 25
                        else (
                            "erhöhte Werte"
                            if evening_percentages[2] > 25
                            else "normale Werte"
                        )
                    )
                )
            )
            evening_perc_message = (
                "("
                + (
                    f"{evening_percentages[0]:.1f}% unter, "
                    if evening_percentages[0] > 0
                    else ""
                )
                + (
                    f"{evening_percentages[1]:.1f}% in, "
                    if evening_percentages[1] > 0
                    else ""
                )
                + (
                    f"{evening_percentages[2]:.1f}% über"
                    if evening_percentages[2] > 0
                    else ""
                )
                + " dem Ziel) "
                if evening_percentages[0] > 10 or evening_percentages[2] > 10
                else ""
            )
            return f"Es zeigen sich {morning_message} {morning_perc_message}im {bp_type} Blutdruck am Morgen und {evening_message} {evening_perc_message}am Abend."

        systolic_message = generate_message(
            "systolischen", morning_systolic_percentages, evening_systolic_percentages
        )
        diastolic_message = generate_message(
            "diastolischen",
            morning_diastolic_percentages,
            evening_diastolic_percentages,
        )

        dispatcher.utter_message(systolic_message)
        dispatcher.utter_message(diastolic_message)

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
                }
            ])

        return []
        # Step 3: Calculate percentages for each category
