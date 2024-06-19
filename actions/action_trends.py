from typing import Text

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from rasa_sdk import Action

from actions import ddp
from actions.utils.db_utils import DBHandler
from actions.utils.utils import get_patient_details, get_bp_range, month_to_german


class ActionTrends(Action):
    def name(self) -> Text:
        return "action_trends"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id")
        change_date = tracker.get_slot("change_date") or None
        change_date_parsed = (
            ddp.get_date_data(change_date).date_obj if change_date else None
        )

        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Bitte geben Sie eine Benutzer-ID an.")
            return []

        patient_details = get_patient_details(user_id, tracker)
        systolisch_span, diastolic_span = get_bp_range(
            patient_details["birthday"], bool(patient_details["medical_preconditions"])
        )
        six_months_ago_beginning_of_month = (pd.Timestamp.now() - pd.DateOffset(months=6)).replace(day=1).strftime(
            "%Y-%m-%d")
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
                    AND CAST(recorded_at AS timestamp) >= '{six_months_ago_beginning_of_month}'
            """

        results = DBHandler().execute_query(query)
        bp_data = pd.DataFrame(
            results, columns=["Systolisch", "Diastolisch", "Puls", "Datum"]
        )

        bp_data["Datum"] = pd.to_datetime(bp_data["Datum"])
        bp_data["Datum_num"] = (bp_data["Datum"] - bp_data["Datum"].min()).dt.days
        bp_data["Month"] = bp_data["Datum"].dt.month
        bp_data["Monthly_average_systolic"] = bp_data.groupby("Month")["Systolisch"].transform("mean")
        bp_data["Monthly_average_diastolic"] = bp_data.groupby("Month")["Diastolisch"].transform("mean")

        plt.figure(figsize=(12, 8))

        # Scatter plot for Systolisch
        sns.scatterplot(data=bp_data, x='Datum_num', y='Systolisch', color="red", legend=False)

        # Regression lines for Systolisch by month
        first = True
        for month, group in bp_data.groupby('Month'):
            sns.regplot(data=group, x='Datum_num', y='Systolisch', scatter=False,
                        label=f'Systolische Trends' if first else "", truncate=True, color='r')
            first = False

        # Scatter plot for Diastolic
        sns.scatterplot(data=bp_data, x='Datum_num', y='Diastolisch', color='b', legend=False)

        # Regression lines for Diastolic by month
        first = True
        for month, group in bp_data.groupby('Month'):
            sns.regplot(data=group, x='Datum_num', y='Diastolisch', scatter=False,
                        label=f'Diastolische Trends' if first else "", truncate=True, color='b')
            first = False

        # Add vertical line for the event date
        if change_date_parsed:
            respective_id = bp_data[bp_data["Datum"] <= change_date_parsed].iloc[-1][
                "Datum_num"
            ]
            plt.axvline(
                x=respective_id,
                color="black",
                linestyle="--",
                label="Änderungsdatum" + f" ({change_date_parsed.strftime('%d.%m.%Y')})",
                linewidth=1,
            )

        # Add target coridors for systolic and diastolic
        plt.axhspan(
            diastolic_span[0], diastolic_span[1], color="green", alpha=0.1, label="Normalbereiche"
        )
        plt.axhspan(
            systolisch_span[0], systolisch_span[1], color="green", alpha=0.1
        )

        # Add titles and labels
        plt.title('Blutdruckentwicklung der letzten 6 Monate')
        plt.xlabel('Datum')
        plt.ylabel('Blutdruck Diastolisch und Systolisch (mmHg)')
        plt.legend()

        # Add x-axis labels
        xticks = bp_data["Datum_num"]
        # pretty date labels month and year
        xlabels = bp_data["Datum"].dt.strftime("%b %Y")
        # Filter always first appearing date of month if available otherwise next larger
        xticks = xticks[~xlabels.duplicated(keep='first')]
        xlabels = xlabels[~xlabels.duplicated(keep='first')]
        plt.xticks(
            ticks=xticks,
            labels=xlabels,
            rotation=45,
        )

        # Display the plot
        plt.tight_layout()
        plt.show()

        trend_messages = generate_trend_messages(bp_data, systolisch_span, diastolic_span)
        for message in trend_messages:
            dispatcher.utter_message(message)

        return []


from sklearn.linear_model import LinearRegression

def generate_trend_messages(bp_data, systolisch_span, diastolic_span):
    trend_messages = []
    months = bp_data["Month"].unique()
    previous_month_values = None

    for month in sorted(months):
        month_data = bp_data[bp_data["Month"] == month]
        year = month_data["Datum"].dt.strftime("%Y").iloc[0]
        month_id = month_data["Datum"].dt.strftime("%m").iloc[0]
        monat = month_to_german[month_id]
        systolic_min = month_data["Systolisch"].min()
        systolic_max = month_data["Systolisch"].max()
        systolic_avg = month_data["Systolisch"].mean()
        diastolic_min = month_data["Diastolisch"].min()
        diastolic_max = month_data["Diastolisch"].max()
        diastolic_avg = month_data["Diastolisch"].mean()
        pulse_min = month_data["Puls"].min()
        pulse_max = month_data["Puls"].max()
        pulse_avg = month_data["Puls"].mean()

        systolic_within_target = month_data[(month_data["Systolisch"] >= systolisch_span[0]) & (
                month_data["Systolisch"] <= systolisch_span[1])].shape[0] / month_data.shape[0] * 100
        systolic_below_target = month_data[month_data["Systolisch"] < systolisch_span[0]].shape[0] / month_data.shape[
            0] * 100
        systolic_above_target = month_data[month_data["Systolisch"] > systolisch_span[1]].shape[0] / month_data.shape[
            0] * 100

        diastolic_within_target = month_data[(month_data["Diastolisch"] >= diastolic_span[0]) & (
                month_data["Diastolisch"] <= diastolic_span[1])].shape[0] / month_data.shape[0] * 100
        diastolic_below_target = month_data[month_data["Diastolisch"] < diastolic_span[0]].shape[0] / month_data.shape[
            0] * 100
        diastolic_above_target = month_data[month_data["Diastolisch"] > diastolic_span[1]].shape[0] / month_data.shape[
            0] * 100

        # Perform linear regression for systolic trend
        X_systolic = month_data["Datum_num"].values.reshape(-1, 1)
        y_systolic = month_data["Systolisch"].values
        systolic_model = LinearRegression().fit(X_systolic, y_systolic)
        systolic_trend = "Aufwärtstrend" if systolic_model.coef_[0] > 0 else "Abwärtstrend"

        # Calculate systolic regression start and end values
        systolic_start = systolic_model.predict([[X_systolic.min()]])[0]
        systolic_end = systolic_model.predict([[X_systolic.max()]])[0]

        # Perform linear regression for diastolic trend
        X_diastolic = month_data["Datum_num"].values.reshape(-1, 1)
        y_diastolic = month_data["Diastolisch"].values
        diastolic_model = LinearRegression().fit(X_diastolic, y_diastolic)
        diastolic_trend = "Aufwärtstrend" if diastolic_model.coef_[0] > 0 else "Abwärtstrend"

        # Calculate diastolic regression start and end values
        diastolic_start = diastolic_model.predict([[X_diastolic.min()]])[0]
        diastolic_end = diastolic_model.predict([[X_diastolic.max()]])[0]

        # Compare with previous month
        if previous_month_values:
            prev_systolic_within_target, prev_diastolic_within_target, prev_systolic_below_target, prev_diastolic_below_target, prev_systolic_above_target, prev_diastolic_above_target = previous_month_values

            systolic_within_arrow = "↑" if systolic_within_target > prev_systolic_within_target else "↓"
            diastolic_within_arrow = "↑" if diastolic_within_target > prev_diastolic_within_target else "↓"
            systolic_below_arrow = "↑" if systolic_below_target > prev_systolic_below_target else "↓"
            diastolic_below_arrow = "↑" if diastolic_below_target > prev_diastolic_below_target else "↓"
            systolic_above_arrow = "↑" if systolic_above_target > prev_systolic_above_target else "↓"
            diastolic_above_arrow = "↑" if diastolic_above_target > prev_diastolic_above_target else "↓"
        else:
            systolic_within_arrow = diastolic_within_arrow = systolic_below_arrow = diastolic_below_arrow = systolic_above_arrow = diastolic_above_arrow = ""

        # Update previous month values
        previous_month_values = (systolic_within_target, diastolic_within_target, systolic_below_target, diastolic_below_target, systolic_above_target, diastolic_above_target)

        message = (
            f"Blutdrucktrends für {monat} {year}:\n\n"
            f"Im {monat} lagen die Blutdruckmessungen zwischen {systolic_min}/{diastolic_min} und {systolic_max}/{diastolic_max} mmHg "
            f"und hatten einen Durchschnitt von {systolic_avg:.0f}/{diastolic_avg:.0f} mmHg. Der Puls lag zwischen {pulse_min} und {pulse_max} "
            f"und hatte einen Durchschnitt von {pulse_avg:.0f} bpm.\n\n"
            f"-\tInnerhalb des Ziels:\t{systolic_within_target:.0f}%{systolic_within_arrow} (systolisch),\t{diastolic_within_target:.0f}%{diastolic_within_arrow} (diastolisch)\n"
            f"-\tUnterhalb des Ziels:\t{systolic_below_target:.0f}%{systolic_below_arrow} (systolisch),\t{diastolic_below_target:.0f}%{diastolic_below_arrow} (diastolisch)\n"
            f"-\tÜber dem Ziel:\t\t{systolic_above_target:.0f}%{systolic_above_arrow} (systolisch),\t\t{diastolic_above_target:.0f}%{diastolic_above_arrow} (diastolisch)\n\n"
            f"Der {monat} zeigt einen {systolic_trend} im systolischen Blutdruck von {systolic_start:.1f} bis {systolic_end:.1f} mmHg "
            f"und einen {diastolic_trend} im diastolischen Blutdruck von {diastolic_start:.1f} bis {diastolic_end:.1f} mmHg."
        )

        trend_messages.append(message)

    return trend_messages
