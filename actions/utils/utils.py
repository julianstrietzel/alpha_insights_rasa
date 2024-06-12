from datetime import datetime
from typing import List, Tuple

from actions.utils.db_utils import DBHandler


def get_patient_details(user_id: str, force_reload=False, tracker=None) -> dict:
    if not force_reload and tracker and tracker.get_slot("birthday"):
        patient_details = {
            "health": tracker.get_slot("health"),
            "geo": tracker.get_slot("geo"),
            "user_id": tracker.get_slot("user_id"),
            "nickname": tracker.get_slot("nickname"),
            "title": tracker.get_slot("title"),
            "home_longitude": tracker.get_slot("home_longitude"),
            "home_latitude": tracker.get_slot("home_latitude"),
            "birthday": tracker.get_slot("birthday"),
            "sex": tracker.get_slot("sex"),
            "medical_preconditions": tracker.get_slot("medical_preconditions"),
        }
        return patient_details
    query = f"""SELECT id, health, geo, user_id, nickname, title, home_longitude, home_latitude, birthday, sex, 
                medical_preconditions FROM patient WHERE user_id = {user_id};"""
    result = DBHandler().execute_query(query)
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
            "medical_preconditions": result[10] or "",
        }
        return patient_details
    else:
        return None


def get_bp_range(birthdate, has_pre_existing_conditions):
    """
    Returns the systolic and diastolic blood pressure ranges based on age and pre-existing conditions.

    Parameters:
    birthdate (str): The birthdate in 'YYYY-MM-DD' format.
    has_pre_existing_conditions (bool): Whether the person has pre-existing conditions.

    Returns:
    tuple: A tuple containing the systolic and diastolic ranges.
    """
    # Define the blood pressure ranges based on age and pre-existing conditions
    systolicTarget = {
        1: [119, 131],  # <65 with pre-existing conditions
        2: [128, 141],  # >65 with pre-existing conditions
        3: [120, 135],  # others
    }

    diastolicTarget = {
        1: [70, 79],  # <65 with pre-existing conditions
        2: [70, 79],  # >65 with pre-existing conditions
        3: [71, 84],  # others
    }

    # Calculate age from birthdate
    birthdate = datetime.strptime(birthdate, "%Y-%m-%d")
    today = datetime.today()
    age = (
        today.year
        - birthdate.year
        - ((today.month, today.day) < (birthdate.month, birthdate.day))
    )

    if has_pre_existing_conditions:
        if age < 65:
            category = 1
        else:
            category = 2
    else:
        category = 3

    systolic_range = systolicTarget[category]
    diastolic_range = diastolicTarget[category]
    return systolic_range, diastolic_range


def get_within(span, value) -> str:
    if span[0] <= value <= span[1]:
        return "within"
    elif value < span[0]:
        return "below"
    elif value > span[1]:
        return "above"
    else:
        return "unknown"


def get_trend(prev, curr) -> str:
    if curr > prev:
        return " (up)"
    elif curr < prev:
        return " (down)"
    else:
        return " (no change)"


def is_critical(
    systolic, diastolic, pulse, systolic_span, diastolic_span, pulse_span=(60, 160)
):
    if systolic > systolic_span[1] or systolic < systolic_span[0]:
        return True
    if diastolic > diastolic_span[1] or diastolic < diastolic_span[0]:
        return True
    if pulse > pulse_span[1] or pulse < pulse_span[0]:
        return True
    return False


def get_bloodpressure(user_id, limit=100, interval="3 MONTHS") -> List:
    query = f"""
    SELECT recorded_at, systolic, diastolic, pulse
    FROM bloodpressure
    WHERE user_id = {user_id}
    """
    print("shit")
    if interval:
        query += f"AND CAST(recorded_at AS timestamp) >= NOW() - INTERVAL '{interval}' "
    query += "ORDER BY recorded_at DESC "
    if limit != 0:
        query += f"LIMIT {limit}"
    query += ";"
    results = DBHandler().execute_query(query)
    return results


def check_most_recent_geofence(timestamp: str, user_id: str):
    query = f"""
    SELECT geo_fence_status
    FROM geo_location
    WHERE user_id = {user_id} 
    AND CAST(recorded_at AS timestamp) <= CAST('{timestamp}' AS timestamp) AND geo_fence_status
    not in ('GEOFENCE_DISABLED', 'UNKNOWN', 'ACCURACY_NEEDS_REFINEMENT', 'ESTIMATED_MEASURE_TO_BE_IGNORED')
    ORDER BY recorded_at DESC
    LIMIT 1;
    """
    result = DBHandler(silent=False).execute_query(query)
    print(result)
    return result[0][0] if result else "unknown"


def get_days_ago(date):
    if date is None:
        return None
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S.%f")
    return (datetime.now() - date).days


def get_blood_pressure_spans(
    tracker, user_id
) -> Tuple[Tuple[int, int], Tuple[int, int], str]:
    birthday = (
        datetime.strptime(tracker.get_slot("birthday"), "%Y-%m-%d")
        if tracker.get_slot("birthday") is not None
        else None
    )
    if not birthday:
        query = f"""SELECT birthday FROM patient WHERE user_id = {user_id};"""
        result = DBHandler().execute_query(query)[0]
        print(result)
        birthday = datetime.strptime(result[0], "%Y-%m-%d") if result else None
    if birthday:
        age = (datetime.now() - birthday).days // 365
        if age < 18:
            systolic_span = (90, 120)
            diastolic_span = (60, 80)
        elif age < 40:
            systolic_span = (110, 130)
            diastolic_span = (70, 85)
        elif age < 60:
            systolic_span = (120, 140)
            diastolic_span = (75, 90)
        else:
            systolic_span = (130, 150)
            diastolic_span = (80, 95)

    else:
        systolic_span = (120, 130)
        diastolic_span = (80, 85)
        age = "unknown"
    return systolic_span, diastolic_span, str(age)


def geofence_data_available(user_id) -> bool:
    """
    Check if valid geofence data is available for the user
    :param user_id:
    :return: boolean
    """
    query = f"""SELECT *
FROM geo_location
WHERE user_id = {user_id}
  AND geo_fence_status
    not in ('GEOFENCE_DISABLED', 'UNKNOWN', 'ACCURACY_NEEDS_REFINEMENT', 'ESTIMATED_MEASURE_TO_BE_IGNORED')
ORDER BY recorded_at DESC
LIMIT 1;"""
    return bool(DBHandler().execute_query(query))
