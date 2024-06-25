import pathlib
from datetime import datetime
from typing import Text

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from rasa_sdk import Action

from actions import ddp
from actions.utils.db_utils import DBHandler
from actions.utils.utils import get_patient_details, get_bp_range


class ActionVeraenderungUeberTag(Action):
    def name(self) -> Text:
        return "action_veraenderungen_ueber_tag"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Bitte geben Sie eine Benutzer-ID an.")
            return []
        change_date = tracker.get_slot("change_date") or None
        change_date_parsed = (
            ddp.get_date_data(change_date).date_obj if change_date else None
        )

        patient_details = get_patient_details(user_id, tracker)
        systolisch_span, diastolic_span = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )

        ref_date = (
            (pd.Timestamp.now() - pd.DateOffset(months=3)).replace(day=1)
            if not change_date
            else change_date_parsed
        ).strftime("%Y-%m-%d")
        ref_date_parsed = datetime.strptime(ref_date, "%Y-%m-%d")

        bp_data = self.preprocess_bp_data(
            f"""
                SELECT
                    systolic,
                    diastolic,
                    pulse,
                    recorded_at
                FROM 
                    bloodpressure
                WHERE 
                    user_id = {user_id}
                    AND CAST(recorded_at AS timestamp) >= '{ref_date}'
            """
        )
        bp_data_before = self.preprocess_bp_data(
            f"""
            SELECT
                systolic,
                diastolic,
                pulse,
                recorded_at
            FROM 
                bloodpressure
            WHERE 
                user_id = {user_id}
                AND CAST(recorded_at AS timestamp) < '{ref_date}'
            """
        )

        def generate_period_trend_message(
            data, period, direction="Seit", ref_data=None
        ):
            data = data[data["Daytime"] == period]
            if data.empty:
                return (
                    f"{direction} dem {ref_date_parsed.strftime('%d.%m.%Y')} wurden keine Blutdruckmessungen am {period} durchgeführt.",
                    None,
                )
            # Calculate statistics
            systolic_min = data["Systolisch"].min()
            systolic_max = data["Systolisch"].max()
            systolic_avg = data["Systolisch"].mean()
            diastolic_min = data["Diastolisch"].min()
            diastolic_max = data["Diastolisch"].max()
            diastolic_avg = data["Diastolisch"].mean()
            pulse_min = data["Puls"].min()
            pulse_max = data["Puls"].max()
            pulse_avg = data["Puls"].mean()

            systolic_within_target = (
                data[
                    (data["Systolisch"] >= systolisch_span[0])
                    & (data["Systolisch"] <= systolisch_span[1])
                ].shape[0]
                / data.shape[0]
                * 100
            )
            systolic_below_target = (
                data[data["Systolisch"] < systolisch_span[0]].shape[0]
                / data.shape[0]
                * 100
            )
            systolic_above_target = (
                data[data["Systolisch"] > systolisch_span[1]].shape[0]
                / data.shape[0]
                * 100
            )

            diastolic_within_target = (
                data[
                    (data["Diastolisch"] >= diastolic_span[0])
                    & (data["Diastolisch"] <= diastolic_span[1])
                ].shape[0]
                / data.shape[0]
                * 100
            )
            diastolic_below_target = (
                data[data["Diastolisch"] < diastolic_span[0]].shape[0]
                / data.shape[0]
                * 100
            )
            diastolic_above_target = (
                data[data["Diastolisch"] > diastolic_span[1]].shape[0]
                / data.shape[0]
                * 100
            )

            if ref_data is None or len(ref_data) == 0:
                message = (
                    f"{direction} dem {ref_date_parsed.strftime('%d.%m.%Y')} lagen die {len(data)} Blutdruckmessungen am {period} zwischen {systolic_min}/{diastolic_min} "
                    f"und {systolic_max}/{diastolic_max} mmHg und hatten einen Durchschnitt von {systolic_avg:.0f}/{diastolic_avg:.0f} mmHg. "
                    f"\nDer Puls lag zwischen {pulse_min} und {pulse_max} und hatte einen Durchschnitt von {pulse_avg:.0f} bpm.\n\n"
                    f"- Innerhalb des Ziels:\t{systolic_within_target:.0f}% systolisch,\t{diastolic_within_target:.0f}% diastolisch\n"
                    f"- Unterhalb des Ziels:\t{systolic_below_target:.0f}% systolisch,\t{diastolic_below_target:.0f}% diastolisch\n"
                    f"- Über dem Ziel:\t\t{systolic_above_target:.0f}% systolisch,\t{diastolic_above_target:.0f}% diastolisch"
                )
            else:
                # Compare with reference data and add arrows
                (
                    ref_systolic_avg,
                    ref_diastolic_avg,
                    ref_pulse_avg,
                    ref_systolic_within_target,
                    ref_diastolic_within_target,
                    ref_systolic_below_target,
                    ref_diastolic_below_target,
                    ref_systolic_above_target,
                    ref_diastolic_above_target,
                ) = ref_data

                systolic_avg_arrow = "↑" if systolic_avg > ref_systolic_avg else "↓"
                diastolic_avg_arrow = "↑" if diastolic_avg > ref_diastolic_avg else "↓"
                pulse_avg_arrow = "↑" if pulse_avg > ref_pulse_avg else "↓"
                systolic_within_arrow = (
                    "↑" if systolic_within_target > ref_systolic_within_target else "↓"
                )
                diastolic_within_arrow = (
                    "↑"
                    if diastolic_within_target > ref_diastolic_within_target
                    else "↓"
                )
                systolic_below_arrow = (
                    "↑" if systolic_below_target > ref_systolic_below_target else "↓"
                )
                diastolic_below_arrow = (
                    "↑" if diastolic_below_target > ref_diastolic_below_target else "↓"
                )
                systolic_above_arrow = (
                    "↑" if systolic_above_target > ref_systolic_above_target else "↓"
                )
                diastolic_above_arrow = (
                    "↑" if diastolic_above_target > ref_diastolic_above_target else "↓"
                )

                message = (
                    f"{direction} dem {ref_date_parsed.strftime('%d.%m.%Y')} lagen die {len(data)} Blutdruckmessungen am {period} zwischen {systolic_min}/{diastolic_min} "
                    f"und {systolic_max}/{diastolic_max} mmHg und hatten einen Durchschnitt von {systolic_avg:.0f} ({systolic_avg_arrow})/{diastolic_avg:.0f} ({diastolic_avg_arrow}) mmHg. "
                    f"Der Puls lag zwischen {pulse_min} und {pulse_max} und hatte einen Durchschnitt von {pulse_avg:.0f} bpm ({pulse_avg_arrow}).\n\n"
                    f"- Innerhalb des Ziels:\t{systolic_within_target:.0f}% ({systolic_within_arrow}) systolisch,\t{diastolic_within_target:.0f}% ({diastolic_within_arrow}) diastolisch\n"
                    f"- Unterhalb des Ziels:\t{systolic_below_target:.0f}% ({systolic_below_arrow}) systolisch,\t{diastolic_below_target:.0f}% ({diastolic_below_arrow}) diastolisch\n"
                    f"- Über dem Ziel:\t\t{systolic_above_target:.0f}% ({systolic_above_arrow}) systolisch,\t{diastolic_above_target:.0f}% ({diastolic_above_arrow}) diastolisch"
                )

            return message, (
                systolic_avg,
                diastolic_avg,
                pulse_avg,
                systolic_within_target,
                diastolic_within_target,
                systolic_below_target,
                diastolic_below_target,
                systolic_above_target,
                diastolic_above_target,
            )

        morning_message_before, morning_insights_before = generate_period_trend_message(
            bp_data_before, "Morgen", "Vor"
        )
        evening_message_before, evening_insights_before = generate_period_trend_message(
            bp_data_before, "Abend", "Vor"
        )

        # Generate messages for morning and evening periods
        morning_message, _ = generate_period_trend_message(
            bp_data, "Morgen", ref_data=morning_insights_before
        )
        evening_message, _ = generate_period_trend_message(
            bp_data, "Abend", ref_data=evening_insights_before
        )

        # Dispatch messages
        if morning_message:
            dispatcher.utter_message(morning_message)
        if evening_message:
            dispatcher.utter_message(evening_message)

        if morning_message_before:
            dispatcher.utter_message(morning_message_before)
        if evening_message_before:
            dispatcher.utter_message(evening_message_before)

        def plot_histogram(bp_data, span, period_label, type_label: str):
            plt.figure(figsize=(12, 6))
            palette = (
                sns.color_palette("Reds", 3)
                if type_label == "Systolisch"
                else sns.color_palette("Blues", 3)
            )
            time_categories = ["Morgen", "Abend", "Andere"]
            existing_categories = bp_data["Daytime"].unique()

            # Create the histogram with KDE for systolic blood pressure values grouped by daytime side by side
            sns.histplot(
                data=bp_data,
                x=type_label,
                hue="Daytime",
                multiple="dodge",
                kde=True,
                bins=10,
                palette=palette,
                hue_order=time_categories,
            )
            handles = [
                mpatches.Patch(color=palette[i], label=time_categories[i])
                for i in range(3)
                if time_categories[i] in existing_categories
            ]
            # Add shaded area for target range
            plt.axvspan(
                span[0], span[1], color="lightgreen", alpha=0.3, label="Zielkorridor"
            )

            if "Morgen" in existing_categories:
                morning_mean = bp_data[bp_data["Daytime"] == "Morgen"][
                    type_label
                ].mean()
                plt.axvline(morning_mean, color=palette[0], linestyle="--")
                handles.append(
                    mpatches.Patch(
                        color=palette[0], label=f"µ_morgen: {morning_mean:.2f}"
                    )
                )
            if "Abend" in existing_categories:
                evening_mean = bp_data[bp_data["Daytime"] == "Abend"][type_label].mean()
                plt.axvline(evening_mean, color=palette[1], linestyle="--")
                handles.append(
                    mpatches.Patch(
                        color=palette[1], label=f"µ_abend: {evening_mean:.2f}"
                    )
                )

            # Add titles and labels
            plt.title(
                f"Histogramm der {type_label.lower()}en Blutdruckwerte {period_label}"
            )
            plt.xlabel(f"{type_label}er Blutdruck (mmHg)")
            plt.ylabel("Frequenz")

            # Use palette and time categories to create custom legend
            handles.append(mpatches.Patch(color="lightgreen", label="Zielkorridor"))
            plt.legend(
                title="Tageszeit",
                handles=handles,
                loc="upper left",
                framealpha=0.3,
                frameon=True,
            )

            # Display the plot
            plt.tight_layout()
            filename = str(
                pathlib.Path().parent.absolute()
                / f"tmp_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_veraenderung_ueber_tag_{type_label}_{period_label}.png"
            )
            plt.savefig(filename)
            return filename

        dispatcher.utter_message(
            image=plot_histogram(
                bp_data,
                systolisch_span,
                "seit dem " + str(ref_date_parsed.strftime("%d.%m.%Y")),
                "Systolisch",
            )
        )
        dispatcher.utter_message(
            image=plot_histogram(
                bp_data,
                diastolic_span,
                "seit dem " + str(ref_date_parsed.strftime("%d.%m.%Y")),
                "Diastolisch",
            )
        )
        dispatcher.utter_message(
            image=plot_histogram(
                bp_data_before,
                systolisch_span,
                "vor dem " + str(ref_date_parsed.strftime("%d.%m.%Y")),
                "Systolisch",
            )
        )
        dispatcher.utter_message(
            image=plot_histogram(
                bp_data_before,
                diastolic_span,
                "vor dem " + str(ref_date_parsed.strftime("%d.%m.%Y")),
                "Diastolisch",
            )
        )
        dispatcher.utter_message(
            buttons=[
                {
                    "title": "Wendepunkte",
                    "payload": "Wendepunkte in den Blutdruckwerten anzeigen",
                },{
                    "title": "Gab es Veränderungen in der Medikation?",
                    "payload": "Hat sich der Blutdruck seit dem Medikamentenwechsel verändert?",
                },
                {
                    "title": "Werte außerhalb des Zielkorridors",
                    "payload": "Gab es hohe systolische Messungen im letzten Monat?",
                }
            ])
        return []

    def preprocess_bp_data(self, query):
        results = DBHandler().execute_query(query)
        bp_data = pd.DataFrame(
            results, columns=["Systolisch", "Diastolisch", "Puls", "Datum"]
        )
        bp_data["Datum"] = pd.to_datetime(bp_data["Datum"])
        bp_data["Stunde"] = bp_data["Datum"].dt.hour
        bp_data["Daytime"] = bp_data["Stunde"].apply(
            lambda x: "Morgen" if 6 <= x < 12 else "Abend" if 18 <= x < 24 else "Andere"
        )
        return bp_data
