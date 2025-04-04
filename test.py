from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from twilio.rest import Client
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
import lazop_sdk as lazop
from datetime import datetime, timedelta
import os, json, logging, urllib.parse, requests
 
# Load environment variables
load_dotenv("keys.env")
 
app = FastAPI()
curConversation = {}
curUser = set()
# ngrok URL for webhook and auth code callback
URL = "https://4621-36-50-163-241.ngrok-free.app"
# Set up Twilio client
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

# Set up logging
logging.basicConfig(level=logging.INFO)

def authURL(url:str , params:dict) -> str:
    parsed_url = list(urllib.parse.urlparse(url))
    parsed_url[4] = urllib.parse.urlencode(params)
    return urllib.parse.urlunparse(parsed_url)

def get_lazada_session_data(appkey, appsecret, access_token, session_id):
    try:
        # Initialize LazopClient with URL, appkey, and appsecret
        url = "https://api.lazada.com/rest"
        client = lazop.LazopClient(url, appkey, appsecret)
        # Create LazopRequest for the '/im/session/get' endpoint
        request = lazop.LazopRequest('/im/session/get', 'GET')
        # Add the session_id parameter
        request.add_api_param('session_id', session_id)
        # Execute the request with the access token for authentication
        response = client.execute(request, access_token)
        # Check the response and return it as JSON
        if response.code == "0":
            print("Request Successful")
            # Extracting last_message_id from the response body
            last_message_id = response.body['data']['last_message_id']
            print(f"Last Message ID: {last_message_id}")
            # Optionally print the whole response body
            print(json.dumps(response.body, indent=4))
            
            return response.body
        else:
            print(f"Error: {response.err_message}")
            return response.err_message
    except Exception as e:
        print(f"An error occurred: {e}")
        return str(e)

class User(BaseModel):
    cust_name: str
    message: str
 
def create_conversation(client: Client, data: User):
    try:
        conversation = client.conversations.v1.conversations.create(
            messaging_service_sid=os.getenv("TWILIO_CHAT_SERVICE_SID"),
            friendly_name=f"LazadaCustConverse-{data.cust_name}"
        )
        print(f"Conversation created successfully. SID: {conversation.sid}")
        curConversation[data.cust_name] = conversation.sid
        return conversation.sid
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def add_participant(client: Client,data: User,conversation_sid: str):
    try:
        participant = client.conversations.v1.conversations(conversation_sid).participants.create(
            identity=f"Lazada@{data.cust_name}"
        )
        print(f"Participant added successfully. SID: {participant.sid}")
        return participant.sid
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def create_webhook(client: Client, conversation_sid: str):
    try:
        # Pre-event webhook for Twilio Flex Studio
        flex_webhook = client.conversations.v1.conversations(conversation_sid).webhooks.create(
            configuration_filters=["onMessageAdded"],
            configuration_flow_sid=os.getenv("TWILIO_FLEX_FLOW_SID"),  # Twilio Studio Flow
            target="studio"
        )

        # Post-event webhook for capturing messages to Lazada
        lazada_webhook = client.conversations.v1.conversations(conversation_sid).webhooks.create(
            configuration_filters=["onMessageAdded"],
            target="webhook",
            configuration_url=URL+"/messageFromTwilio",
            configuration_method="POST",
            configuration_triggers=["post-webhook"]  # Post-event trigger
        )

        print(f"Webhooks created successfully. Flex: {flex_webhook.sid} | Lazada: {lazada_webhook.sid}")
        return flex_webhook.sid, lazada_webhook.sid

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def create_message(client: Client, data: User, conversation_sid: str):
    try:
        message = client.conversations.v1.conversations(conversation_sid).messages.create(
            author=data.cust_name,
            body=data.message,
            attributes=json.dumps({"customer_id": f"Lazada@{data.cust_name}"}),
            x_twilio_webhook_enabled="true"  # Enables webhook for message events
        )
        print(f"Message sent successfully. SID: {message.sid}")
        return message.sid
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/messageToTwilio")
async def message_from_twilio(request: Request):
    try:
        data = await request.json()
        conversation_id = data.get('data').get('session_id')
        user = data.get('data').get('user_account_id')
        seller_id = data.get('seller_id')
        print(f"Conversation_SID: {conversation_id}")
        if user != None:
            print(f"Seller_ID: {seller_id}")
            print(f"User_ID: {data.get('data').get('user_account_id')}")
        else:
            user = data.get('data').get('from_user_id')
            if user not in curUser and user != seller_id:
                curUser.add(user)
            if user in curUser:
                message = json.loads(data.get('data').get('content'))
                print(f"User_ID: {user}")
                print(f"Seller_ID: {data.get('seller_id')}")
                print(f"Message: {message.get('txt')}")
                data = User()
                data.cust_name = user,
                data.message =  message.get('txt')
        #appkey = os.getenv("LAZADA_APP_KEY")
        # appsecret = os.getenv("LAZADA_APP_SECRET")
        # access_token = os.getenv("LAZADA_ACCESS_TOKEN")

        # Fetch session data and the last message ID
        # session_data = get_lazada_session_data(appkey, appsecret, access_token, conversation_id)
        # print(f"Last Message ID: {session_data.get('data').get('last_message_id')}")

    except Exception as e:
        logging.error(f"❌ Error processing Lazada IM callback: {e}")
    try:
        # Check if conversation exists
        print("data Name:",data.cust_name)
        print(data.cust_name in curConversation)
        if data.cust_name in curConversation:
            conversation_sid = curConversation[data.cust_name]
            print(f"Conversation {conversation_sid} already exists.")
            if client.conversations.conversations(conversation_sid).fetch().state == "closed":
                print(f"Conversation {conversation_sid} is closed. Creating a new one.")
                # Deleting the customer from CurrentCustomer list as the conversation is closed and therefore message cannot be send to the same conversation_sid. 
                del curConversation[data.cust_name]
                
        # cheking if the customer is not in the current conversation list and creating a new conversation for the customer
        elif data.cust_name not in curConversation:
            # Create a conversation
            conversation_sid = create_conversation(client, data)
            try:
                # Add participant
                add_participant(client, data, conversation_sid)
 
                try:
                    # Create webhook
                    create_webhook(client, conversation_sid)
                except Exception as e:
                    return JSONResponse(
                        content={"error": f"Error creating webhook: {str(e)}"},
                        status_code=500
                    )
            except Exception as e:
                return JSONResponse(
                    content={"error": f"Error creating participant: {str(e)}"},
                    status_code=500
                )
        try:
            # Send message
            message_sid = create_message(client, data, conversation_sid)
            return JSONResponse(
                content={"status": "success", "message_sid": message_sid, "conversation_sid": conversation_sid},
                status_code=200
            )
 
        except Exception as e:
            return JSONResponse(
                content={"error": f"Error sending message: {str(e)}"},
                status_code=500
            )
            
    except Exception as e:
        return JSONResponse(
            content={"error": f"Error creating conversation: {str(e)}"},
            status_code=500
        )

@app.post("/messageFromTwilio")
async def message_from_twilio(request: Request):
    try:
        raw_data = await request.body()
        
        # Decode the bytes into a string
        decoded_data = raw_data.decode("utf-8")

        # Parse the URL-encoded data into a dictionary
        data = urllib.parse.parse_qs(decoded_data)

        # Example of extracting the message body and author
        author = data.get("Author", ["Unknown"])[0]
        body = data.get("Body", ["No message"])[0]
        conversation_sid = data.get("ConversationSid",['No conversation'])[0]

        print(f"Message from {author}: {body}")
        print(f"Conversation SID: {conversation_sid}")
        client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
        print(f"Conversation Status:{client.conversations.conversations(conversation_sid).fetch().state}")
        print("Current Conversation:",curConversation)

        return JSONResponse(content={"status": "success", "author": author, "body": body}, status_code=200)

    except Exception as e:
        print(f"❌ Error receiving message: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

app.get("/")
def home():
    return {"message": "Welcome to the Twilio Conversations API!"}


@app.get("/auth") 
async def lazada_auth(request: Request):
    try:
        # Check if there's a 'code' parameter in the query string
        code = request.query_params.get("code")
        if code:
            logging.info(f"🔑 Received auth code: {code}")
            return {"message": "Authorization successful!", "code": code}
        else:
            # If no 'code' parameter, generate the authorization URL
            logging.info("Generating Lazada auth URL...")
            try:
                url = "https://auth.lazada.com/oauth/authorize"
                params = {
                    "response_type": "code",  # Requesting the authorization code
                    "force_auth": "true",     # Force the authorization even if the user is logged in
                    "redirect_uri": URL+"/auth",  # Your redirect URL
                    "client_id": os.getenv("LAZADA_APP_KEY")  # Your Lazada app client ID
                }
                auth_url = authURL(url, params)  # Generate the URL
                logging.info(f"Auth URL generated: {auth_url}")
                # Return the generated URL
                # You have to redirect the user (Seller) to this URL to grant us access to their Lazada account chat
                return {"url": auth_url}
            except Exception as e:
                logging.error(f"❌ Error generating Lazada auth URL: {e}")
                return {"error": f"Error generating Lazada auth URL: {e}"}
    except Exception as e:
        logging.error(f"❌ Error in auth process: {e}")
        return {"error": f"Error in auth process: {e}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
