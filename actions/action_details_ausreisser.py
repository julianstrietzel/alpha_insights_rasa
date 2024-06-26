import pathlib
from datetime import datetime
from typing import Text

import matplotlib.pyplot as plt
import matplotlib.transforms as transforms
import pandas as pd
import seaborn as sns
from rasa_sdk import Action

from actions import ddp
from actions.utils import utils
from actions.utils.db_utils import DBHandler
from actions.utils.utils import zeitspanne_to_timespan, at_the_last_prefix


class ActionDetailsAusreisser(Action):
    def name(self) -> Text:
        return "action_details_ausreisser"

    def run(self, dispatcher, tracker, domain):
        user_id = tracker.get_slot("user_id") or 25601
        typ = tracker.get_slot("typ") or None
        zeitspanne = next(tracker.get_latest_entity_values("timespan"), None)
        change_date_input = tracker.get_slot("change_date") or None
        if change_date_input:
            change_date_parsed = ddp.get_date_data(change_date_input).date_obj
        else:
            change_date_parsed = None
        since_date = bool(change_date_parsed)
        systolic_span, diastolic_span, _ = utils.get_blood_pressure_spans(
            tracker, user_id
        )

        if zeitspanne:
            timespan = zeitspanne_to_timespan.get(zeitspanne)
            date_filter = (
                f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
            )
        else:
            zeitspanne = tracker.get_slot("timespan") or "Monat"
            timespan = zeitspanne_to_timespan.get(zeitspanne)
            if since_date:
                since_date = True
                date_filter = f"AND CAST(recorded_at AS timestamp) >= '{change_date_parsed.strftime('%Y-%m-%d')}'"
            else:
                date_filter = f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"

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
                ORDER BY recorded_at ASC
            """
        resulti = DBHandler().execute_query(query)
        if not resulti:
            dispatcher.utter_message("Keine Daten gefunden.")
            return []

        df = df_from_result(utils.recorded_at_to_datetime(resulti))

        # Function to detect outliers
        def detect_outliers(series):
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 0.5 * iqr
            upper_bound = q3 + 0.5 * iqr
            return (series < lower_bound) | (series > upper_bound)

        # Add outlier columns
        df["Systolische Ausreißer"] = detect_outliers(df["Systolisch"])
        df["Diastolische Ausreißer"] = detect_outliers(df["Diastolisch"])

        df[zeitspanne.capitalize()] = (
            df["Datum"].dt.to_period(timespan.capitalize()[0]).astype(str)
        )

        def plot_box_and_outliers(typ=typ):
            color = "red" if typ == "systolisch" else "blue"
            plt.figure(figsize=(10, 6))
            sns.boxplot(
                x=zeitspanne.capitalize(), y=typ.capitalize(), data=df, color=color
            )
            sns.scatterplot(
                x=zeitspanne.capitalize(),
                y=typ.capitalize(),
                data=df[df[f"{typ.capitalize()}e Ausreißer"]],
                hue="Tageszeit ",
                color=color,
            )
            plt.title(
                f"{typ.capitalize()}er Blutdruck Boxplot nach {zeitspanne.capitalize()}"
            )

            span = systolic_span if typ == "systolisch" else diastolic_span
            # highlight target range
            plt.axhspan(span[0], span[1], color="green", alpha=0.2)

            # rotate x-axis labels
            plt.xticks(rotation=45)

            if since_date:
                df["Änderungsdatum"] = pd.to_datetime(change_date_parsed).to_period(
                    timespan.capitalize()[0]
                )
                vline = plt.axvline(
                    x=df["Änderungsdatum"].astype(str).iloc[0],
                    color="red",
                    linestyle="--",
                    label="Änderungsdatum"
                    + f" ({change_date_parsed.strftime('%d.%m.%Y')})",
                )
                ax = plt.gca()
                trans = transforms.blended_transform_factory(ax.transData, ax.transAxes)
                vline.set_transform(
                    trans
                    + transforms.ScaledTranslation(
                        -20 / 72.0, 0, plt.gcf().dpi_scale_trans
                    )
                )

                plt.legend()
            filename = str(
                pathlib.Path().parent.absolute()
                / (
                    f"tmp_{typ}_boxplot_{zeitspanne}_and_outliers_"
                    + str(datetime.now())
                    + ".png"
                )
            )
            plt.tight_layout()
            plt.savefig(filename)
            return filename

        current_date_one_timespan_ago = (
            pd.to_datetime(datetime.now())
            - pd.DateOffset(
                months=1 if zeitspanne == "Monat" else 1,
                days=1 if zeitspanne == "Tag" else 0,
                weeks=1 if zeitspanne == "Woche" else 0,
                years=1 if zeitspanne == "Jahr" else 0,
            )
        ).strftime("%Y-%m-%d")
        df_recently = (
            df[df["Datum"] >= current_date_one_timespan_ago]
            if not since_date
            else df[df["Datum"] >= pd.to_datetime(change_date_parsed)]
        )

        utter_quote_outliers_recently(
            df_recently,
            dispatcher,
            change_date_parsed,
            since_date,
            zeitspanne,
        )

        recent_dia_outliers, recent_sys_outliers = utter_outliers_daytime(
            df, df_recently, diastolic_span, dispatcher, systolic_span
        )

        if since_date:
            utter_change_in_outliers_since_date(
                change_date_parsed,
                detect_outliers,
                df_recently,
                dispatcher,
                recent_dia_outliers,
                recent_sys_outliers,
                user_id,
            )

        if typ in ["diastolisch", "systolisch"]:
            dispatcher.utter_message(image=plot_box_and_outliers())
        else:
            dispatcher.utter_message(image=plot_box_and_outliers("systolisch"))
            dispatcher.utter_message(image=plot_box_and_outliers("diastolisch"))
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
            ]
        )
        return []


# Die Anzahl der Ausreißer hat sich nach der Medikamentenänderung am ... signifikant auf 20% und 5% reduziert.
def utter_change_in_outliers_since_date(
    change_date_parsed,
    detect_outliers,
    df_recently,
    dispatcher,
    recent_dia_outliers,
    recent_sys_outliers,
    user_id,
):
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
                        AND CAST(recorded_at AS timestamp) <= '{change_date_parsed.strftime('%Y-%m-%d')}'
                """
    results = DBHandler().execute_query(query)
    if not results:
        dispatcher.utter_message(
            "Keine Daten vor dem Änderungsdatum gefunden. Die Anzahl der Ausreißer kann nicht verglichen werden."
        )
        return
    df_before = df_from_result(utils.recorded_at_to_datetime(results))
    sys_percent_after = len(recent_sys_outliers) / len(df_recently) * 100
    dia_percent_after = len(recent_dia_outliers) / len(df_recently) * 100
    # Add outlier columns
    df_before["Systolische Ausreißer"] = detect_outliers(df_before["Systolisch"])
    df_before["Diastolische Ausreißer"] = detect_outliers(df_before["Diastolisch"])
    sys_percent_before = (
        len(df_before[df_before["Systolische Ausreißer"]]) / len(df_before) * 100
    )
    dia_percent_before = (
        len(df_before[df_before["Diastolische Ausreißer"]]) / len(df_before) * 100
    )
    dispatcher.utter_message(
        f"Die Quote der Ausreißer im systolischen Blutwert hat sich seit dem {change_date_parsed.strftime('%d.%m.%Y')} von {round(sys_percent_before)}% auf {round(sys_percent_after)}% "
        + ("erhöht." if sys_percent_after > sys_percent_before else "verringert.")
    )
    dispatcher.utter_message(
        f"Die Quote der Ausreißer im diastolischen Blutwert hat sich seit dem {change_date_parsed.strftime('%d.%m.%Y')} von {round(dia_percent_before)}% auf {round(dia_percent_after)}% "
        + ("erhöht." if dia_percent_after > dia_percent_before else "verringert.")
    )


def df_from_result(results):
    data = {
        "Datum": [recorded_at for systolic, diastolic, pulse, recorded_at in results],
        "Systolisch": [
            int(systolic) for systolic, diastolic, pulse, recorded_at in results
        ],
        "Diastolisch": [
            int(diastolic) for systolic, diastolic, pulse, recorded_at in results
        ],
        "Puls": [int(pulse) for systolic, diastolic, pulse, recorded_at in results],
        "Tageszeit ": [
            utils.get_time_of_day(recorded_at) + " Ausreißer"
            for systolic, diastolic, pulse, recorded_at in results
        ],
        "Tageszeit": [
            utils.get_time_of_day(recorded_at)
            for systolic, diastolic, pulse, recorded_at in results
        ],
    }
    df_before = pd.DataFrame(data)
    return df_before


# In der letzten Woche waren 50% der systolischen und 30% der diastolischen Messungen extreme Ausreißer.
def utter_quote_outliers_recently(
    df_recently, dispatcher, change_date, since_date, zeitspanne
):
    # In der letzten Woche waren 50% der systolischen und 30% der diastolischen Messungen extreme Ausreißer.
    pretty_change_date = change_date.strftime("%d.%m.%Y") if change_date else None
    if len(df_recently) > 0:
        sys_outliers_quote = round(
            len(df_recently[df_recently["Systolische Ausreißer"]])
            / len(df_recently)
            * 100
        )
        dia_outliers_quote = round(
            len(df_recently[df_recently["Diastolische Ausreißer"]])
            / len(df_recently)
            * 100
        )
        dynamic_message = (
            at_the_last_prefix[zeitspanne]
            if not since_date
            else f"Seit dem {pretty_change_date}"
        ) + (
            f" gab es keine Ausreißer."
            if sys_outliers_quote == 0 and dia_outliers_quote == 0
            else (
                " waren "
                + str(sys_outliers_quote)
                + "% der systolischen und "
                + str(dia_outliers_quote)
                + "% der diastolischen Messungen extreme Ausreißer."
            )
        )
        dispatcher.utter_message(dynamic_message)
    else:
        dispatcher.utter_message(
            "Es gibt keine Messungen "
            + (
                at_the_last_prefix[zeitspanne].lower() + "."
                if not since_date
                else "seit dem " + pretty_change_date + "."
            )
        )


# Alle diese Messungen wurden am Morgen vorgenommen. / Von diesen waren 50% (sys) und 100% (diastolisch) am Morgen.
# 50% (sys) und 100% (dias) der Ausreißer lagen über dem Zielbereich. /
def utter_outliers_daytime(df, df_recently, diastolic_span, dispatcher, systolic_span):
    recent_sys_outliers = df_recently[df_recently["Systolische Ausreißer"]]
    recent_dia_outliers = df_recently[df_recently["Diastolische Ausreißer"]]
    if len(df_recently["Tageszeit"].unique()) > 1:
        most_common_tageszeit = (pd.concat([recent_sys_outliers, recent_dia_outliers]))[
            "Tageszeit"
        ].mode()[0]
        count_sys_outliers = len(recent_sys_outliers)
        count_sys_at_tageszeit = len(
            recent_sys_outliers[
                recent_sys_outliers["Tageszeit"] == most_common_tageszeit
            ]
        )
        count_dia_outliers = len(recent_dia_outliers)
        count_dia_at_tageszeit = len(
            recent_dia_outliers[
                recent_dia_outliers["Tageszeit"] == most_common_tageszeit
            ]
        )
        dispatcher.utter_message(
            f"{round(count_sys_at_tageszeit / count_sys_outliers * 100)}% der systolischen und "
            + f"{round(count_dia_at_tageszeit / count_dia_outliers * 100)}% der diastolischen Ausreißer "
            + "wurden am "
            + most_common_tageszeit.capitalize()
            + " aufgenommen."
        )

    else:
        dispatcher.utter_message(
            "Alle Ausreißer wurden am "
            + df["Tageszeit"].unique()[0].capitalize()
            + " aufgenommen."
        )
    df_recently["sys_above"] = recent_sys_outliers["Systolisch"] > systolic_span[1]
    df_recently["dia_above"] = recent_dia_outliers["Diastolisch"] > diastolic_span[1]
    df_recently["sys_below"] = recent_sys_outliers["Systolisch"] < systolic_span[0]
    df_recently["dia_below"] = recent_dia_outliers["Diastolisch"] < diastolic_span[0]
    perc_above_sys = (
        df_recently["sys_above"].sum() / len(recent_sys_outliers) * 100
        if len(recent_sys_outliers) > 0
        else 0
    )
    perc_above_dia = (
        df_recently["dia_above"].sum() / len(recent_dia_outliers) * 100
        if len(recent_dia_outliers) > 0
        else 0
    )
    perc_below_sys = (
        df_recently["sys_below"].sum() / len(recent_sys_outliers) * 100
        if len(recent_sys_outliers) > 0
        else 0
    )
    perc_below_dia = (
        df_recently["dia_below"].sum() / len(recent_dia_outliers) * 100
        if len(recent_dia_outliers) > 0
        else 0
    )
    if perc_above_sys > 0 or perc_below_sys > 0:
        dispatcher.utter_message(
            f"{round(max(perc_above_sys, perc_below_sys))}% der systolischen Ausreißer liegen {f'über {systolic_span[1]} mmHg' if perc_above_sys > perc_below_sys else f'unter {systolic_span[0]} mmHg'}."
        )
    else:
        dispatcher.utter_message(
            "Keine systolischen Ausreißer liegen außerhalb des Zielkorridors."
        )
    if perc_above_dia > 0 or perc_below_dia > 0:
        dispatcher.utter_message(
            f"{round(max(perc_above_dia, perc_below_dia))}% der diastolischen Ausreißer liegen {f'über {diastolic_span[1]} mmHg' if perc_above_dia > perc_below_dia else f'unter {diastolic_span[0]} mmHg'}."
        )
    else:
        dispatcher.utter_message(
            "Keine diastolischen Ausreißer liegen außerhalb des Zielkorridors."
        )
    return recent_dia_outliers, recent_sys_outliers
