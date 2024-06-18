from defog import Defog


class DefogHandler:
    def __init__(self):
        self.defog = Defog()
        self.defog.update_glossary(
            """
        - geofence_detailed_status: IN_GEOFENCE,STILL_JUST_LEFT_GEOFENCE,RETURNED_TO_GEOFENCE,JUST_LEFT_GEOFENCE,OUTSIDE_GEOFENCE -> Within geofence there usually is a known environment.
        - recorded_at (timestamp): Time of recording in YYYY-MM-DD HH24:MI:SS.US.
        - user_id (bigint): patient identifier.
        - sex is FEMALE or MALE
        - The target corridor for systolic blood pressure is [90, 120] and for diastolic blood pressure is [60, 80].
        """
        )

    def ask_query(self, query, user_id, backgroudn_info_string_for_llm):
        return self.defog.run_query(
            f"User Input: {query}; Background Information: {backgroudn_info_string_for_llm}",
            f"Only consider data from patient with user_id = {user_id}",
        )
