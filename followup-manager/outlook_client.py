"""
Follow Up Manager - Outlook Client
Microsoft Graph API operations
"""
import requests
import logging
from datetime import datetime, timedelta
from config import (
    AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET,
    GRAPH_API_BASE, TOKEN_URL, MONITORED_EMAIL
)

logger = logging.getLogger(__name__)

class OutlookClient:
    def __init__(self):
        self.token = None
        self.token_expires = None
        self.email = MONITORED_EMAIL
    
    def _get_token(self):
        """Get or refresh access token"""
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            return self.token
        
        resp = requests.post(TOKEN_URL, data={
            "client_id": AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        })
        resp.raise_for_status()
        data = resp.json()
        self.token = data["access_token"]
        self.token_expires = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)
        return self.token
    
    def _request(self, method, endpoint, **kwargs):
        """Make authenticated request"""
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._get_token()}"
        headers["Content-Type"] = "application/json"
        
        url = f"{GRAPH_API_BASE}{endpoint}"
        resp = requests.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else None
    
    def _get_all_pages(self, endpoint, params=None):
        """Fetch all pages"""
        items = []
        url = f"{GRAPH_API_BASE}{endpoint}"
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        
        headers = {"Authorization": f"Bearer {self._get_token()}"}
        
        while url:
            resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
        
        return items
    
    # === Email Fetching ===
    
    def get_sent_emails(self, since_date):
        """Get sent emails since date"""
        params = {
            "$filter": f"sentDateTime ge {since_date}T00:00:00Z",
            "$orderby": "sentDateTime desc",
            "$top": "100",
            "$select": "id,subject,toRecipients,sentDateTime,bodyPreview,hasAttachments,conversationId"
        }
        return self._get_all_pages(f"/users/{self.email}/mailFolders/SentItems/messages", params)
    
    def get_inbox_emails(self, since_date):
        """Get inbox emails since date"""
        params = {
            "$filter": f"receivedDateTime ge {since_date}T00:00:00Z",
            "$orderby": "receivedDateTime desc",
            "$top": "100",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,conversationId"
        }
        return self._get_all_pages(f"/users/{self.email}/mailFolders/Inbox/messages", params)
    
    def get_message(self, message_id):
        """Get full message"""
        return self._request("GET", f"/users/{self.email}/messages/{message_id}")
    
    def get_attachments(self, message_id):
        """Get message attachments"""
        result = self._request("GET", f"/users/{self.email}/messages/{message_id}/attachments")
        return result.get("value", []) if result else []
    
    def get_pdf_attachments(self, message_id):
        """Get PDF attachments only"""
        attachments = self.get_attachments(message_id)
        return [a for a in attachments if a.get("name", "").lower().endswith(".pdf")]
    
    # === Draft Creation ===
    
    def get_folder_id(self, folder_name):
        """Get folder ID by name, create if doesn't exist"""
        try:
            # Search in mail folders
            folders = self._request("GET", f"/users/{self.email}/mailFolders")
            for folder in folders.get("value", []):
                if folder.get("displayName", "").lower() == folder_name.lower():
                    return folder.get("id")
            
            # Create folder if not found
            new_folder = self._request("POST", f"/users/{self.email}/mailFolders", json={
                "displayName": folder_name
            })
            return new_folder.get("id")
        except Exception as e:
            logger.warning(f"Folder error: {e}")
            return None
    
    def create_draft(self, to_email, subject, body_html, folder_id=None):
        """Create a draft in specified folder"""
        draft_data = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": to_email}}]
        }
        
        # Create in specific folder or default drafts
        if folder_id:
            endpoint = f"/users/{self.email}/mailFolders/{folder_id}/messages"
        else:
            endpoint = f"/users/{self.email}/messages"
        
        return self._request("POST", endpoint, json=draft_data)
    
    def create_forward_draft(self, original_message_id, body_html, to_email, folder_id=None):
        """
        Create a forward draft that includes the original email.
        The body_html goes in the 'comment' which appears above the forwarded content.
        """
        try:
            # Create forward draft with message and recipient together
            draft = self._request("POST", 
                f"/users/{self.email}/messages/{original_message_id}/createForward",
                json={
                    "comment": body_html,
                    "toRecipients": [{"emailAddress": {"address": to_email}}]
                }
            )
            
            if not draft or not draft.get("id"):
                return None
            
            draft_id = draft["id"]
            
            # Move to Draft Follow Up folder
            if folder_id:
                try:
                    moved = self._request("POST", f"/users/{self.email}/messages/{draft_id}/move", json={
                        "destinationId": folder_id
                    })
                    if moved and moved.get("id"):
                        draft_id = moved["id"]
                except Exception as e:
                    logger.warning(f"Could not move draft to folder: {e}")
            
            return {"id": draft_id}
            
        except Exception as e:
            logger.error(f"Forward draft error: {e}")
            return None
    
    def create_threaded_draft(self, to_email, subject, body_html, original_message_id=None, use_followup_folder=True):
        """
        Create a draft with thread history in Draft Follow Up folder.
        """
        # Get Draft Follow Up folder
        folder_id = None
        if use_followup_folder:
            folder_id = self.get_folder_id("Draft Follow Up")
        
        if original_message_id:
            draft = self.create_forward_draft(original_message_id, body_html, to_email, folder_id)
            if draft:
                return {"id": draft.get("id"), "method": "forward"}
        
        # Fallback to simple draft
        draft = self.create_draft(to_email, subject, body_html, folder_id)
        return {"id": draft.get("id") if draft else None, "method": "new"}
    
    def get_draft(self, draft_id):
        """Get draft by ID"""
        try:
            return self._request("GET", f"/users/{self.email}/messages/{draft_id}")
        except:
            return None
    
    # === Send ===
    
    def send_email(self, to_email, subject, body_html):
        """Send email directly"""
        return self._request("POST", f"/users/{self.email}/sendMail", json={
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": body_html},
                "toRecipients": [{"emailAddress": {"address": to_email}}]
            }
        })


# Singleton
_client = None
def get_outlook_client():
    global _client
    if _client is None:
        _client = OutlookClient()
    return _client
