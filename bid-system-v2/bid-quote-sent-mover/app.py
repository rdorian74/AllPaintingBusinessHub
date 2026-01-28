"""
Bid Quote Sent Mover - All Painting Ltd.
Port: 3035

PURPOSE: Scans the SENT folder in Outlook for estimate emails, matches them with
Pipedrive deals in "Quote Requested" and "In Estimation" stages, and moves
matched deals to "Quote Sent & Decision Pending" stage.

Email subject pattern: "Estimate - 26C011 -PlanIt Const -Painting of Dollarama Central City 2- -1109-10153 King George Blvd surrey"
Format: Estimate - {estimate_id} -{gc_name} -{project_name}- -{project_address}

Handles revised estimates (subject contains "revised")
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
from difflib import SequenceMatcher

# =============================================================================
# CONFIGURATION
# =============================================================================

PORT = 3035
APP_NAME = "Bid Quote Sent Mover"
APP_VERSION = "1.0.0"

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "quote_sent_mover.db")

# Azure / Microsoft Graph API credentials
AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
MONITORED_EMAIL = "info@allpaintingltd.com"

# Pipedrive
PIPEDRIVE_API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
PIPEDRIVE_DOMAIN = os.environ.get("PIPEDRIVE_DOMAIN", "allpainting")
PIPEDRIVE_PIPELINE_NAME = "Pipeline"
PIPEDRIVE_BASE_URL = f"https://{PIPEDRIVE_DOMAIN}.pipedrive.com/api/v1"

# Source stages to check
SOURCE_STAGES = ["Quote Requested", "In Estimation"]
# Target stage to move to
TARGET_STAGE = "Quote Sent & Decision Pending"

# Claude API
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Matching threshold
MATCH_THRESHOLD = 85  # 85% confidence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Background scanner state
_scanner_running = False
_scanner_thread = None
_last_scan_time = None
_last_scan_result = None


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    ''')
    
    # Processed emails table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id TEXT PRIMARY KEY,
            subject TEXT,
            estimate_id TEXT,
            processed_at TEXT,
            result TEXT,
            matched_deal_id INTEGER,
            action_taken TEXT
        )
    ''')
    
    # Activity log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action TEXT,
            email_subject TEXT,
            estimate_id TEXT,
            deal_id INTEGER,
            deal_title TEXT,
            status TEXT,
            message TEXT,
            is_revised INTEGER DEFAULT 0,
            duplicate_deal_id INTEGER
        )
    ''')
    
    # Default settings
    defaults = {
        'auto_scan_enabled': 'false',
        'scan_interval_minutes': '30',
        'days_to_scan': '7'
    }
    
    for key, value in defaults.items():
        cursor.execute('''
            INSERT OR IGNORE INTO settings (key, value, updated_at) 
            VALUES (?, ?, ?)
        ''', (key, value, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


def get_setting(key: str, default: str = None) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def is_email_processed(message_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM processed_emails WHERE message_id = ?', (message_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def mark_email_processed(message_id: str, subject: str, estimate_id: str, 
                         result: str, matched_deal_id: int = None, action_taken: str = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO processed_emails 
        (message_id, subject, estimate_id, processed_at, result, matched_deal_id, action_taken)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (message_id, subject, estimate_id, datetime.now().isoformat(), 
          result, matched_deal_id, action_taken))
    conn.commit()
    conn.close()


def log_activity(action: str, email_subject: str = None, estimate_id: str = None,
                 deal_id: int = None, deal_title: str = None, status: str = 'success',
                 message: str = None, is_revised: bool = False, duplicate_deal_id: int = None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO activity_log 
        (timestamp, action, email_subject, estimate_id, deal_id, deal_title, 
         status, message, is_revised, duplicate_deal_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), action, email_subject, estimate_id,
          deal_id, deal_title, status, message, 1 if is_revised else 0, duplicate_deal_id))
    conn.commit()
    conn.close()


def get_activity_log(limit: int = 100) -> List[Dict]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_processed_count() -> Dict:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM processed_emails')
    total = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as moved FROM processed_emails WHERE action_taken = 'moved'")
    moved = cursor.fetchone()['moved']
    cursor.execute("SELECT COUNT(*) as duplicates FROM processed_emails WHERE action_taken = 'duplicate_found'")
    duplicates = cursor.fetchone()['duplicates']
    cursor.execute("SELECT COUNT(*) as no_match FROM processed_emails WHERE action_taken = 'no_match'")
    no_match = cursor.fetchone()['no_match']
    conn.close()
    return {'total': total, 'moved': moved, 'duplicates': duplicates, 'no_match': no_match}


def clear_processed_emails() -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM processed_emails')
    count = cursor.fetchone()[0]
    cursor.execute('DELETE FROM processed_emails')
    conn.commit()
    conn.close()
    return count


# =============================================================================
# OUTLOOK CLIENT - For SENT folder only
# =============================================================================

class OutlookSentFolderClient:
    """Microsoft Graph API client for accessing SENT emails from info@allpaintingltd.com"""
    
    def __init__(self):
        self.client_id = AZURE_CLIENT_ID
        self.tenant_id = AZURE_TENANT_ID
        self.client_secret = AZURE_CLIENT_SECRET
        self.monitored_email = MONITORED_EMAIL
        self.access_token = None
        self.token_expires = None
    
    def _get_access_token(self):
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
        try:
            self._get_access_token()
            endpoint = f"/users/{self.monitored_email}/mailFolders/SentItems"
            response = self._make_request("GET", endpoint)
            
            if response.status_code == 200:
                return {"success": True, "message": "Connection to Sent folder successful"}
            else:
                return {"success": False, "message": f"Error: {response.text}"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_sent_folder_id(self) -> Optional[str]:
        """Get the Sent Items folder ID"""
        try:
            endpoint = f"/users/{self.monitored_email}/mailFolders/SentItems"
            response = self._make_request("GET", endpoint)
            if response.status_code == 200:
                return response.json().get("id")
            return None
        except Exception as e:
            logger.error(f"Error getting Sent folder: {e}")
            return None
    
    def get_sent_estimate_emails(self, days_back: int = 7, max_emails: int = 500) -> List[Dict]:
        """
        Get emails from Sent folder that start with 'Estimate' in subject
        """
        from datetime import timezone
        
        # Use UTC timezone explicitly
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        logger.info(f"Searching emails from {start_str} to {end_str}")
        
        sent_folder_id = self.get_sent_folder_id()
        if not sent_folder_id:
            logger.error("Could not get Sent folder ID")
            return []
        
        endpoint = f"/users/{self.monitored_email}/mailFolders/{sent_folder_id}/messages"
        
        # First, let's get ALL recent emails to debug (without subject filter)
        debug_params = {
            "$filter": f"sentDateTime ge {start_str}",
            "$orderby": "sentDateTime desc",
            "$top": 20,
            "$select": "id,subject,sentDateTime"
        }
        
        logger.info("DEBUG: Fetching recent emails without subject filter...")
        debug_response = self._make_request("GET", endpoint, params=debug_params)
        if debug_response.status_code == 200:
            debug_data = debug_response.json()
            debug_emails = debug_data.get("value", [])
            logger.info(f"DEBUG: Found {len(debug_emails)} total recent emails")
            for email in debug_emails[:10]:
                subj = email.get('subject', '')[:80]
                sent = email.get('sentDateTime', '')
                logger.info(f"DEBUG EMAIL: [{sent}] {subj}")
        else:
            logger.error(f"DEBUG query failed: {debug_response.text}")
        
        # Now filter for Estimate emails - try without startswith first
        # Some Graph API versions have issues with startswith
        filter_query = f"sentDateTime ge {start_str} and sentDateTime le {end_str}"
        
        params = {
            "$filter": filter_query,
            "$orderby": "sentDateTime desc",
            "$top": min(max_emails, 100),
            "$select": "id,subject,sentDateTime,toRecipients",
            "$count": "true"
        }
        
        all_emails = []
        estimate_emails = []
        
        while len(all_emails) < max_emails:
            response = self._make_request("GET", endpoint, params=params)
            
            if response.status_code != 200:
                logger.error(f"Failed to get sent emails: {response.text}")
                break
            
            data = response.json()
            emails = data.get("value", [])
            all_emails.extend(emails)
            
            # Filter for Estimate emails in Python (more reliable than API filter)
            for email in emails:
                subject = email.get('subject', '')
                if subject.lower().startswith('estimate'):
                    logger.info(f"Found estimate email: {subject[:100]}...")
                    estimate_emails.append(email)
            
            next_link = data.get("@odata.nextLink")
            if not next_link or len(emails) == 0:
                break
            
            endpoint = next_link.replace("https://graph.microsoft.com/v1.0", "")
            params = None
        
        logger.info(f"Found {len(estimate_emails)} estimate emails out of {len(all_emails)} total (last {days_back} days)")
        return estimate_emails[:max_emails]
        
        logger.info(f"Found {len(all_emails)} estimate emails in Sent folder (last {days_back} days)")
        return all_emails[:max_emails]


# =============================================================================
# PIPEDRIVE CLIENT
# =============================================================================

class PipedriveClient:
    def __init__(self, api_token: str = None, domain: str = None):
        self.api_token = api_token or PIPEDRIVE_API_TOKEN
        self.domain = domain or PIPEDRIVE_DOMAIN
        self.base_url = f"https://{self.domain}.pipedrive.com/api/v1"
        self._pipelines_cache = None
        self._stages_cache = {}
    
    def _request(self, endpoint: str, method: str = 'GET', data: dict = None, params: dict = None) -> Optional[Dict]:
        url = f"{self.base_url}/{endpoint}"
        if params is None:
            params = {}
        params['api_token'] = self.api_token
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, params=params, json=data, 
                                        headers={'Content-Type': 'application/json'}, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, params=params, json=data,
                                       headers={'Content-Type': 'application/json'}, timeout=30)
            else:
                return None
            
            if response.status_code == 429:
                time.sleep(int(response.headers.get('Retry-After', 60)))
                return self._request(endpoint, method, data, params)
            
            response.raise_for_status()
            result = response.json()
            return result.get('data') if result.get('success') else None
        except Exception as e:
            logger.error(f"Pipedrive request failed: {e}")
            return None
    
    def test_connection(self) -> Dict:
        result = self._request('users/me')
        if result:
            return {'success': True, 'user': result.get('name'), 'company': result.get('company_name')}
        return {'success': False, 'error': 'Failed to connect'}
    
    def get_pipelines(self, force_refresh: bool = False) -> List[Dict]:
        if self._pipelines_cache is None or force_refresh:
            self._pipelines_cache = self._request('pipelines') or []
        return self._pipelines_cache
    
    def get_pipeline_by_name(self, name: str) -> Optional[Dict]:
        for p in self.get_pipelines():
            if p.get('name', '').lower() == name.lower():
                return p
        return None
    
    def get_stages(self, pipeline_id: int, force_refresh: bool = False) -> List[Dict]:
        key = str(pipeline_id)
        if key not in self._stages_cache or force_refresh:
            self._stages_cache[key] = self._request('stages', params={'pipeline_id': pipeline_id}) or []
        return self._stages_cache.get(key, [])
    
    def get_stage_by_name(self, pipeline_id: int, stage_name: str) -> Optional[Dict]:
        for s in self.get_stages(pipeline_id):
            if s.get('name', '').lower() == stage_name.lower():
                return s
        return None
    
    def get_deals_in_stages(self, pipeline_id: int, stage_ids: List[int], limit: int = 500) -> List[Dict]:
        """Get all deals in specific stages"""
        all_deals = []
        for stage_id in stage_ids:
            params = {'stage_id': stage_id, 'status': 'open', 'limit': limit}
            start = 0
            while True:
                params['start'] = start
                result = self._request('deals', params=params)
                if not result:
                    break
                all_deals.extend(result)
                if len(result) < limit:
                    break
                start += limit
        return all_deals
    
    def get_deals_in_stage(self, pipeline_id: int, stage_id: int, limit: int = 500) -> List[Dict]:
        """Get all deals in a specific stage"""
        params = {'stage_id': stage_id, 'status': 'open', 'limit': limit}
        all_deals = []
        start = 0
        while True:
            params['start'] = start
            result = self._request('deals', params=params)
            if not result:
                break
            all_deals.extend(result)
            if len(result) < limit:
                break
            start += limit
        return all_deals
    
    def update_deal(self, deal_id: int, data: Dict) -> Optional[Dict]:
        """Update a deal"""
        return self._request(f'deals/{deal_id}', method='PUT', data=data)
    
    def move_deal_to_stage(self, deal_id: int, stage_id: int) -> Optional[Dict]:
        """Move a deal to a different stage"""
        return self.update_deal(deal_id, {'stage_id': stage_id})
    
    def rename_deal(self, deal_id: int, new_title: str) -> Optional[Dict]:
        """Rename a deal"""
        return self.update_deal(deal_id, {'title': new_title})
    
    def add_note_to_deal(self, deal_id: int, content: str) -> Optional[Dict]:
        """Add a note to a deal"""
        return self._request('notes', method='POST', data={'deal_id': deal_id, 'content': content})


# =============================================================================
# ESTIMATE EMAIL PARSER - AI-POWERED
# =============================================================================

def parse_estimate_subject_basic(subject: str) -> Optional[Dict]:
    """
    Basic regex parsing as fallback.
    Format examples:
    - "Estimate - 26C011 -PlanIt Const -Painting of Dollarama- -1109 King George Blvd"
    - "Estimate - 26C-010 - Company Name - Project Name - Address"
    - "Estimate - 26R-001 - GC - Project - Location"
    """
    if not subject:
        return None
    
    # Check if this is a revised estimate
    is_revised = 'revised' in subject.lower()
    
    # Clean up subject - remove "RE:", "FW:", etc.
    cleaned = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE).strip()
    
    # Must start with "Estimate"
    if not cleaned.lower().startswith('estimate'):
        return None
    
    return {
        'estimate_id': None,
        'gc_name': None,
        'project_name': None,
        'project_address': None,
        'is_revised': is_revised,
        'original_subject': subject,
        'parse_method': 'basic_fallback'
    }


def parse_estimate_subject_with_ai(subject: str, api_key: str = None) -> Optional[Dict]:
    """
    Use AI to extract estimate info from subject line.
    Handles all variations of estimate ID format and messy subject lines.
    """
    if not subject:
        return None
    
    api_key = api_key or ANTHROPIC_API_KEY
    if not api_key:
        return parse_estimate_subject_basic(subject)
    
    # Check if this is a revised estimate
    is_revised = 'revised' in subject.lower()
    
    # Clean up subject
    cleaned = re.sub(r'^(RE:|FW:|Fwd:)\s*', '', subject, flags=re.IGNORECASE).strip()
    
    # Must start with "Estimate"
    if not cleaned.lower().startswith('estimate'):
        return None
    
    prompt = f"""Extract information from this estimate email subject line for a commercial painting company.

SUBJECT LINE:
"{subject}"

RULES FOR EXTRACTION:
1. Estimate ID: Usually after "Estimate -" or "Estimate-". Can be formats like:
   - 26C011, 26C-011, 26R-001, 25C-299-A, 29C317, #25C-324
   - May include revision markers like "Revision 2" or "Rev #2" (note this separately)
   - Extract the FULL ID including any dashes, letters, numbers

2. GC Name (General Contractor): The company name, usually after the estimate ID
   - Extract the COMPLETE company name, don't truncate
   - Examples: "Keller Const", "PlanIt Const", "Centra Const", "DMC projects", "BriteStar"

3. Project Name: The project/building name
   - Extract the COMPLETE project name
   - Examples: "Int ptg", "27 Light poles", "Painting of Dollarama Central City 2"

4. Project Address: The location/address
   - Extract the COMPLETE address if present
   - May include unit numbers, street names, city names

Respond ONLY with this exact JSON format, no other text:
{{
    "estimate_id": "<full estimate ID or null>",
    "gc_name": "<full GC company name or null>",
    "project_name": "<full project name or null>",
    "project_address": "<full address or null>",
    "has_revision": <true if this mentions revision/revised, false otherwise>
}}"""

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=15
        )
        
        if response.status_code != 200:
            logger.error(f"AI parsing error: {response.text}")
            return parse_estimate_subject_basic(subject)
        
        result = response.json()
        content = result.get('content', [{}])[0].get('text', '{}')
        
        # Parse JSON response
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            ai_result = json.loads(json_match.group())
            
            return {
                'estimate_id': ai_result.get('estimate_id'),
                'gc_name': ai_result.get('gc_name'),
                'project_name': ai_result.get('project_name'),
                'project_address': ai_result.get('project_address'),
                'is_revised': is_revised or ai_result.get('has_revision', False),
                'original_subject': subject,
                'parse_method': 'ai'
            }
    
    except Exception as e:
        logger.error(f"AI parsing exception: {e}")
    
    return parse_estimate_subject_basic(subject)


def parse_estimate_subject(subject: str) -> Optional[Dict]:
    """
    Parse estimate email subject line using AI.
    Falls back to basic parsing if AI fails.
    """
    return parse_estimate_subject_with_ai(subject, ANTHROPIC_API_KEY)


# =============================================================================
# AI MATCHER
# =============================================================================

class AIEstimateMatcher:
    """Uses Claude to match estimate emails with Pipedrive deals"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
    
    def match_estimate_to_deal(self, estimate_info: Dict, deals: List[Dict]) -> Tuple[bool, Optional[Dict], int]:
        """
        Use AI to find the best matching deal for an estimate
        Returns: (found_match, matching_deal, confidence_percentage)
        """
        if not self.api_key:
            logger.warning("No API key, falling back to fuzzy matching")
            return self._fuzzy_match(estimate_info, deals)
        
        if not deals:
            return False, None, 0
        
        # Build deals list for prompt
        deals_text = ""
        for i, deal in enumerate(deals[:50]):  # Limit to 50 deals
            org_name = ""
            if isinstance(deal.get('organization'), dict):
                org_name = deal['organization'].get('name', '')
            elif deal.get('org_name'):
                org_name = deal['org_name']
            
            deals_text += f"{i+1}. ID:{deal['id']} | Title: {deal.get('title', 'N/A')} | Org: {org_name}\n"
        
        prompt = f"""You are matching sent estimates to Pipedrive deals for a commercial painting company.

ESTIMATE EMAIL INFO:
- Estimate ID: {estimate_info.get('estimate_id', 'N/A')}
- GC (General Contractor): {estimate_info.get('gc_name', 'N/A')}
- Project Name: {estimate_info.get('project_name', 'N/A')}
- Project Address: {estimate_info.get('project_address', 'N/A')}
- Original Subject: {estimate_info.get('original_subject', 'N/A')}

PIPEDRIVE DEALS TO CHECK:
{deals_text}

TASK: Find the deal that BEST matches this estimate. Consider:
1. Project name similarity (most important)
2. GC/Organization name match
3. Address similarity
4. Any partial matches in the deal title

Respond in this exact JSON format:
{{
    "match_found": true/false,
    "deal_index": <1-based index from list above, or null>,
    "deal_id": <deal ID number, or null>,
    "confidence": <0-100>,
    "reason": "<brief explanation>"
}}

Be strict - only match if you're at least 85% confident. Construction projects often have similar names, so verify multiple factors match."""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"AI API error: {response.text}")
                return self._fuzzy_match(estimate_info, deals)
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            # Parse JSON response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                ai_result = json.loads(json_match.group())
                
                if ai_result.get('match_found') and ai_result.get('confidence', 0) >= MATCH_THRESHOLD:
                    deal_id = ai_result.get('deal_id')
                    # Find the deal by ID
                    for deal in deals:
                        if deal['id'] == deal_id:
                            return True, deal, ai_result.get('confidence', 85)
                    
                    # Try by index if ID didn't work
                    deal_idx = ai_result.get('deal_index')
                    if deal_idx and 1 <= deal_idx <= len(deals):
                        return True, deals[deal_idx - 1], ai_result.get('confidence', 85)
                
                return False, None, ai_result.get('confidence', 0)
            
        except Exception as e:
            logger.error(f"AI matching error: {e}")
        
        return self._fuzzy_match(estimate_info, deals)
    
    def _fuzzy_match(self, estimate_info: Dict, deals: List[Dict]) -> Tuple[bool, Optional[Dict], int]:
        """Fallback fuzzy matching"""
        project_name = (estimate_info.get('project_name') or '').lower()
        gc_name = (estimate_info.get('gc_name') or '').lower()
        address = (estimate_info.get('project_address') or '').lower()
        
        best_match = None
        best_score = 0
        
        for deal in deals:
            title = (deal.get('title') or '').lower()
            org_name = ''
            if isinstance(deal.get('organization'), dict):
                org_name = (deal['organization'].get('name') or '').lower()
            
            score = 0
            
            # Project name in title
            if project_name and project_name in title:
                score += 50
            elif project_name:
                ratio = SequenceMatcher(None, project_name, title).ratio()
                score += int(ratio * 40)
            
            # GC name match
            if gc_name and gc_name in org_name:
                score += 30
            elif gc_name and org_name:
                ratio = SequenceMatcher(None, gc_name, org_name).ratio()
                score += int(ratio * 20)
            
            # Address in title
            if address and len(address) > 10:
                if address in title:
                    score += 20
                else:
                    # Check for street number
                    addr_parts = address.split()
                    if addr_parts and addr_parts[0].isdigit():
                        if addr_parts[0] in title:
                            score += 10
            
            if score > best_score:
                best_score = score
                best_match = deal
        
        if best_score >= MATCH_THRESHOLD:
            return True, best_match, best_score
        
        return False, None, best_score
    
    def match_estimate_to_deal_with_candidates(self, estimate_info: Dict, deals: List[Dict]) -> Tuple[bool, Optional[Dict], int, List[Dict]]:
        """
        Use AI to find the best matching deal for an estimate.
        Also returns a list of candidate deals that were considered with their scores.
        Returns: (found_match, matching_deal, confidence_percentage, candidates_considered)
        """
        candidates_considered = []
        
        if not deals:
            return False, None, 0, []
        
        # First, calculate fuzzy scores for all deals to show candidates
        estimate_id = (estimate_info.get('estimate_id') or '').lower()
        project_name = (estimate_info.get('project_name') or '').lower()
        gc_name = (estimate_info.get('gc_name') or '').lower()
        address = (estimate_info.get('project_address') or '').lower()
        
        deal_scores = []
        for deal in deals:
            title = (deal.get('title') or '').lower()
            org_name = ''
            if isinstance(deal.get('organization'), dict):
                org_name = (deal['organization'].get('name') or '').lower()
            elif deal.get('org_name'):
                org_name = (deal.get('org_name') or '').lower()
            
            score = 0
            match_reasons = []
            
            # Check if estimate ID is in title (strong match)
            if estimate_id and estimate_id in title:
                score += 60
                match_reasons.append(f"Estimate ID '{estimate_id}' in title")
            
            # Project name in title
            if project_name and len(project_name) > 3:
                if project_name in title:
                    score += 40
                    match_reasons.append(f"Project name exact match")
                else:
                    ratio = SequenceMatcher(None, project_name, title).ratio()
                    if ratio > 0.5:
                        score += int(ratio * 30)
                        match_reasons.append(f"Project name {int(ratio*100)}% similar")
            
            # GC name match
            if gc_name and len(gc_name) > 2:
                if gc_name in org_name or gc_name in title:
                    score += 30
                    match_reasons.append(f"GC name match")
                elif org_name:
                    ratio = SequenceMatcher(None, gc_name, org_name).ratio()
                    if ratio > 0.6:
                        score += int(ratio * 20)
                        match_reasons.append(f"GC name {int(ratio*100)}% similar")
            
            # Address in title
            if address and len(address) > 10:
                if address in title:
                    score += 20
                    match_reasons.append(f"Address in title")
                else:
                    # Check for street number
                    addr_parts = address.split()
                    if addr_parts and addr_parts[0].isdigit():
                        if addr_parts[0] in title:
                            score += 10
                            match_reasons.append(f"Street number match")
            
            deal_scores.append({
                'deal': deal,
                'score': score,
                'reasons': match_reasons
            })
        
        # Sort by score descending
        deal_scores.sort(key=lambda x: x['score'], reverse=True)
        
        # Build candidates list (top 10 with score > 0)
        for ds in deal_scores[:10]:
            if ds['score'] > 0:
                deal = ds['deal']
                org_name = ''
                if isinstance(deal.get('organization'), dict):
                    org_name = deal['organization'].get('name', '')
                elif deal.get('org_name'):
                    org_name = deal.get('org_name', '')
                
                candidates_considered.append({
                    'id': deal['id'],
                    'title': deal.get('title', ''),
                    'org_name': org_name,
                    'score': ds['score'],
                    'reasons': ds['reasons']
                })
        
        # Now use AI for final matching decision
        if not self.api_key:
            logger.warning("No API key, using fuzzy matching only")
            if deal_scores and deal_scores[0]['score'] >= MATCH_THRESHOLD:
                return True, deal_scores[0]['deal'], deal_scores[0]['score'], candidates_considered
            return False, None, deal_scores[0]['score'] if deal_scores else 0, candidates_considered
        
        # Build deals list for AI prompt (top 20 by score)
        top_deals = [ds['deal'] for ds in deal_scores[:20]]
        deals_text = ""
        for i, deal in enumerate(top_deals):
            org_name = ""
            if isinstance(deal.get('organization'), dict):
                org_name = deal['organization'].get('name', '')
            elif deal.get('org_name'):
                org_name = deal['org_name']
            
            deals_text += f"{i+1}. ID:{deal['id']} | Title: {deal.get('title', 'N/A')} | Org: {org_name}\n"
        
        prompt = f"""You are matching a sent estimate email to Pipedrive deals for a commercial painting company.

ESTIMATE EMAIL INFO:
- Estimate ID: {estimate_info.get('estimate_id', 'N/A')}
- GC (General Contractor): {estimate_info.get('gc_name', 'N/A')}
- Project Name: {estimate_info.get('project_name', 'N/A')}
- Project Address: {estimate_info.get('project_address', 'N/A')}
- Original Subject: {estimate_info.get('original_subject', 'N/A')}

PIPEDRIVE DEALS TO CHECK (from "Quote Requested" and "In Estimation" stages):
{deals_text}

MATCHING RULES:
1. The estimate ID (like 26C-010, 25C-321, etc.) should ideally appear in or relate to the deal title
2. The GC/Organization name should match
3. Project name and address similarity helps confirm
4. These are painting projects - look for painting-related terms
5. Be careful: different estimate IDs mean different projects even if GC is the same

IMPORTANT: Only match if you are confident this estimate corresponds to THIS SPECIFIC deal.
Different estimate numbers (e.g., 25C-319 vs 25C-320) are DIFFERENT projects even for the same GC.

Respond in this exact JSON format:
{{
    "match_found": true/false,
    "deal_index": <1-based index from list above, or null>,
    "deal_id": <deal ID number, or null>,
    "confidence": <0-100>,
    "reason": "<brief explanation>"
}}"""

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"AI API error: {response.text}")
                # Fallback to fuzzy
                if deal_scores and deal_scores[0]['score'] >= MATCH_THRESHOLD:
                    return True, deal_scores[0]['deal'], deal_scores[0]['score'], candidates_considered
                return False, None, deal_scores[0]['score'] if deal_scores else 0, candidates_considered
            
            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')
            
            # Parse JSON response
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                ai_result = json.loads(json_match.group())
                
                if ai_result.get('match_found') and ai_result.get('confidence', 0) >= MATCH_THRESHOLD:
                    deal_id = ai_result.get('deal_id')
                    # Find the deal by ID
                    for deal in deals:
                        if deal['id'] == deal_id:
                            return True, deal, ai_result.get('confidence', 85), candidates_considered
                    
                    # Try by index if ID didn't work
                    deal_idx = ai_result.get('deal_index')
                    if deal_idx and 1 <= deal_idx <= len(top_deals):
                        return True, top_deals[deal_idx - 1], ai_result.get('confidence', 85), candidates_considered
                
                return False, None, ai_result.get('confidence', 0), candidates_considered
            
        except Exception as e:
            logger.error(f"AI matching error: {e}")
        
        # Fallback
        if deal_scores and deal_scores[0]['score'] >= MATCH_THRESHOLD:
            return True, deal_scores[0]['deal'], deal_scores[0]['score'], candidates_considered
        return False, None, deal_scores[0]['score'] if deal_scores else 0, candidates_considered


# =============================================================================
# QUOTE SENT MOVER SERVICE
# =============================================================================

class QuoteSentMoverService:
    """Main service that orchestrates the entire process"""
    
    def __init__(self):
        self.outlook = OutlookSentFolderClient()
        self.pipedrive = PipedriveClient()
        self.matcher = AIEstimateMatcher()
        
        self._pipeline_id = None
        self._source_stage_ids = []
        self._target_stage_id = None
    
    def initialize(self) -> bool:
        """Initialize Pipedrive stage IDs"""
        try:
            # Get pipeline
            pipeline = self.pipedrive.get_pipeline_by_name(PIPEDRIVE_PIPELINE_NAME)
            if not pipeline:
                logger.error(f"Pipeline '{PIPEDRIVE_PIPELINE_NAME}' not found")
                return False
            
            self._pipeline_id = pipeline['id']
            
            # Get source stage IDs
            for stage_name in SOURCE_STAGES:
                stage = self.pipedrive.get_stage_by_name(self._pipeline_id, stage_name)
                if stage:
                    self._source_stage_ids.append(stage['id'])
                    logger.info(f"Found source stage: {stage_name} (ID: {stage['id']})")
            
            if not self._source_stage_ids:
                logger.error("No source stages found")
                return False
            
            # Get target stage ID
            target_stage = self.pipedrive.get_stage_by_name(self._pipeline_id, TARGET_STAGE)
            if not target_stage:
                logger.error(f"Target stage '{TARGET_STAGE}' not found")
                return False
            
            self._target_stage_id = target_stage['id']
            logger.info(f"Found target stage: {TARGET_STAGE} (ID: {self._target_stage_id})")
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False
    
    def get_source_deals(self, force_refresh: bool = False) -> List[Dict]:
        """Get all deals in source stages (Quote Requested, In Estimation)"""
        return self.pipedrive.get_deals_in_stages(self._pipeline_id, self._source_stage_ids)
    
    def get_target_stage_deals(self) -> List[Dict]:
        """Get deals in target stage for duplicate checking"""
        return self.pipedrive.get_deals_in_stage(self._pipeline_id, self._target_stage_id)
    
    def _normalize_for_comparison(self, text: str) -> str:
        """
        Normalize text for comparison by removing all dash types and extra spaces.
        Handles: em-dash (—), en-dash (–), regular hyphen (-), and extra spaces.
        """
        if not text:
            return ''
        
        # Convert to lowercase
        text = text.lower()
        
        # Use regex to replace ALL unicode dash-like characters
        # This covers: hyphen, en-dash, em-dash, figure dash, minus sign, etc.
        import re
        text = re.sub(r'[\u002D\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]', '', text)
        
        # Remove all whitespace (spaces, tabs, etc.)
        text = re.sub(r'\s+', '', text)
        
        # Remove colons and other punctuation that might vary
        text = text.replace(':', '')
        text = text.replace('.', '')
        text = text.replace(',', '')
        
        return text
    
    def check_for_duplicate(self, estimate_info: Dict, target_deals: List[Dict]) -> Tuple[bool, Optional[Dict]]:
        """Check if a deal already exists in Quote Sent & Decision Pending"""
        estimate_id = estimate_info.get('estimate_id', '')
        project_name = (estimate_info.get('project_name') or '')
        gc_name = (estimate_info.get('gc_name') or '')
        
        # Normalize estimate ID for comparison
        estimate_id_normalized = self._normalize_for_comparison(estimate_id)
        
        logger.info(f"=== DUPLICATE CHECK ===")
        logger.info(f"Estimate ID: '{estimate_id}' -> normalized: '{estimate_id_normalized}'")
        logger.info(f"Checking against {len(target_deals)} deals in target stage")
        
        for deal in target_deals:
            title = deal.get('title') or ''
            title_normalized = self._normalize_for_comparison(title)
            
            # Log first few deals for debugging
            if target_deals.index(deal) < 5:
                logger.info(f"  Deal {deal.get('id')}: '{title[:60]}...' -> normalized contains '{estimate_id_normalized}': {estimate_id_normalized in title_normalized if estimate_id_normalized else 'N/A'}")
            
            # Check if estimate ID is in the title (normalized comparison)
            if estimate_id_normalized and len(estimate_id_normalized) >= 4:
                if estimate_id_normalized in title_normalized:
                    logger.info(f"✓ DUPLICATE FOUND: '{estimate_id}' (normalized: '{estimate_id_normalized}') in deal '{title}'")
                    return True, deal
            
            # Check project name match (normalized)
            project_name_normalized = self._normalize_for_comparison(project_name)
            if project_name_normalized and len(project_name_normalized) > 10:
                if project_name_normalized in title_normalized:
                    logger.info(f"✓ DUPLICATE FOUND (project name): '{project_name}' in deal '{title}'")
                    return True, deal
                # Fuzzy match on original (lowercased) values
                ratio = SequenceMatcher(None, project_name.lower(), title.lower()).ratio()
                if ratio > 0.85:
                    logger.info(f"✓ DUPLICATE FOUND (fuzzy {ratio:.0%}): '{project_name}' ~ deal '{title}'")
                    return True, deal
            
            # Check GC name + some project indicator
            gc_name_lower = gc_name.lower()
            title_lower = title.lower()
            if gc_name_lower and len(gc_name_lower) > 3 and gc_name_lower in title_lower:
                # If GC matches and some other indicator matches
                if project_name and len(project_name) > 5:
                    project_words = project_name.lower().split()
                    matching_words = sum(1 for w in project_words if len(w) > 3 and w in title_lower)
                    if matching_words >= 2:
                        logger.info(f"✓ DUPLICATE FOUND (GC + {matching_words} project words): deal '{title}'")
                        return True, deal
        
        logger.info(f"✗ No duplicate found for estimate ID '{estimate_id}'")
        return False, None
    
    def build_new_deal_title(self, estimate_info: Dict) -> str:
        """Build a standardized deal title from estimate info"""
        parts = []
        
        if estimate_info.get('estimate_id'):
            parts.append(estimate_info['estimate_id'])
        if estimate_info.get('gc_name'):
            parts.append(estimate_info['gc_name'])
        if estimate_info.get('project_name'):
            parts.append(estimate_info['project_name'])
        if estimate_info.get('project_address'):
            parts.append(estimate_info['project_address'])
        
        if parts:
            return ' - '.join(parts)
        return None
    
    def process_estimate_email(self, email: Dict, source_deals: List[Dict], 
                                target_deals: List[Dict]) -> Dict:
        """Process a single estimate email"""
        subject = email.get('subject', '')
        message_id = email.get('id')
        
        # Skip if already processed
        if is_email_processed(message_id):
            return {
                'status': 'skipped',
                'message': 'Already processed',
                'email_subject': subject
            }
        
        # Parse the subject
        estimate_info = parse_estimate_subject(subject)
        if not estimate_info:
            mark_email_processed(message_id, subject, None, 'parse_failed', None, 'parse_failed')
            return {
                'status': 'error',
                'message': 'Could not parse estimate subject',
                'email_subject': subject
            }
        
        estimate_id = estimate_info.get('estimate_id')
        is_revised = estimate_info.get('is_revised', False)
        
        # Check for duplicates in target stage first
        is_duplicate, duplicate_deal = self.check_for_duplicate(estimate_info, target_deals)
        
        if is_duplicate and not is_revised:
            # Found duplicate, don't process (unless it's a revised estimate)
            mark_email_processed(message_id, subject, estimate_id, 'duplicate', 
                                duplicate_deal['id'], 'duplicate_found')
            log_activity(
                action='duplicate_found',
                email_subject=subject,
                estimate_id=estimate_id,
                deal_id=duplicate_deal['id'],
                deal_title=duplicate_deal.get('title'),
                status='skipped',
                message=f"Duplicate found in '{TARGET_STAGE}'",
                duplicate_deal_id=duplicate_deal['id']
            )
            return {
                'status': 'duplicate',
                'message': f"Duplicate found: {duplicate_deal.get('title')}",
                'email_subject': subject,
                'duplicate_deal_id': duplicate_deal['id'],
                'duplicate_deal_title': duplicate_deal.get('title')
            }
        
        # If it's a revised estimate and duplicate exists, update the existing deal
        if is_duplicate and is_revised:
            # Update the existing deal with revised info
            new_title = self.build_new_deal_title(estimate_info)
            if new_title and new_title != duplicate_deal.get('title'):
                self.pipedrive.rename_deal(duplicate_deal['id'], new_title)
            
            # Add note about revision
            note = f"📝 **Revised Estimate Sent**\n\nEstimate ID: {estimate_id}\nSent: {email.get('sentDateTime', 'N/A')}"
            self.pipedrive.add_note_to_deal(duplicate_deal['id'], note)
            
            mark_email_processed(message_id, subject, estimate_id, 'revised_update',
                                duplicate_deal['id'], 'revised_update')
            log_activity(
                action='revised_update',
                email_subject=subject,
                estimate_id=estimate_id,
                deal_id=duplicate_deal['id'],
                deal_title=duplicate_deal.get('title'),
                status='success',
                message='Updated existing deal with revised estimate',
                is_revised=True
            )
            return {
                'status': 'revised_update',
                'message': f"Updated existing deal with revised estimate",
                'email_subject': subject,
                'deal_id': duplicate_deal['id']
            }
        
        # Try to match with source stage deals
        found_match, matched_deal, confidence = self.matcher.match_estimate_to_deal(
            estimate_info, source_deals
        )
        
        if not found_match:
            mark_email_processed(message_id, subject, estimate_id, 'no_match', None, 'no_match')
            log_activity(
                action='no_match',
                email_subject=subject,
                estimate_id=estimate_id,
                status='warning',
                message=f'No matching deal found (confidence: {confidence}%)'
            )
            return {
                'status': 'no_match',
                'message': f'No matching deal found (confidence: {confidence}%)',
                'email_subject': subject,
                'confidence': confidence
            }
        
        # Found a match - rename and move the deal
        old_title = matched_deal.get('title')
        new_title = self.build_new_deal_title(estimate_info)
        
        # Rename the deal
        if new_title and new_title != old_title:
            self.pipedrive.rename_deal(matched_deal['id'], new_title)
            logger.info(f"Renamed deal {matched_deal['id']}: '{old_title}' -> '{new_title}'")
        
        # Move to target stage
        self.pipedrive.move_deal_to_stage(matched_deal['id'], self._target_stage_id)
        logger.info(f"Moved deal {matched_deal['id']} to '{TARGET_STAGE}'")
        
        # Add note to deal
        note = f"📧 **Quote Sent**\n\nEstimate ID: {estimate_id}\nSent: {email.get('sentDateTime', 'N/A')}\nMatch confidence: {confidence}%"
        if is_revised:
            note = f"📧 **Revised Quote Sent**\n\n{note}"
        self.pipedrive.add_note_to_deal(matched_deal['id'], note)
        
        mark_email_processed(message_id, subject, estimate_id, 'moved',
                            matched_deal['id'], 'moved')
        log_activity(
            action='moved',
            email_subject=subject,
            estimate_id=estimate_id,
            deal_id=matched_deal['id'],
            deal_title=new_title or old_title,
            status='success',
            message=f"Moved to '{TARGET_STAGE}' (confidence: {confidence}%)",
            is_revised=is_revised
        )
        
        return {
            'status': 'success',
            'message': f"Deal moved to '{TARGET_STAGE}'",
            'email_subject': subject,
            'deal_id': matched_deal['id'],
            'old_title': old_title,
            'new_title': new_title,
            'confidence': confidence,
            'is_revised': is_revised
        }
    
    def scan(self, days_back: int = 7) -> Dict:
        """Scan sent emails and process them"""
        if not self.initialize():
            return {
                'success': False,
                'error': 'Failed to initialize Pipedrive connection'
            }
        
        # Get sent estimate emails
        emails = self.outlook.get_sent_estimate_emails(days_back=days_back)
        
        if not emails:
            return {
                'success': True,
                'message': 'No estimate emails found in sent folder',
                'processed': 0,
                'results': []
            }
        
        # Get deals
        source_deals = self.get_source_deals()
        target_deals = self.get_target_stage_deals()
        
        logger.info(f"Found {len(emails)} estimate emails, {len(source_deals)} source deals, {len(target_deals)} target deals")
        
        results = []
        summary = {
            'total': len(emails),
            'moved': 0,
            'duplicates': 0,
            'no_match': 0,
            'skipped': 0,
            'revised': 0,
            'errors': 0
        }
        
        for email in emails:
            try:
                result = self.process_estimate_email(email, source_deals, target_deals)
                results.append(result)
                
                if result['status'] == 'success':
                    summary['moved'] += 1
                elif result['status'] == 'duplicate':
                    summary['duplicates'] += 1
                elif result['status'] == 'no_match':
                    summary['no_match'] += 1
                elif result['status'] == 'skipped':
                    summary['skipped'] += 1
                elif result['status'] == 'revised_update':
                    summary['revised'] += 1
                else:
                    summary['errors'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing email: {e}")
                results.append({
                    'status': 'error',
                    'message': str(e),
                    'email_subject': email.get('subject', 'Unknown')
                })
                summary['errors'] += 1
        
        return {
            'success': True,
            'summary': summary,
            'results': results
        }


# =============================================================================
# BACKGROUND SCANNER
# =============================================================================

def scanner_loop():
    global _scanner_running, _last_scan_time, _last_scan_result
    
    logger.info("Background scanner started")
    service = QuoteSentMoverService()
    
    while _scanner_running:
        try:
            if get_setting('auto_scan_enabled', 'false') != 'true':
                break
            
            days = int(get_setting('days_to_scan', '7'))
            interval = int(get_setting('scan_interval_minutes', '30')) * 60
            
            logger.info(f"Running auto scan (last {days} days)")
            result = service.scan(days_back=days)
            
            _last_scan_time = datetime.now()
            _last_scan_result = result
            
            if result.get('success'):
                summary = result.get('summary', {})
                logger.info(f"Auto scan complete: {summary.get('moved', 0)} moved, "
                           f"{summary.get('duplicates', 0)} duplicates")
            
            # Wait for next interval
            remaining = interval
            while remaining > 0 and _scanner_running:
                time.sleep(min(10, remaining))
                remaining -= 10
                
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            time.sleep(60)
    
    logger.info("Background scanner stopped")


def start_scanner():
    global _scanner_thread, _scanner_running
    if _scanner_running:
        return
    _scanner_running = True
    _scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
    _scanner_thread.start()


def stop_scanner():
    global _scanner_running
    _scanner_running = False


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    return jsonify({
        "service": APP_NAME,
        "version": APP_VERSION,
        "port": PORT,
        "description": "Scans sent Outlook emails for estimates and moves matching Pipedrive deals to 'Quote Sent & Decision Pending'"
    })


@app.route('/api/status')
def api_status():
    stats = get_processed_count()
    return jsonify({
        "service": APP_NAME,
        "version": APP_VERSION,
        "outlook_configured": bool(AZURE_CLIENT_SECRET),
        "pipedrive_configured": bool(PIPEDRIVE_API_TOKEN),
        "ai_configured": bool(ANTHROPIC_API_KEY),
        "auto_scan_enabled": get_setting('auto_scan_enabled', 'false') == 'true',
        "scanner_running": _scanner_running,
        "last_scan_time": _last_scan_time.isoformat() if _last_scan_time else None,
        "stats": stats,
        "settings": {
            "days_to_scan": int(get_setting('days_to_scan', '7')),
            "scan_interval_minutes": int(get_setting('scan_interval_minutes', '30'))
        }
    })


@app.route('/api/test-outlook')
def api_test_outlook():
    """Test Outlook connection"""
    client = OutlookSentFolderClient()
    return jsonify(client.test_connection())


@app.route('/api/test-pipedrive')
def api_test_pipedrive():
    """Test Pipedrive connection"""
    client = PipedriveClient()
    return jsonify(client.test_connection())


@app.route('/api/scan', methods=['POST'])
def api_scan():
    """Run a manual scan"""
    data = request.get_json() or {}
    days_back = data.get('days_back', int(get_setting('days_to_scan', '7')))
    
    service = QuoteSentMoverService()
    result = service.scan(days_back=days_back)
    
    global _last_scan_time, _last_scan_result
    _last_scan_time = datetime.now()
    _last_scan_result = result
    
    return jsonify(result)


@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Preview what emails would be processed (no API calls, no changes)"""
    data = request.get_json() or {}
    days_back = data.get('days_back', int(get_setting('days_to_scan', '7')))
    
    client = OutlookSentFolderClient()
    emails = client.get_sent_estimate_emails(days_back=days_back)
    
    preview = []
    for email in emails:
        subject = email.get('subject', '')
        estimate_info = parse_estimate_subject(subject)
        already_processed = is_email_processed(email.get('id'))
        
        preview.append({
            'subject': subject,
            'sent_date': email.get('sentDateTime'),
            'parsed': estimate_info,
            'already_processed': already_processed
        })
    
    return jsonify({
        "success": True,
        "total_emails": len(emails),
        "preview": preview[:50]  # Limit to 50
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update settings"""
    if request.method == 'GET':
        return jsonify({
            "auto_scan_enabled": get_setting('auto_scan_enabled', 'false') == 'true',
            "scan_interval_minutes": int(get_setting('scan_interval_minutes', '30')),
            "days_to_scan": int(get_setting('days_to_scan', '7')),
            "scanner_running": _scanner_running,
            "last_scan_time": _last_scan_time.isoformat() if _last_scan_time else None
        })
    else:
        data = request.get_json() or {}
        
        if 'auto_scan_enabled' in data:
            enabled = data['auto_scan_enabled']
            set_setting('auto_scan_enabled', 'true' if enabled else 'false')
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


@app.route('/api/activity-log')
def api_activity_log():
    """Get recent activity log"""
    limit = request.args.get('limit', 100, type=int)
    log = get_activity_log(limit)
    return jsonify({
        "success": True,
        "log": log
    })


@app.route('/api/clear-processed', methods=['POST'])
def api_clear_processed():
    """Clear processed emails to allow re-scanning"""
    count = clear_processed_emails()
    return jsonify({
        "success": True,
        "message": f"Cleared {count} processed email records"
    })


@app.route('/api/candidates', methods=['POST'])
def api_get_candidates():
    """
    Get list of estimate email candidates with their match status.
    This does NOT make changes - just shows what would happen.
    Returns a table-ready list with matching info for each estimate.
    Includes source deals (candidate deals considered) for each estimate.
    """
    data = request.get_json() or {}
    days_back = data.get('days_back', int(get_setting('days_to_scan', '7')))
    
    try:
        # Initialize service
        service = QuoteSentMoverService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize Pipedrive connection"})
        
        # Get sent estimate emails
        emails = service.outlook.get_sent_estimate_emails(days_back=days_back)
        
        if not emails:
            return jsonify({
                "success": True,
                "candidates": [],
                "source_deals": [],
                "target_deals": [],
                "source_deals_count": 0,
                "target_deals_count": 0
            })
        
        # Get deals
        source_deals = service.get_source_deals()
        target_deals = service.get_target_stage_deals()
        
        # Build simplified source deals list for frontend
        source_deals_simple = []
        for deal in source_deals:
            org_name = ""
            if isinstance(deal.get('organization'), dict):
                org_name = deal['organization'].get('name', '')
            elif deal.get('org_name'):
                org_name = deal['org_name']
            
            source_deals_simple.append({
                'id': deal['id'],
                'title': deal.get('title', ''),
                'org_name': org_name,
                'stage_id': deal.get('stage_id'),
                'add_time': deal.get('add_time', '')
            })
        
        # Build simplified target deals list for frontend
        target_deals_simple = []
        for deal in target_deals:
            org_name = ""
            if isinstance(deal.get('organization'), dict):
                org_name = deal['organization'].get('name', '')
            elif deal.get('org_name'):
                org_name = deal['org_name']
            
            target_deals_simple.append({
                'id': deal['id'],
                'title': deal.get('title', ''),
                'org_name': org_name
            })
        
        candidates = []
        for email in emails:
            subject = email.get('subject', '')
            message_id = email.get('id')
            sent_date = email.get('sentDateTime', '')
            
            # Check if already processed FIRST (before AI calls)
            already_processed = is_email_processed(message_id)
            
            # Get previous result if processed
            prev_result = None
            prev_action = None
            prev_deal_id = None
            prev_estimate_id = None
            if already_processed:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT result, action_taken, matched_deal_id, estimate_id FROM processed_emails WHERE message_id = ?',
                    (message_id,)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    prev_result = row['result']
                    prev_action = row['action_taken']
                    prev_deal_id = row['matched_deal_id']
                    prev_estimate_id = row['estimate_id'] if 'estimate_id' in row.keys() else None
                
                # For already processed emails, skip AI - just show previous results
                candidate = {
                    'message_id': message_id,
                    'subject': subject,
                    'sent_date': sent_date,
                    'estimate_id': prev_estimate_id,
                    'gc_name': None,
                    'project_name': None,
                    'project_address': None,
                    'is_revised': False,
                    'parse_success': True,
                    'parse_method': 'cached',
                    'already_processed': True,
                    'previous_result': prev_result,
                    'previous_action': prev_action,
                    'previous_deal_id': prev_deal_id,
                    'status': 'processed',
                    'status_detail': f'Previously: {prev_action or prev_result}',
                    'matched_deal': {'id': prev_deal_id, 'title': f'Deal #{prev_deal_id}'} if prev_deal_id else None,
                    'confidence': 100,
                    'duplicate_deal': None,
                    'candidate_deals_considered': []
                }
                candidates.append(candidate)
                continue
            
            # Only parse with AI for NEW (unprocessed) emails
            estimate_info = parse_estimate_subject(subject)
            
            candidate = {
                'message_id': message_id,
                'subject': subject,
                'sent_date': sent_date,
                'estimate_id': estimate_info.get('estimate_id') if estimate_info else None,
                'gc_name': estimate_info.get('gc_name') if estimate_info else None,
                'project_name': estimate_info.get('project_name') if estimate_info else None,
                'project_address': estimate_info.get('project_address') if estimate_info else None,
                'is_revised': estimate_info.get('is_revised', False) if estimate_info else False,
                'parse_success': estimate_info is not None and estimate_info.get('estimate_id') is not None,
                'parse_method': estimate_info.get('parse_method', 'unknown') if estimate_info else 'failed',
                'already_processed': False,
                'previous_result': None,
                'previous_action': None,
                'previous_deal_id': None,
                'status': 'unknown',
                'status_detail': '',
                'matched_deal': None,
                'confidence': 0,
                'duplicate_deal': None,
                'candidate_deals_considered': []
            }
            
            # If not parsed properly, mark as error
            if not estimate_info or not estimate_info.get('estimate_id'):
                candidate['status'] = 'parse_error'
                candidate['status_detail'] = 'Could not parse subject line'
                candidates.append(candidate)
                continue
            
            # Check for duplicates in target stage
            is_duplicate, duplicate_deal = service.check_for_duplicate(estimate_info, target_deals)
            
            if is_duplicate:
                candidate['status'] = 'duplicate'
                candidate['status_detail'] = f"Already in '{TARGET_STAGE}'"
                candidate['duplicate_deal'] = {
                    'id': duplicate_deal['id'],
                    'title': duplicate_deal.get('title', '')
                }
                if estimate_info.get('is_revised'):
                    candidate['status'] = 'revised_duplicate'
                    candidate['status_detail'] = 'Revised estimate - can update existing deal'
                candidates.append(candidate)
                continue
            
            # Try to find a match in source deals - also get candidates considered
            found_match, matched_deal, confidence, candidates_considered = service.matcher.match_estimate_to_deal_with_candidates(
                estimate_info, source_deals
            )
            
            # Store the candidates considered (top matches)
            candidate['candidate_deals_considered'] = candidates_considered
            
            if found_match:
                candidate['status'] = 'ready'
                candidate['status_detail'] = f'Match found ({confidence}% confidence)'
                candidate['matched_deal'] = {
                    'id': matched_deal['id'],
                    'title': matched_deal.get('title', '')
                }
                candidate['confidence'] = confidence
            else:
                candidate['status'] = 'no_match'
                candidate['status_detail'] = f'No matching deal found ({confidence}% max confidence)'
                candidate['confidence'] = confidence
            
            candidates.append(candidate)
        
        return jsonify({
            "success": True,
            "candidates": candidates,
            "source_deals": source_deals_simple,
            "target_deals": target_deals_simple,
            "source_deals_count": len(source_deals),
            "target_deals_count": len(target_deals),
            "summary": {
                "total": len(candidates),
                "ready": len([c for c in candidates if c['status'] == 'ready']),
                "duplicates": len([c for c in candidates if c['status'] in ['duplicate', 'revised_duplicate']]),
                "no_match": len([c for c in candidates if c['status'] == 'no_match']),
                "parse_errors": len([c for c in candidates if c['status'] == 'parse_error']),
                "already_processed": len([c for c in candidates if c['already_processed']])
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting candidates: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/process-single', methods=['POST'])
def api_process_single():
    """Process a single estimate email by message_id"""
    data = request.get_json() or {}
    message_id = data.get('message_id')
    force = data.get('force', False)  # Force re-process even if already done
    
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})
    
    try:
        # Check if already processed (unless forcing)
        if not force and is_email_processed(message_id):
            return jsonify({
                "success": False,
                "error": "Already processed. Use force=true to re-process."
            })
        
        # If forcing, clear the processed record first
        if force:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM processed_emails WHERE message_id = ?', (message_id,))
            conn.commit()
            conn.close()
        
        # Initialize service
        service = QuoteSentMoverService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize"})
        
        # Get the specific email
        client = OutlookSentFolderClient()
        
        # We need to fetch this specific email
        token = client._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        url = f"https://graph.microsoft.com/v1.0/users/{MONITORED_EMAIL}/messages/{message_id}"
        params = {"$select": "id,subject,sentDateTime,toRecipients"}
        
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            return jsonify({"success": False, "error": "Could not fetch email"})
        
        email = response.json()
        
        # Get deals
        source_deals = service.get_source_deals()
        target_deals = service.get_target_stage_deals()
        
        # Process
        result = service.process_estimate_email(email, source_deals, target_deals)
        
        return jsonify({
            "success": True,
            "result": result
        })
        
    except Exception as e:
        logger.error(f"Error processing single: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/process-batch', methods=['POST'])
def api_process_batch():
    """Process multiple estimate emails by message_ids"""
    data = request.get_json() or {}
    message_ids = data.get('message_ids', [])
    force = data.get('force', False)
    
    if not message_ids:
        return jsonify({"success": False, "error": "message_ids required"})
    
    try:
        # Initialize service
        service = QuoteSentMoverService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize"})
        
        # Get deals once
        source_deals = service.get_source_deals()
        target_deals = service.get_target_stage_deals()
        
        # Get Outlook client
        client = OutlookSentFolderClient()
        token = client._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        results = []
        summary = {
            'total': len(message_ids),
            'moved': 0,
            'duplicates': 0,
            'no_match': 0,
            'skipped': 0,
            'errors': 0
        }
        
        for message_id in message_ids:
            try:
                # Check if already processed (unless forcing)
                if not force and is_email_processed(message_id):
                    results.append({
                        'message_id': message_id,
                        'status': 'skipped',
                        'message': 'Already processed'
                    })
                    summary['skipped'] += 1
                    continue
                
                # If forcing, clear the processed record first
                if force:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM processed_emails WHERE message_id = ?', (message_id,))
                    conn.commit()
                    conn.close()
                
                # Fetch email
                url = f"https://graph.microsoft.com/v1.0/users/{MONITORED_EMAIL}/messages/{message_id}"
                params = {"$select": "id,subject,sentDateTime,toRecipients"}
                
                response = requests.get(url, headers=headers, params=params)
                if response.status_code != 200:
                    results.append({
                        'message_id': message_id,
                        'status': 'error',
                        'message': 'Could not fetch email'
                    })
                    summary['errors'] += 1
                    continue
                
                email = response.json()
                
                # Process
                result = service.process_estimate_email(email, source_deals, target_deals)
                result['message_id'] = message_id
                results.append(result)
                
                if result['status'] == 'success':
                    summary['moved'] += 1
                elif result['status'] == 'duplicate':
                    summary['duplicates'] += 1
                elif result['status'] == 'no_match':
                    summary['no_match'] += 1
                elif result['status'] == 'skipped':
                    summary['skipped'] += 1
                else:
                    summary['errors'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing {message_id}: {e}")
                results.append({
                    'message_id': message_id,
                    'status': 'error',
                    'message': str(e)
                })
                summary['errors'] += 1
        
        return jsonify({
            "success": True,
            "summary": summary,
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Error in batch process: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/reset-single', methods=['POST'])
def api_reset_single():
    """Reset a single processed email to allow re-processing"""
    data = request.get_json() or {}
    message_id = data.get('message_id')
    
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM processed_emails WHERE message_id = ?', (message_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return jsonify({
        "success": True,
        "message": f"Reset {'successful' if deleted else 'nothing to reset'}"
    })


@app.route('/api/ignore-email', methods=['POST'])
def api_ignore_email():
    """Mark an email as ignored/deleted - won't show up in future scans"""
    data = request.get_json() or {}
    message_id = data.get('message_id')
    subject = data.get('subject', '')
    
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})
    
    # Mark as processed with 'ignored' status
    mark_email_processed(message_id, subject, None, 'ignored', None, 'user_ignored')
    
    log_activity(
        action='ignored',
        email_subject=subject,
        estimate_id=None,
        deal_id=None,
        deal_title=None,
        status='success',
        message='Email ignored by user'
    )
    
    return jsonify({
        "success": True,
        "message": "Email marked as ignored"
    })


@app.route('/api/create-deal', methods=['POST'])
def api_create_deal():
    """Create a new deal in Pipedrive for an estimate email that had no match"""
    data = request.get_json() or {}
    message_id = data.get('message_id')
    subject = data.get('subject', '')
    estimate_info = data.get('estimate_info', {})
    force = data.get('force', False)  # Force creation even if duplicate exists
    
    if not message_id:
        return jsonify({"success": False, "error": "message_id required"})
    
    try:
        # Initialize service
        service = QuoteSentMoverService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize Pipedrive"})
        
        # Check for duplicates first (unless force=True)
        if not force and estimate_info:
            target_deals = service.get_target_stage_deals()
            is_duplicate, duplicate_deal = service.check_for_duplicate(estimate_info, target_deals)
            if is_duplicate:
                return jsonify({
                    "success": False,
                    "error": "duplicate_exists",
                    "message": f"A deal already exists in Quote Sent stage",
                    "duplicate_deal": {
                        "id": duplicate_deal['id'],
                        "title": duplicate_deal.get('title', '')
                    }
                })
        
        # Build deal title from estimate info or subject
        if estimate_info and estimate_info.get('estimate_id'):
            deal_title = f"Estimate - {estimate_info.get('estimate_id', '')}"
            if estimate_info.get('gc_name'):
                deal_title += f" - {estimate_info['gc_name']}"
            if estimate_info.get('project_name'):
                deal_title += f" - {estimate_info['project_name']}"
        else:
            # Use subject but clean it up
            deal_title = subject
        
        # Create the deal in Pipedrive
        deal_data = {
            "title": deal_title,
            "stage_id": service._target_stage_id,
            "pipeline_id": service._pipeline_id
        }
        
        # Try to find org by GC name
        if estimate_info and estimate_info.get('gc_name'):
            gc_name = estimate_info['gc_name']
            # Search for organization
            search_url = f"{PIPEDRIVE_BASE_URL}/organizations/search"
            search_params = {
                "api_token": PIPEDRIVE_API_TOKEN,
                "term": gc_name,
                "limit": 5
            }
            search_resp = requests.get(search_url, params=search_params)
            if search_resp.status_code == 200:
                search_data = search_resp.json()
                items = search_data.get('data', {}).get('items', [])
                if items:
                    # Use first matching org
                    deal_data['org_id'] = items[0]['item']['id']
                    logger.info(f"Found org '{items[0]['item']['name']}' for GC '{gc_name}'")
        
        # Create deal
        create_url = f"{PIPEDRIVE_BASE_URL}/deals"
        create_params = {"api_token": PIPEDRIVE_API_TOKEN}
        create_resp = requests.post(create_url, params=create_params, json=deal_data)
        
        if create_resp.status_code not in [200, 201]:
            logger.error(f"Failed to create deal: {create_resp.text}")
            return jsonify({"success": False, "error": f"Pipedrive error: {create_resp.text}"})
        
        result = create_resp.json()
        new_deal = result.get('data', {})
        new_deal_id = new_deal.get('id')
        
        if not new_deal_id:
            return jsonify({"success": False, "error": "Deal created but no ID returned"})
        
        # Mark email as processed
        estimate_id = estimate_info.get('estimate_id') if estimate_info else None
        mark_email_processed(message_id, subject, estimate_id, 'success', new_deal_id, 'deal_created')
        
        log_activity(
            action='deal_created',
            email_subject=subject,
            estimate_id=estimate_id,
            deal_id=new_deal_id,
            deal_title=deal_title,
            status='success',
            message=f'Created new deal in Quote Sent stage'
        )
        
        return jsonify({
            "success": True,
            "message": f"Deal created successfully",
            "deal_id": new_deal_id,
            "deal_title": deal_title
        })
        
    except Exception as e:
        logger.error(f"Error creating deal: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/pipedrive/stages')
def api_pipedrive_stages():
    """Get Pipedrive pipeline and stages info"""
    try:
        service = QuoteSentMoverService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize"})
        
        source_deals = service.get_source_deals()
        target_deals = service.get_target_stage_deals()
        
        return jsonify({
            "success": True,
            "pipeline_id": service._pipeline_id,
            "source_stages": SOURCE_STAGES,
            "source_stage_ids": service._source_stage_ids,
            "target_stage": TARGET_STAGE,
            "target_stage_id": service._target_stage_id,
            "source_deals_count": len(source_deals),
            "target_deals_count": len(target_deals),
            "source_deals_sample": [{"id": d['id'], "title": d.get('title', '')[:60]} for d in source_deals[:10]],
            "target_deals_sample": [{"id": d['id'], "title": d.get('title', '')[:60]} for d in target_deals[:10]]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    init_database()
    
    if get_setting('auto_scan_enabled', 'false') == 'true':
        start_scanner()
    
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
