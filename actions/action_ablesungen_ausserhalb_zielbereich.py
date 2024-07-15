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
        if limit:
            limit = int(limit)
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
        joint_plot = sns.jointplot(
            data=df,
            x="Systolic",
            y="Diastolic",
            hue="Tageszeit",
            palette="rocket",
            alpha=0.6,  # Adjust transparency for better visibility
            marginal_kws=dict(
                common_norm=False
            ),  # Ensure KDE plots are not normalized together
        )

        # Set the titles and labels
        joint_plot.set_axis_labels(
            "Systolisch (mmHg)\nBlutdruckmessungen gruppiert nach Tageszeit",
            "Diastolisch (mmHg)",
        )

        # Adding blood pressure spans to the joint plot
        systolic_span, diastolic_span, _ = get_blood_pressure_spans(tracker, user_id)
        joint_plot.ax_joint.axvspan(
            systolic_span[0], systolic_span[1], color="green", alpha=0.1
        )
        joint_plot.ax_joint.axhspan(
            diastolic_span[0], diastolic_span[1], color="green", alpha=0.1
        )

        # plt to image and send
        file_path = str(
            pathlib.Path().parent.absolute()
            / ("tmp_scatter_plot_" + str(datetime.now()) + ".png")
        )
        plt.savefig(file_path)
        dispatcher.utter_message(image=str(file_path))
        dispatcher.utter_message(
            buttons=[
                {
                    "title": "Zeig Wendepunkte in den BD Daten. ",
                    "payload": "Veränderungen im Blutdrucktrend in den letzten 3 Monaten.",
                },
                {
                    "title": "Details über Ausreißer",
                    "payload": "Haben Sie außergewöhnliche Blutdruckwerte festgestellt?",
                },
            ]
        )
        return []
