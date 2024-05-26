from datetime import datetime
from typing import List

from actions.utils.db_utils import DBHandler


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


def is_critical(systolic, diastolic, pulse, systolic_span, diastolic_span, pulse_span=(60, 160)):
    if systolic > systolic_span[1] or systolic < systolic_span[0]:
        return True
    if diastolic > diastolic_span[1] or diastolic < diastolic_span[0]:
        return True
    if pulse > pulse_span[1] or pulse < pulse_span[0]:
        return True
    return False


def get_bloodpressure(user_id, limit=100, interval = "3 MONTHS") -> List:
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


def check_most_recent_geofence(timestamp:str, user_id:str):
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
        date = datetime.strptime(date, '%Y-%m-%d %H:%M:%S.%f')
    return (datetime.now() - date).days
