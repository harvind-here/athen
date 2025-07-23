from flask import Flask, request, jsonify, send_from_directory, Response, make_response, redirect
from flask_cors import CORS
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
import logging
import json
import traceback
import tempfile
from pydub import AudioSegment
import base64
import requests
from datetime import date, datetime, timedelta
from functools import wraps
import secrets
from google.auth.exceptions import RefreshError

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from config.settings import *
from database.mongodb import MongoDB
from managers.conversation_manager import ConversationHistoryManager
from managers.reminder_manager import RemindersManager
from managers.scheduling_manager import SchedulingManager
from managers.auth_manager import AuthManager, TOKEN_FILE_LOGIN, TOKEN_FILE_CALENDAR
from services.web_service import web_search
from services.speech_service import text_to_speech
from utils.function_tools import function_tools

app = Flask(__name__, 
    static_folder=os.path.abspath("frontend/build"),
    static_url_path="")

app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": os.environ.get("FRONTEND_URL", "").split(','),
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-User-ID", "Accept", "Cookie"],
        "expose_headers": ["Content-Type", "X-User-ID", "Set-Cookie"],
    }
})

mongodb = MongoDB(MONGODB_URI)
groq_client = Groq(api_key=GROQ_API_KEY)
history_manager = ConversationHistoryManager(mongodb.conversations)
reminders_manager = RemindersManager(mongodb.reminders)
scheduling_manager = SchedulingManager()
auth_manager = AuthManager(GOOGLE_CLIENT_CONFIG)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

auth_flows = {}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.cookies.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

    
def process_chat(user_input, user_id):
    recent_context = history_manager.get_recent_context(user_id)
    current_time = datetime.now()
    formatted_time = current_time.strftime(r"%Y-%m-%d %I:%M:%S %p")
    day_of_week = current_time.strftime("%A")

    formatted_context = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in recent_context])

    system_message = f"""You are 'Athen', a virtual personal assistant created to engage and assist the user by following the tasks they ask you to do. You can perform tasks by selecting the most appropriate function. Your capabilities include accessing the user's Google Calendar (create, delete, list events), handling reminders (add, mark as completed, list), and now you can also perform web searches when explicitly asked to do so.

    When the user asks you to search for something online or if you need to verify information, use the web_search function. Only use this function when explicitly asked or when you need to verify important information. Do not use it for every query.

    The following is the recent context of previous message history of the user with you <"{formatted_context}">.  When responding, ANALYZE ONLY THE LATEST USER INPUT TO DETERMINE THE APPROPRIATE ACTION. DO NOT CONSIDER PREVIOUS MESSAGES FOR FUNCTION CALLING.
    Choose one of two response formats:

    1. Function Call Format (for task-oriented requests):
    If the user's latest input requires a specific task to be completed using available functions, respond with a JSON object in this format:
    {function_tools}. Refer carefully what are the functions used for which purposes using the descriptions provided in each functions. AND VERY IMPORTANTLY IF REQUIRED ARGUMENTS ARE PROVIDED BY THE USER DONT TOOL CALL STRAIGHT AWAY, INSTEAD ASK THE USER NECESSARY INFORMATION THAT IS MISSING IN A FOLLOWUP/RESPONSE by using secong response format (Nomral response format) AND THEN PROCEED TO TOOL CALLING TILL YOU GET THE DETAILS COMPLETELY. FOR EXAMPLE IF USER ASKS YOU TO SCHEDULE AN EVENT IN GOOGLE CALENDAR WITHOUT REQUIRED INFORMATIONS LIKE SUMMARY, START TIME AND END TIME, YOU SHOULD ASK THEM THESE DETAILS IN A FOLLOW UP AND THEN AFTER YOU GET THE REQUIRED DETAILS ONLY PROCEED TO TOOL CALLING. Check the necessary parameters/arguments for each function in the structure given. (( OPTIONAL - If you can append your explanation or confirmation of the action taken or function choosed in a short description outside the tool calling format and If you feel you need more accurate data in order to respond to the user, dont hesitate to use the web_search function to get more information)).

    2. Normal Response Format (for general queries or when no function is needed):
    If the user's latest input is a general query or doesn't require a specific function, respond with a JSON object in this format:
    {{
        "response": "Your direct response to the user's query or input. respond only to the latest user input and not to the previous conversation history or context."
    }}

    The current date and time is {formatted_time}, and today is {day_of_week}. Use the current date and time for relative references and respond with dates and times in sentence format (example: 3rd May 2024) with AM/PM format only. And importantly if you have the required arguments to tool call proceed to tool call and DONT expect all optional arguments. AAsk followup only if the required arguments are not fulfilled"""

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_input}
    ]

    try:
        response = groq_client.chat.completions.create(
            messages=messages,
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.5,
            max_tokens=1024,
            top_p=1,
            stop=None,
            stream=False,
            functions=function_tools
        )

        assistant_message = response.choices[0].message
        content = assistant_message.content
        tool_calls = assistant_message.tool_calls
        
        event_link = None
        web_link = None
        auth_url = None
        final_response = None

        if tool_calls:
            try:
                tool_call = tool_calls[0]
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                if function_name in ["create_event", "get_upcoming_events", "delete_event"]:
                    service = scheduling_manager.get_google_calendar_service(auth_manager)
                    if not service:
                        return {
                            'llm_resp': "I need your permission to access Google Calendar first. Please use the 'Integrate Calendar' button.",
                            'auth_url': None 
                        }
                    
                    if function_name == "create_event":
                        event_details = function_args.get("event_details")
                        result = scheduling_manager.create_event(service=service, event_details=event_details)
                        if isinstance(result, str) and result.startswith("https://"):
                            event_link = result
                            final_response = f"OK. I've created the event: {event_details.get('summary', 'Untitled Event')}"
                        else:
                            final_response = result
                    elif function_name == "get_upcoming_events":
                        max_results = function_args.get('max_results', 10)
                        final_response = scheduling_manager.get_upcoming_events(service, max_results)

                elif function_name == "get_active_reminders":
                    reminders = reminders_manager.get_active_reminders(user_id=user_id)
                    if reminders:
                        final_response = "Here are your active reminders:\n" + "\n".join([f"- {r['reminder']}" for r in reminders])
                    else:
                        final_response = "You have no active reminders."
                elif function_name == "add_reminder":
                    reminder_text = function_args.get('reminder')
                    reminders_manager.add_reminder(user_id=user_id, reminder=reminder_text)
                    final_response = f"OK. I've added the reminder: '{reminder_text}'."
                elif function_name == "complete_reminder":
                    reminder_text = function_args.get('reminder_text')
                    success = reminders_manager.complete_reminder(user_id=user_id, reminder_text=reminder_text)
                    final_response = f"OK. I've marked '{reminder_text}' as completed." if success else f"Sorry, I couldn't find an active reminder matching '{reminder_text}'."
                elif function_name == "web_search":
                    query = function_args.get("query")
                    result = web_search(query=query, groq_client=groq_client)
                    if isinstance(result, str) and result.startswith("http"):
                        web_link = result
                        final_response = f"Here's a link I found for '{query}': {web_link}"
                    else:
                        final_response = result
                else:
                    final_response = f"Sorry, I don't know how to handle the function: {function_name}"
            except Exception as e:
                logger.error(f"Error executing function: {e}")
                final_response = "Sorry, I encountered an error."
        else:
            try:
                if content and content.strip().startswith('{'):
                    parsed_content = json.loads(content)
                    final_response = parsed_content.get("response", content)
                else:
                    final_response = content or "I'm not sure how to respond."
            except json.JSONDecodeError:
                final_response = content

        return {
            'llm_resp': final_response,
            'event_link': event_link,
            'web_link': web_link,
            'auth_url': auth_url
        }
    except Exception as e:
        logger.error(f"Critical error in process_chat: {str(e)}")
        return {'llm_resp': "Sorry, an internal error occurred."}









@app.route('/')
def serve_root():
    return send_from_directory(app.static_folder, 'index.html')












@app.route('/callback.html')
def serve_callback():
    return send_from_directory('frontend/public', 'callback.html')

@app.route('/<path:path>')
def serve_static_or_index(path):
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')











@app.route('/api/auth_status')
def auth_status():
    user_id = request.cookies.get('user_id')
    if user_id:
        user = mongodb.get_user_by_google_id(user_id)
        if user:
            calendar_creds = auth_manager.get_calendar_credentials()
            return jsonify({
                'authenticated': True,
                'user': {
                    "id": str(user.get("google_id")),
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "isCalendarAuthorized": calendar_creds is not None and 'access_token' in calendar_creds
                }
            })
    return jsonify({'authenticated': False, 'user': None})















@app.route('/api/auth/google/login', methods=['POST'])
def google_login():
    data = request.get_json()
    frontend_origin = data.get('frontend_origin')
    state = secrets.token_urlsafe(32)
    scopes = auth_manager.get_login_scopes()
    authorization_url = auth_manager.get_authorization_url(state, scopes, frontend_origin)
    auth_flows[state] = {'flow': 'login', 'frontend_origin': frontend_origin}
    return jsonify({"authUrl": authorization_url})

















@app.route('/api/auth/google/calendar', methods=['POST'])
@login_required
def google_calendar_auth():
    data = request.get_json()
    frontend_origin = data.get('frontend_origin')
    state = secrets.token_urlsafe(32)
    scopes = auth_manager.get_calendar_scopes()
    authorization_url = auth_manager.get_authorization_url(state, scopes, frontend_origin)
    auth_flows[state] = {'flow': 'calendar', 'frontend_origin': frontend_origin}
    return jsonify({"authUrl": authorization_url})
















@app.route('/api/auth/google/callback')
def google_auth_callback():
    state = request.args.get('state')
    auth_flow = auth_flows.pop(state, None)
    if not auth_flow:
        return "State mismatch or expired Try Logging Again", 400

    flow_type = auth_flow['flow']
    frontend_origin = auth_flow['frontend_origin']
    authorization_response = request.url

    try:
        if flow_type == 'login':
            scopes = auth_manager.get_login_scopes()
            token_file = TOKEN_FILE_LOGIN
            credentials = auth_manager.handle_oauth_callback(authorization_response, state, scopes, token_file, frontend_origin)
            if not credentials:
                return "Authentication failed: Could not process credentials", 400
            
            auth_manager.login_credentials = credentials
            user_info = auth_manager.get_user_info()
            
            user_data = {
                "google_id": user_info.get("sub"),
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "last_login_at": datetime.utcnow()
            }
            mongodb.create_user(user_data)
            
            response = make_response(redirect('/callback.html'))
            response.set_cookie('user_id', user_data['google_id'], httponly=True, samesite='Lax')
            return response

        elif flow_type == 'calendar':
            scopes = auth_manager.get_calendar_scopes()
            token_file = TOKEN_FILE_CALENDAR
            credentials = auth_manager.handle_oauth_callback(authorization_response, state, scopes, token_file, frontend_origin)
            if not credentials:
                return "Calendar authorization failed", 400
            
            auth_manager.calendar_credentials = credentials
            
    except Exception as e:
        logger.error(f"Error during OAuth callback: {e}")
        return "An error occurred during authentication.", 500

    return redirect('/callback.html')
















@app.route('/api/auth/logout', methods=['POST'])
def logout():
    auth_manager.clear_credentials_file()
    response = make_response(jsonify({"message": "Logout successful"}))
    response.delete_cookie('user_id')
    return response






















@app.route('/api/auth/session')
def get_session():
    user_id = request.cookies.get('user_id')
    if not user_id:
        return jsonify({"user": None})
    
    user = mongodb.get_user_by_google_id(user_id)
    calendar_creds = auth_manager.get_calendar_credentials()
    
    user_data = auth_manager.format_user_response(user)
    if user_data.get("user"):
        user_data["user"]["isCalendarAuthorized"] = calendar_creds is not None and 'access_token' in calendar_creds

    return jsonify(user_data)



@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.json
    user_input = data.get('message')
    is_speech = data.get('is_speech', False)
    user_id = request.cookies.get('user_id')

    if not user_input:
        return jsonify({'error': 'No message provided'}), 400

    history_manager.add_message(user_id, "user", user_input)
    resp = process_chat(user_input, user_id)
    final_response = resp.get('llm_resp')
    history_manager.add_message(user_id, "assistant", final_response)

    response_data = {'response': final_response}
    if resp.get('event_link'):
        response_data['event_link'] = resp['event_link']
    if resp.get('web_link'):
        response_data['web_link'] = resp['web_link']
    if resp.get('auth_url'):
        response_data['auth_url'] = resp['auth_url']

    if is_speech and final_response and not resp.get('auth_url'):
        try:
            audio_data = text_to_speech(final_response)
            if audio_data:
                response_data['audio'] = audio_data
        except Exception as tts_error:
            logger.error(f"TTS error: {tts_error}")

    return jsonify(response_data)









@app.route('/api/speech-to-text', methods=['POST'])
def speech_to_text():
    try:
        audio_file = request.files['audio']
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
            audio_file.save(temp_file.name)
            temp_filename = temp_file.name

        audio = AudioSegment.from_file(temp_filename)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        output_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
        audio.export(output_wav, format='wav')

        API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
        hf_token = os.environ.get('HUGGING_FACE_INFERENCEAPI')
        headers = {"Authorization": f"Bearer {hf_token}"}

        with open(output_wav, "rb") as f:
            data = f.read()
        response = requests.post(API_URL, headers=headers, data=data)
        output = response.json()
        logger.info(f"Hugging Face API response: {output}")

        if "text" in output:
            return jsonify({'transcription': output['text']})
        else:
            raise ValueError(f"Unexpected API response: {output}")
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'temp_filename' in locals(): os.remove(temp_filename)
        if 'output_wav' in locals(): os.remove(output_wav)

@app.route('/api/conversation_history', methods=['GET'])
@login_required
def load_conversation_history():
    user_id = request.cookies.get('user_id')
    today_doc = history_manager.get_today_document(user_id)
    if not today_doc or "messages" not in today_doc:
        return jsonify({"conversation_history": []})
    
    return jsonify({"conversation_history": today_doc["messages"]})
    
@app.route('/api/clear_chat_history', methods=['POST'])
@login_required
def clear_chat_history():
    user_id = request.cookies.get('user_id')
    history_manager.clear_history(user_id)
    reminders_manager.clear_reminders(user_id)
    return jsonify({'message': 'Chat history and reminders cleared successfully'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
