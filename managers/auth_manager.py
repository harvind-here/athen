import os
import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from pip._vendor import cachecontrol
import google.auth.transport.requests
import logging
from datetime import datetime
from flask import make_response, jsonify

logger = logging.getLogger(__name__)

class AuthManager:
    def __init__(self, google_client_config):
        self.google_client_config = google_client_config
        
    def create_oauth_flow(self, state=None):
        try:
            flow = Flow.from_client_config(
                self.google_client_config,
                scopes=[
                    "openid",
                    "https://www.googleapis.com/auth/userinfo.profile",
                    "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/calendar"
                ]
            )
            
            # Set the redirect URI from the config
            flow.redirect_uri = self.google_client_config["web"]["redirect_uris"][0]
            
            logger.info(f"Created OAuth flow with redirect URI: {flow.redirect_uri}")
            return flow
            
        except Exception as e:
            logger.error(f"Error creating OAuth flow: {str(e)}")
            raise
        
    def get_authorization_url(self, state):
        try:
            flow = self.create_oauth_flow(state)
            authorization_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                state=state,
                prompt='consent'  # Always show consent screen
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
            flow.fetch_token(authorization_response=authorization_response)
            credentials = flow.credentials
            
            logger.info("Successfully obtained credentials")
            
            return {
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            }
            
        except Exception as e:
            logger.error(f"Error in handle_oauth_callback: {str(e)}")
            logger.error(f"Authorization response: {authorization_response}")
            logger.error(f"State: {state}")
            return None
            
    def get_user_info(self, credentials):
        try:
            session = requests.session()
            cached_session = cachecontrol.CacheControl(session)
            
            headers = {
                'Authorization': f'Bearer {credentials.token}',
                'Accept': 'application/json'
            }
            
            response = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers=headers,
                timeout=10
            )
            
            response.raise_for_status()
            user_info = response.json()
            
            logger.info("Successfully retrieved user info")
            return user_info
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting user info: {str(e)}")
            if response := getattr(e, 'response', None):
                logger.error(f"Response status: {response.status_code}")
                logger.error(f"Response body: {response.text}")
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