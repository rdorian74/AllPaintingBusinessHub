"""
Bid Email Scanner - All Painting Ltd.
Port: 3031

PURPOSE: Monitors info@allpaintingltd.com for bid invitations.
When it finds one, it extracts the project details using AI (Claude),
then saves it to the bid database.

This is a background service with API endpoints - no web UI.
The bid-center dashboard calls these APIs.

INHERITED FROM: ai-agent-pipedrive/backfill.py
"""

import os
import re
import json
import sqlite3
import logging
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, jsonify, request

# =============================================================================
# CONFIGURATION (inherited from ai-agent-pipedrive)
# =============================================================================

PORT = 3031
APP_NAME = "Bid Email Scanner"
APP_VERSION = "2.0.0"

# Database path - this app OWNS the bid_tracker.db
DATABASE_PATH = os.path.join(os.path.dirname(__file__), "bid_tracker.db")

# Azure / Microsoft Graph API credentials (from ai-agent-pipedrive/backfill.py)
AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
MONITORED_EMAIL = "info@allpaintingltd.com"

# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Emails to ignore - Ian's emails (from ai-agent-pipedrive/backfill.py)
IAN_EMAILS = [
    "emeraldpainting@gmail.com",
    "ianc@allpaintingltd.com"
]

# Bid keywords for initial filtering (from ai-agent-pipedrive/backfill.py)
BID_KEYWORDS = [
    "bid", "bids", "bidding", "bidder", "bidders",
    "tender", "tenders", "tendering",
    "addendum", "addenda", "addendums",
    "rfp", "rfps", "rfq", "rfqs", "rfi", "rfis",
    "itt", "itts", "itb", "itbs",
    "invitation to bid", "invitation to tender",
    "request for proposal", "request for quote",
    "bid due", "bid deadline", "bid closing",
    "tender due", "tender deadline",
    "pre-qualification", "prequalification",
    "bid submission", "tender submission",
    "bid documents", "tender documents",
    "clarification", "clarifications",
    "site meeting", "site visit",
    "amendment", "amendments",
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Background scanner state
_scanner_running = False
_scanner_thread = None
_last_scan_time = None
_last_scan_result = None


# =============================================================================
# DATABASE FUNCTIONS (inherited from ai-agent-pipedrive/database.py)
# =============================================================================

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize the bid_tracker database (schema from ai-agent-pipedrive)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Main bid tracker table (exact schema from ai-agent-pipedrive)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bid_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            gc_company TEXT,
            gc_contact_email TEXT,
            gc_contact_name TEXT,
            gc_phone TEXT,
            bid_due_date TEXT,
            bid_due_time TEXT,
            project_address TEXT,
            scope_of_work TEXT,
            bid_reference_number TEXT,
            project_type TEXT,
            current_addendum INTEGER DEFAULT 0,
            status TEXT DEFAULT 'open',
            original_bid_email_date TEXT,
            source_email_ids TEXT,
            all_email_subjects TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Scanner settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scanner_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    ''')
    
    # Processed emails table (to avoid re-processing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id TEXT PRIMARY KEY,
            subject TEXT,
            processed_at TEXT,
            result TEXT
        )
    ''')
    
    # Default settings
    defaults = {
        'auto_scan_enabled': 'false',
        'scan_interval_minutes': '15',
        'days_to_scan': '7'
    }
    
    for key, value in defaults.items():
        cursor.execute('''
            INSERT OR IGNORE INTO scanner_settings (key, value, updated_at) 
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


def get_setting(key: str, default: str = None) -> str:
    """Get a setting value"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM scanner_settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key: str, value: str):
    """Set a setting value"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO scanner_settings (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_all_bids() -> List[Dict]:
    """Get all bids from database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bid_by_id(bid_id: int) -> Optional[Dict]:
    """Get a specific bid by ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker WHERE id = ?', (bid_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def is_email_processed(message_id: str) -> bool:
    """Check if an email has already been processed"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM processed_emails WHERE message_id = ?', (message_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_email_processed(message_id: str, subject: str, result: str):
    """Mark an email as processed"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO processed_emails (message_id, subject, processed_at, result)
        VALUES (?, ?, ?, ?)
    ''', (message_id, subject, datetime.now().isoformat(), result))
    conn.commit()
    conn.close()


def clear_processed_emails() -> int:
    """Clear all processed email records to allow re-scanning"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM processed_emails')
    count = cursor.fetchone()[0]
    cursor.execute('DELETE FROM processed_emails')
    conn.commit()
    conn.close()
    logger.info(f"Cleared {count} processed email records")
    return count


def update_bid_from_rescan(bid_id: int, extracted: Dict):
    """Update a bid with re-scanned information"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Only update fields that have values in the new extraction
    updates = []
    values = []
    
    field_mapping = {
        'project_name': 'project_name',
        'gc_company': 'gc_company',
        'gc_contact_email': 'gc_contact_email',
        'gc_contact_name': 'gc_contact_name',
        'gc_phone': 'gc_phone',
        'bid_due_date': 'bid_due_date',
        'bid_due_time': 'bid_due_time',
        'project_address': 'project_address',
        'scope_of_work': 'scope_of_work',
        'bid_reference_number': 'bid_reference_number',
        'project_type': 'project_type'
    }
    
    for extract_key, db_field in field_mapping.items():
        if extracted.get(extract_key):
            updates.append(f"{db_field} = ?")
            values.append(extracted[extract_key])
    
    if updates:
        values.append(bid_id)
        query = f"UPDATE bid_tracker SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, values)
        conn.commit()
        logger.info(f"Updated bid {bid_id} with {len(updates)} fields")
    
    conn.close()


def create_bid(extracted: Dict, from_address: str, from_name: str,
               received_at: str, message_id: str, subject: str) -> int:
    """Create a new bid in the database (from ai-agent-pipedrive/backfill.py)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO bid_tracker (
            project_name, gc_company, gc_contact_email, gc_contact_name,
            gc_phone, bid_due_date, bid_due_time, project_address, 
            scope_of_work, bid_reference_number, project_type,
            original_bid_email_date, source_email_ids, all_email_subjects,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        extracted.get("project_name"),
        extracted.get("gc_company"),
        extracted.get("gc_contact_email") or from_address,
        extracted.get("gc_contact_name") or from_name,
        extracted.get("gc_phone"),
        extracted.get("bid_due_date"),
        extracted.get("bid_due_time"),
        extracted.get("project_address"),
        extracted.get("scope_of_work"),
        extracted.get("bid_reference_number"),
        extracted.get("project_type"),
        received_at,
        json.dumps([message_id]),
        json.dumps([subject]),
        datetime.now().isoformat()
    ))
    
    bid_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    logger.info(f"Created bid ID {bid_id}: {extracted.get('project_name')}")
    return bid_id


def update_bid_addendum(bid_id: int, extracted: Dict):
    """Update an existing bid with addendum info (from ai-agent-pipedrive/backfill.py)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current addendum count
    cursor.execute("SELECT current_addendum FROM bid_tracker WHERE id = ?", (bid_id,))
    row = cursor.fetchone()
    current = row[0] if row and row[0] else 0
    
    # Update
    updates = {"current_addendum": current + 1, "updated_at": datetime.now().isoformat()}
    if extracted.get("bid_due_date"):
        updates["bid_due_date"] = extracted["bid_due_date"]
    if extracted.get("bid_due_time"):
        updates["bid_due_time"] = extracted["bid_due_time"]
    
    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    cursor.execute(
        f"UPDATE bid_tracker SET {set_clause} WHERE id = ?",
        list(updates.values()) + [bid_id]
    )
    
    conn.commit()
    conn.close()
    
    logger.info(f"Updated bid ID {bid_id} with addendum #{current + 1}")


def get_bids_due_on_date(date_str: str) -> List[Dict]:
    """Get all bids due on a specific date (from ai-agent-pipedrive/database.py)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM bid_tracker 
        WHERE date(bid_due_date) = date(?)
        ORDER BY project_name
    ''', (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bids_due_today() -> List[Dict]:
    """Get all bids due today"""
    today = datetime.now().strftime('%Y-%m-%d')
    return get_bids_due_on_date(today)


def get_bids_due_tomorrow() -> List[Dict]:
    """Get all bids due tomorrow"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    return get_bids_due_on_date(tomorrow)


def get_bids_due_in_range(start_date: str, end_date: str) -> List[Dict]:
    """Get all bids due between two dates"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM bid_tracker 
        WHERE date(bid_due_date) >= date(?) AND date(bid_due_date) <= date(?)
        ORDER BY bid_due_date, project_name
    ''', (start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# OUTLOOK CLIENT (inherited from ai-agent-pipedrive/backfill.py - OutlookGraphClient)
# =============================================================================

class OutlookClient:
    """Microsoft Graph API client for accessing emails (from ai-agent-pipedrive/backfill.py)"""
    
    def __init__(self):
        self.client_id = AZURE_CLIENT_ID
        self.tenant_id = AZURE_TENANT_ID
        self.client_secret = AZURE_CLIENT_SECRET
        self.monitored_email = MONITORED_EMAIL
        self.access_token = None
        self.token_expires = None
    
    def _get_access_token(self):
        """Get or refresh the access token"""
        if self.access_token and self.token_expires:
            if datetime.now() < self.token_expires:
                return self.access_token
        
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
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        return response
    
    def test_connection(self) -> Dict:
        """Test the connection"""
        try:
            self._get_access_token()
            endpoint = f"/users/{self.monitored_email}/mailFolders/inbox"
            response = self._make_request("GET", endpoint)
            
            if response.status_code == 200:
                return {"success": True, "message": "Connection successful"}
            else:
                return {"success": False, "message": f"Error: {response.text}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_mail_folders(self) -> List[Dict]:
        """Get all mail folders (from ai-agent-pipedrive/backfill.py)"""
        endpoint = f"/users/{self.monitored_email}/mailFolders"
        params = {"$top": 100}
        
        response = self._make_request("GET", endpoint, params=params)
        
        if response.status_code != 200:
            raise Exception(f"Failed to get mail folders: {response.text}")
        
        folders = response.json().get("value", [])
        
        # Also get child folders for each folder
        all_folders = []
        for folder in folders:
            all_folders.append({
                "id": folder["id"],
                "name": folder["displayName"],
                "total_count": folder.get("totalItemCount", 0),
                "unread_count": folder.get("unreadItemCount", 0),
                "parent_id": None
            })
            
            # Get child folders
            child_endpoint = f"/users/{self.monitored_email}/mailFolders/{folder['id']}/childFolders"
            child_response = self._make_request("GET", child_endpoint)
            if child_response.status_code == 200:
                child_folders = child_response.json().get("value", [])
                for child in child_folders:
                    all_folders.append({
                        "id": child["id"],
                        "name": f"{folder['displayName']} / {child['displayName']}",
                        "total_count": child.get("totalItemCount", 0),
                        "unread_count": child.get("unreadItemCount", 0),
                        "parent_id": folder["id"]
                    })
        
        return all_folders
    
    def get_inbox_folder_id(self) -> Optional[str]:
        """Get the Inbox folder ID"""
        try:
            endpoint = f"/users/{self.monitored_email}/mailFolders/Inbox"
            response = self._make_request("GET", endpoint)
            if response.status_code == 200:
                return response.json().get("id")
            return None
        except Exception as e:
            logger.error(f"Error getting Inbox folder: {e}")
            return None
    
    def get_emails_in_range(self, start_date: datetime, end_date: datetime, 
                           folder_id: str = None,
                           max_emails: int = 500,
                           inbox_only: bool = True) -> List[Dict]:
        """
        Get emails within a date range (from ai-agent-pipedrive/backfill.py)
        """
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        filter_query = f"receivedDateTime ge {start_str} and receivedDateTime le {end_str}"
        
        # Default to Inbox folder if inbox_only is True and no folder specified
        if inbox_only and not folder_id:
            folder_id = self.get_inbox_folder_id()
            if folder_id:
                logger.info(f"Scanning Inbox folder only (ID: {folder_id[:20]}...)")
        
        # Use specific folder or default to all messages
        if folder_id:
            endpoint = f"/users/{self.monitored_email}/mailFolders/{folder_id}/messages"
        else:
            endpoint = f"/users/{self.monitored_email}/messages"
        
        params = {
            "$filter": filter_query,
            "$orderby": "receivedDateTime desc",
            "$top": min(max_emails, 100),
            "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments"
        }
        
        all_emails = []
        
        while len(all_emails) < max_emails:
            response = self._make_request("GET", endpoint, params=params)
            
            if response.status_code != 200:
                raise Exception(f"Failed to get emails: {response.text}")
            
            data = response.json()
            emails = data.get("value", [])
            all_emails.extend(emails)
            
            # Check for next page
            next_link = data.get("@odata.nextLink")
            if not next_link or len(emails) == 0:
                break
            
            # Update endpoint for pagination
            endpoint = next_link.replace("https://graph.microsoft.com/v1.0", "")
            params = None  # Parameters are in the nextLink
        
        # Filter out Ian's emails (from ai-agent-pipedrive/backfill.py)
        ian_emails_lower = [e.lower() for e in IAN_EMAILS]
        filtered = [
            e for e in all_emails
            if e.get("from", {}).get("emailAddress", {}).get("address", "").lower() not in ian_emails_lower
        ]
        
        return filtered[:max_emails]
    
    def get_email_by_id(self, message_id: str) -> Optional[Dict]:
        """Get a specific email by its message ID"""
        try:
            endpoint = f"/users/{self.monitored_email}/messages/{message_id}"
            params = {
                "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments"
            }
            
            response = self._make_request("GET", endpoint, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get email {message_id}: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting email {message_id}: {e}")
            return None


# =============================================================================
# BID EMAIL ANALYZER (inherited from ai-agent-pipedrive/backfill.py - BidEmailAnalyzer)
# =============================================================================

class BidEmailAnalyzer:
    """Analyzes emails to detect bids using Claude AI (from ai-agent-pipedrive/backfill.py)"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
    
    def keyword_scan(self, text: str) -> List[str]:
        """Quick keyword scan before using Claude API"""
        text_lower = text.lower()
        text_lower = re.sub(r'\s+', ' ', text_lower)
        
        matched = []
        for keyword in BID_KEYWORDS:
            if len(keyword) <= 3:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, text_lower):
                    matched.append(keyword)
            else:
                if keyword.lower() in text_lower:
                    matched.append(keyword)
        
        return matched
    
    def analyze_email(self, email_data: Dict, existing_bids: List[Dict] = None) -> Dict:
        """
        Analyze an email using Claude AI (from ai-agent-pipedrive/backfill.py)
        """
        from anthropic import Anthropic
        
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")
        body_preview = email_data.get("body_preview", "")
        from_address = email_data.get("from_address", "")
        from_name = email_data.get("from_name", "")
        cc_addresses = email_data.get("cc_addresses", [])
        
        # Always use full body - clean HTML tags but keep content
        # Don't fall back to body_preview as it misses important details like due dates!
        email_content = body if body else body_preview
        email_content = re.sub(r'<[^>]+>', ' ', email_content)  # Remove HTML tags
        email_content = re.sub(r'&nbsp;', ' ', email_content)   # Replace &nbsp;
        email_content = re.sub(r'&[a-zA-Z]+;', '', email_content)  # Remove other HTML entities
        email_content = re.sub(r'\s+', ' ', email_content).strip()  # Normalize whitespace
        
        # For very long emails, keep beginning AND end (signature/contact info is often at the end)
        max_content_length = 12000
        if len(email_content) > max_content_length:
            # Keep first 8000 chars and last 4000 chars (for signatures/contact info)
            beginning = email_content[:8000]
            ending = email_content[-4000:]
            email_content = beginning + "\n\n[... middle content truncated ...]\n\n" + ending
            logger.info(f"Email truncated: kept first 8000 + last 4000 chars")
        
        # Log body content for debugging date extraction issues
        logger.info(f"Analyzing email: {subject[:60]}...")
        logger.info(f"Body length: raw={len(body)}, cleaned={len(email_content)}")
        
        # Check if body contains date-related keywords
        date_keywords = ['tender closing', 'deadline', 'due by', 'due date', 'submit by', 'before', 'closing date']
        found_date_keywords = [kw for kw in date_keywords if kw in email_content.lower()]
        if found_date_keywords:
            logger.info(f"Found date keywords in body: {found_date_keywords}")
        
        prompt = self._build_prompt(email_data, email_content, existing_bids)
        
        try:
            client = Anthropic(api_key=self.api_key)
            
            response = client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text
            result = self._parse_response(response_text)
            
            # Calculate cost
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cost = (input_tokens * 3.00 / 1_000_000) + (output_tokens * 15.00 / 1_000_000)
            
            result["cost"] = round(cost, 6)
            result["input_tokens"] = input_tokens
            result["output_tokens"] = output_tokens
            
            return result
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return {
                "valid": False,
                "category": "error",
                "reason": str(e),
                "cost": 0
            }
    
    def _build_prompt(self, email_data: Dict, email_content: str, 
                      existing_bids: List[Dict] = None) -> str:
        """Build the analysis prompt (from ai-agent-pipedrive/backfill.py - exact prompt)"""
        
        subject = email_data.get("subject", "")
        from_address = email_data.get("from_address", "")
        from_name = email_data.get("from_name", "")
        cc_addresses = email_data.get("cc_addresses", [])
        
        prompt = f"""You are an email classifier for All Painting Ltd., a commercial painting contractor.
Analyze this email to determine if it's a legitimate INCOMING bid invitation that we need to respond to.

**TODAY'S DATE: {datetime.now().strftime('%Y-%m-%d')} ({datetime.now().strftime('%A, %B %d, %Y')})**

## EMAIL TO ANALYZE

**From:** {from_name} <{from_address}>
**Subject:** {subject}
**CC:** {', '.join(cc_addresses) if cc_addresses else 'None'}
**Email Date:** {email_data.get('received_datetime', 'Unknown')}

**Body:**
{email_content[:12000]}

## CLASSIFICATION RULES

**VALID emails (INCOMING bid requests we need to respond to):**
1. **New Bid Invitation**: Invitation to bid on a painting project FROM a general contractor TO us
2. **Addendum**: Update or amendment to an existing bid we're working on
3. **Clarification**: Response to questions about a bid

**INVALID emails (do NOT include):**
1. **Outgoing Estimates**: Emails with "Estimate:" or "Quote:" in subject - these are OUR estimates going OUT
2. **Estimate Confirmations**: Replies to our own estimates (e.g., "RE: Estimate: 25C-284...")
3. **Newsletter/Marketing**: Marketing emails, company newsletters
4. **Spam**: Unsolicited sales emails
5. **Internal/Admin**: Account notices, subscription confirmations
6. **Unrelated**: Emails not about construction bids
7. **Bid Submission Confirmations**: Confirmation that we submitted a bid

**IMPORTANT: If the email subject contains "Estimate:" followed by a reference number (like "Estimate: 25C-284"), this is an OUTGOING estimate from All Painting, NOT an incoming bid request. Mark as INVALID.**

## GC CONTACT EMAIL - IMPORTANT

**⚠️ CRITICAL: READ THE ENTIRE EMAIL INCLUDING THE SIGNATURE AT THE BOTTOM!**
**Contact information is often at the END of the email in the signature block!**

**IGNORE these tracking/system email addresses and extract the REAL contact email from the email body:**
- Anything ending in @shared1.ccsend.com (Constant Contact)
- Anything ending in @smartbidnet.com (SmartBidNet)  
- Anything ending in @buildingconnected.com (BuildingConnected - look for real GC email in body)
- Anything containing "notifications@" or "noreply@"

If the From address is one of these tracking emails, search the EMAIL BODY and SIGNATURE for:
- The actual GC company name
- The estimator/contact person's name
- Their direct email address (often in signature)
- Their phone number (often in signature)

## ⚠️ CRITICAL: BID DUE DATE EXTRACTION ⚠️

**THIS IS THE MOST IMPORTANT FIELD - YOU MUST FIND AND EXTRACT THE DATE**

**READ THE ENTIRE EMAIL BODY CAREFULLY - The deadline is almost always mentioned somewhere.**

**Search for ALL of these trigger phrases (case-insensitive):**
1. **Tender/Bid closing phrases:**
   - "Tender closing" / "Tender closes"
   - "Bid closing" / "Bid closes" / "Bids close"
   - "Closing date" / "Close date"
   - "Tender due" / "Tenders due"
   
2. **Due/Deadline phrases:**
   - "Due by" / "Due date" / "Due on" / "Due:"
   - "Deadline" / "Deadline:"
   - "Bids due" / "Bid due" / "Pricing due"
   - "Submit by" / "Submission deadline" / "Submission date"
   
3. **Price/Quote request phrases:**
   - "I will need your price before"
   - "Please submit your price by"
   - "Need your quote by"
   - "Pricing required by"
   - "Please provide pricing by"
   - "Quote deadline"
   
4. **Response/Return phrases:**
   - "Please respond by"
   - "Response required by"
   - "Return by"
   - "RSVP by"

**Date formats to recognize and convert:**
- "February 8th, 2026" → "2026-02-08"
- "February 8, 2026" → "2026-02-08"
- "Feb 8, 2026" → "2026-02-08"
- "Feb 8th, 2026" → "2026-02-08"
- "8th February 2026" → "2026-02-08"
- "02/08/2026" or "2/8/2026" → "2026-02-08"
- "08-Feb-2026" → "2026-02-08"
- "2026-02-08" → "2026-02-08"
- "February 8" (no year) → assume current/next year → "2026-02-08"

**Day + Date combinations:**
- "Tuesday, February 8th" → "2026-02-08"
- "on February 8th" → "2026-02-08"
- "before February 8th" → "2026-02-08"

**Relative dates (calculate from today {datetime.now().strftime('%Y-%m-%d')}):**
- "next Tuesday" → calculate actual date
- "this Friday" → calculate actual date
- "in 2 weeks" → calculate actual date
- "by end of month" → last day of current month
- "end of January" → "2026-01-31"

**EXAMPLES FROM REAL EMAILS:**
- "Tender closing: I will need your price before 12 noon on February 8th, 2026" → "2026-02-08"
- "Bids are due by 2:00 PM on Tuesday, January 28th" → "2026-01-28"
- "Please submit your bid no later than January 28, 2026" → "2026-01-28"
- "Deadline: Jan 28/26" → "2026-01-28"
- "Pricing due: January 28" → "2026-01-28"
- "Tender closes January 30, 2026 at 2pm" → "2026-01-30"
- "We need your price by Friday" → calculate the date

**⚠️ BUILDINGCONNECTED EMAILS - SPECIAL FORMAT:**
BuildingConnected emails have a specific format with structured sections. Look for:
- **"Project Details"** section containing: Location, Bid Due date
- **"Client Details"** section containing: Lead contact name, phone, email, company name
- **"Bid Due:"** field - this is the deadline date (extract it!)
- Even if year shows "2025", if the date hasn't passed yet in 2026, use 2026

**If you see a BuildingConnected email format:**
1. Find "Bid Due:" field → extract the date
2. Find "Lead:" field → extract contact name, phone, email  
3. Find "Location:" field → extract project address
4. The GC company name is usually after the contact email

**IMPORTANT RULES:**
1. ALWAYS convert to YYYY-MM-DD format
2. If year is not specified, assume current year (or next year if date has passed)
3. If no explicit date but email mentions "ASAP" or "urgent", use 7 days from email date
4. If this is an addendum, look for UPDATED/NEW deadline dates
5. **DO NOT return null for bid_due_date if ANY date reference exists in the email**

**BID DUE TIME:**
- Look for times near the deadline: "12 noon", "2:00 PM", "10:00am", "end of day", "COB"
- "noon" or "12 noon" = "12:00 PM"
- "COB" or "end of day" or "close of business" = "5:00 PM"
- Include timezone if mentioned (e.g., "2:00 PM PST", "10:00 AM Pacific")
- Default to "2:00 PM PST" if date found but no time specified

**GC CONTACT INFO - EXTRACT FROM EMAIL SIGNATURE:**
- **Contact Name**: Look carefully in the signature block
- **Phone**: Look for phone numbers in signature - format: xxx-xxx-xxxx
- **Email**: Find the REAL email, not tracking emails

**PROJECT ADDRESS:**
- Look for street addresses, city names, locations
- Include full address: street, city, province/state

## WHAT TO EXTRACT

- **Project Name**: The name of the project (e.g., "Vancouver Library Renovation")
- **Bid Reference Number**: Official bid/tender number if provided
- **GC Company**: General contractor company name (check email signature, letterhead)
- **GC Contact Name**: Person's full name (check signature block carefully)
- **GC Phone**: Phone number (check signature block, often after name)
- **GC Contact Email**: The REAL email address, NOT tracking emails
- **Bid Due Date**: MUST be in YYYY-MM-DD format - THIS IS CRITICAL
- **Bid Due Time**: Time with timezone (default "2:00 PM PST" if date found but no time)
- **Project Address**: Full street address of the project
- **Project Type**: Commercial / Residential / Government / Institutional
- **Scope of Work**: Brief description of painting scope
- **Addendum Number**: If this is an addendum, what number

"""
        
        if existing_bids:
            prompt += "\n## EXISTING BIDS (for duplicate detection)\n\n"
            prompt += "**Check if this email is about the SAME PROJECT as any existing bid.**\n"
            prompt += "**Match by: project address, GC company + similar project name, or same GC contact.**\n\n"
            for bid in existing_bids[:30]:
                prompt += f"- ID: {bid.get('id')} | Project: {bid.get('project_name', 'Unknown')} | GC: {bid.get('gc_company', 'Unknown')} | Address: {bid.get('project_address', 'N/A')} | Email: {bid.get('gc_contact_email', 'N/A')}\n"
            prompt += "\nIf this email matches an existing bid, provide the matching bid ID.\n"
        
        prompt += """
## RESPONSE FORMAT

Respond with ONLY this JSON (no other text):

```json
{
    "valid": true or false,
    "category": "new_bid" | "addendum" | "clarification" | "invalid",
    "reason": "Brief explanation",
    "confidence": "high" | "medium" | "low",
    "extracted_info": {
        "project_name": "string or null",
        "bid_reference_number": "string or null",
        "gc_company": "string or null - CHECK EMAIL SIGNATURE AND LETTERHEAD",
        "gc_contact_name": "string or null - LOOK IN EMAIL SIGNATURE BLOCK",
        "gc_phone": "string or null - LOOK IN EMAIL SIGNATURE FOR PHONE NUMBERS",
        "gc_contact_email": "REAL email address - NOT tracking emails like @ccsend.com or @buildingconnected.com",
        "bid_due_date": "YYYY-MM-DD format - ALWAYS TRY TO EXTRACT A DATE",
        "bid_due_time": "string with timezone, default '2:00 PM PST' if date found",
        "project_address": "full street address or null",
        "project_type": "Commercial/Residential/Government/Institutional or null",
        "scope_of_work": "string or null",
        "addendum_number": number or null
    },
    "matching_bid_id": number or null,
    "summary": "2-3 sentence summary"
}
```

CRITICAL REMINDERS:
1. If subject contains "Estimate:" with a reference number -> INVALID (it's our outgoing estimate)
2. Extract REAL GC email, not tracking emails (@ccsend.com, @smartbidnet.com, @buildingconnected.com)
3. Check existing bids for duplicates - same project address or same GC + similar name = duplicate
4. **BID DUE DATE IS CRITICAL** - Search the entire email for any date reference related to submission deadline
5. If date found but no time, default to "2:00 PM PST"
"""
        return prompt
    
    def _parse_response(self, response_text: str) -> Dict:
        """Parse Claude's JSON response"""
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("No JSON found")
            
            result = json.loads(json_str)
            
            if "valid" not in result:
                result["valid"] = False
            if "category" not in result:
                result["category"] = "unknown"
            if "extracted_info" not in result:
                result["extracted_info"] = {}
            
            return result
            
        except Exception as e:
            return {
                "valid": False,
                "category": "error",
                "reason": f"Parse error: {str(e)}",
                "extracted_info": {}
            }


# =============================================================================
# EMAIL SCANNING FUNCTIONS
# =============================================================================

def scan_emails(days_back: int = None) -> Dict:
    """Scan emails and process bid invitations (from ai-agent-pipedrive/backfill.py)"""
    global _last_scan_time, _last_scan_result
    
    if days_back is None:
        days_back = int(get_setting('days_to_scan', '7'))
    
    summary = {
        "total_emails_scanned": 0,
        "keyword_matches": 0,
        "valid_bids": 0,
        "new_bids_created": 0,
        "addendums_updated": 0,
        "duplicates_skipped": 0,
        "already_processed": 0,
        "errors": 0,
        "total_cost": 0,
        "scan_time": datetime.now().isoformat()
    }
    
    try:
        outlook = OutlookClient()
        analyzer = BidEmailAnalyzer(api_key=ANTHROPIC_API_KEY, model=CLAUDE_MODEL)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        logger.info(f"Scanning emails from {start_date} to {end_date}")
        emails = outlook.get_emails_in_range(start_date, end_date)
        summary["total_emails_scanned"] = len(emails)
        logger.info(f"Found {len(emails)} emails to process")
        
        # Get existing bids for duplicate detection
        existing_bids = get_all_bids()
        
        for email in emails:
            message_id = email.get("id", "")
            subject = email.get("subject", "")
            body = email.get("body", {}).get("content", "")
            body_preview = email.get("bodyPreview", "")
            from_address = email.get("from", {}).get("emailAddress", {}).get("address", "")
            from_name = email.get("from", {}).get("emailAddress", {}).get("name", "")
            received_at = email.get("receivedDateTime", "")
            
            # Skip if already processed
            if is_email_processed(message_id):
                summary["already_processed"] += 1
                continue
            
            # Step 1: Keyword scan (free, no API cost)
            text_to_scan = f"{subject} {body_preview}"
            keywords = analyzer.keyword_scan(text_to_scan)
            
            if not keywords:
                mark_email_processed(message_id, subject, "no_keywords")
                continue
            
            summary["keyword_matches"] += 1
            
            # Step 2: Claude analysis
            email_data = {
                "subject": subject,
                "body": body,
                "body_preview": body_preview,
                "from_address": from_address,
                "from_name": from_name,
                "received_datetime": received_at,
                "cc_addresses": [r.get("emailAddress", {}).get("address", "") 
                               for r in email.get("ccRecipients", [])]
            }
            
            analysis = analyzer.analyze_email(email_data, existing_bids)
            summary["total_cost"] += analysis.get("cost", 0)
            
            if not analysis.get("valid"):
                mark_email_processed(message_id, subject, f"invalid:{analysis.get('reason', 'unknown')}")
                continue
            
            summary["valid_bids"] += 1
            extracted = analysis.get("extracted_info", {})
            category = analysis.get("category", "new_bid")
            matching_bid_id = analysis.get("matching_bid_id")
            
            # Step 3: Create or update bid
            if matching_bid_id:
                if category == "addendum":
                    update_bid_addendum(matching_bid_id, extracted)
                    summary["addendums_updated"] += 1
                    mark_email_processed(message_id, subject, f"addendum_updated:{matching_bid_id}")
                else:
                    summary["duplicates_skipped"] += 1
                    mark_email_processed(message_id, subject, f"duplicate:{matching_bid_id}")
            else:
                bid_id = create_bid(
                    extracted,
                    from_address,
                    from_name,
                    received_at,
                    message_id,
                    subject
                )
                summary["new_bids_created"] += 1
                mark_email_processed(message_id, subject, f"created:{bid_id}")
                
                # Add to existing bids for future duplicate detection in this scan
                existing_bids.append({
                    "id": bid_id,
                    "project_name": extracted.get("project_name"),
                    "gc_company": extracted.get("gc_company"),
                    "gc_contact_email": extracted.get("gc_contact_email"),
                    "project_address": extracted.get("project_address")
                })
        
        logger.info(f"Scan complete: {summary['new_bids_created']} new, {summary['addendums_updated']} addendums")
        
    except Exception as e:
        logger.error(f"Scan error: {e}")
        summary["error"] = str(e)
        summary["errors"] += 1
    
    _last_scan_time = datetime.now()
    _last_scan_result = summary
    
    # Add alias fields for dashboard compatibility
    summary["emails_analyzed"] = summary["keyword_matches"]  # Emails that were sent to Claude
    summary["bids_updated"] = summary["addendums_updated"]   # Alias for addendums
    summary["skipped_already_processed"] = summary["already_processed"]
    
    # Add a human-readable message
    if summary["already_processed"] > 0 and summary["new_bids_created"] == 0:
        summary["message"] = f"All {summary['total_emails_scanned']} emails were already processed. {summary['already_processed']} skipped."
    else:
        summary["message"] = f"Scanned {summary['total_emails_scanned']} emails. Found {summary['new_bids_created']} new bids, {summary['addendums_updated']} addendums."
    
    return summary


# =============================================================================
# BACKGROUND SCANNER
# =============================================================================

def scanner_loop():
    """Background loop that scans for new emails periodically"""
    global _scanner_running
    
    logger.info("Background scanner started")
    
    while _scanner_running:
        try:
            # Check if auto-scan is enabled
            if get_setting('auto_scan_enabled', 'false') != 'true':
                time.sleep(60)
                continue
            
            # Get interval
            interval = int(get_setting('scan_interval_minutes', '15'))
            
            # Run scan
            logger.info("Auto-scan triggered")
            scan_emails()
            
            # Sleep for interval (check every 10 seconds if we should stop)
            sleep_remaining = interval * 60
            while sleep_remaining > 0 and _scanner_running:
                time.sleep(min(10, sleep_remaining))
                sleep_remaining -= 10
                
        except Exception as e:
            logger.error(f"Scanner loop error: {e}")
            time.sleep(60)
    
    logger.info("Background scanner stopped")


def start_scanner():
    """Start the background scanner"""
    global _scanner_thread, _scanner_running
    
    if _scanner_running:
        return
    
    _scanner_running = True
    _scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
    _scanner_thread.start()
    logger.info("Scanner thread started")


def stop_scanner():
    """Stop the background scanner"""
    global _scanner_running
    _scanner_running = False
    logger.info("Scanner stop requested")


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    """Service info"""
    return jsonify({
        "service": APP_NAME,
        "version": APP_VERSION,
        "port": PORT,
        "purpose": "Monitors info@allpaintingltd.com for bid invitations. "
                   "When it finds one, it extracts the project details using AI (Claude), "
                   "then saves it to the bid database."
    })


@app.route('/api/status')
def api_status():
    """Get scanner status"""
    return jsonify({
        "service": APP_NAME,
        "running": _scanner_running,
        "auto_scan_enabled": get_setting('auto_scan_enabled', 'false') == 'true',
        "scan_interval_minutes": int(get_setting('scan_interval_minutes', '15')),
        "days_to_scan": int(get_setting('days_to_scan', '7')),
        "last_scan_time": _last_scan_time.isoformat() if _last_scan_time else None,
        "last_scan_result": _last_scan_result,
        "total_bids": len(get_all_bids())
    })


@app.route('/api/test-connection')
def api_test_connection():
    """Test connection to Outlook"""
    outlook = OutlookClient()
    result = outlook.test_connection()
    return jsonify(result)


@app.route('/api/folders')
def api_get_folders():
    """Get available mail folders"""
    try:
        outlook = OutlookClient()
        folders = outlook.get_mail_folders()
        return jsonify({"success": True, "folders": folders})
    except Exception as e:
        logger.error(f"Error getting folders: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """Manually trigger a scan"""
    data = request.get_json() or {}
    days_back = data.get('days_back')
    force_rescan = data.get('force_rescan', False)
    
    logger.info(f"API scan called: days_back={days_back}, force_rescan={force_rescan}")
    
    # If force_rescan, clear processed emails first
    if force_rescan:
        cleared = clear_processed_emails()
        logger.info(f"Force rescan: cleared {cleared} processed email records")
    
    result = scan_emails(days_back=days_back)
    result["force_rescan_used"] = force_rescan
    return jsonify(result)


@app.route('/api/clear-processed', methods=['POST'])
def api_clear_processed():
    """Clear the processed emails log to allow re-scanning"""
    try:
        count = clear_processed_emails()
        return jsonify({
            "success": True,
            "message": f"Cleared {count} processed email records. Next scan will re-analyze all emails.",
            "cleared_count": count
        })
    except Exception as e:
        logger.error(f"Error clearing processed emails: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/rescan-bid/<int:bid_id>', methods=['POST'])
def api_rescan_bid(bid_id):
    """Re-scan a specific bid's original email to update its details"""
    try:
        # Get the bid
        bid = get_bid_by_id(bid_id)
        if not bid:
            return jsonify({"success": False, "error": "Bid not found"}), 404
        
        # Get source email IDs
        source_ids_raw = bid.get('source_email_ids', '[]')
        if isinstance(source_ids_raw, str):
            try:
                source_ids = json.loads(source_ids_raw)
            except:
                source_ids = []
        else:
            source_ids = source_ids_raw or []
        
        if not source_ids:
            return jsonify({"success": False, "error": "No source email IDs found for this bid"}), 400
        
        # Fetch the original email from Outlook
        outlook = OutlookClient()
        analyzer = BidEmailAnalyzer(api_key=ANTHROPIC_API_KEY, model=CLAUDE_MODEL)
        
        # Try to get the first source email
        message_id = source_ids[0]
        email = outlook.get_email_by_id(message_id)
        
        if not email:
            return jsonify({"success": False, "error": "Could not retrieve original email from Outlook"}), 404
        
        # Re-analyze the email
        body = email.get("body", {}).get("content", "")
        email_data = {
            "subject": email.get("subject", ""),
            "body": body,
            "body_preview": email.get("bodyPreview", ""),
            "from_address": email.get("from", {}).get("emailAddress", {}).get("address", ""),
            "from_name": email.get("from", {}).get("emailAddress", {}).get("name", ""),
            "received_datetime": email.get("receivedDateTime", ""),
            "cc_addresses": [r.get("emailAddress", {}).get("address", "") for r in email.get("ccRecipients", [])]
        }
        
        analysis = analyzer.analyze_email(email_data, [])
        
        if not analysis.get("valid"):
            return jsonify({
                "success": False, 
                "error": f"Email analysis returned invalid: {analysis.get('reason', 'unknown')}"
            }), 400
        
        # Update the bid with new extracted info
        extracted = analysis.get("extracted_info", {})
        update_bid_from_rescan(bid_id, extracted)
        
        return jsonify({
            "success": True,
            "message": "Bid updated with re-scanned information",
            "updated_fields": extracted
        })
        
    except Exception as e:
        logger.error(f"Error rescanning bid {bid_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Preview what emails would be processed (keyword scan only, no Claude API)"""
    try:
        data = request.get_json() or {}
        days_back = data.get('days_back', 7)
        
        outlook = OutlookClient()
        analyzer = BidEmailAnalyzer(api_key=ANTHROPIC_API_KEY)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        emails = outlook.get_emails_in_range(start_date, end_date, max_emails=500)
        
        # Just do keyword scan (free, no API cost)
        preview = []
        for email in emails:
            subject = email.get("subject", "")
            body_preview = email.get("bodyPreview", "")
            text_to_scan = f"{subject} {body_preview}"
            keywords = analyzer.keyword_scan(text_to_scan)
            
            if keywords:
                preview.append({
                    "subject": subject,
                    "from": email.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "received": email.get("receivedDateTime", ""),
                    "matched_keywords": keywords[:5]
                })
        
        return jsonify({
            "success": True,
            "total_emails": len(emails),
            "keyword_matches": len(preview),
            "preview": preview[:50]  # Limit preview to 50 items
        })
        
    except Exception as e:
        logger.error(f"Preview error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/bids')
def api_get_bids():
    """Get all bids"""
    bids = get_all_bids()
    return jsonify({
        "success": True,
        "bids": bids,
        "count": len(bids)
    })


@app.route('/api/bids/<int:bid_id>')
def api_get_bid(bid_id):
    """Get a specific bid"""
    bid = get_bid_by_id(bid_id)
    if bid:
        return jsonify({"success": True, "bid": bid})
    else:
        return jsonify({"success": False, "error": "Bid not found"}), 404


@app.route('/api/bids/<int:bid_id>', methods=['DELETE'])
def api_delete_bid(bid_id):
    """Delete a bid"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bid_tracker WHERE id = ?', (bid_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    if deleted:
        return jsonify({"success": True, "message": f"Deleted bid {bid_id}"})
    else:
        return jsonify({"success": False, "error": "Bid not found"}), 404


@app.route('/api/bids/due-today')
def api_bids_due_today():
    """Get bids due today"""
    bids = get_bids_due_today()
    return jsonify({"success": True, "bids": bids, "count": len(bids)})


@app.route('/api/bids/due-tomorrow')
def api_bids_due_tomorrow():
    """Get bids due tomorrow"""
    bids = get_bids_due_tomorrow()
    return jsonify({"success": True, "bids": bids, "count": len(bids)})


@app.route('/api/bids/due-range')
def api_bids_due_range():
    """Get bids due in a date range"""
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    
    if not start_date or not end_date:
        return jsonify({"success": False, "error": "start and end dates required"}), 400
    
    bids = get_bids_due_in_range(start_date, end_date)
    return jsonify({"success": True, "bids": bids, "count": len(bids)})


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update settings"""
    if request.method == 'GET':
        return jsonify({
            "auto_scan_enabled": get_setting('auto_scan_enabled', 'false') == 'true',
            "scan_interval_minutes": int(get_setting('scan_interval_minutes', '15')),
            "days_to_scan": int(get_setting('days_to_scan', '7')),
            "scanner_running": _scanner_running,
            "last_scan_time": _last_scan_time.isoformat() if _last_scan_time else None,
            "last_scan_result": _last_scan_result
        })
    else:
        data = request.get_json() or {}
        
        if 'auto_scan_enabled' in data:
            enabled = data['auto_scan_enabled']
            set_setting('auto_scan_enabled', 'true' if enabled else 'false')
            # Start or stop scanner based on setting
            if enabled:
                start_scanner()
            else:
                stop_scanner()
        
        if 'scan_interval_minutes' in data:
            set_setting('scan_interval_minutes', str(data['scan_interval_minutes']))
        
        if 'days_to_scan' in data:
            set_setting('days_to_scan', str(data['days_to_scan']))
        
        return jsonify({
            "success": True, 
            "message": "Settings updated",
            "auto_scan_enabled": get_setting('auto_scan_enabled', 'false') == 'true',
            "scanner_running": _scanner_running
        })


@app.route('/api/scanner/start', methods=['POST'])
def api_start_scanner():
    """Start the background scanner"""
    set_setting('auto_scan_enabled', 'true')
    start_scanner()
    return jsonify({"success": True, "message": "Scanner started"})


@app.route('/api/scanner/stop', methods=['POST'])
def api_stop_scanner():
    """Stop the background scanner"""
    set_setting('auto_scan_enabled', 'false')
    stop_scanner()
    return jsonify({"success": True, "message": "Scanner stopped"})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    # Initialize database
    init_database()
    
    # Start background scanner if enabled
    if get_setting('auto_scan_enabled', 'false') == 'true':
        start_scanner()
    
    logger.info(f"Starting {APP_NAME} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
