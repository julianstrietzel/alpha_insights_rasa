import uuid
from typing import Optional, Text, Any

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Action, Tracker

from actions.action_details_ausreisser import ActionDetailsAusreisser
from actions.action_wendepunkte import ActionWendepunkte


class MockDispatcher(CollectingDispatcher):
    def __init__(self) -> None:
        self.messages = []
        super().__init__()

    def utter_message(self, text: Optional[Text] = None, image: Optional[Text] = None):
        if text:
            self.messages.append(text)
        else:
            self.messages.append(image)

    def utter_attachment(self, attachment: Text, **kwargs: Any) -> None:
        self.messages.append(attachment)


class TestClient:
    def __init__(self, action: Action):
        self.action = action

    def invoke_message(self, message, slots):
        dispatcher = MockDispatcher()

        tracker = Tracker(
            sender_id=str(uuid.uuid4()),
            slots=slots,
            latest_message=message,
            events=[],
            paused=False,
            followup_action="",
            active_loop={},
            latest_action_name=None,
        )

        domain = {}

        slots = self.action.run(dispatcher=dispatcher, tracker=tracker, domain=domain)
        return dispatcher.messages, slots


client = TestClient(ActionWendepunkte())

messages, slots = client.invoke_message(
    None,
    slots={
        "health": "good",
        "geo": "9384z5bj",
        "user_id": "25601",
        "nickname": "testuser",
        "title": "testtitle",
        "home_longitude": "0.0",
        "home_latitude": "0.0",
        "birthday": "2020-01-01",
        "sex": "FEMALE",
        "medical_preconditions": "",
        "timespan": "Woche",
        "typ": "systolisch",
        "change_date": "2024-04-01",
    },
)
print("Messages from dispatcher:\n")
for message in messages:
    print(str(message).strip())
