# Removed os, Request, Flow, SCOPES, TOKEN_FILE, CREDENTIALS_FILE imports as they are no longer needed here
import json
import pytz
import re # Add re import
from datetime import datetime
import datetime as dt
# Credentials might still be needed for type hinting if used, but not for logic
# from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging
# Removed config import

logger = logging.getLogger(__name__)

class SchedulingManager:
    # Removed handle_auth_callback method

    def get_google_calendar_service(self, auth_manager):
        """
        Gets the Google Calendar service object using credentials from AuthManager.
        Returns the service object if credentials are valid, otherwise None.
        Does NOT initiate authentication flow.
        """
        try:
            creds = auth_manager.get_credentials() # Get credentials from AuthManager

            if creds and creds.valid:
                service = build("calendar", "v3", credentials=creds)
                logger.info("Successfully built Google Calendar service.")
                return service
            else:
                logger.warning("No valid credentials available from AuthManager.")
                return None # Indicate that service cannot be built

        except Exception as e:
            # Catch potential errors during build() or get_credentials()
            logger.error(f"Error getting Google Calendar service: {e}")
            return None
    def create_event(self, service, event_details):
        # Check if service object is valid before proceeding
        if not service:
            logger.error("Cannot create event: Google Calendar service object is invalid or missing.")
            # Return an error message or raise an exception
            return "Error: Authentication required to create calendar events."

        def parse_datetime(dt_string):
            # Define all known formats, including the one with month name and AM/PM
            formats = [
                "%Y-%m-%d %I:%M:%S %p",  # Example: 2024-07-20 02:30:00 PM
                "%Y-%m-%d %I:%M %p",     # Example: 2024-07-20 02:30 PM
                "%Y-%m-%d %H:%M:%S",     # Example: 2024-07-20 14:30:00
                "%Y-%m-%dT%H:%M:%S",     # Example: 2024-07-20T14:30:00 (ISO format without timezone)
                "%Y-%m-%dT%H:%M:%S%z",   # Example: 2024-07-20T14:30:00+05:30
                "%I:%M %p, %d %B %Y",    # Example: 11:00 AM, 17 April 2025 (Handles ordinal in preprocessing)
                # Add other common formats if needed
                "%d %b %Y %I:%M %p",    # Example: 17 Apr 2025 11:00 AM
            ]

            # Preprocess string *once* to remove ordinal suffixes (st, nd, rd, th)
            # The 're' module is imported at the top of the file now
            processed_dt_string = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", dt_string)

            # Loop through all defined formats
            for fmt in formats:
                try:
                    # Try parsing the *processed* string using the current format
                    naive_dt = datetime.strptime(processed_dt_string, fmt)

                    # Localize the naive datetime object to the target timezone
                    return pytz.timezone("Asia/Kolkata").localize(naive_dt)

                except ValueError:
                    # If parsing fails with this format, try the next one
                    continue
                except pytz.exceptions.AmbiguousTimeError:
                     # Handle ambiguous times during DST transitions
                     logger.warning(f"Ambiguous time detected for '{dt_string}', resolving with is_dst=None.")
                     return pytz.timezone("Asia/Kolkata").localize(naive_dt, is_dst=None)
                except pytz.exceptions.NonExistentTimeError:
                     # Handle non-existent times during DST transitions
                     logger.warning(f"Non-existent time detected for '{dt_string}', resolving with is_dst=None.")
                     return pytz.timezone("Asia/Kolkata").localize(naive_dt, is_dst=None)

            # If the loop completes without returning, none of the formats matched
            logger.error(f"Failed to parse datetime string '{dt_string}' (processed as '{processed_dt_string}') with any known format.")
            raise ValueError(f"Unable to parse datetime string '{dt_string}' with known formats.")

        try:
            # Ensure start_time and end_time exist before parsing
            if 'start_time' not in event_details or not event_details['start_time']:
                 raise ValueError("Missing event start time.")
            if 'end_time' not in event_details or not event_details['end_time']:
                 raise ValueError("Missing event end time.")

            start_datetime = parse_datetime(event_details['start_time'])
            end_datetime = parse_datetime(event_details['end_time'])

            if end_datetime <= start_datetime:
                logger.error(f"End time ({end_datetime.strftime('%Y-%m-%d %H:%M:%S')}) must be after start time ({start_datetime.strftime('%Y-%m-%d %H:%M:%S')}).")
                return "Error: Event end time must be after the start time."

            event = {
                "summary": event_details["summary"],
                "location": event_details.get("location", ""),
                "description": event_details.get("description", ""),
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "Asia/Kolkata", # Explicitly set timezone
                },
                "end": {
                    "dateTime": end_datetime.isoformat(),
                    "timeZone": "Asia/Kolkata", # Explicitly set timezone
                },
            }
            if "attendees" in event_details and event_details["attendees"]:
                event["attendees"] = [{"email": attendee} for attendee in event_details["attendees"]]

            logger.info(f"Attempting to insert event: {event['summary']}")
            created_event = service.events().insert(calendarId="primary", body=event).execute()
            logger.info(f"Successfully created event. Link: {created_event.get('htmlLink')}")
            return created_event.get('htmlLink') # Return the link on success

        except ValueError as e:
            logger.error(f"Error parsing date/time for event creation: {e}")
            return f"Error: Could not understand the date or time provided - {e}"
        except HttpError as error:
            logger.error(f"Google Calendar API error during event creation: {error}")
            # Provide a more user-friendly error
            error_details = json.loads(error.content).get('error', {})
            message = error_details.get('message', 'An API error occurred.')
            return f"Error creating event: {message}. Please ensure I have the correct permissions."
        except Exception as e:
            logger.error(f"Unexpected error during event creation: {e}")
            return "An unexpected error occurred while creating the event."


    def get_event_id(self, service, summary):
        """Retrieve event ID based on event summary. Requires a valid service object."""
        if not service:
            logger.error("Cannot get event ID: Google Calendar service object is invalid or missing.")
            return None # Indicate failure

        try:
            now = dt.datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
            logger.info(f"Searching for event with summary: '{summary}' starting from {now}")

            events_result = service.events().list(
                calendarId='primary',
                timeMin=now,
                q=summary, # Use 'q' for free text search, more efficient
                maxResults=50, # Limit results for efficiency
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])
            logger.debug(f"Found {len(events)} potential matches for '{summary}'.")

            # Find the first exact match for the summary
            for event in events:
                if event.get('summary') == summary:
                    event_id = event.get('id')
                    logger.info(f"Found event ID '{event_id}' for summary '{summary}'.")
                    return event_id

            logger.warning(f"No upcoming event found with the exact summary: '{summary}'.")
            return None # Not found

        except HttpError as error:
            logger.error(f"Google Calendar API error during event search: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during event search: {e}")
            return None


    def delete_event(self, service, summary):
        """Deletes an event based on its summary. Requires a valid service object."""
        if not service:
            logger.error("Cannot delete event: Google Calendar service object is invalid or missing.")
            return False # Indicate failure

        try:
            event_id = self.get_event_id(service, summary) # Use the refactored method
            if event_id:
                logger.info(f"Attempting to delete event with ID: {event_id} (Summary: '{summary}')")
                service.events().delete(calendarId='primary', eventId=event_id).execute()
                logger.info(f"Successfully deleted event with ID: {event_id}")
                return True # Indicate success
            else:
                logger.warning(f"Cannot delete event: No event found with summary '{summary}'.")
                return False # Indicate event not found

        except HttpError as error:
            logger.error(f"Google Calendar API error during event deletion: {error}")
            # Check if it's a 'not found' error, which might happen in race conditions
            if error.resp.status == 404:
                 logger.warning(f"Event with summary '{summary}' (ID: {event_id}) was already deleted or not found (404).")
                 return False # Treat as 'not found'
            return False # Indicate failure for other errors
        except Exception as e:
            logger.error(f"Unexpected error during event deletion: {e}")
            return False


    def get_upcoming_events(self, service, max_results):
        """Gets upcoming events. Requires a valid service object."""
        if not service:
            logger.error("Cannot get upcoming events: Google Calendar service object is invalid or missing.")
            return "Error: Authentication required to fetch calendar events."

        now = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc).isoformat()
        logger.info(f"Fetching up to {max_results} upcoming events from {now}")

        try:
            events_result = service.events().list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime"
            ).execute()

            events = events_result.get("items", [])
            logger.debug(f"Retrieved {len(events)} upcoming events.")

            if not events:
                return "You have no upcoming events."

            formatted_events = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'No Title')

                # Handle date vs dateTime
                if 'T' in start: # It's a dateTime
                    try:
                        # Parse ISO format, potentially with 'Z' or offset
                        if start.endswith('Z'):
                            start_dt_utc = dt.datetime.fromisoformat(start.replace('Z', '+00:00'))
                        else:
                            start_dt_utc = dt.datetime.fromisoformat(start)

                        # Convert to local timezone (Asia/Kolkata)
                        start_dt_local = start_dt_utc.astimezone(pytz.timezone("Asia/Kolkata"))
                        formatted_start = start_dt_local.strftime("%d %b %Y, %I:%M %p") # Example: 20 Jul 2024, 02:30 PM
                    except ValueError:
                        formatted_start = start # Fallback if parsing fails
                else: # It's an all-day date
                    try:
                        # Parse YYYY-MM-DD format
                        start_dt = dt.datetime.strptime(start, "%Y-%m-%d").date()
                        formatted_start = start_dt.strftime("%d %b %Y") + " (All day)" # Example: 20 Jul 2024 (All day)
                    except ValueError:
                         formatted_start = start # Fallback

                formatted_events.append(f"- {formatted_start}: {summary}")

            response = "Here are your upcoming events:\n" + "\n".join(formatted_events)
            return response

        except HttpError as error:
            logger.error(f"Google Calendar API error fetching upcoming events: {error}")
            error_details = json.loads(error.content).get('error', {})
            message = error_details.get('message', 'An API error occurred.')
            return f"Error fetching upcoming events: {message}. Please ensure I have the correct permissions."
        except Exception as e:
            logger.error(f"Unexpected error fetching upcoming events: {e}")
            return "An unexpected error occurred while fetching upcoming events."
