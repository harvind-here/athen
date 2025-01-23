from dotenv import load_dotenv
import os

load_dotenv()

# User Settings
USER_NAME = os.getenv('USER_NAME', 'User')
USER_AGE = os.getenv('USER_AGE', 'Unknown')
USER_OCCUPATION = os.getenv('USER_OCCUPATION', 'Unknown')
USER_INTERESTS = os.getenv('USER_INTERESTS', 'Unknown')

# API Keys
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
VOICE_ID = os.getenv('VOICE_ID')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID')
GOOGLE_CALENDAR_CREDENTIALS = os.getenv('GOOGLE_CALENDAR_CREDENTIALS')
MONGODB_URI = os.getenv('MONGODB_URI')
HUGGING_FACE_INFERENCEAPI = os.getenv('HUGGING_FACE_INFERENCEAPI')

# Google Calendar Settings
SCOPES = "https://www.googleapis.com/auth/calendar"
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json" 