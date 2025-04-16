import os
import requests
import json # Add json import
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
import logging
from datetime import datetime
from flask import make_response, jsonify

logger = logging.getLogger(__name__)

TOKEN_FILE = "token.json" # Define token file path

class AuthManager:
    def __init__(self, google_client_config):
        self.google_client_config = google_client_config
        self.credentials = self.load_credentials() # Try loading on init

    def load_credentials(self):
        """Loads credentials from token.json if it exists."""
        if os.path.exists(TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(TOKEN_FILE, self.get_scopes())
                # Check if credentials are valid or refreshable
                if creds and creds.valid:
                     logger.info("Loaded valid credentials from token.json")
                     return creds
                elif creds and creds.refresh_token:
                     logger.info("Loaded credentials from token.json, needs refresh.")
                     # Attempt to refresh
                     try:
                         request = google.auth.transport.requests.Request()
                         creds.refresh(request)
                         logger.info("Successfully refreshed credentials.")
                         self.save_credentials(creds) # Save refreshed token
                         return creds
                     except Exception as e:
                         logger.error(f"Failed to refresh credentials: {e}. Need re-authentication.")
                         os.remove(TOKEN_FILE) # Remove invalid token file
                         return None
                else:
                     logger.warning("token.json found but credentials invalid and not refreshable.")
                     os.remove(TOKEN_FILE) # Remove invalid token file
                     return None
            except Exception as e:
                logger.error(f"Error loading credentials from {TOKEN_FILE}: {e}")
                # If loading fails, remove potentially corrupt file
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                return None
        logger.info("token.json not found.")
        return None

    def save_credentials(self, credentials):
        """Saves credentials to token.json."""
        try:
            # Use credentials.to_json() which returns a JSON string
            creds_json_str = credentials.to_json()
            # Parse the string back to a dict to potentially add/modify
            creds_data = json.loads(creds_json_str)
            # Ensure client_id and client_secret from config are included if missing
            # (to_json might not include them depending on how creds were created)
            if 'client_id' not in creds_data:
                creds_data['client_id'] = self.google_client_config['web']['client_id']
            if 'client_secret' not in creds_data:
                creds_data['client_secret'] = self.google_client_config['web']['client_secret']

            with open(TOKEN_FILE, 'w') as token_file:
                # Dump the potentially augmented dict back to JSON
                json.dump(creds_data, token_file)
            logger.info(f"Credentials saved to {TOKEN_FILE}")
        except Exception as e:
            logger.error(f"Error saving credentials to {TOKEN_FILE}: {e}")

    def get_scopes(self):
        """Returns the list of scopes."""
        return [
            "openid",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/calendar"
        ]
    def create_oauth_flow(self, state=None):
        # ... (no changes needed here, but ensure scopes match get_scopes)
        try:
            flow = Flow.from_client_config(
                self.google_client_config,
                scopes=self.get_scopes() # Use helper method
            )
            flow.redirect_uri = self.google_client_config["web"]["redirect_uris"][0]
            logger.info(f"Created OAuth flow with redirect URI: {flow.redirect_uri}")
            return flow
        except Exception as e:
            logger.error(f"Error creating OAuth flow: {str(e)}")
            raise

    def get_authorization_url(self, state):
        # Check if we already have valid credentials
        if self.credentials and self.credentials.valid:
             logger.info("Valid credentials already exist. Skipping authorization URL generation.")
             # Indicate that auth is not needed
             return None # Or perhaps raise an exception or return a specific status

        # If no valid credentials, proceed to generate URL
        try:
            flow = self.create_oauth_flow(state)
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=state,
                prompt='consent'
            )
            logger.info(f"Generated authorization URL with state: {state}")
            return authorization_url
        except Exception as e:
            logger.error(f"Error getting authorization URL: {str(e)}")
            raise

    def handle_oauth_callback(self, authorization_response, state):
        try:
            logger.info(f"Handling OAuth callback with state: {state}")
            logger.info(f"Authorization response: {authorization_response}")

            flow = self.create_oauth_flow(state)
            # Fetch token using the authorization response
            flow.fetch_token(authorization_response=authorization_response)
            self.credentials = flow.credentials # Store credentials object

            logger.info("Successfully obtained credentials via OAuth callback.")

            # Save the obtained credentials to token.json
            self.save_credentials(self.credentials)

            # Return the credentials dictionary for session storage (as before)
            # Although the primary persistence is token.json, storing in session
            # might still be useful for the current request lifecycle.
            return {
                'token': self.credentials.token,
                'refresh_token': self.credentials.refresh_token,
                'token_uri': self.credentials.token_uri,
                'client_id': self.credentials.client_id,
                'client_secret': self.credentials.client_secret,
                'scopes': self.credentials.scopes
            }

        except Exception as e:
            logger.error(f"Error in handle_oauth_callback: {str(e)}")
            logger.error(f"Authorization response: {authorization_response}")
            logger.error(f"State: {state}")
            # Ensure credentials are None if callback fails
            self.credentials = None
            return None

    def get_credentials(self):
        """Returns the current credentials, attempting to load/refresh if needed."""
        if not self.credentials or not self.credentials.valid:
            self.credentials = self.load_credentials()
        return self.credentials

    def get_user_info(self, credentials=None): # Allow passing credentials or use stored ones
        creds_to_use = credentials or self.get_credentials() # Use passed or stored/loaded creds

        if not creds_to_use:
             logger.error("No valid credentials available to get user info.")
             raise ValueError("Authentication required.") # Or return None/raise specific error

        try:
            # Use the creds_to_use object directly
            request = google.auth.transport.requests.Request()
            # Refresh if necessary before making the request
            if not creds_to_use.valid and creds_to_use.refresh_token:
                try:
                    creds_to_use.refresh(request)
                    logger.info("Refreshed credentials before getting user info.")
                    self.save_credentials(creds_to_use) # Save refreshed token
                except Exception as refresh_error:
                    logger.error(f"Failed to refresh credentials before getting user info: {refresh_error}")
                    # Clear invalid credentials and potentially remove token file
                    self.credentials = None
                    if os.path.exists(TOKEN_FILE):
                        os.remove(TOKEN_FILE)
                    raise ValueError("Authentication required due to refresh failure.")

            # Check validity again after potential refresh
            if not creds_to_use.valid:
                 logger.error("Credentials invalid even after refresh attempt.")
                 raise ValueError("Authentication required.")

            # Make the API call using authorized session
            authed_session = google.auth.transport.requests.AuthorizedSession(creds_to_use)
            response = authed_session.get('https://www.googleapis.com/oauth2/v3/userinfo')

            response.raise_for_status()
            user_info = response.json()

            logger.info("Successfully retrieved user info")
            return user_info

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting user info: {str(e)}")
            if response := getattr(e, 'response', None):
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response body: {response.text}")
            # If auth error (e.g., 401), maybe clear credentials
            if response and response.status_code in [401, 403]:
                 self.credentials = None
                 if os.path.exists(TOKEN_FILE):
                     os.remove(TOKEN_FILE)
                 logger.warning("Authentication error fetching user info. Cleared credentials.")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting user info: {str(e)}")
            raise

    def create_success_response(self):
        """Create HTML response for successful authentication"""
        return make_response(
            """
            <html>
                <body>
                    <script>
                        function closeAndRedirect() {
                            if (window.opener) {
                                window.opener.location.href = '/';
                                setTimeout(function() {
                                    window.close();
                                }, 1000);
                            } else {
                                window.location.href = '/';
                            }
                        }
                        window.onload = closeAndRedirect;
                    </script>
                    <p>Login successful! Redirecting...</p>
                </body>
            </html>
            """
        )

    def create_guest_user_data(self, user_id, name):
        """Create user data for guest login"""
        return {
            "_id": user_id,
            "name": name,
            "is_guest": True,
            "created_at": datetime.utcnow()
        }

    def format_user_response(self, user):
        """Format user data for response"""
        return {
            "user": {
                "id": str(user.get("_id", user.get("google_id"))),
                "name": user.get("name"),
                "email": user.get("email"),
                "isGuest": user.get("is_guest", False)
            }
        } if user else {"user": None}

    def clear_credentials_file(self):
        """Deletes the token.json file if it exists."""
        if os.path.exists(TOKEN_FILE):
            try:
                os.remove(TOKEN_FILE)
                self.credentials = None # Clear loaded credentials in memory too
                logger.info(f"Successfully deleted {TOKEN_FILE}.")
                return True
            except Exception as e:
                logger.error(f"Error deleting {TOKEN_FILE}: {e}")
                return False
        else:
            logger.info(f"{TOKEN_FILE} not found, nothing to delete.")
            return True # Consider it success if file doesn't exist
