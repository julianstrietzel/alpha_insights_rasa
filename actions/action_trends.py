from typing import Text

from rasa_sdk import Action


class ActionTrends(Action):
    def name(self) -> Text:
        return "action_trends"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
