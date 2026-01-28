"""
Bid Calendar - All Painting Ltd.
Port: 3033

PURPOSE: Creates calendar events for bid deadlines using Microsoft Graph API.
INHERITED FROM: ai-agent-pipedrive/outlook_calendar.py
"""

import os
import sqlite3
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import Flask, jsonify, request

PORT = 3033
APP_NAME = "Bid Calendar"
APP_VERSION = "2.0.0"

BID_TRACKER_DB = os.environ.get('BID_TRACKER_DB_PATH',
    os.path.join(os.path.dirname(__file__), "..", "bid-email-scanner", "bid_tracker.db"))
LOCAL_DB = os.path.join(os.path.dirname(__file__), "calendar_events.db")

# Azure/Graph API (from ai-agent-pipedrive/outlook_calendar.py)
AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
CALENDAR_USER = "info@allpaintingltd.com"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)


def get_bid_tracker_connection():
    if not os.path.exists(BID_TRACKER_DB): return None
    conn = sqlite3.connect(BID_TRACKER_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_local_connection():
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS calendar_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bid_tracker_id INTEGER, outlook_entry_id TEXT,
        event_date TEXT, event_start_time TEXT, event_end_time TEXT, reminder_minutes INTEGER, created_at TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)''')
    for k, v in {'calendar_start_time': '08:00', 'calendar_end_time': '09:00', 'calendar_reminder': '1440'}.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                      (k, v, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = None) -> str:
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key: str, value: str):
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)',
                   (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def log_calendar_event(bid_id: int, outlook_id: str, date: str, start: str, end: str, reminder: int):
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO calendar_events 
        (bid_tracker_id, outlook_entry_id, event_date, event_start_time, event_end_time, reminder_minutes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)''', (bid_id, outlook_id, date, start, end, reminder, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_calendar_event_for_bid(bid_id: int) -> Optional[Dict]:
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM calendar_events WHERE bid_tracker_id = ? ORDER BY created_at DESC LIMIT 1', (bid_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_bid_by_id(bid_id: int) -> Optional[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return None
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker WHERE id = ?', (bid_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_bids_due_on_date(date_str: str) -> List[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker WHERE date(bid_due_date) = date(?) ORDER BY project_name', (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


class OutlookCalendar:
    """Outlook Calendar using Microsoft Graph API (from ai-agent-pipedrive/outlook_calendar.py)"""
    
    REMINDER_OPTIONS = {'none': None, '1hour': 60, '4hours': 240, '1day': 1440, '2days': 2880, '1week': 10080}
    
    def __init__(self):
        self.access_token = None
        self.token_expires = None
    
    def _get_access_token(self):
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        response = requests.post(f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
            data={"client_id": AZURE_CLIENT_ID, "client_secret": AZURE_CLIENT_SECRET,
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"})
        if response.status_code != 200: raise Exception(f"Token error: {response.text}")
        data = response.json()
        self.access_token = data["access_token"]
        self.token_expires = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 300)
        return self.access_token
    
    def find_existing_event(self, project_name: str, event_date: datetime) -> Optional[Dict]:
        """Check if calendar event already exists (from ai-agent-pipedrive/outlook_calendar.py)"""
        try:
            token = self._get_access_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            start = event_date.replace(hour=0, minute=0, second=0)
            end = event_date.replace(hour=23, minute=59, second=59)
            params = {
                "$filter": f"start/dateTime ge '{start.strftime('%Y-%m-%dT%H:%M:%S')}' and start/dateTime le '{end.strftime('%Y-%m-%dT%H:%M:%S')}'",
                "$select": "id,subject,start,end", "$top": 50
            }
            response = requests.get(f"https://graph.microsoft.com/v1.0/users/{CALENDAR_USER}/events",
                                   headers=headers, params=params)
            if response.status_code == 200:
                project_lower = project_name.lower().strip() if project_name else ''
                for event in response.json().get('value', []):
                    if project_lower and project_lower in event.get('subject', '').lower():
                        logger.info(f"Found existing event: {event.get('subject')}")
                        return event
            return None
        except Exception as e:
            logger.warning(f"Error checking existing event: {e}")
            return None
    
    def create_bid_event(self, bid: Dict, start_time: str = "08:00", end_time: str = "09:00",
                         reminder_minutes: int = 1440, skip_duplicate_check: bool = False) -> Optional[str]:
        """Create calendar event for bid deadline (from ai-agent-pipedrive/outlook_calendar.py)"""
        try:
            # Parse due date
            due_date = None
            if bid.get('bid_due_date'):
                date_str = bid['bid_due_date']
                if date_str and isinstance(date_str, str) and date_str.strip():
                    for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y', '%m/%d/%Y']:
                        try:
                            due_date = datetime.strptime(date_str.strip(), fmt)
                            break
                        except: continue
            
            if not due_date:
                logger.warning(f"No valid date for calendar event: {bid.get('project_name')}")
                return None
            
            # Check for existing (unless skipped)
            if not skip_duplicate_check:
                existing = self.find_existing_event(bid.get('project_name', ''), due_date)
                if existing:
                    logger.info(f"Calendar event already exists for '{bid.get('project_name')}', returning existing")
                    return existing.get('id')
            
            # Build title: NB - GC Company - Project Name - Address
            title_parts = ["NB"]
            if bid.get('gc_company'): title_parts.append(bid['gc_company'])
            if bid.get('project_name'): title_parts.append(bid['project_name'])
            if bid.get('project_address'):
                addr = bid['project_address'][:50] + "..." if len(bid['project_address']) > 50 else bid['project_address']
                title_parts.append(addr)
            subject = " - ".join(title_parts)
            if subject == "NB": subject = f"NB - {bid.get('project_name', 'Unknown Project')}"
            
            # Build body
            body_lines = ["=" * 50, "BID DEADLINE REMINDER", "=" * 50, "",
                         f"Project: {bid.get('project_name', 'N/A')}",
                         f"GC Company: {bid.get('gc_company', 'N/A')}", ""]
            if bid.get('gc_contact_name'): body_lines.append(f"Contact: {bid['gc_contact_name']}")
            if bid.get('gc_contact_email'): body_lines.append(f"Email: {bid['gc_contact_email']}")
            if bid.get('gc_phone'): body_lines.append(f"Phone: {bid['gc_phone']}")
            body_lines.append("")
            if bid.get('project_address'): body_lines.append(f"Address: {bid['project_address']}")
            if bid.get('scope_of_work'):
                body_lines.extend(["", "Scope of Work:", "-" * 30, bid['scope_of_work']])
            body_lines.extend(["", "=" * 50, "-- Created by Bid Calendar Service"])
            
            # Parse times
            try:
                sh, sm = map(int, start_time.split(':'))
                eh, em = map(int, end_time.split(':'))
            except:
                sh, sm, eh, em = 8, 0, 9, 0
            start_dt = due_date.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end_dt = due_date.replace(hour=eh, minute=em, second=0, microsecond=0)
            
            payload = {
                "subject": subject,
                "body": {"contentType": "text", "content": "\n".join(body_lines)},
                "start": {"dateTime": start_dt.strftime('%Y-%m-%dT%H:%M:%S'), "timeZone": "Pacific Standard Time"},
                "end": {"dateTime": end_dt.strftime('%Y-%m-%dT%H:%M:%S'), "timeZone": "Pacific Standard Time"},
                "location": {"displayName": bid.get('project_address', '')},
                "categories": ["Bid Deadline"],
                "isReminderOn": reminder_minutes > 0 if reminder_minutes else False,
                "reminderMinutesBeforeStart": reminder_minutes if reminder_minutes and reminder_minutes > 0 else 0
            }
            
            response = requests.post(
                f"https://graph.microsoft.com/v1.0/users/{CALENDAR_USER}/events",
                headers={"Authorization": f"Bearer {self._get_access_token()}", "Content-Type": "application/json"},
                json=payload)
            
            if response.status_code in [200, 201]:
                event_id = response.json().get('id')
                logger.info(f"Created calendar event for: {bid.get('project_name')}")
                return event_id
            else:
                logger.error(f"Failed to create event: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Calendar event error: {e}")
            return None


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    return jsonify({
        "service": APP_NAME, "version": APP_VERSION, "port": PORT,
        "purpose": "Creates calendar events for bid deadlines using Microsoft Graph API."
    })


@app.route('/api/status')
def api_status():
    today = datetime.now().strftime('%Y-%m-%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    return jsonify({
        "service": APP_NAME,
        "calendar_start_time": get_setting('calendar_start_time', '08:00'),
        "calendar_end_time": get_setting('calendar_end_time', '09:00'),
        "calendar_reminder": int(get_setting('calendar_reminder', '1440')),
        "bids_due_today": len(get_bids_due_on_date(today)),
        "bids_due_tomorrow": len(get_bids_due_on_date(tomorrow))
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify({
            "calendar_start_time": get_setting('calendar_start_time', '08:00'),
            "calendar_end_time": get_setting('calendar_end_time', '09:00'),
            "calendar_reminder": int(get_setting('calendar_reminder', '1440'))
        })
    data = request.get_json() or {}
    for key in ['calendar_start_time', 'calendar_end_time', 'calendar_reminder']:
        if key in data: set_setting(key, str(data[key]))
    return jsonify({"success": True, "message": "Settings updated"})


@app.route('/api/create/<int:bid_id>', methods=['POST'])
def api_create_event(bid_id):
    """Create calendar event for a bid"""
    # Check if Azure credentials are configured
    if not AZURE_CLIENT_SECRET:
        return jsonify({"success": False, "error": "Azure client secret not configured. Set AZURE_CLIENT_SECRET environment variable."}), 500
    
    bid = get_bid_by_id(bid_id)
    if not bid:
        return jsonify({"success": False, "error": "Bid not found"}), 404
    
    if not bid.get('bid_due_date'):
        return jsonify({"success": False, "error": "Bid has no due date set"}), 400
    
    # Be lenient with JSON parsing - accept empty body
    try:
        data = request.get_json(force=True, silent=True) or {}
    except:
        data = {}
    
    start_time = data.get('start_time', get_setting('calendar_start_time', '08:00'))
    end_time = data.get('end_time', get_setting('calendar_end_time', '09:00'))
    reminder = int(data.get('reminder', get_setting('calendar_reminder', '1440')))
    
    try:
        calendar = OutlookCalendar()
        entry_id = calendar.create_bid_event(bid, start_time, end_time, reminder)
        
        if entry_id:
            log_calendar_event(bid_id, entry_id, bid.get('bid_due_date', ''), start_time, end_time, reminder)
            return jsonify({"success": True, "message": "Calendar event created", "entry_id": entry_id})
        return jsonify({"success": False, "error": "Failed to create event - check logs for details"}), 500
    except Exception as e:
        logger.error(f"Calendar creation error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/status/<int:bid_id>')
def api_event_status(bid_id):
    """Check if a bid has a calendar event"""
    event = get_calendar_event_for_bid(bid_id)
    return jsonify({"has_event": event is not None, "event": event})


@app.route('/api/bids/due-today')
def api_bids_due_today():
    today = datetime.now().strftime('%Y-%m-%d')
    bids = get_bids_due_on_date(today)
    return jsonify({"success": True, "bids": bids, "count": len(bids)})


@app.route('/api/bids/due-tomorrow')
def api_bids_due_tomorrow():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    bids = get_bids_due_on_date(tomorrow)
    return jsonify({"success": True, "bids": bids, "count": len(bids)})


if __name__ == '__main__':
    init_database()
    logger.info(f"Starting {APP_NAME} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
