import uuid
from typing import Optional, Text, Any

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Action, Tracker

from actions.action_grund_info import ActionGrundInfo


class MockDispatcher(CollectingDispatcher):
    def __init__(self) -> None:
        self.messages = []
        super().__init__()

    def utter_message(self, text: Optional[Text] = None, image: Optional[Text] = None, buttons = None):
        if text:
            self.messages.append(text)
        else:
            self.messages.append(image)

    def utter_attachment(self, attachment: Text, **kwargs: Any) -> None:
        self.messages.append(attachment)


class TestClient:
    def __init__(self, action: Action):
        self.action = action

    async def invoke_message(self, message, slots):
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

        slots = self.action.run(
            dispatcher=dispatcher, tracker=tracker, domain=domain
        )
        return dispatcher.messages, slots


async def main():
    action = ActionGrundInfo()
    client = TestClient(action)

    messages, slots = await client.invoke_message(
        {"text": "Was ist der maximale Blutdruck von unserem nutzer?"},
        slots={
            "health": "good",
            "geo": "9384z5bj",
            "user_id": "1900413",
            "nickname": "testuser",
            "title": "testtitle",
            "home_longitude": "0.0",
            "home_latitude": "0.0",
            "birthday": "2020-01-01",
            "sex": "FEMALE",
            "medical_preconditions": "",
            "timespan": "Jahr",
            "typ": "",
            "change_date": "Januar",
        },
    )
    print(f"Messages from action {action.name()}:\n")
    for message in messages:
        print(str(message).strip())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
