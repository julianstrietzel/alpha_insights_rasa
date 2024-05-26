from datetime import datetime
from typing import Any, Text, Dict, List, Tuple, Optional

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.utils.db_utils import DBHandler, get_blood_pressure_spans, geofence_data_available
from actions.utils.gpt_utils import GPTHandler

from rasa_sdk.events import SlotSet

from actions.utils.utils import get_within, get_trend, is_critical, get_bloodpressure, check_most_recent_geofence, \
    get_days_ago


class ActionAskGPT(Action):
    def __init__(self):
        self.gpt_handler: GPTHandler = GPTHandler()
        super().__init__()

    def name(self) -> Text:
        return "action_ask_gpt"

    async def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        if tracker.get_slot("gpt_confirmed") != "true":
            dispatcher.utter_message("Please confirm that you want to ask GPT.")
            return []
        user_input = next(tracker.latest_message.get('text'), None)
        if user_input is None:
            raise ValueError("No user input provided to ask to GPT.")
            return []
        dispatcher.utter_message("We did not match the request you had to our database. "
                                 "Let me ask GPT, whether it could help us.")
        self.gpt_handler.execute_query(user_input, dispatcher.utter_message)
        continue_query = ("Are you ready with your answer on the previous question? If yes, please answer with 'ready'."
                          " Otherwise use your tools ans knowledge to generate an advanced answer.")

        return []


class ActionSetGPTConfirmed(Action):
    def name(self) -> Text:
        return "action_set_gpt_confirmed"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        return [SlotSet("gpt_confirmed", "true")]

class ActionGetBasicUserDetails(Action):
    def name(self) -> Text:
        return "action_get_basic_user_details"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        print(user_id)
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        details, response = ActionGetBasicUserDetails.get_patient_details(user_id)
        if details is None:
            dispatcher.utter_message("No user found with the provided user id.")
            print(response)
            return []
        slot_events = [SlotSet(key, value) for key, value in details.items() if value is not None]
        print(details)
        if details is None:
            dispatcher.utter_message("No user found with the provided user id.")
            print(response)
            return slot_events
        dispatcher.utter_message(f"User {user_id} has the following details: {response}")
        return slot_events

    @staticmethod
    def get_patient_details(user_id) -> Tuple[Optional[Dict], str]:
        try:
            # Define the SQL query
            query = f"""SELECT id, health, geo, user_id, nickname, title, home_longitude, home_latitude, birthday, sex, 
            medical_preconditions FROM patient WHERE user_id = {user_id};"""

            result = DBHandler().execute_query(query)
            # log result
            print(result)
            # log result datatype
            print(type(result))
            patient_details = None
            if result:
                result = result[0]
                patient_details = {
                    "health": result[1],
                    "geo": result[2],
                    "user_id": result[3],
                    "nickname": result[4],
                    "title": result[5],
                    "home_longitude": result[6],
                    "home_latitude": result[7],
                    "birthday": result[8],
                    "sex": result[9],
                    "medical_preconditions": result[10]
                }

                response = "\n"
                for detail_name, detail_value in [
                    ("ID", patient_details['user_id']),
                    ("Health", patient_details['health']),
                    ("Geo", patient_details['geo']),
                    ("Nickname", patient_details['nickname']),
                    ("Title", patient_details['title']),
                    ("Home Longitude", patient_details['home_longitude']),
                    ("Home Latitude", patient_details['home_latitude']),
                    ("Birthday", patient_details['birthday']),
                    ("Sex", patient_details['sex']),
                    ("Medical Preconditions", patient_details['medical_preconditions'])
                ]:
                    if detail_value is not None:
                        response += f"{detail_name}: {detail_value}\n"
            else:
                response = "No patient found with the given user ID."

            return patient_details, response
        except Exception as e:
            return None, f"An error occurred: {e}"


class ActionRecentBloodPressureReadings(Action):
    def name(self) -> Text:
        return "action_get_most_recent_blood_pressure"

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        result = get_bloodpressure(user_id, 1)
        if not result:
            dispatcher.utter_message("No blood pressure readings found for the provided user id.")
            return []
        print(result)
        recorded_at, systolic, diastolic, pulse = result[0]

        response = (
            f"Most recent reading was recorded {get_days_ago(recorded_at)} days ago, Systolic: {systolic} mmHg, Diastolic: {diastolic} mmHg, Pulse: {pulse}\n")

        dispatcher.utter_message(response)
        return []


class ActionGetUserNickname(Action):
    def name(self) -> Text:
        return "action_get_user_nickname"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        query = f"""SELECT nickname FROM patient WHERE user_id = {user_id};"""
        result = DBHandler().execute_query(query)
        nickname = result[0][0] if result else None
        if nickname is None:
            dispatcher.utter_message("No user found with the provided user id.")
            print(nickname)
            return []
        dispatcher.utter_message(f"The nickname of user {user_id} is {nickname}.")
        return []


class ActionGetBloodPressureTrendsThreeMonths(Action):

    def name(self) -> Text:
        return "action_get_blood_pressure_trends_three_months"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        query = f"""
    SELECT
        DATE_TRUNC('month', CAST(recorded_at AS timestamp)) AS month,
        MAX(systolic) AS max_systolic,
        MIN(systolic) AS min_systolic,
        AVG(systolic) AS avg_systolic,
        MAX(diastolic) AS max_diastolic,
        MIN(diastolic) AS min_diastolic,
        AVG(diastolic) AS avg_diastolic,
        MAX(pulse) AS max_pulse,
        MIN(pulse) AS min_pulse,
        AVG(pulse) AS avg_pulse,
        COUNT(*) AS measurement_count
    FROM bloodpressure
    WHERE user_id = 1900413 AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 MONTHS'
    GROUP BY month
    ORDER BY month;
"""
        results = DBHandler().execute_query(query)
        if not results:
            dispatcher.utter_message(
                "No blood pressure records found for the past three months for the provided user id.")
            return []

        response = "Blood pressure trends for the past three months:\n"
        prev = None
        for record in results:
            month, max_systolic, min_systolic, avg_systolic, max_diastolic, min_diastolic, avg_diastolic, max_pulse, min_pulse, avg_pulse, measurement_count = record
            response += f"Month: {month.strftime('%B %Y')}\n"
            response += f"Measurements: {measurement_count}"
            if prev:
                response += get_trend(prev["measurement_count"], measurement_count)
            response += f"\nMax Systolic: {max_systolic}, Min Systolic: {min_systolic}, Avg Systolic: {avg_systolic:.2f}"
            if prev:
                response += get_trend(prev["avg_systolic"], avg_systolic)
            response += f"\nMax Diastolic: {max_diastolic}, Min Diastolic: {min_diastolic}, Avg Diastolic: {avg_diastolic:.2f}"
            if prev:
                response += get_trend(prev["avg_diastolic"], avg_diastolic)
            response += f"\nMax Pulse: {max_pulse}, Min Pulse: {min_pulse}, Avg Pulse: {avg_pulse:.2f}"
            if prev:
                response += get_trend(prev["avg_pulse"], avg_pulse)
            prev = {
                "month": month,
                "max_systolic": max_systolic,
                "min_systolic": min_systolic,
                "avg_systolic": avg_systolic,
                "max_diastolic": max_diastolic,
                "min_diastolic": min_diastolic,
                "avg_diastolic": avg_diastolic,
                "max_pulse": max_pulse,
                "min_pulse": min_pulse,
                "avg_pulse": avg_pulse,
                "measurement_count": measurement_count
            }
            response += "\n\n"
        systolic_span, diastolic_span, age = get_blood_pressure_spans(tracker, user_id)

        response += (f"Recommended blood pressure spans for patients in this age group ({age}):\n"
                     f"Systolic: {systolic_span[0]} - {systolic_span[1]} "
                     f"({get_within(systolic_span, prev['avg_systolic'])})\n"
                     f"Diastolic: {diastolic_span[0]} - {diastolic_span[1]} "
                     f"({get_within(diastolic_span, prev['avg_diastolic'])})\n")

        dispatcher.utter_message(response)
        return []


class ActionHighBloodPressureReadings(Action):
    def name(self) -> Text:
        return "action_high_blood_pressure_readings"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        # Retrieve the type, direction, and limit from the entities
        bp_type = next(tracker.get_latest_entity_values("type"), "systolic")
        direction = next(tracker.get_latest_entity_values("direction"), "higher")
        limit = next(tracker.get_latest_entity_values("limit"), 0)
        time_span = "3 " + str(next(tracker.get_latest_entity_values("timespan"), "month")).upper()

        # Define the SQL query
        if "low" in direction:
            operator = "<"
        elif "high" in direction:
            operator = ">"
        else:
            dispatcher.utter_message("Invalid direction. Please provide either 'higher' or 'lower'.")
            return []

        if bp_type == "pulse":
            limit = int(limit) if limit and limit != 0 else 110
        else:
            limit = int(limit) if limit and limit != 0 \
                else get_blood_pressure_spans(tracker, user_id)[0 if bp_type == "systolic" else 1][
                0 if operator == "<" else 1]
        query = f"""
        SELECT recorded_at, systolic, diastolic, pulse
        FROM bloodpressure
        WHERE user_id = {user_id} AND {bp_type} {operator} {limit} 
        AND CAST(recorded_at AS timestamp) > NOW() - INTERVAL '{time_span}'
        ORDER BY recorded_at DESC;
        """
        count_all_measurements = f"""
        SELECT COUNT(*)
        FROM bloodpressure
        WHERE user_id = {user_id} AND CAST(recorded_at AS timestamp) > NOW() - INTERVAL '{time_span}';
        """

        # Execute the query
        results = DBHandler().execute_query(query)
        if not results:
            dispatcher.utter_message(
                f"No {bp_type} measurements {direction} than {limit} {'mmhg ' if type != 'pulse' else ''}"
                f"in the past month for the provided user id.")
            return []

        # Format the response
        response = (f"Of the {DBHandler().execute_query(count_all_measurements)[0][0]} blood pressure measurements "
                    f"in the last {time_span.lower()} "
                    f"there are {len(results)} {bp_type.capitalize()} blood pressure readings {direction} than {limit}"
                    f"{' mmhg' if type != 'pulse' else ''}:\n")
        for record in results:
            recorded_at, systolic, diastolic, pulse = record
            response += (f"{datetime.strptime(recorded_at, '%Y-%m-%d %H:%M:%S.%f').strftime('%H:%M, %B %d, %Y')}:"
                         f" Systolic = {systolic} mmHg, diastolic = {diastolic} mmHg, pulse = {pulse}\n")

        dispatcher.utter_message(response)
        return []


class ActionBloodPressureGeofenceCorrelation(Action):
    def name(self) -> Text:
        return "action_blood_pressure_geofence_correlation"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        # Define the SQL query to get blood pressure readings and geofence status
        query = f"""
        SELECT recorded_at, systolic, diastolic, pulse
        FROM bloodpressure
        WHERE user_id = {user_id} AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '3 MONTH'
        ORDER BY recorded_at DESC;
        """

        # Execute the query
        results = DBHandler().execute_query(query)
        if not results:
            dispatcher.utter_message("No blood pressure readings in the past month for the provided user id.")
            return []

        def calculate_average(readings):
            total_systolic = sum(reading[1] for reading in readings)
            total_diastolic = sum(reading[2] for reading in readings)
            count = len(readings)
            return (total_systolic / count, total_diastolic / count) if count else (0, 0)

        # Process the results to determine the correlation
        inside_geofence_readings = []
        outside_geofence_readings = []
        just_left_geofence_readings = []
        still_just_left_geofence_readings = []
        returned_to_geofence_readings = []

        for record in results:
            recorded_at, systolic, diastolic, geofence_status = record
            if geofence_status == 'IN_GEOFENCE':
                inside_geofence_readings.append((recorded_at, systolic, diastolic))
            elif geofence_status == 'OUTSIDE_GEOFENCE':
                outside_geofence_readings.append((recorded_at, systolic, diastolic))
            elif geofence_status == 'JUST_LEFT_GEOFENCE' or geofence_status == 'STILL_JUST_LEFT_GEOFENCE':
                still_just_left_geofence_readings.append((recorded_at, systolic, diastolic))
            elif geofence_status == 'RETURNED_TO_GEOFENCE':
                returned_to_geofence_readings.append((recorded_at, systolic, diastolic))

        # Check if we have enough data for all statuses
        if not inside_geofence_readings or not outside_geofence_readings or not just_left_geofence_readings or not still_just_left_geofence_readings or not returned_to_geofence_readings:
            dispatcher.utter_message(
                "Insufficient data to determine a correlation between blood pressure and geofence status.")
            return []

        # Calculate average readings for each geofence status
        avg_inside = calculate_average(inside_geofence_readings)
        avg_outside = calculate_average(outside_geofence_readings)
        avg_just_left = calculate_average(just_left_geofence_readings)
        avg_still_just_left = calculate_average(still_just_left_geofence_readings)
        avg_returned = calculate_average(returned_to_geofence_readings)

        # Format the response
        response = (f"Correlation between blood pressure and geofence status in the past month:\n"
                    f"Inside Geofence: Average Systolic = {avg_inside[0]:.2f} mmHg, Average Diastolic = {avg_inside[1]:.2f} mmHg\n"
                    f"Outside Geofence: Average Systolic = {avg_outside[0]:.2f} mmHg, Average Diastolic = {avg_outside[1]:.2f} mmHg\n"
                    f"Just Left Geofence: Average Systolic = {avg_just_left[0]:.2f} mmHg, Average Diastolic = {avg_just_left[1]:.2f} mmHg\n"
                    f"Returned to Geofence: Average Systolic = {avg_returned[0]:.2f} mmHg, Average Diastolic = {avg_returned[1]:.2f} mmHg\n"
                    f"Number of readings inside geofence: {len(inside_geofence_readings)}, "
                    f"Number of readings outside geofence: {len(outside_geofence_readings)}, "
                    f"Number of readings just left geofence: {len(just_left_geofence_readings)}, "
                    f"Number of readings still just left geofence: {len(still_just_left_geofence_readings)}, "
                    f"Number of readings returned to geofence: {len(returned_to_geofence_readings)}")
        dispatcher.utter_message(response)
        return []


class ActionBloodPressureTimeOfDay(Action):
    def name(self) -> Text:
        return "action_check_blood_pressure_time_of_day"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id")

        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        results = get_bloodpressure(user_id)

        if not results:
            dispatcher.utter_message("No blood pressure readings found for the provided user id.")
            return []

        time_of_day_readings = {'morning': [], 'afternoon': [], 'evening': [], 'night': []}
        for record in results:
            recorded_at, systolic, diastolic, pulse = record
            hour = datetime.strptime(recorded_at, '%Y-%m-%d %H:%M:%S.%f').hour
            if 6 <= hour < 12:
                time_of_day_readings['morning'].append((systolic, diastolic))
            elif 12 <= hour < 18:
                time_of_day_readings['afternoon'].append((systolic, diastolic))
            elif 18 <= hour < 24:
                time_of_day_readings['evening'].append((systolic, diastolic))
            else:
                time_of_day_readings['night'].append((systolic, diastolic))

        response = "Statistics about blood pressure readings by time of day:\n"
        for time_of_day, readings in time_of_day_readings.items():
            if readings:
                avg_systolic = sum(r[0] for r in readings) / len(readings)
                avg_diastolic = sum(r[1] for r in readings) / len(readings)
                max_systolic = max(r[0] for r in readings)
                min_systolic = min(r[0] for r in readings)
                max_diastolic = max(r[1] for r in readings)
                min_diastolic = min(r[1] for r in readings)
                response += (
                    f"{time_of_day.capitalize()}: Systolic - Avg: {avg_systolic:.2f}, Max: {max_systolic}, Min: {min_systolic}, N: {len(readings)}; "
                    f"Diastolic - Avg: {avg_diastolic:.2f}, Max: {max_diastolic}, Min: {min_diastolic}, N: {len(readings)};\n")

        # attach reasonable spans for this user
        systolic_span, diastolic_span, age = get_blood_pressure_spans(tracker, user_id)
        response += (f"Normal blood pressure spans for this user:\n"
                     f"Systolic: {systolic_span[0]} - {systolic_span[1]}\n"
                     f"Diastolic: {diastolic_span[0]} - {diastolic_span[1]}\n")

        dispatcher.utter_message(response)
        return []


class ActionCriticalBloodPressureAlerts(Action):
    def name(self) -> Text:
        return "action_critical_blood_pressure_alerts"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id")

        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        results = get_bloodpressure(user_id, 1200)
        if not results:
            dispatcher.utter_message("No blood pressure readings found for the provided user id.")
            return []

        systolic_span, diastolic_span, age = get_blood_pressure_spans(tracker, user_id)
        critical_readings = [record for record in results if
                             is_critical(record[1], record[2], record[3], systolic_span, diastolic_span)]

        if not critical_readings:
            dispatcher.utter_message("No critical blood pressure readings found for the provided user id.")
            return []
        response = f"{len(critical_readings)} critical blood pressure readings found for the provided user id:\n"
        response += f"The user is {age} years old. Recommended blood pressure spans: Systolic: {systolic_span[0]} - {systolic_span[1]}, Diastolic: {diastolic_span[0]} - {diastolic_span[1]}\n"
        response += self.add_counts(critical_readings, systolic_span, "systolic")
        response += self.add_counts(critical_readings, diastolic_span, "diastolic")

        dispatcher.utter_message(response)
        return []

    @staticmethod
    def add_counts(critical_readings, span, type: str) -> str:
        relevant = False
        response = f"Number of critical {type} readings in each 10 mmHg span:\n"
        for i in range(0, span[0], 10):
            number_readings_in_span = len([r for r in critical_readings if r[1] in range(i, i + 10)])
            if number_readings_in_span > 0:
                relevant = True
                response += f"{i}-{i + 9} mmHg: {number_readings_in_span} readings\n"
        response += "\n"
        for i in range(span[1], 200, 10):
            number_readings_in_span = len([r for r in critical_readings if r[1] in range(i, i + 10)])
            if number_readings_in_span > 0:
                relevant = True
                response += f"{i}-{i + 9} mmHg: {number_readings_in_span} readings\n"
        response += "\n"
        if not relevant:
            response = ""
        return response


class ActionGetLocationSpecificBloodPressure(Action):
    def name(self) -> Text:
        return "action_get_location_specific_blood_pressure"

    def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        user_id = tracker.get_slot("user_id")

        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        results = get_bloodpressure(user_id, 1000)
        if not results:
            dispatcher.utter_message("No blood pressure readings found for the provided user id.")
            return []
        if not geofence_data_available(user_id):
            dispatcher.utter_message("No geofence data available for the provided user id.")
            return []

        # a) for each reading classify if outside according to check_most_recent_geofence
        # b) calculate most recent and average, min and max systolic, diastolic as well as pulse
        valid_geostati = {
            "inside": ['IN_GEOFENCE', 'RETURNED_TO_GEOFENCE', 'IN'],
            "outside": ['OUTSIDE_GEOFENCE', 'JUST_LEFT_GEOFENCE', 'STILL_JUST_LEFT_GEOFENCE', 'OUT']
        }
        location = next(tracker.get_latest_entity_values('location'), )
        print("valid values" + str(valid_geostati[location]))
        results = [record for record in results
                   if check_most_recent_geofence(record[0], user_id) in valid_geostati[location]]
        print("afterwars" + str(results))
        if not results:
            dispatcher.utter_message(f"No blood pressure readings found for the provided "
                                     f"user id {location} the geofence.")
            return []

        response = f"Blood pressure readings {location} the geofence:\n"
        most_recent = results[0]
        avg_systolic = sum(r[1] for r in results) / len(results)
        avg_diastolic = sum(r[2] for r in results) / len(results)
        avg_pulse = sum(r[3] for r in results) / len(results)
        max_systolic = max(r[1] for r in results)
        min_systolic = min(r[1] for r in results)
        max_diastolic = max(r[2] for r in results)
        min_diastolic = min(r[2] for r in results)
        max_pulse = max(r[3] for r in results)
        min_pulse = min(r[3] for r in results)

        response += (f"Most recent reading {location} geofence was recorded {get_days_ago(most_recent[0])} days ago.\n"
                     f"Systolic: {most_recent[1]} mmHg, Diastolic: {most_recent[2]} mmHg, Pulse: {most_recent[3]}\n")
        response += (f"Min, Average and Max Values:\n"
                     f"Systolic: {min_systolic}, {avg_systolic:.2f}, {max_systolic}\n"
                     f"Diastolic: {min_diastolic}, {avg_diastolic:.2f}, {max_diastolic}\n"
                     f"Pulse: {min_pulse}, {avg_pulse:.2f}, {max_pulse}\n")

        corridor = get_blood_pressure_spans(tracker, user_id)

        response += (f"Recommended blood pressure spans for patients in this age group:\n"
                     f"Systolic: {corridor[0][0]} - {corridor[0][1]}\n"
                     f"Diastolic: {corridor[1][0]} - {corridor[1][1]}\n")

        dispatcher.utter_message(response)
        return []


class ActionBloodPressureHomeVsOther(Action):
    def name(self) -> Text:
        return "action_blood_pressure_home_vs_other"

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        # TODO: Implement the action
        dispatcher.utter_message("This is a dummy action for the intent 'blood_pressure_home_vs_other'.")
        return []


class ActionUserMedicalPreconditions(Action):
    def name(self) -> Text:
        return "action_get_user_medical_preconditions"

    async def run(
            self,
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []

        medical_preconditions, response = ActionUserMedicalPreconditions.get_medical_preconditions(user_id)
        if not medical_preconditions or medical_preconditions == "":
            dispatcher.utter_message("There are not medical preconditions known related to this user.")
            print(response)
            return []

        dispatcher.utter_message(f"User {user_id} has the following medical preconditions: {medical_preconditions}")
        return []

    @staticmethod
    def get_medical_preconditions(user_id) -> Tuple[Optional[str], str]:
        try:
            query = f"SELECT medical_preconditions FROM patient WHERE user_id = {user_id};"
            result = DBHandler().execute_query(query)
            print(result)
            medical_preconditions = None
            if result:
                medical_preconditions = result[0][0]
                response = medical_preconditions if medical_preconditions else "No medical preconditions found."
            else:
                response = "No patient found with the given user ID."

            return medical_preconditions, response
        except Exception as e:
            return None, f"An error occurred: {e}"


class ActionTrendChangesSinceDate(Action):
    def name(self) -> Text:
        return "action_blood_pressure_trend_changed_since_date"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # TODO: Implement the action
        dispatcher.utter_message(
            "This is a dummy action for the intent 'action_blood_pressure_trend_changed_since_date'.")
        return []


class ActionRespondToGreeting(Action):

    def name(self) -> Text:
        return "action_respond_to_greeting"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # if user_id is set call basic information action otherwise utter provide user_id
        user_id = tracker.get_slot("user_id")
        if user_id is None or user_id == "-1":
            dispatcher.utter_message("Please provide a user id.")
            return []
        else:
            return ActionGetBasicUserDetails().run(dispatcher, tracker, domain)
