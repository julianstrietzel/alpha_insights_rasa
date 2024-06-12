from typing import Text

from rasa_sdk import Action


class ActionWendepunkte(Action):
    def name(self) -> Text:
        return "action_wendepunkte"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
