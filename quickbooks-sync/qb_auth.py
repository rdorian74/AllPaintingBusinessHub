"""
QuickBooks OAuth 2.0 Authentication Handler
Handles initial authorization and token refresh
"""

import os
import json
import time
import base64
import requests
from datetime import datetime, timedelta
import config


class QBAuth:
    """Handles QuickBooks OAuth 2.0 authentication"""
    
    def __init__(self):
        self.client_id = config.CLIENT_ID
        self.client_secret = config.CLIENT_SECRET
        self.redirect_uri = config.REDIRECT_URI
        self.token_file = config.TOKEN_FILE
        self.tokens = self._load_tokens()
    
    def _load_tokens(self):
        """Load tokens from file"""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Error loading tokens: {e}")
        return {}
    
    def _save_tokens(self):
        """Save tokens to file"""
        try:
            with open(self.token_file, 'w') as f:
                json.dump(self.tokens, f, indent=2)
            print("✅ Tokens saved")
        except Exception as e:
            print(f"❌ Error saving tokens: {e}")
    
    def get_authorization_url(self):
        """Get the URL for user to authorize the app"""
        import urllib.parse
        
        params = {
            'client_id': self.client_id,
            'scope': config.SCOPES,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'state': 'allpainting'  # CSRF protection
        }
        
        url = f"{config.AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url
    
    def exchange_code_for_tokens(self, auth_code):
        """Exchange authorization code for access and refresh tokens"""
        
        # Create Basic Auth header
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {auth_bytes}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': self.redirect_uri
        }
        
        try:
            response = requests.post(config.TOKEN_URL, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Store tokens with expiry time
                self.tokens = {
                    'access_token': token_data['access_token'],
                    'refresh_token': token_data['refresh_token'],
                    'token_type': token_data.get('token_type', 'bearer'),
                    'expires_in': token_data.get('expires_in', 3600),
                    'obtained_at': datetime.now().isoformat(),
                    'expires_at': (datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat()
                }
                
                self._save_tokens()
                print("✅ Tokens obtained successfully")
                return True, "Authorization successful!"
            else:
                error_msg = response.json().get('error_description', response.text)
                print(f"❌ Token exchange failed: {error_msg}")
                return False, f"Token exchange failed: {error_msg}"
                
        except Exception as e:
            print(f"❌ Error exchanging code: {e}")
            return False, str(e)
    
    def refresh_access_token(self):
        """Refresh the access token using the refresh token"""
        
        if not self.tokens.get('refresh_token'):
            return False, "No refresh token available. Please re-authorize."
        
        # Create Basic Auth header
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {auth_bytes}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.tokens['refresh_token']
        }
        
        try:
            response = requests.post(config.TOKEN_URL, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Update tokens
                self.tokens['access_token'] = token_data['access_token']
                self.tokens['refresh_token'] = token_data.get('refresh_token', self.tokens['refresh_token'])
                self.tokens['expires_in'] = token_data.get('expires_in', 3600)
                self.tokens['obtained_at'] = datetime.now().isoformat()
                self.tokens['expires_at'] = (datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat()
                
                self._save_tokens()
                print("✅ Access token refreshed")
                return True, "Token refreshed successfully"
            else:
                error_msg = response.json().get('error_description', response.text)
                print(f"❌ Token refresh failed: {error_msg}")
                return False, f"Token refresh failed: {error_msg}"
                
        except Exception as e:
            print(f"❌ Error refreshing token: {e}")
            return False, str(e)
    
    def get_access_token(self):
        """Get a valid access token, refreshing if necessary"""
        
        if not self.tokens.get('access_token'):
            return None
        
        # Check if token is expired or about to expire (within 5 minutes)
        if self.tokens.get('expires_at'):
            try:
                expires_at = datetime.fromisoformat(self.tokens['expires_at'])
                if datetime.now() >= expires_at - timedelta(minutes=5):
                    print("🔄 Token expired or expiring soon, refreshing...")
                    success, msg = self.refresh_access_token()
                    if not success:
                        return None
            except Exception as e:
                print(f"⚠️ Error checking token expiry: {e}")
        
        return self.tokens.get('access_token')
    
    def is_authenticated(self):
        """Check if we have valid authentication"""
        return self.get_access_token() is not None
    
    def get_auth_status(self):
        """Get detailed authentication status"""
        if not self.tokens.get('access_token'):
            return {
                'authenticated': False,
                'message': 'Not authenticated. Please authorize the app.'
            }
        
        status = {
            'authenticated': True,
            'obtained_at': self.tokens.get('obtained_at'),
            'expires_at': self.tokens.get('expires_at')
        }
        
        if self.tokens.get('expires_at'):
            try:
                expires_at = datetime.fromisoformat(self.tokens['expires_at'])
                remaining = expires_at - datetime.now()
                status['expires_in_minutes'] = int(remaining.total_seconds() / 60)
                status['message'] = f"Authenticated. Token expires in {status['expires_in_minutes']} minutes."
            except:
                status['message'] = "Authenticated."
        
        return status
    
    def revoke_tokens(self):
        """Clear stored tokens (logout)"""
        self.tokens = {}
        if os.path.exists(self.token_file):
            os.remove(self.token_file)
        print("✅ Tokens revoked")
        return True
