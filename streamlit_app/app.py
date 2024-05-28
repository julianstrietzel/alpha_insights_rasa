import streamlit as st
import requests

st.set_page_config(page_title="Rasa Chatbot", page_icon=":robot_face:", layout="centered")

def get_bot_response(message):
    url = "http://localhost:5005/webhooks/rest/webhook"
    payload = {
        "sender": "user",
        "message": message
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

st.title("Rasa Chatbot")
st.write("Talk to the bot by typing your message and hitting enter.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.write(f"{msg['sender']}: {msg['message']}")

user_message = st.text_input("You: ", "")

if st.button("Send"):
    if user_message:
        st.session_state.messages.append({"sender": "You", "message": user_message})

        responses = get_bot_response(user_message)
        for response in responses:
            st.session_state.messages.append({"sender": "Bot", "message": response.get("text", "")})
        
        st.experimental_rerun()
