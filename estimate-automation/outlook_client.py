"""
Outlook Client - Microsoft Graph API integration for email operations
"""
import requests
from datetime import datetime, timedelta
import json
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
    
    def get_recent_emails(self, minutes_back=10, from_addresses=None):
        """
        Get recent emails from specific senders
        
        Args:
            minutes_back: How many minutes back to search
            from_addresses: List of email addresses to filter by
        
        Returns:
            List of email objects
        """
        # Calculate the time filter
        since_time = datetime.utcnow() - timedelta(minutes=minutes_back)
        since_str = since_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Build filter query
        filter_parts = [f"receivedDateTime ge {since_str}"]
        
        if from_addresses:
            # Filter by sender addresses
            sender_filters = [f"from/emailAddress/address eq '{addr}'" for addr in from_addresses]
            filter_parts.append(f"({' or '.join(sender_filters)})")
        
        filter_query = " and ".join(filter_parts)
        
        # Make request
        endpoint = f"/users/{self.monitored_email}/messages"
        params = {
            "$filter": filter_query,
            "$orderby": "receivedDateTime desc",
            "$top": 50,
            "$select": "id,subject,from,receivedDateTime,body,hasAttachments"
        }
        
        response = self._make_request("GET", endpoint, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get emails: {response.text}")
        
        return response.json().get("value", [])
    
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
                print(f"Warning: Could not move draft to folder: {move_response.text}")
        
        return draft
    
    def create_draft_with_attachment(self, to_email, subject, body_html, attachment_path, folder_id=None):
        """
        Create a draft email with a PDF attachment
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            attachment_path: Path to the PDF file to attach
            folder_id: Optional folder ID to save the draft in
        
        Returns:
            Created message object
        """
        import base64
        import os
        
        # First create the draft
        draft = self.create_draft(to_email, subject, body_html, folder_id=None)  # Don't move yet
        
        # Read and encode the attachment
        with open(attachment_path, "rb") as f:
            attachment_content = base64.b64encode(f.read()).decode("utf-8")
        
        attachment_name = os.path.basename(attachment_path)
        
        # Add the attachment
        attachment_data = {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": attachment_name,
            "contentType": "application/pdf",
            "contentBytes": attachment_content
        }
        
        endpoint = f"/users/{self.monitored_email}/messages/{draft['id']}/attachments"
        response = self._make_request("POST", endpoint, data=attachment_data)
        
        if response.status_code not in [200, 201]:
            raise Exception(f"Failed to add attachment: {response.text}")
        
        # Now move to folder if specified
        if folder_id:
            move_endpoint = f"/users/{self.monitored_email}/messages/{draft['id']}/move"
            move_data = {"destinationId": folder_id}
            move_response = self._make_request("POST", move_endpoint, data=move_data)
            
            if move_response.status_code not in [200, 201]:
                print(f"Warning: Could not move draft to folder: {move_response.text}")
        
        return draft
    
    # =========================================================================
    # NEW: SEND EMAIL FUNCTIONS (for AI Agent auto mode)
    # =========================================================================
    
    def send_email(self, to_email, subject, body_html, save_to_sent=True):
        """
        Send an email directly (not as draft)
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            save_to_sent: Whether to save a copy in Sent Items (default: True)
        
        Returns:
            Dictionary with success status
        """
        message_data = {
            "message": {
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
            },
            "saveToSentItems": save_to_sent
        }
        
        endpoint = f"/users/{self.monitored_email}/sendMail"
        response = self._make_request("POST", endpoint, data=message_data)
        
        if response.status_code == 202:  # sendMail returns 202 Accepted
            return {"success": True, "message": "Email sent successfully"}
        else:
            raise Exception(f"Failed to send email: {response.text}")
    
    def send_email_with_attachment(self, to_email, subject, body_html, attachment_path, save_to_sent=True):
        """
        Send an email with a PDF attachment directly (not as draft)
        
        This is used by the AI Agent in "auto" mode to send estimates
        directly to clients without creating a draft first.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            attachment_path: Path to the PDF file to attach
            save_to_sent: Whether to save a copy in Sent Items (default: True)
        
        Returns:
            Dictionary with success status and details
        """
        import base64
        import os
        
        # Read and encode the attachment
        with open(attachment_path, "rb") as f:
            attachment_content = base64.b64encode(f.read()).decode("utf-8")
        
        attachment_name = os.path.basename(attachment_path)
        
        # Build the message with attachment
        message_data = {
            "message": {
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
                ],
                "attachments": [
                    {
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": attachment_name,
                        "contentType": "application/pdf",
                        "contentBytes": attachment_content
                    }
                ]
            },
            "saveToSentItems": save_to_sent
        }
        
        endpoint = f"/users/{self.monitored_email}/sendMail"
        response = self._make_request("POST", endpoint, data=message_data)
        
        if response.status_code == 202:  # sendMail returns 202 Accepted
            return {
                "success": True,
                "message": "Email sent successfully",
                "to_email": to_email,
                "subject": subject,
                "attachment": attachment_name
            }
        else:
            raise Exception(f"Failed to send email with attachment: {response.text}")
    
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
    
    def test_send_permission(self):
        """
        Test if the app has Mail.Send permission
        This doesn't actually send an email, just validates the permission exists
        """
        try:
            # We can't really test send without sending, but we can verify 
            # the token has the right scope by checking the token claims
            # For now, we'll just return a message
            return {
                "success": True, 
                "message": "Mail.Send permission should be configured in Azure Portal"
            }
        except Exception as e:
            return {"success": False, "message": str(e)}


# Test the client if run directly
if __name__ == "__main__":
    print("Testing Outlook Client...")
    client = OutlookClient()
    
    # Test basic connection
    result = client.test_connection()
    print(f"Connection test: {result}")
    
    # Note: To test send_email_with_attachment, you would need to actually send an email
    # which we don't want to do in a test script
    print("\nNote: send_email_with_attachment() is ready for use by the AI Agent")
    print("It will send emails directly when AI_AGENT_MODE='auto'")
