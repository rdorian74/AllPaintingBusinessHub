"""
Outlook Client - Microsoft Graph API integration for email operations
Bid/Addendum Agent - All Painting Ltd.
"""
import requests
from datetime import datetime, timedelta
import json
import base64
import os
import config


class OutlookClient:
    """Client for interacting with Outlook via Microsoft Graph API"""
    
    def __init__(self):
        self.client_id = config.AZURE_CLIENT_ID
        self.tenant_id = config.AZURE_TENANT_ID
        self.client_secret = config.AZURE_CLIENT_SECRET
        self.monitored_email = config.MONITORED_EMAIL
        self.access_token = None
        self.token_expires = None
    
    def _get_access_token(self):
        """Get or refresh the access token"""
        # Check if we have a valid token
        if self.access_token and self.token_expires:
            if datetime.now() < self.token_expires:
                return self.access_token
        
        # Request new token
        token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        
        token_data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials"
        }
        
        response = requests.post(token_url, data=token_data)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get access token: {response.text}")
        
        token_json = response.json()
        self.access_token = token_json["access_token"]
        # Token typically expires in 1 hour, we'll refresh 5 minutes early
        expires_in = token_json.get("expires_in", 3600)
        self.token_expires = datetime.now() + timedelta(seconds=expires_in - 300)
        
        return self.access_token
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """Make an authenticated request to Microsoft Graph API"""
        token = self._get_access_token()
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        url = f"https://graph.microsoft.com/v1.0{endpoint}"
        
        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data)
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, json=data)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        return response
    
    def get_recent_emails(self, minutes_back=10, exclude_addresses=None):
        """
        Get recent emails, excluding specific senders
        
        Args:
            minutes_back: How many minutes back to search
            exclude_addresses: List of email addresses to exclude
        
        Returns:
            List of email objects
        """
        # Calculate the time filter
        since_time = datetime.utcnow() - timedelta(minutes=minutes_back)
        since_str = since_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build filter query - just time filter, we'll filter senders in code
        filter_query = f"receivedDateTime ge {since_str}"
        
        # Make request
        endpoint = f"/users/{self.monitored_email}/messages"
        params = {
            "$filter": filter_query,
            "$orderby": "receivedDateTime desc",
            "$top": 50,
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments,internetMessageId"
        }
        
        response = self._make_request("GET", endpoint, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get emails: {response.text}")
        
        emails = response.json().get("value", [])
        
        # Filter out excluded addresses
        if exclude_addresses:
            exclude_lower = [e.lower() for e in exclude_addresses]
            emails = [
                e for e in emails 
                if e.get("from", {}).get("emailAddress", {}).get("address", "").lower() not in exclude_lower
            ]
        
        return emails
    
    def get_email_by_id(self, message_id):
        """Get a specific email by ID"""
        endpoint = f"/users/{self.monitored_email}/messages/{message_id}"
        params = {
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments,internetMessageId"
        }
        
        response = self._make_request("GET", endpoint, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get email: {response.text}")
        
        return response.json()
    
    def get_email_attachments(self, message_id):
        """Get attachments for a specific email"""
        endpoint = f"/users/{self.monitored_email}/messages/{message_id}/attachments"
        
        response = self._make_request("GET", endpoint)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get attachments: {response.text}")
        
        return response.json().get("value", [])
    
    def get_or_create_folder(self, folder_name):
        """Get or create a mail folder"""
        # First, try to find the folder
        endpoint = f"/users/{self.monitored_email}/mailFolders"
        params = {"$filter": f"displayName eq '{folder_name}'"}
        
        response = self._make_request("GET", endpoint, params=params)
        
        if response.status_code == 200:
            folders = response.json().get("value", [])
            if folders:
                return folders[0]["id"]
        
        # Folder doesn't exist, create it
        data = {"displayName": folder_name}
        response = self._make_request("POST", endpoint, data=data)
        
        if response.status_code in [200, 201]:
            print(f"   ✅ Created folder: {folder_name}")
            return response.json()["id"]
        else:
            raise Exception(f"Failed to create folder: {response.text}")
    
    def create_draft(self, to_email, subject, body_html, folder_id=None):
        """
        Create a draft email
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            folder_id: Optional folder ID to save the draft in
        
        Returns:
            Created message object
        """
        message_data = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ]
        }
        
        # Create the draft
        endpoint = f"/users/{self.monitored_email}/messages"
        response = self._make_request("POST", endpoint, data=message_data)
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create draft: {response.text}")
        
        draft = response.json()
        
        # If a folder is specified, move the draft to that folder
        if folder_id:
            move_endpoint = f"/users/{self.monitored_email}/messages/{draft['id']}/move"
            move_data = {"destinationId": folder_id}
            move_response = self._make_request("POST", move_endpoint, data=move_data)
            
            if move_response.status_code not in [200, 201]:
                print(f"   ⚠️ Warning: Could not move draft to folder: {move_response.text}")
        
        return draft
    
    def create_forward_draft(self, original_message_id, to_email, comment_html, folder_id=None):
        """
        Create a forward draft using Microsoft Graph's proper createForward endpoint.
        This properly marks the original email as forwarded and preserves attachments correctly.
        
        Args:
            original_message_id: ID of the original email to forward
            to_email: Recipient email address
            comment_html: HTML comment to add above the forwarded content
            folder_id: Optional folder ID to save the draft in
        
        Returns:
            Created message object with forward content and attachments
        """
        # Step 1: Create the forward draft using Graph API's createForward
        # This properly marks the original as forwarded and includes attachments
        endpoint = f"/users/{self.monitored_email}/messages/{original_message_id}/createForward"
        
        response = self._make_request("POST", endpoint)
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to create forward draft: {response.text}")
        
        draft = response.json()
        draft_id = draft["id"]
        
        print(f"      📧 Forward draft created (ID: {draft_id[:20]}...)")
        
        # Step 2: Update the draft to add our comment/summary and set the recipient
        # The createForward endpoint creates a draft but doesn't set recipients
        
        # Get the current body content (the forwarded message)
        original_forward_body = draft.get("body", {}).get("content", "")
        
        # Prepend our comment/summary to the forwarded content
        updated_body = f"""
{comment_html}

{original_forward_body}
"""
        
        # Update the draft with recipient and our comment
        update_data = {
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ],
            "body": {
                "contentType": "HTML",
                "content": updated_body
            }
        }
        
        update_endpoint = f"/users/{self.monitored_email}/messages/{draft_id}"
        update_response = self._make_request("PATCH", update_endpoint, data=update_data)
        
        if update_response.status_code not in [200, 201]:
            print(f"      ⚠️ Warning: Could not update draft: {update_response.text}")
        else:
            draft = update_response.json()
            print(f"      ✅ Draft updated with recipient and summary")
        
        # Step 3: Move to specified folder if provided
        if folder_id:
            move_endpoint = f"/users/{self.monitored_email}/messages/{draft_id}/move"
            move_data = {"destinationId": folder_id}
            move_response = self._make_request("POST", move_endpoint, data=move_data)
            
            if move_response.status_code not in [200, 201]:
                print(f"      ⚠️ Warning: Could not move draft to folder: {move_response.text}")
            else:
                # Update draft with moved message info
                draft = move_response.json()
                print(f"      ✅ Draft moved to folder")
        
        return draft
    
    def forward_email(self, message_id, to_email, comment_html):
        """
        Forward an email to a recipient
        
        Args:
            message_id: ID of the email to forward
            to_email: Recipient email address
            comment_html: HTML comment to add above the forwarded content
        
        Returns:
            Success status
        """
        endpoint = f"/users/{self.monitored_email}/messages/{message_id}/forward"
        
        data = {
            "comment": comment_html,
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email
                    }
                }
            ]
        }
        
        response = self._make_request("POST", endpoint, data=data)
        
        if response.status_code == 202:  # Forward returns 202 Accepted
            return {"success": True, "message": "Email forwarded successfully"}
        else:
            raise Exception(f"Failed to forward email: {response.text}")
    
    def mark_as_read(self, message_id):
        """Mark an email as read"""
        endpoint = f"/users/{self.monitored_email}/messages/{message_id}"
        data = {"isRead": True}
        
        response = self._make_request("PATCH", endpoint, data=data)
        
        return response.status_code == 200
    
    def test_connection(self):
        """Test the connection to Microsoft Graph API"""
        try:
            token = self._get_access_token()
            
            # Try to access the mailbox
            endpoint = f"/users/{self.monitored_email}/mailFolders/inbox"
            response = self._make_request("GET", endpoint)
            
            if response.status_code == 200:
                return {"success": True, "message": "Connection successful"}
            else:
                return {"success": False, "message": f"Error: {response.text}"}
        
        except Exception as e:
            return {"success": False, "message": str(e)}


# Test the client if run directly
if __name__ == "__main__":
    print("Testing Outlook Client for Bid Agent...")
    client = OutlookClient()
    
    # Test basic connection
    result = client.test_connection()
    print(f"Connection test: {result}")
    
    if result["success"]:
        # Test getting recent emails
        print("\nGetting recent emails (last 60 minutes)...")
        emails = client.get_recent_emails(minutes_back=60, exclude_addresses=config.IAN_EMAILS)
        print(f"Found {len(emails)} emails (excluding Ian)")
        
        for email in emails[:5]:
            sender = email.get("from", {}).get("emailAddress", {}).get("address", "unknown")
            subject = email.get("subject", "No subject")[:50]
            print(f"  - From: {sender} | Subject: {subject}")
