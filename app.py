from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import os
from groq import Groq
import logging
import json
import traceback
import tempfile
from pydub import AudioSegment
import base64
import requests
from datetime import date, datetime

from config.settings import *
from database.mongodb import MongoDB
from managers.conversation_manager import ConversationHistoryManager
from managers.reminder_manager import RemindersManager
from managers.scheduling_manager import SchedulingManager
from services.web_service import web_search
from services.speech_service import text_to_speech
from utils.function_tools import function_tools

# Initialize Flask app
app = Flask(__name__, static_folder=os.path.abspath("frontend/build"), static_url_path="")
CORS(app)
app.secret_key = os.urandom(24)

# Initialize MongoDB
mongodb = MongoDB(MONGODB_URI)
conversations_collection = mongodb.conversations
reminders_collection = mongodb.reminders

# Initialize managers and clients
groq_client = Groq(api_key=GROQ_API_KEY)
history_manager = ConversationHistoryManager(conversations_collection)
reminders_manager = RemindersManager(reminders_collection)
scheduling_manager = SchedulingManager()

logger = logging.getLogger(__name__)

def process_chat(user_input):
    recent_context = history_manager.get_recent_context()
    current_time = datetime.now()
    formatted_time = current_time.strftime(r"%Y-%m-%d %I:%M:%S %p")
    day_of_week = current_time.strftime("%A")

    formatted_context = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in recent_context])

    system_message = f"""You are 'Athen', a virtual personal assistant created to engage and satisfy {USER_NAME}, the one who created you and you work for, by following the tasks they ask you to do. {USER_NAME} is {USER_AGE} years old and he is a {USER_OCCUPATION}. Their interests include {USER_INTERESTS}. You can perform tasks by selecting the most appropriate function. Your capabilities include accessing the user's Google Calendar (create, delete, list events), handling reminders (add, mark as completed, list), and now you can also perform web searches when explicitly asked to do so.

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

    The current date and time is {formatted_time}, and today is {day_of_week}. Use the current date and time for relative references and respond with dates and times in sentence format (example: 3rd May 2024) with AM/PM format only."""

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_input}
    ]

    try:
        response = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
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
        
        logger.debug(f"Assistant message: {assistant_message}")
        logger.debug(f"Content: {content}")
        logger.debug(f"Tool calls: {tool_calls}")

        event_link = None
        web_link = None
        auth_url = None
        final_response = None

        if tool_calls:
            try:
                tool_call = tool_calls[0]
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                logger.debug(f"Function name: {function_name}")
                logger.debug(f"Function args: {function_args}")

                if function_name == "create_event":
                    service, auth_url = scheduling_manager.get_google_calendar_service()
                    if auth_url:
                        final_response = "Please authenticate with Google Calendar first"
                        return {
                            'llm_resp': final_response,
                            'auth_url': auth_url
                        }
                    
                    if not service:
                        raise Exception("Failed to initialize Google Calendar service")
                    
                    event_details = function_args.get("event_details")
                    if not event_details:
                        raise ValueError("No event details provided")
                    
                    logger.debug(f"Creating event with details: {event_details}")
                    result = scheduling_manager.create_event(service=service, event_details=event_details)
                    
                    if result and isinstance(result, str) and result.startswith("https://"):
                        event_link = result
                        final_response = f"I've created the event '{event_details['summary']}' for {event_details['start_time']} to {event_details['end_time']}."
                    else:
                        final_response = "I couldn't create the event. Please try again."

                elif function_name == "get_upcoming_events":
                    service, auth_url = scheduling_manager.get_google_calendar_service()
                    if auth_url:
                        final_response = "Please authenticate with Google Calendar first"
                        return {
                            'llm_resp': final_response,
                            'auth_url': auth_url
                        }
                    result = scheduling_manager.get_upcoming_events(service, function_args.get('max_results', 10))
                    final_response = result

                elif function_name == "get_active_reminders":
                    reminders = reminders_manager.get_active_reminders()
                    if reminders:
                        final_response = "Here are your active reminders:\n" + "\n".join([f"- {r['reminder']}" for r in reminders])
                    else:
                        final_response = "You don't have any active reminders."

                elif function_name == "add_reminder":
                    reminders_manager.add_reminder(**function_args)
                    final_response = f"Reminder '{function_args['reminder']}' added successfully."

                elif function_name == "complete_reminder":
                    success = reminders_manager.complete_reminder(**function_args)
                    final_response = f"Reminder '{function_args['reminder_text']}' marked as completed." if success else f"Reminder '{function_args['reminder_text']}' not found or already completed."

                elif function_name == "web_search":
                    result = web_search(**function_args, groq_client=groq_client)
                    if result and isinstance(result, str) and result.startswith("https://"):
                        web_link = result
                    final_response = result

                else:
                    final_response = f"Unknown function: {function_name}"

            except Exception as e:
                logger.error(f"Error executing function {function_name}: {e}")
                final_response = f"Sorry, there was an error: {str(e)}"
        else:
            try:
                if content:
                    parsed_content = json.loads(content)
                    if isinstance(parsed_content, dict) and "response" in parsed_content:
                        final_response = parsed_content["response"]
                    else:
                        final_response = content
                else:
                    final_response = "I apologize, but I couldn't generate a proper response."
            except json.JSONDecodeError:
                final_response = content if content else "I apologize, but I couldn't generate a proper response."

        return {
            'llm_resp': final_response,
            'event_link': event_link,
            'web_link': web_link,
            'auth_url': auth_url
        }
    
    except Exception as e:
        logger.error(f"Error in process_chat: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'llm_resp': f"An error occurred: {str(e)}",
            'event_link': None,
            'web_link': None,
            'auth_url': None
        }

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

@app.route('/oauth_callback')
def oauth_callback():
    auth_code = request.args.get('code')
    if auth_code:
        try:
            service = scheduling_manager.handle_auth_callback(auth_code)
            if service:
                session['auth_pending'] = False
                return "Authentication successful! You can close this window."
            else:
                return "Authentication failed. Please try again."
        except Exception as e:
            return "Authentication failed. Please try again."
    else:
        return "Authentication failed. No authorization code received."

@app.route('/api/auth_status')
def auth_status():
    return jsonify({'authenticated': not session.get('auth_pending', True)})

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_input = data['message']
        is_speech = data.get('is_speech', False)
        logger.info(f"Received message: {user_input}, is_speech: {is_speech}")

        # Add user message to history
        history_manager.add_message("user", user_input)

        # Process the chat
        resp = process_chat(user_input)
        
        # Get the response components
        final_response = resp.get('llm_resp', '')
        event_link = resp.get('event_link')
        auth_url = resp.get('auth_url')
        
        # Add assistant response to history
        history_manager.add_message("assistant", final_response)

        # Prepare response data
        response_data = {
            'response': final_response
        }

        # Convert response to speech if input was from speech
        if is_speech:
            audio_data = text_to_speech(final_response)
            if audio_data:
                response_data['audio'] = audio_data
        
        # Add optional response components
        if event_link:
            response_data['event_link'] = event_link
        if auth_url:
            response_data['auth_url'] = auth_url

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': str(e),
            'response': 'I apologize, but I encountered an error processing your request.'
        }), 500

@app.route('/api/speech-to-text', methods=['POST'])
def speech_to_text():
    try:
        audio_file = request.files['audio']
        print("Audio file received:", audio_file)

        # Save the input file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
            audio_file.save(temp_file.name)
            temp_filename = temp_file.name

        # Convert using pydub
        audio = AudioSegment.from_file(temp_filename)
        output_wav = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
        audio = audio.set_frame_rate(16000)  # Set sample rate to 16kHz
        audio = audio.set_channels(1)        # Convert to mono
        audio = audio.set_sample_width(2)    # Set to 16-bit
        audio.export(output_wav, format='wav')

        API_URL = "https://api-inference.huggingface.co/models/openai/whisper-large-v3"
        headers = {"Authorization": "Bearer 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"}

        def query(filename):
            with open(filename, "rb") as f:
                data = f.read()
            response = requests.post(API_URL, headers=headers, data=data)
            return response.json()

        output = query(output_wav)
        print("Hugging Face API response:", output)

        if "text" in output:
            transcription = output['text']
            return jsonify({'transcription': transcription})
        else:
            raise ValueError(f"Unexpected API response: {output}")
    except Exception as e:
        print("Error occurred:", str(e))
        return jsonify({'error': str(e)}), 500
    finally:
        if 'temp_filename' in locals():
            os.remove(temp_filename)
        if 'output_wav' in locals():
            os.remove(output_wav)

@app.route('/api/conversation_history', methods=['GET'])
def load_conversation_history():
    try:
        today_doc = history_manager.get_today_document()
        recent_context = today_doc["messages"][-history_manager.context_length:]

        conversation_history = []
        for message in recent_context:
            conversation_history.append({
                "role": message.get("role", "unknown"),
                "content": message.get("content", ""),
                "timestamp": message.get("timestamp", datetime.utcnow()).isoformat()
            })

        return jsonify({"conversation_history": conversation_history}), 200

    except Exception as e:
        logger.error(f"Error in load_conversation_history: {str(e)}")
        return jsonify({'error': f'An internal server error occurred: {str(e)}'}), 500
    
@app.route('/api/clear_chat_history', methods=['POST'])
def clear_chat_history():
    try:
        today = date.today().isoformat()
        conversations_collection.delete_one({"date": today})
        reminders_collection.delete_many({})
        reminders_manager.initialize_reminders()
        return jsonify({'message': 'Chat history and reminders cleared successfully'}), 200
    except Exception as e:
        logger.error(f"Error clearing chat history and reminders: {str(e)}")
        return jsonify({'error': f'An error occurred while clearing chat history and reminders: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)