from typing import Text

from rasa_sdk import Action


class ActionTrendanderungenMedikation(Action):
    def name(self) -> Text:
        return "action_trendaenderungen_medikation"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
