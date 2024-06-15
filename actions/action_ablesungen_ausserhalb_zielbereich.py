import os
from datetime import datetime
from typing import Text

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from rasa_sdk import Action

from actions.utils.db_utils import DBHandler
from actions.utils.utils import get_blood_pressure_spans, get_time_of_day


class ActionAblesungenAusserhalbZielbereich(Action):
    def name(self) -> Text:
        return "action_ablesungen_ausserhalb_zielbereich"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id")
        zeitspanne = tracker.get_slot("timespan") or "Monat"
        zeitspanne_entity = next(tracker.get_latest_entity_values("timespan"), None)
        change_date = tracker.get_slot("change_date") or None
        direction = tracker.get_slot("direction") or "über"
        typ = tracker.get_slot("typ") or None
        limit = tracker.get_slot("limit") or None
        timespan_to_zeitspanne = {
            "Tag": "day",
            "Woche": "week",
            "Monat": "month",
            "Jahr": "year",
        }
        mehrzahl_zeitspanne = {
            "Tag": "Tagen",
            "Woche": "Wochen",
            "Monat": "Monaten",
            "Jahr": "Jahren",
        }

        if zeitspanne_entity:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan_to_zeitspanne[zeitspanne_entity]}'"
        elif change_date:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= '{change_date}'"
        else:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan_to_zeitspanne[zeitspanne]}'"
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
        results = DBHandler().execute_query(query)
        if not results:
            dispatcher.utter_message("Keine Daten gefunden.")
            return []
        results = [
            (
                systolic,
                diastolic,
                pulse,
                datetime.strptime(recorded_at, "%Y-%m-%d %H:%M:%S.%f"),
            )
            for systolic, diastolic, pulse, recorded_at in results
        ]
        count_bp_measurements = len(results)
        systolic_span, diastolic_span, _ = get_blood_pressure_spans(tracker, user_id)
        if typ == "systolisch" and limit:
            systolic_span = (limit, limit)
        elif typ == "diastolisch" and limit:
            diastolic_span = (limit, limit)

        def message_bp_measurements(results, typ, span):
            of_range_bp_measurements = [
                (value, recorded_at)
                for value, recorded_at in results
                if (value > span[1] and direction == "über")
                or (value < span[0] and direction == "unter")
            ]
            if not of_range_bp_measurements:
                return
            of_range_quote = round(len(of_range_bp_measurements) / len(results) * 100)
            dispatcher.utter_message(
                f"Von den {count_bp_measurements} Blutdruckmessungen "
                + (
                    f"in den letzten 3 {mehrzahl_zeitspanne[zeitspanne]}"
                    if not change_date
                    else ("seit dem " + change_date)
                )
                + " liegen "
                + str(len(of_range_bp_measurements))
                + f" ({of_range_quote}%) der {typ} Blutdruckmessungen "
                + str(direction)
                + " "
                + str(span[1])
                + " mmHg."
            )

            morning_bp_measurements = [
                (value, recorded_at)
                for value, recorded_at in of_range_bp_measurements
                if 6 <= recorded_at.hour < 12
            ]
            evening_bp_measurements = [
                (value, recorded_at)
                for value, recorded_at in of_range_bp_measurements
                if 16 <= recorded_at.hour < 24
            ]
            quote_morning = round(
                len(morning_bp_measurements) / len(of_range_bp_measurements) * 100
            )
            quote_evening = round(
                len(evening_bp_measurements) / len(of_range_bp_measurements) * 100
            )
            if 60 <= quote_morning < 98:
                dispatcher.utter_message(
                    f"{quote_morning}% dieser Ausreißer wurden am Morgen aufgenommen."
                )
            elif 60 <= quote_evening < 98:
                dispatcher.utter_message(
                    f"{quote_evening}% dieser Ausreißer wurden am Abend aufgezeichnet."
                )
            elif quote_morning >= 95:
                dispatcher.utter_message(
                    "Alle diese Ausreißer wurden am Morgen aufgezeichnet."
                )
            elif quote_evening >= 95:
                dispatcher.utter_message(
                    "Alle diese Ausreißer wurden am Abend aufgezeichnet."
                )
            else:
                dispatcher.utter_message(
                    "Die Ausreißer sind gleichmäßig über den Tag verteilt."
                )

        if typ == "systolisch" or typ not in ["diastolisch", "systolisch"]:
            message_bp_measurements(
                [
                    (systolic, recorded_at)
                    for systolic, diastolic, pulse, recorded_at in results
                ],
                "systolisch",
                systolic_span,
            )
        if typ == "diastolisch" or typ not in ["diastolisch", "systolisch"]:
            message_bp_measurements(
                [
                    (diastolic, recorded_at)
                    for systolic, diastolic, pulse, recorded_at in results
                ],
                "diastolisch",
                diastolic_span,
            )

        data = {
            "Systolic": [
                systolic for systolic, diastolic, pulse, recorded_at in results
            ],
            "Diastolic": [
                diastolic for systolic, diastolic, pulse, recorded_at in results
            ],
            "Daytime": [
                get_time_of_day(recorded_at)
                for systolic, diastolic, pulse, recorded_at in results
            ],
        }

        df = pd.DataFrame(data)

        # Create scatter plot using seaborn
        plt.figure(figsize=(10, 6))
        scatter_plot = sns.scatterplot(
            data=df,
            x="Systolic",
            y="Diastolic",
            hue="Daytime",
            style="Daytime",
            palette="deep",
        )
        systolic_span, diastolic_span, _ = get_blood_pressure_spans(tracker, user_id)
        plt.title("Blood Pressure Readings Grouped by Daytime - Outliers Only")
        plt.xlabel("Systolic (mmHg)")
        plt.ylabel("Diastolic (mmHg)")
        plt.axvspan(systolic_span[0], systolic_span[1], color="green", alpha=0.1)
        print(systolic_span, diastolic_span)
        plt.axhspan(diastolic_span[0], diastolic_span[1], color="green", alpha=0.1)
        plt.legend(title="Daytime", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True)
        plt.tight_layout()
        # plt to image and send
        title = os.getcwd() + "/tmp_scatter_plot_" + str(datetime.now()) + ".png"
        plt.savefig(title)
        dispatcher.utter_message(image=title)
        return []
