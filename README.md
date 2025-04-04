# TwilioLazadaChat
Testing Twilio Flex - to - Lazada IM Chat Integration using a middleware Python FastAPI program.

## Steps to run this code:
Step 0 (Optional): Create a virtual environment using command ```python venv -m venv``` and then to activate it use this command ```venv\Scripts\activate``` or ```venv\bin\activate```
Step 1: Install requirements using command ```pip install requirements.txt```
Step 2: Add keys in key.env
Step 3: install ngrok if you don't have it and create a public http on port 8000 using command ```ngrok http 8000```
Step 4: copy the url and paste it in the code ```test.py``` > Global variable ```URL```.
Step 5: run the python program using the command ```python test.py``` or ```uvicorn test:app --host 0.0.0.0 --port 8000 --reload```
