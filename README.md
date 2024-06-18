**use python 3.9**

`rasa train` to train the model  
`rasa shell --debug ` to test the model locally  
`rasa run actions` to run the custom actions server
Set the OPENAI_API_KEY environment variable to your OpenAI API key.

### For deploying to streamlit

`rasa run -m models --enable-api --cors "*"
`  
`rasa run actions
`  
`cd streamlit_app  
`  
`streamlit run app.py`

### to run defog

use python 3.9
defog init -> Use defog api key
defog gen bloodpressure geo_location patient

https://docs.defog.ai/defog-python/