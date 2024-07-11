import streamlit as st
import requests
from urllib.parse import urlparse, parse_qs

st.set_page_config(page_title="Rasa Chatbot", page_icon=":robot_face:", layout="centered")

def get_user_id():
    query_params = st.query_params
    return query_params.get('user_id', [''])

def get_bot_response(message):
    url = f"http://localhost:5005/webhooks/rest/webhook"
    payload = {
        "sender": "user",
        "message": message
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

def main():
    user_id = get_user_id()
    if not user_id:
        st.error("User ID not provided in the URL. Please include a user_id parameter.")
        return

    st.title("Rasa Chatbot")
    st.write("Talk to the bot by typing your message and hitting enter.")

    if "messages" not in st.session_state:
        st.session_state.messages = []
        get_bot_response(f"Hello {user_id}")

    if "buttons" not in st.session_state:
        st.session_state.buttons = []

    if "user_message" not in st.session_state:
        st.session_state.user_message = ""

    if "last_button_payload" not in st.session_state:
        st.session_state.last_button_payload = None

    def send_message(user_message):
        if user_message:
            st.session_state.messages.append({"sender": "You", "message": user_message})
            responses = get_bot_response(user_message)
            st.session_state.buttons = []
            for response in responses:
                if "image" in response:
                    st.session_state.messages.append({"sender": "Bot", "image": response["image"]})
                elif "buttons" in response:
                    st.session_state.messages.append({"sender": "Bot", "message": response.get("text", "").replace('\n', '<br>')})
                    st.session_state.buttons = response["buttons"]
                else:
                    st.session_state.messages.append({"sender": "Bot", "message": response.get("text", "").replace('\n', '<br>')})
            st.session_state.user_message = ""

    def on_text_input_change():
        send_message(st.session_state.user_message)
        st.session_state.user_message = ""

    st.markdown("""
        <style>
        .chat-bubble {
            padding: 10px;
            border-radius: 10px;
            margin: 10px;
            width: fit-content;
            max-width: 70%;
            color: black;
        }
        .user-bubble {
            background-color: #DCF8C6;
            align-self: flex-end;
        }
        .bot-bubble {
            background-color: #F1F0F0;
            align-self: flex-start;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
        }
        </style>
        """, unsafe_allow_html=True)

    for msg in st.session_state.messages:
        if msg['sender'] == "You":
            st.markdown(
                '<div class="chat-container"><div class="chat-bubble user-bubble">{}</div></div>'.format(
                    msg["message"].replace("\n", "<br>")
                ),
                unsafe_allow_html=True,
            )
        else:
            if "image" in msg:
                st.image(msg["image"])
            else:
                if msg['message'] == "":
                    continue
                st.markdown(
                    '<div class="chat-container"><div class="chat-bubble bot-bubble"><pre>{}</pre></div></div>'.format(
                        msg["message"].replace("\n", "<br>")
                    ),
                    unsafe_allow_html=True,
                )

    # Display action buttons
    if st.session_state.buttons:
        st.write("Please choose an option:")
        for i, button in enumerate(st.session_state.buttons):
            if st.button(button["title"], key=f"button_{i}"):
                st.session_state.last_button_payload = button["payload"]
                send_message(st.session_state.last_button_payload)
                st.session_state.last_button_payload = None
                st.rerun()

    st.text_input("You: ", key="user_message", on_change=on_text_input_change)

if __name__ == "__main__":
    main()
