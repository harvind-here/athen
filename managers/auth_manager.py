import os
import requests
import json
import logging
import time
from datetime import datetime
from flask import make_response, jsonify, request

logger = logging.getLogger(__name__)

TOKEN_FILE_LOGIN = "token_login.json"
TOKEN_FILE_CALENDAR = "token_calendar.json"

class AuthManager:
    def __init__(self, google_client_config):
        self.google_client_config = google_client_config

    def get_login_scopes(self):
        return [
            "openid",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/userinfo.email",
        ]

    def get_calendar_scopes(self):
        return ["https://www.googleapis.com/auth/calendar"]

    def get_authorization_url(self, state, scopes, frontend_origin=None):
        try:
            params = {
                "client_id": self.google_client_config["web"]["client_id"],
                "redirect_uri": self.get_redirect_uri(frontend_origin),
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
                "state": state,
                "prompt": "consent",
            }
            auth_url = "https://accounts.google.com/o/oauth2/auth"
            return f"{auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        except Exception as e:
            logger.error(f"Error getting authorization URL: {str(e)}")
            raise

    def handle_oauth_callback(self, authorization_response, state, scopes, token_file, frontend_origin=None):
        try:
            code = request.args.get('code')
            data = {
                "code": code,
                "client_id": self.google_client_config["web"]["client_id"],
                "client_secret": self.google_client_config["web"]["client_secret"],
                "redirect_uri": self.get_redirect_uri(frontend_origin),
                "grant_type": "authorization_code",
            }
            response = requests.post("https://oauth2.googleapis.com/token", data=data)
            response.raise_for_status()
            credentials = response.json()
            self.save_credentials(credentials, token_file)
            return credentials
        except Exception as e:
            logger.error(f"Error in handle_oauth_callback: {str(e)}")
            return None

    def get_user_info(self):
        login_credentials = self.load_credentials(TOKEN_FILE_LOGIN, self.get_login_scopes())
        if not login_credentials:
            raise ValueError("User not logged in.")

        for attempt in range(3):
            try:
                headers = {"Authorization": f"Bearer {login_credentials['access_token']}"}
                response = requests.get('https://www.googleapis.com/oauth2/v3/userinfo', headers=headers, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                logger.error(f"Error getting user info (attempt {attempt + 1}): {str(e)}")
                if attempt < 2:
                    time.sleep(1) # wait 1 second before retrying
                else:
                    raise
        return None # Should not be reached, but as a fallback

    def get_redirect_uri(self, frontend_origin):
        redirect_uris = self.google_client_config["web"]["redirect_uris"]
        if frontend_origin:
            if 'localhost' in frontend_origin or '127.0.0.1' in frontend_origin:
                return next((uri for uri in redirect_uris if '127.0.0.1' in uri or 'localhost' in uri), redirect_uris[0])
            else:
                return next((uri for uri in redirect_uris if 'onrender' in uri), redirect_uris[0])
        else:
            host = request.host.split(':')[0]
            if host == 'localhost' or host == '127.0.0.1':
                return next((uri for uri in redirect_uris if '127.0.0.1' in uri or 'localhost' in uri), redirect_uris[0])
            else:
                return next((uri for uri in redirect_uris if 'onrender' in uri), redirect_uris[0])

    def save_credentials(self, credentials, token_file):
        try:
            with open(token_file, 'w') as f:
                json.dump(credentials, f)
            logger.info(f"Credentials saved to {token_file}")
        except Exception as e:
            logger.error(f"Error saving credentials to {token_file}: {e}")

    def load_credentials(self, token_file, scopes):
        if os.path.exists(token_file):
            try:
                with open(token_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading credentials from {token_file}: {e}")
                if os.path.exists(token_file):
                    os.remove(token_file)
                return None
        return None

    def format_user_response(self, user):
        return {
            "user": {
                "id": str(user.get("_id", user.get("google_id"))),
                "name": user.get("name"),
                "email": user.get("email"),
            }
        } if user else {"user": None}

    def clear_credentials_file(self):
        for token_file in [TOKEN_FILE_LOGIN, TOKEN_FILE_CALENDAR]:
            if token_file == "credentials.json":
                logger.warning("Attempted to delete credentials.json. Skipping.")
                continue
            if os.path.exists(token_file):
                try:
                    os.remove(token_file)
                    logger.info(f"Successfully deleted {token_file}.")
                except Exception as e:
                    logger.error(f"Error deleting {token_file}: {e}")

    def get_calendar_credentials(self):
        return self.load_credentials(TOKEN_FILE_CALENDAR, self.get_calendar_scopes())
