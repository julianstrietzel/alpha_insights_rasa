import pathlib
from datetime import datetime
from typing import Text

import matplotlib.pyplot as plt
import pandas as pd
import ruptures as rpt
import seaborn as sns
import sklearn.linear_model
from rasa_sdk import Action

from actions.utils import utils
from actions.utils.db_utils import DBHandler
from actions.utils.utils import zeitspanne_to_timespan


class ActionWendepunkte(Action):
    def name(self) -> Text:
        return "action_wendepunkte"

    def run(self, dispatcher, tracker, domain):
        (
            change_date,
            diastolic_span,
            pretty_change_date,
            resulti,
            since_date,
            systolic_span,
            typ,
            user_id,
            zeitspanne,
        ) = init_method_run(tracker)
        if typ not in ["systolisch", "diastolisch"]:
            typ = None

        if not resulti:
            dispatcher.utter_message("Keine Daten gefunden.")
            return []
        data = pd.DataFrame(
            {
                "systolisch": [systolic for systolic, _, _, _ in resulti],
                "diastolisch": [diastolic for _, diastolic, _, _ in resulti],
                "pulse": [pulse for _, _, pulse, _ in resulti],
                "recorded_at": [recorded_at for _, _, _, recorded_at in resulti],
            }
        )
        data["recorded_at"] = pd.to_datetime(data["recorded_at"])
        data["recorded_at_ordinal"] = data["recorded_at"].apply(lambda x: x.toordinal())

        def analyze_inflection_points(data, typ, span):
            signal = data[typ].values
            data["idx"] = range(len(data))

            model = "l2"
            algo = rpt.Dynp(model=model, min_size=7, jump=5).fit(signal)
            inflection_result = algo.predict(n_bkps=3)[:-1]
            plt.figure(figsize=(12, 6))
            sns.scatterplot(data=data, x="idx", y=typ, color="black", label="Messwerte")
            segments = []
            prev = 0
            for bkp in inflection_result:
                segment_data = data.iloc[prev:bkp]
                X = segment_data["recorded_at_ordinal"].values.reshape(-1, 1)
                y = segment_data[typ].values
                reg = sklearn.linear_model.LinearRegression().fit(X, y)
                segments.append((segment_data, reg))
                plt.axvline(
                    x=data["idx"].iloc[bkp],
                    color="r",
                    linestyle="--",
                    label="Wendepunkt" if prev == 0 else None,
                )
                sns.regplot(
                    data=data.iloc[prev:bkp],
                    x="idx",
                    y=typ,
                    scatter=False,
                    color="blue",
                    label="Trendlinie" if prev == 0 else None,
                )
                prev = bkp
            sns.regplot(
                data=data.iloc[prev:], x="idx", y=typ, scatter=False, color="blue"
            )
            segment_data = data.iloc[prev:]
            X = segment_data["recorded_at_ordinal"].values.reshape(-1, 1)
            y = segment_data[typ].values
            segments.append(
                (segment_data, sklearn.linear_model.LinearRegression().fit(X, y))
            )
            plt.axhspan(
                span[0], span[1], color="green", alpha=0.1, label="Normalbereich"
            )
            # Adjust x-axis to display datetime values
            ax = plt.gca()
            plt.xlabel("Datum")
            ax.set_xticks(range(0, len(data), 30))  # <--- set the ticks first
            ax.set_xticklabels(
                data["recorded_at"][range(0, len(data), 30)].dt.strftime("%Y-%m-%d")
            )
            plt.xticks(rotation=45)
            plt.ylabel(f"{typ.capitalize()}er Wert")
            plt.title(f"Wendepunkte in den {typ.capitalize()}en Blutdruckwerten")

            change_dates = [data["recorded_at"].iloc[bkp] for bkp in inflection_result]
            dispatcher.utter_message(
                f"Die drei signifikanten Wendepunkte im {typ.capitalize()}en Blutdruck liegen am {change_dates[0].strftime('%d. %B %Y')}, {change_dates[1].strftime('%d. %B %Y')} und {change_dates[2].strftime('%d. %B %Y')}:"
            )
            summary = []
            for i, (segment_data, reg) in enumerate(segments):
                if len(segment_data) < 7:
                    continue
                start_date = segment_data["recorded_at"].iloc[0].strftime("%d. %B %Y")
                end_date = segment_data["recorded_at"].iloc[-1].strftime("%d. %B %Y")
                start_bp = reg.predict([[segment_data["recorded_at_ordinal"].iloc[0]]])[
                    0
                ]
                end_bp = reg.predict([[segment_data["recorded_at_ordinal"].iloc[-1]]])[
                    0
                ]
                trend = (
                    "Aufwärtstrend"
                    if reg.coef_[0] > 0.05
                    else (
                        "Abwärtstrend" if reg.coef_[0] < -0.05 else "konstanten Verlauf"
                    )
                )
                summary.append(
                    f"{i + 1}. Wir sehen einen {trend} von {start_bp:.0f} auf {end_bp:.0f} vom {start_date} bis zum {end_date}."
                )
            for s in summary:
                dispatcher.utter_message(s)
            if change_date:
                respective_id = data[
                    data["recorded_at"] <= datetime.strptime(change_date, "%Y-%m-%d")
                ].iloc[-1]["idx"]
                plt.axvline(
                    x=respective_id,
                    color="g",
                    linestyle="--",
                    label="Änderungsdatum"
                    + f' ({pd.to_datetime(change_date).strftime("%d.%m.%Y")})',
                )
            filename = str(
                pathlib.Path().parent.absolute()
                / f"tmp_{user_id}_{typ}_wendepunkte_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            )
            # Adjust x-axis to display datetime values
            ax = plt.gca()
            plt.xlabel("Datum")
            ax.set_xticks(range(0, len(data), 30))  # <--- set the ticks first
            ax.set_xticklabels(
                data["recorded_at"][range(0, len(data), 30)].dt.strftime("%Y-%m-%d")
            )
            plt.xticks(rotation=45)
            plt.ylabel(f"{typ.capitalize()}er Wert")
            plt.title(f"Wendepunkte in den {typ.capitalize()}en Blutdruckwerten")
            plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
            plt.tight_layout()
            plt.savefig(filename)
            dispatcher.utter_message(image=filename)

        if typ:
            analyze_inflection_points(
                data, typ, systolic_span if typ == "systolisch" else diastolic_span
            )
        else:
            analyze_inflection_points(data, "systolisch", systolic_span)
            analyze_inflection_points(data, "diastolisch", diastolic_span)


def init_method_run(tracker):
    user_id = tracker.get_slot("user_id") or 25601
    typ = tracker.get_slot("typ") or None
    zeitspanne = next(tracker.get_latest_entity_values("timespan"), None)
    change_date = tracker.get_slot("change_date") or None
    pretty_change_date = (
        pd.to_datetime(change_date).strftime("%d.%m.%Y") if change_date else None
    )
    since_date = bool(change_date)
    systolic_span, diastolic_span, _ = utils.get_blood_pressure_spans(tracker, user_id)
    if zeitspanne:
        timespan = zeitspanne_to_timespan.get(zeitspanne)
        date_filter = (
            f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
        )
    else:
        zeitspanne = tracker.get_slot("timespan") or "Monat"
        timespan = zeitspanne_to_timespan.get(zeitspanne)
        if change_date:
            since_date = True
            date_filter = f"AND CAST(recorded_at AS timestamp) >= '{pd.to_datetime(change_date) - pd.Timedelta(1, 'W')}'"
        else:
            date_filter = (
                f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 {timespan}'"
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
                    {date_filter}
                ORDER BY recorded_at ASC
            """
    resulti = DBHandler().execute_query(query)

    return (
        change_date,
        diastolic_span,
        pretty_change_date,
        resulti,
        since_date,
        systolic_span,
        typ,
        user_id,
        zeitspanne,
    )
