import os
import json
import pytz
from datetime import datetime
import datetime as dt
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
from config.settings import SCOPES, TOKEN_FILE, CREDENTIALS_FILE

logger = logging.getLogger(__name__)

class SchedulingManager:
    def get_google_calendar_service(self):
        try:
            creds = None
            if os.path.exists(TOKEN_FILE):
                try:
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
                except Exception as e:
                    logger.error(f"Error loading credentials from {TOKEN_FILE}: {e}")
                    os.remove(TOKEN_FILE)
                    creds = None

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        logger.info("Successfully refreshed credentials.")
                    except Exception as e:
                        logger.error(f"Error refreshing credentials: {e}")
                        creds = None

                if not creds:
                    if not os.path.exists(CREDENTIALS_FILE):
                        raise FileNotFoundError(f"Credentials file {CREDENTIALS_FILE} not found.")

                    flow = Flow.from_client_secrets_file(
                        CREDENTIALS_FILE,
                        scopes=SCOPES,
                        redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI")
                    )
                    auth_url, _ = flow.authorization_url(prompt='consent')
                    logger.info(f"Generated authorization URL: {auth_url}")
                    return None, auth_url

            if creds and creds.valid:
                with open(TOKEN_FILE, "w") as token_file:
                    token_file.write(creds.to_json())
                    logger.info(f"Saved credentials to {TOKEN_FILE}.")
                service = build("calendar", "v3", credentials=creds)
                return service, None

        except Exception as e:
            logger.error(f"Error in get_google_calendar_service: {e}")
            return None, None

    def handle_auth_callback(self, auth_code):
        try:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"Credentials file {CREDENTIALS_FILE} not found.")

            flow = Flow.from_client_secrets_file(
                CREDENTIALS_FILE,
                scopes=SCOPES,
                redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI")
            )
            flow.fetch_token(code=auth_code)
            creds = flow.credentials

            with open(TOKEN_FILE, "w") as token_file:
                token_file.write(creds.to_json())
                logger.info(f"Saved new credentials to {TOKEN_FILE}.")

            return build("calendar", "v3", credentials=creds)

        except Exception as e:
            logger.error(f"Error in handle_auth_callback: {e}")
            return None
    
    def create_event(self, service, event_details):
        def parse_datetime(dt_string):
            formats = [
                "%Y-%m-%d %I:%M:%S %p",
                "%Y-%m-%d %I:%M %p",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S"
            ]
            for fmt in formats:
                try:
                    naive_dt = datetime.strptime(dt_string, fmt)
                    return pytz.timezone("Asia/Kolkata").localize(naive_dt)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse datetime: {dt_string}")
        
        try:
            start_datetime = parse_datetime(event_details['start_time'])
            end_datetime = parse_datetime(event_details['end_time'])
            
            if end_datetime <= start_datetime:
                return None
            
            event = {
                "summary": event_details["summary"],
                "location": event_details.get("location", ""),
                "description": event_details.get("description", ""),
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "Asia/Kolkata",
                },
                "end": {
                    "dateTime": end_datetime.isoformat(),
                    "timeZone": "Asia/Kolkata",
                },
            }
            if "attendees" in event_details:
                event["attendees"] = [{"email": attendee} for attendee in event_details["attendees"]]
            
            event = service.events().insert(calendarId="primary", body=event).execute()
            return event.get('htmlLink')
        except ValueError as e:
            return None
        except HttpError as error:
            return None

    def get_event_id(self, service, summary):
        """Retrieve event ID based on event summary"""
        creds = None
        if os.path.exists('token.json'):
            with open('token.json', 'rb') as token:
                creds = json.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = Flow.from_client_secrets_file(
                    'credentials.json', SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f"Please go to this URL: {auth_url}")
                authorization_response = input("Enter the authorization code: ")
                flow.fetch_token(code=authorization_response)
                creds = flow.credentials
            
            with open('token.json', 'wb') as token:
                json.dump(creds, token)
        
        now = dt.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                            maxResults=100, singleEvents=True,
                                            orderBy='startTime').execute()
        events = events_result.get('items', [])

        for event in events:
            if event['summary'] == summary:
                return event['id']

        return None

    def delete_event(self, service, summary):
        event_id = self.get_event_id(service, summary)
        if event_id:
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            return True
        return False
        
    def get_upcoming_events(self, service, max_results):
        now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
        try:
            events_result = service.events().list(calendarId="primary", timeMin=now, 
                                                maxResults=max_results, singleEvents=True,
                                                orderBy="startTime").execute()
            events = events_result.get("items", [])
            
            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                if 'T' in start:
                    start_dt = dt.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    start_dt = start_dt.astimezone(pytz.timezone("Asia/Kolkata"))
                    formatted_start = start_dt.strftime("%Y-%m-%d %I:%M %p")
                else:
                    formatted_start = start
                
                formatted_events.append(f"{formatted_start}: {event['summary']}")
            
            response = "Here are your upcoming events:\n" + "\n".join(formatted_events)
            return response
        except HttpError as error:
            return "Failed to fetch upcoming events. Please try again."