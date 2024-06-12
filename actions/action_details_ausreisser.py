from typing import Text

from rasa_sdk import Action


class ActionDetailsAusreisser(Action):
    def name(self) -> Text:
        return "action_details_ausreisser"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
