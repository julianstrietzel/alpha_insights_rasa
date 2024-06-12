from typing import Text

from rasa_sdk import Action


class ActionVeraenderungUeberTag(Action):
    def name(self) -> Text:
        return "action_veraenderungen_ueber_tag"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
