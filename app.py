from flask import Flask, request, jsonify, send_from_directory, session, Response, make_response, redirect # Add redirect
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
from datetime import date, datetime, timedelta
from functools import wraps
# Removed Credentials import as it's handled within AuthManager now
import secrets

# Allow OAuth2 to work with HTTP for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from config.settings import *
from database.mongodb import MongoDB
from managers.conversation_manager import ConversationHistoryManager
from managers.reminder_manager import RemindersManager
from managers.scheduling_manager import SchedulingManager
from managers.auth_manager import AuthManager
from services.web_service import web_search
from services.speech_service import text_to_speech
from utils.function_tools import function_tools

# Initialize Flask app with session configuration
app = Flask(__name__, static_folder=os.path.abspath("frontend/build"), static_url_path="")

# Set the secret key for session management
app.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Configure session
app.config.update(
    SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_COOKIE_NAME='athen_session',
    SESSION_COOKIE_PATH='/',
    SESSION_COOKIE_DOMAIN=None,  # Set to your domain in production
    SESSION_TYPE='filesystem',  # Use filesystem to store session data
    SECRET_KEY=app.secret_key
)

# Set up session interface
from flask_session import Session
Session(app)

# Configure CORS with credentials support
CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5000"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-User-ID", "Accept", "Cookie"],
        "expose_headers": ["Content-Type", "X-User-ID", "Set-Cookie"],
        "supports_credentials": True
    }
})

# Initialize MongoDB
mongodb = MongoDB(MONGODB_URI)

# Initialize managers and clients
groq_client = Groq(api_key=GROQ_API_KEY)
history_manager = ConversationHistoryManager(mongodb.conversations)
reminders_manager = RemindersManager(mongodb.reminders)
scheduling_manager = SchedulingManager()
auth_manager = AuthManager(GOOGLE_CLIENT_CONFIG)

logger = logging.getLogger(__name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/auth/google')
def google_auth():
    try:
        # Generate and store a secure state token
        # Check if already authenticated via token.json
        existing_creds = auth_manager.get_credentials()
        if existing_creds and existing_creds.valid:
            logger.info("User already authenticated via token.json. No need for new auth URL.")
            # Return a message indicating already authenticated, or maybe user info
            user_info = auth_manager.get_user_info() # Get info using stored creds
            # Ensure user is in session if needed for other parts of the app
            if 'user_id' not in session and user_info:
                 session['user_id'] = user_info.get('sub')
                 session.permanent = True
                 session.modified = True
                 # Optionally store credentials dict in session too, though token.json is primary
                 session['credentials'] = {
                     'token': existing_creds.token,
                     'refresh_token': existing_creds.refresh_token,
                     'token_uri': existing_creds.token_uri,
                     'client_id': existing_creds.client_id,
                     'client_secret': existing_creds.client_secret,
                     'scopes': existing_creds.scopes
                 }

            response = make_response(jsonify({"message": "Already authenticated", "user": user_info}))
            # Save session if modified
            if session.modified:
                 app.session_interface.save_session(app, session, response)
            return response

        # If not authenticated via token.json, proceed with OAuth flow
        state = secrets.token_urlsafe(32)
        session['oauth_state'] = state
        session.permanent = True
        session.modified = True

        authorization_url = auth_manager.get_authorization_url(state)

        if not authorization_url:
             # This case should ideally not happen if the initial check passed,
             # but handle defensively. It might mean get_authorization_url itself
             # found valid creds after the initial check.
             logger.warning("get_authorization_url returned None unexpectedly after initial check.")
             return jsonify({"message": "Already authenticated"}), 200

        # Create response with auth URL
        response = make_response(jsonify({"authUrl": authorization_url}))

        # Set state cookie
        response.set_cookie(
            'oauth_state',
            state,
            httponly=True,
            samesite='Lax',
            secure=False, # Set to True in production with HTTPS
            max_age=1800, # 30 minutes
            path='/',
            domain=None
        )

        # Force session save
        app.session_interface.save_session(app, session, response)

        logger.info(f"Setting oauth_state in session and cookie: {state}")
        logger.info(f"Current session after setting state: {dict(session)}")

        return response

    except Exception as e:
        logger.error(f"Error in google_auth: {str(e)}")
        logger.error(traceback.format_exc()) # Log full traceback
        return jsonify({"error": "An internal error occurred during authentication setup."}), 500


@app.route('/api/auth/google/callback')
def google_auth_callback():
    try:
        # Get states from all possible sources
        session_state = session.get('oauth_state')
        cookie_state = request.cookies.get('oauth_state')
        received_state = request.args.get('state')
        auth_code = request.args.get('code')

        # Detailed logging
        logger.info("OAuth Callback - State Verification:")
        logger.info(f"Session State: {session_state}")
        logger.info(f"Cookie State: {cookie_state}")
        logger.info(f"Received State: {received_state}")
        logger.info(f"Auth Code: {auth_code}")
        logger.info(f"Full Session Data: {dict(session)}")
        logger.info(f"All Cookies: {dict(request.cookies)}")
        logger.info(f"Full Request URL: {request.url}")

        # Use any available state (session or cookie)
        stored_state = session_state or cookie_state

        # Basic state validation (optional but recommended)
        # if not received_state or received_state != stored_state:
        #     logger.warning("OAuth state mismatch or missing.")
        #     # Decide how to handle: maybe proceed cautiously or return error
        #     # return "Authentication failed: State mismatch", 400

        if auth_code:
            # Get the full URL including query parameters
            authorization_response = request.url
            # Ensure HTTPS if behind a proxy
            if request.headers.get('X-Forwarded-Proto', 'http') == 'https':
                if not authorization_response.startswith('https://'):
                     authorization_response = 'https://' + authorization_response.split('://', 1)[1]

            # Exchange code for tokens using AuthManager
            # This now saves to token.json internally
            credentials_dict = auth_manager.handle_oauth_callback(
                authorization_response,
                stored_state or received_state # Pass the state used
            )

            if not credentials_dict:
                logger.error("Failed to get credentials from OAuth callback via AuthManager")
                return "Authentication failed: Could not process credentials", 400

            # Store credentials dict in session (optional, as token.json is primary)
            session["credentials"] = credentials_dict

            # Get user info using AuthManager (which uses stored/refreshed credentials)
            try:
                user_info = auth_manager.get_user_info() # No need to pass creds
                if not user_info:
                     raise ValueError("Failed to retrieve user info after authentication.")
            except Exception as user_info_error:
                 logger.error(f"Error getting user info after callback: {user_info_error}")
                 return "Authentication succeeded but failed to retrieve user details.", 500

            # Create or update user in database
            user_data = {
                "google_id": user_info.get("sub"), # Use .get for safety
                "email": user_info.get("email"),
                "name": user_info.get("name"),
                "picture": user_info.get("picture"),
                "is_guest": False,
                # Add/update timestamps if your schema supports them
                "last_login_at": datetime.utcnow()
            }
            # Ensure google_id exists before proceeding
            if not user_data["google_id"]:
                 logger.error("User info retrieved but missing 'sub' (google_id).")
                 return "Authentication failed: Invalid user information received.", 500

            mongodb.create_user(user_data) # Assumes this handles updates too
            session["user_id"] = user_data["google_id"]
            session.permanent = True # Make session persistent
            session.modified = True

            # Create success response (HTML to close popup)
            response = auth_manager.create_success_response()

            # Clean up OAuth state from session and cookie
            session.pop('oauth_state', None)
            response.delete_cookie('oauth_state', path='/')

            # Save the session with user_id and potentially credentials
            app.session_interface.save_session(app, session, response)

            logger.info(f"Successfully authenticated user {user_data['email']} ({user_data['google_id']}).")
            return response

        else:
            error_description = request.args.get('error', 'No authorization code received')
            logger.error(f"OAuth callback failed. Error: {error_description}")
            return f"Authentication failed: {error_description}", 400

    except Exception as e:
        logger.error(f"Critical error in Google OAuth callback: {str(e)}")
        logger.error(traceback.format_exc())
        # Generic error to user
        return "An internal error occurred during authentication.", 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    user_id = data.get("id")
    is_guest = data.get("isGuest")
    name = data.get("name")
    
    if is_guest:
        user_data = auth_manager.create_guest_user_data(user_id, name)
        mongodb.create_user(user_data)
    
    session["user_id"] = user_id
    return jsonify({"message": "Login successful"})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    # Clear the server-side session
    session.clear()
    # Clear the persisted credentials file
    deleted_token = auth_manager.clear_credentials_file()
    if deleted_token:
        logger.info("Logout successful and token.json deleted.")
        return jsonify({"message": "Logout successful"})
    else:
        logger.warning("Logout successful but failed to delete token.json.")
        # Still return success to the user, but log the issue
        return jsonify({"message": "Logout successful, but encountered an issue clearing credentials file."})


@app.route('/api/auth/session')
def get_session():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"user": None})
    
    user = mongodb.get_user_by_id(user_id) or mongodb.get_user_by_google_id(user_id)
    return jsonify(auth_manager.format_user_response(user))

def process_chat(user_input, user_id):
    recent_context = history_manager.get_recent_context(user_id)
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

    The current date and time is {formatted_time}, and today is {day_of_week}. Use the current date and time for relative references and respond with dates and times in sentence format (example: 3rd May 2024) with AM/PM format only. And importantly if you have the required arguments to tool call proceed to tool call and DONT expect all optional arguments. AAsk followup only if the required arguments are not fulfilled"""

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

                # --- Calendar Function Handling ---
                if function_name in ["create_event", "get_upcoming_events", "delete_event"]: # Add delete_event if applicable
                    # Get service object using the updated method, passing auth_manager
                    service = scheduling_manager.get_google_calendar_service(auth_manager)

                    if not service:
                        # If service is None, authentication is needed.
                        # Generate auth URL using AuthManager
                        state = secrets.token_urlsafe(32) # Generate a fresh state
                        session['oauth_state'] = state # Store state for callback validation
                        session.modified = True
                        auth_url = auth_manager.get_authorization_url(state)

                        if auth_url:
                             logger.info("Authentication required for Google Calendar. Returning auth URL.")
                             final_response = "I need your permission to access Google Calendar first. Please authenticate."
                             # Return auth_url so frontend can trigger the flow
                             return {
                                 'llm_resp': final_response,
                                 'auth_url': auth_url # Send URL to frontend
                             }
                        else:
                             # This might happen if get_authorization_url finds valid creds
                             # after get_google_calendar_service failed (unlikely but possible race)
                             logger.error("Failed to get service but also failed to get auth URL.")
                             final_response = "There was an issue accessing Google Calendar. Please try logging in again."
                             return {'llm_resp': final_response}

                    # --- If service is valid, proceed with the specific function ---
                    if function_name == "create_event":
                        event_details = function_args.get("event_details")
                        if not event_details:
                            final_response = "I need more details to create the event (like summary, start time, end time)."
                        else:
                            logger.debug(f"Creating event with details: {event_details}")
                            result = scheduling_manager.create_event(service=service, event_details=event_details)
                            # Check result type: link, error message, etc.
                            if isinstance(result, str) and result.startswith("https://"):
                                event_link = result
                                final_response = f"OK. I've created the event: {event_details.get('summary', 'Untitled Event')}"
                            elif isinstance(result, str): # Handle error messages from create_event
                                final_response = result # Pass the error message back
                            else:
                                final_response = "I couldn't create the event. Please check the details and try again."

                    elif function_name == "get_upcoming_events":
                        max_results = function_args.get('max_results', 10)
                        logger.debug(f"Getting up to {max_results} upcoming events.")
                        result = scheduling_manager.get_upcoming_events(service, max_results)
                        final_response = result # Pass the formatted list or error message

                    # Add delete_event handling if needed
                    # elif function_name == "delete_event":
                    #     summary = function_args.get("summary")
                    #     if not summary:
                    #         final_response = "Please tell me the summary of the event you want to delete."
                    #     else:
                    #         deleted = scheduling_manager.delete_event(service, summary)
                    #         final_response = f"OK. I've deleted the event '{summary}'." if deleted else f"Sorry, I couldn't find or delete the event '{summary}'."

                # --- Other Function Handling (Reminders, Web Search) ---
                elif function_name == "get_active_reminders":
                    # Pass user_id if reminders are user-specific
                    reminders = reminders_manager.get_active_reminders(user_id=user_id) # Assuming method needs user_id
                    if reminders:
                        final_response = "Here are your active reminders:\n" + "\n".join([f"- {r['reminder']} (ID: {r.get('_id', 'N/A')})" for r in reminders]) # Include ID if helpful
                    else:
                        final_response = "You have no active reminders."

                elif function_name == "add_reminder":
                    # Add user_id when adding reminder
                    reminder_text = function_args.get('reminder')
                    if reminder_text:
                         reminders_manager.add_reminder(user_id=user_id, reminder=reminder_text)
                         final_response = f"OK. I've added the reminder: '{reminder_text}'."
                    else:
                         final_response = "What reminder should I add?"

                elif function_name == "complete_reminder":
                    # Pass user_id when completing
                    reminder_text = function_args.get('reminder_text') # Or reminder_id if using IDs
                    if reminder_text:
                         success = reminders_manager.complete_reminder(user_id=user_id, reminder_text=reminder_text) # Assuming completion by text
                         final_response = f"OK. I've marked '{reminder_text}' as completed." if success else f"Sorry, I couldn't find an active reminder matching '{reminder_text}'."
                    else:
                         final_response = "Which reminder should I mark as completed?"


                elif function_name == "web_search":
                    query = function_args.get("query")
                    if query:
                         result = web_search(query=query, groq_client=groq_client)
                         # Check if result is a link or summary
                         if isinstance(result, str) and result.startswith("http"):
                             web_link = result # Assume it's a direct link
                             final_response = f"Here's a link I found for '{query}': {web_link}"
                         elif isinstance(result, str):
                             final_response = result # Assume it's a summary
                         else:
                             final_response = f"Sorry, I couldn't find information for '{query}'."
                    else:
                         final_response = "What would you like me to search for?"

                else:
                    final_response = f"Sorry, I don't know how to handle the function: {function_name}"

            except Exception as e:
                logger.error(f"Error executing function '{function_name}': {e}")
                logger.error(traceback.format_exc())
                final_response = f"Sorry, I encountered an error while trying to {function_name.replace('_', ' ')}."
        # --- Handling LLM's direct response (no tool call) ---
        else:
            try:
                # Check if content is already a JSON string containing 'response'
                if content and content.strip().startswith('{') and content.strip().endswith('}'):
                    parsed_content = json.loads(content)
                    if isinstance(parsed_content, dict) and "response" in parsed_content:
                        final_response = parsed_content["response"]
                    else:
                        # If JSON but not the expected format, use the raw content
                        final_response = content
                elif content:
                    # If not JSON, use the content directly
                    final_response = content
                else:
                    # Handle cases where the LLM might return empty content
                    logger.warning("LLM returned empty content and no tool calls.")
                    final_response = "I'm not sure how to respond to that. Can you please rephrase?"

            except json.JSONDecodeError:
                # If content is not valid JSON, treat it as a plain string response
                final_response = content if content else "I apologize, I couldn't generate a response."
            except Exception as parse_error:
                logger.error(f"Error parsing LLM content: {parse_error}")
                final_response = content # Fallback to raw content on other parsing errors

        # --- Return the final processed response ---
        # Note: auth_url is now potentially set within the calendar function handling
        return {
            'llm_resp': final_response,
            'event_link': event_link, # Will be None if not set
            'web_link': web_link,     # Will be None if not set
            'auth_url': auth_url      # Will be None if not set
        }

    except Exception as e:
        logger.error(f"Critical error in process_chat: {str(e)}")
        logger.error(traceback.format_exc())
        # Return a generic error message to the user
        return {
            'llm_resp': "Sorry, I encountered an internal error while processing your request.",
            'event_link': None,
            'web_link': None,
            'auth_url': None
        }


# Route for the root path: Always serve index.html. Frontend handles auth check and routing.
@app.route('/')
def serve_root():
    logger.debug("Serving index.html for root path '/'.")
    return send_from_directory(app.static_folder, 'index.html')


# Route for other paths: Serve static files or fallback to index.html for SPA routing
@app.route('/<path:path>')
def serve_static_or_index(path):
    static_folder = app.static_folder
    file_path = os.path.join(static_folder, path)

    # Check if the requested path corresponds to an existing static file
    if os.path.exists(file_path) and not os.path.isdir(file_path):
        # Serve the existing static file (e.g., main.js, styles.css)
        return send_from_directory(static_folder, path)
    else:
        # If it's not an existing file, assume it's a frontend route
        # and serve index.html to let React Router handle it.
        logger.debug(f"Path '{path}' not found as static file, serving index.html for SPA routing.")
        return send_from_directory(static_folder, 'index.html')


# Remove the old /oauth_callback route as it's replaced by /api/auth/google/callback
# @app.route('/oauth_callback')
# def oauth_callback():
#     ... (removed) ...

@app.route('/api/auth_status')
def auth_status():
    # Check authentication status based on session and potentially token.json validity
    user_id = session.get("user_id")
    google_authenticated = False
    user_info = None

    # Check if user is logged in via session
    if user_id:
        user = mongodb.get_user_by_id(user_id) or mongodb.get_user_by_google_id(user_id)
        if user:
             user_info = {
                 "id": str(user.get("_id", user.get("google_id"))),
                 "name": user.get("name"),
                 "email": user.get("email"),
                 "isGuest": user.get("is_guest", False)
             }
             # If user is not a guest, check Google auth status via AuthManager
             if not user.get("is_guest", True):
                  creds = auth_manager.get_credentials()
                  google_authenticated = creds is not None and creds.valid

    # If no user_id in session, still check if token.json exists and is valid
    elif os.path.exists(TOKEN_FILE):
         creds = auth_manager.get_credentials() # This will load/refresh if needed
         if creds and creds.valid:
             google_authenticated = True
             # Try to get user info to populate response if possible
             try:
                 g_user_info = auth_manager.get_user_info()
                 if g_user_info:
                      # Attempt to find user in DB based on email/sub from token
                      db_user = mongodb.get_user_by_google_id(g_user_info.get('sub')) or mongodb.get_user_by_email(g_user_info.get('email'))
                      if db_user:
                           user_info = {
                               "id": str(db_user.get("_id", db_user.get("google_id"))),
                               "name": db_user.get("name"),
                               "email": db_user.get("email"),
                               "isGuest": db_user.get("is_guest", False)
                           }
                           # Add user_id to session if found
                           session['user_id'] = user_info['id']
                           session.modified = True
                      else:
                           # If user not in DB but token valid, maybe just return basic info
                           user_info = {
                               "id": g_user_info.get('sub'),
                               "name": g_user_info.get('name'),
                               "email": g_user_info.get('email'),
                               "isGuest": False # Assume not guest if Google authenticated
                           }
             except Exception as e:
                  logger.warning(f"Error getting user info from valid token during auth_status check: {e}")


    return jsonify({
        'authenticated': bool(user_info), # Overall app auth status (session/guest)
        'google_authenticated': google_authenticated, # Specific Google API auth status
        'user': user_info # User details if available
    })


@app.route('/api/chat', methods=['POST'])
@login_required # Ensures session['user_id'] exists
def chat():
    try:
        data = request.json
        user_input = data.get('message')
        is_speech = data.get('is_speech', False)
        user_id = session.get('user_id') # Get user_id from session (guaranteed by @login_required)

        if not user_input:
             return jsonify({'error': 'No message provided'}), 400

        logger.info(f"User {user_id} | Input: '{user_input}' | Speech: {is_speech}")

        # Add user message to history
        history_manager.add_message(user_id, "user", user_input)

        # Process the chat using the updated logic
        resp = process_chat(user_input, user_id)

        # Get the response components
        final_response = resp.get('llm_resp', 'Sorry, I could not process that.')
        event_link = resp.get('event_link')
        web_link = resp.get('web_link') # Added web_link handling
        auth_url = resp.get('auth_url')

        # Add assistant response to history
        history_manager.add_message(user_id, "assistant", final_response)

        # Prepare response data
        response_data = {
            'response': final_response
        }

        # Add optional components if they exist
        if event_link:
            response_data['event_link'] = event_link
        if web_link:
            response_data['web_link'] = web_link
        if auth_url:
            response_data['auth_url'] = auth_url

        # --- Text-to-Speech Conversion ---
        if is_speech and final_response: # Only generate speech if there's text
            try:
                # Ensure the response isn't an error message asking for auth
                if not auth_url:
                     logger.info(f"Generating speech for response: '{final_response[:50]}...'")
                     audio_data = text_to_speech(final_response)
                     if audio_data:
                         response_data['audio'] = audio_data # Add base64 audio data
                         logger.info("Successfully generated audio response.")
                     else:
                         logger.error("Text-to-speech conversion returned no data.")
                else:
                     logger.info("Skipping speech generation for auth request.")

            except Exception as tts_error:
                logger.error(f"Error during text-to-speech conversion: {tts_error}")
                # Don't fail the whole request, just log the TTS error

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"Critical error in chat endpoint for user {user_id}: {str(e)}")
        logger.error(traceback.format_exc())
        # Return a generic error response
        return jsonify({
            'error': 'An internal server error occurred.',
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
        hf_token = os.environ.get('HUGGING_FACE_INFERENCEAPI')
        if not hf_token:
            raise ValueError("Hugging Face API token not found in environment variables")
            
        print("Using Hugging Face token")
        
        headers = {
            "Authorization": f"Bearer {hf_token}",
            "Content-Type": "audio/wav"
        }

        def query(filename):
            with open(filename, "rb") as f:
                data = f.read()
            response = requests.post(API_URL, headers=headers, data=data)
            print("Response status code:", response.status_code)
            print("Response headers:", response.headers)
            if response.status_code == 401:
                raise ValueError("Unauthorized: Please check your Hugging Face API token")
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
@login_required
def load_conversation_history():
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401

        today_doc = history_manager.get_today_document(user_id)
        if not today_doc or "messages" not in today_doc:
            return jsonify({"conversation_history": []}), 200

        conversation_history = []
        for message in today_doc["messages"]:
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
@login_required
def clear_chat_history():
    try:
        user_id = session.get('user_id')  # Get user_id from session instead of headers
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
            
        # Clear all conversations for the user
        history_manager.clear_history(user_id)
        # Clear all reminders for the user
        reminders_manager.clear_reminders(user_id)
        
        return jsonify({'message': 'Chat history and reminders cleared successfully'}), 200
    except Exception as e:
        logger.error(f"Error clearing chat history and reminders: {str(e)}")
        return jsonify({'error': f'An error occurred while clearing chat history and reminders: {str(e)}'}), 500

@app.before_request
def make_session_permanent():
    session.permanent = True
    # Log session data for debugging
    logger.debug(f"Session data: {dict(session)}")
    logger.debug(f"Request cookies: {request.cookies}")
    logger.debug(f"Request headers: {dict(request.headers)}")

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    # In production, host should be '0.0.0.0' to accept all incoming connections
    app.run(host='0.0.0.0', port=port, debug=False)
