from typing import Text

from rasa_sdk import Action


class ActionAktuellerBDStatus(Action):
    def name(self) -> Text:
        return "action_aktueller_bd_status"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
