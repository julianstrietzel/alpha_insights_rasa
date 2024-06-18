import pathlib
from datetime import datetime
from typing import Text

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt
from rasa_sdk import Action

from actions.utils import utils
from actions.utils.db_utils import DBHandler


class ActionTrendanderungenMedikation(Action):
    def name(self) -> Text:
        return "action_trendaenderungen_medikation"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id") or 25601
        change_date = tracker.get_slot("change_date") or None
        change_date_not_str = pd.to_datetime(change_date)
        if not change_date:
            dispatcher.utter_message(
                "Bitte geben Sie ein Datum der relevanten Medikationsänderung an."
            )
            return []
        pretty_change_date = (
            pd.to_datetime(change_date).strftime("%d.%m.%Y") if change_date else None
        )
        systolic_span, diastolic_span, _ = utils.get_blood_pressure_spans(
            tracker, user_id
        )
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
                            AND CAST(recorded_at AS timestamp) >= '{pd.to_datetime(change_date) - pd.Timedelta(4, 'W')}'
                        ORDER BY recorded_at ASC
                    """
        results = DBHandler().execute_query(query)
        bp_data = pd.DataFrame(
            results, columns=["Systolic", "Diastolic", "Pulse", "Date"]
        )
        bp_data["Event"] = bp_data["Date"] >= change_date
        bp_data["Date"] = pd.to_datetime(bp_data["Date"])
        # Add a column to identify the event
        bp_data["Date_num"] = (bp_data["Date"] - bp_data["Date"].min()).dt.days
        bp_data_after = bp_data[bp_data["Date"] >= change_date_not_str]
        bp_data_before = bp_data[bp_data["Date"] < change_date_not_str]
        plt.figure(figsize=(12, 6))

        sns.scatterplot(
            data=bp_data,
            x="Date_num",
            y="Systolic",
            hue="Event",
            style="Event",
            palette="deep",
            markers=["o"],
            s=20,
            legend=False,
        )
        sns.regplot(
            data=bp_data[bp_data["Event"] == False],
            x="Date_num",
            y="Systolic",
            scatter=False,
            label="Trend vor Änderung",
            color="blue",
        )
        sns.regplot(
            data=bp_data[bp_data["Event"] == True],
            x="Date_num",
            y="Systolic",
            scatter=False,
            label="Trend nach Änderung",
            color="red",
        )
        sys_avg_before = bp_data_before["Systolic"].mean()
        sys_avg_after = bp_data_after["Systolic"].mean()
        sys_max_before = bp_data_before["Systolic"].max()
        sys_max_after = bp_data_after["Systolic"].max()
        sys_min_before = bp_data_before["Systolic"].min()
        sys_min_after = bp_data_after["Systolic"].min()

        sys_below_before, sys_within_before, sys_above_before = (
            utils.calculate_percentages(bp_data_before["Systolic"], systolic_span)
        )
        sys_below_after, sys_within_after, sys_above_after = (
            utils.calculate_percentages(bp_data_after["Systolic"], systolic_span)
        )

        plt.axhline(
            y=sys_avg_before,
            color="blue",
            linestyle="--",
            label=f"Sys. Durch. vorher: {sys_avg_before:.1f}",
            alpha=0.5,
        )
        plt.axhline(
            y=sys_avg_after,
            color="red",
            linestyle="--",
            label=f"Sys. Durch. nachher: {sys_avg_after:.1f}",
            alpha=0.5,
        )

        # Same for diastolic
        sns.scatterplot(
            data=bp_data,
            x="Date_num",
            y="Diastolic",
            hue="Event",
            style="Event",
            palette=["green", "orange"],
            markers=["o"],
            s=20,
            legend=False,
        )
        sns.regplot(
            data=bp_data[bp_data["Event"] == False],
            x="Date_num",
            y="Diastolic",
            scatter=False,
            label="Trend vor Änderung",
            color="green",
        )
        sns.regplot(
            data=bp_data[bp_data["Event"] == True],
            x="Date_num",
            y="Diastolic",
            scatter=False,
            label="Trend nach Änderung",
            color="orange",
        )

        dia_avg_before = bp_data_before["Diastolic"].mean()
        dia_avg_after = bp_data_after["Diastolic"].mean()
        dia_max_before = bp_data_before["Diastolic"].max()
        dia_max_after = bp_data_after["Diastolic"].max()
        dia_min_before = bp_data_before["Diastolic"].min()
        dia_min_after = bp_data_after["Diastolic"].min()

        dia_below_before, dia_within_before, dia_above_before = (
            utils.calculate_percentages(bp_data_before["Diastolic"], diastolic_span)
        )
        dia_below_after, dia_within_after, dia_above_after = (
            utils.calculate_percentages(bp_data_after["Diastolic"], diastolic_span)
        )

        plt.axhline(
            y=dia_avg_before,
            color="green",
            linestyle="--",
            label=f"Dias. Durch. vorher: {dia_avg_before:.1f}",
            alpha=0.5,
        )
        plt.axhline(
            y=dia_avg_after,
            color="orange",
            linestyle="--",
            label=f"Dias. Durch. nachher: {dia_avg_after:.1f}",
            alpha=0.5,
        )

        # Add vertical line for the event date
        respective_id = bp_data[bp_data["Date"] <= change_date_not_str].iloc[-1][
            "Date_num"
        ]
        plt.axvline(
            x=respective_id,
            color="black",
            linestyle="--",
            label="Änderungsdatum" + f" ({pretty_change_date})",
            linewidth=1,
        )

        # Add titles and labels
        plt.title(
            "Trendänderung im systolischen und diastolischen Blutdruck seit Medikationsänderung"
        )
        plt.xlabel("Datum")
        plt.ylabel("Systolische und Diastolische Werte (mmHg)")

        xticks = bp_data["Date_num"]
        xlabels = bp_data["Date"].dt.strftime("%Y-%m-%d")
        plt.xticks(
            ticks=xticks[:: int(len(xticks) / 10)],
            labels=xlabels[:: int(len(xticks) / 10)],
            rotation=45,
        )

        # Display the plot
        plt.legend(title="Legend", bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.tight_layout()
        filename = str(
            pathlib.Path().parent.absolute()
            / f"tmp_{user_id}_medikation_trendaenderung_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        )
        plt.savefig(filename)

        def generate_arrow(before, after):
            if before > after:
                return "↓"
            if before < after:
                return "↑"
            else:
                return "→"

        dispatcher.utter_message(
            f"""
        In den Wochen nach dem {pretty_change_date} lagen die Blutdruckmessungen zwischen {sys_min_after}/{dia_min_after} und {sys_max_after}/{dia_max_after} mmHg und hatten einen Durchschnitt von {sys_avg_after:.2f}({generate_arrow(sys_avg_before, sys_avg_after)})/{dia_avg_after:.2f}({generate_arrow(dia_avg_before, dia_avg_after)}) mmHg.
        
        - Innerhalb des Ziels:\t{sys_within_after:.0f}% ({generate_arrow(sys_within_before, sys_within_after)}) systolisch,\t{dia_within_after:.0f}% ({generate_arrow(dia_within_before, dia_within_after)}) diastolisch
        - Unterhalb des Ziels:\t{sys_below_after:.0f}% ({generate_arrow(sys_below_before, sys_below_after)}) systolisch,\t{dia_below_after:.0f}% ({generate_arrow(dia_below_before, dia_below_after)}) diastolisch
        - Über dem Ziel:\t{sys_above_after:.0f}% ({generate_arrow(sys_above_before, sys_above_after)}) systolisch,\t{dia_above_after:.0f}% ({generate_arrow(dia_above_before, dia_above_after)}) diastolisch
        """
        )
        dispatcher.utter_message(
            f"""In den Wochen davor lagen die Messungen zwischen {sys_min_before}/{dia_min_before} mmHg und {sys_max_before}/{dia_max_before} mmHg und hatten einen Durchschnitt von {sys_avg_before:.2f}/{dia_avg_before:.2f} mmHg.
        
        - Innerhalb des Ziels:\t{sys_within_before:.0f}% systolisch,\t{dia_within_before:.0f}% diastolisch
        - Unterhalb des Ziels:\t{sys_below_before:.0f}% systolisch,\t{dia_below_before:.0f}% diastolisch
        - Über dem Ziel:\t{sys_above_before:.0f}% systolisch,\t{dia_above_before:.0f}% diastolisch
        """
        )
        dispatcher.utter_message(image=filename)

        return []
