from typing import Text

from rasa_sdk import Action


class ActionAblesungenAusserhalbZielbereich(Action):
    def name(self) -> Text:
        return "action_ablesungen_ausserhalb_zielbereich"

    def run(self, dispatcher, tracker, domain):
        dispatcher.utter_message(self.name())
        return []
