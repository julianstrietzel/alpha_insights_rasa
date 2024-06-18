import pathlib
from datetime import datetime
from typing import Text

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from rasa_sdk import Action

from actions import ddp
from actions.utils.db_utils import DBHandler
from actions.utils.utils import (
    get_blood_pressure_spans,
    get_time_of_day,
    zeitspanne_to_timespan,
    mehrzahl_zeitspanne,
    recorded_at_to_datetime,
)


class ActionAblesungenAusserhalbZielbereich(Action):
    def name(self) -> Text:
        return "action_ablesungen_ausserhalb_zielbereich"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id")
        zeitspanne = tracker.get_slot("timespan") or "Monat"
        zeitspanne_entity = next(tracker.get_latest_entity_values("timespan"), None)
        change_date_input = tracker.get_slot("change_date") or None
        direction = tracker.get_slot("direction") or "über"
        typ = tracker.get_slot("type") or None
        limit = tracker.get_slot("limit") or None
        change_date_parsed = (
            ddp.get_date_data(change_date_input).date_obj if change_date_input else None
        )

        if zeitspanne_entity:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {zeitspanne_to_timespan[zeitspanne_entity]}'"
        elif change_date_parsed:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= '{change_date_parsed.strftime('%Y-%m-%d')}'"
        else:
            date_filter = f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {zeitspanne_to_timespan[zeitspanne]}'"
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
        results = recorded_at_to_datetime(results)
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
                text=(
                    f"Von den {count_bp_measurements} Blutdruckmessungen "
                    + (
                        f"in den letzten 3 {mehrzahl_zeitspanne[zeitspanne]}"
                        if not change_date_parsed
                        else ("seit dem " + change_date_parsed.strftime("%d.%m.%Y"))
                    )
                    + " liegen "
                    + str(len(of_range_bp_measurements))
                    + f" ({of_range_quote}%) der {typ} Blutdruckmessungen "
                    + str(direction)
                    + " "
                    + str(span[1])
                    + " mmHg."
                )
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
            "Tageszeit": [
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
            hue="Tageszeit",
            style="Tageszeit",
            palette="deep",
        )
        systolic_span, diastolic_span, _ = get_blood_pressure_spans(tracker, user_id)
        plt.title("Blutdruckmessungen gruppiert nach Tageszeit")
        plt.xlabel("Systolisch (mmHg)")
        plt.ylabel("Diastolisch (mmHg)")
        plt.axvspan(systolic_span[0], systolic_span[1], color="green", alpha=0.1)
        print(systolic_span, diastolic_span)
        plt.axhspan(diastolic_span[0], diastolic_span[1], color="green", alpha=0.1)
        plt.legend(title="Tageszeit", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True)
        plt.tight_layout()
        # plt to image and send
        file_path = str(
            pathlib.Path().parent.absolute()
            / ("tmp_scatter_plot_" + str(datetime.now()) + ".png")
        )
        plt.savefig(file_path)
        dispatcher.utter_message(image=str(file_path))
        return []
