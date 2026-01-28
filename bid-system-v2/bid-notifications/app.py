"""
Bid Notifications - All Painting Ltd.
Port: 3034

PURPOSE: Sends daily deadline reminder emails and other notifications.
Uses Microsoft Graph API to send emails (same as email scanner).
INHERITED FROM: ai-agent-pipedrive/daily_email.py
"""

import os
import sqlite3
import logging
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import Flask, jsonify, request

PORT = 3034
APP_NAME = "Bid Notifications"
APP_VERSION = "2.0.0"

BID_TRACKER_DB = os.environ.get('BID_TRACKER_DB_PATH',
    os.path.join(os.path.dirname(__file__), "..", "bid-email-scanner", "bid_tracker.db"))
LOCAL_DB = os.path.join(os.path.dirname(__file__), "notifications.db")

# Azure / Microsoft Graph API credentials (same as email scanner)
AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
SENDER_EMAIL = "info@allpaintingltd.com"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)

_email_scheduler_running = False
_email_scheduler_thread = None


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
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS email_log (id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_at TEXT, recipient TEXT, bids_today INTEGER, bids_tomorrow INTEGER, status TEXT)''')
    for k, v in {
        'email_enabled': 'true', 'email_send_time': '07:00',
        'email_recipient': 'info@allpaintingltd.com', 'last_email_sent_date': ''
    }.items():
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


def log_email_sent(recipient: str, bids_today: int, bids_tomorrow: int, status: str):
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO email_log (sent_at, recipient, bids_today, bids_tomorrow, status) VALUES (?, ?, ?, ?, ?)',
                   (datetime.now().isoformat(), recipient, bids_today, bids_tomorrow, status))
    conn.commit()
    conn.close()


def get_bids_due_on_date(date_str: str) -> List[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker WHERE date(bid_due_date) = date(?) ORDER BY project_name', (date_str,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_bids_due_today() -> List[Dict]:
    return get_bids_due_on_date(datetime.now().strftime('%Y-%m-%d'))


def get_bids_due_tomorrow() -> List[Dict]:
    return get_bids_due_on_date((datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'))


class DailyEmailReport:
    """Sends daily deadline reminder emails via Microsoft Graph API"""
    
    def __init__(self, recipient_email: str = "info@allpaintingltd.com"):
        self.recipient_email = recipient_email
        self._access_token = None
        self._token_expires = None
    
    def _get_access_token(self) -> Optional[str]:
        """Get OAuth access token for Microsoft Graph API"""
        if self._access_token and self._token_expires and datetime.now() < self._token_expires:
            return self._access_token
        
        if not AZURE_CLIENT_SECRET:
            logger.error("AZURE_CLIENT_SECRET not set")
            return None
        
        token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": AZURE_CLIENT_ID,
            "client_secret": AZURE_CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default"
        }
        
        try:
            response = requests.post(token_url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
                return self._access_token
            else:
                logger.error(f"Token request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Token request error: {e}")
            return None
    
    def send_deadline_report(self, bids_today: List[Dict], bids_tomorrow: List[Dict]) -> bool:
        """Send the daily deadline report email via Microsoft Graph API"""
        try:
            token = self._get_access_token()
            if not token:
                logger.error("Failed to get access token for sending email")
                return False
            
            today_count = len(bids_today)
            tomorrow_count = len(bids_tomorrow)
            
            # Build subject
            if today_count > 0:
                subject = f"🚨 BID DEADLINES TODAY - {today_count} Bid{'s' if today_count != 1 else ''} Due"
            elif tomorrow_count > 0:
                subject = f"📋 Bid Deadline Reminder - {tomorrow_count} Bid{'s' if tomorrow_count != 1 else ''} Due Tomorrow"
            else:
                subject = "✅ Daily Bid Report - No Deadlines Today or Tomorrow"
            
            # Build email message
            message = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": self._build_html_body(bids_today, bids_tomorrow)
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": self.recipient_email}}
                    ],
                    "importance": "high" if today_count > 0 else "normal"
                },
                "saveToSentItems": "true"
            }
            
            # Send via Graph API
            url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, headers=headers, json=message)
            
            if response.status_code == 202:
                logger.info(f"Sent deadline report: {today_count} today, {tomorrow_count} tomorrow to {self.recipient_email}")
                return True
            else:
                logger.error(f"Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _build_html_body(self, bids_today: List[Dict], bids_tomorrow: List[Dict]) -> str:
        """Build HTML email body (from ai-agent-pipedrive/daily_email.py)"""
        today_date = datetime.now().strftime("%B %d, %Y")
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%B %d, %Y")
        
        html = f"""<html><head><style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; color: #333; line-height: 1.6; }}
            .container {{ max-width: 700px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #0f2744, #1a3a5c); color: white; padding: 30px; border-radius: 12px 12px 0 0; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .section {{ background: #f8fafc; padding: 20px; margin-bottom: 2px; }}
            .section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 15px; }}
            .section-title.today {{ color: #dc2626; }}
            .section-title.tomorrow {{ color: #f59e0b; }}
            .bid-card {{ background: white; border-radius: 10px; padding: 20px; margin-bottom: 15px; border-left: 4px solid #3b82f6; }}
            .bid-card.urgent {{ border-left-color: #dc2626; }}
            .bid-title {{ font-size: 16px; font-weight: 600; color: #0f2744; margin-bottom: 10px; }}
            .bid-detail {{ font-size: 14px; color: #64748b; margin: 5px 0; }}
            .footer {{ background: #f1f5f9; padding: 20px; border-radius: 0 0 12px 12px; text-align: center; color: #64748b; }}
            .no-bids {{ text-align: center; padding: 30px; color: #10b981; }}
        </style></head><body><div class="container">
            <div class="header"><h1>📋 Bid Deadline Report</h1><p>Good morning! Here's your summary for {today_date}</p></div>"""
        
        # Today section
        html += f'<div class="section"><div class="section-title today">🚨 Due TODAY ({today_date}) - {len(bids_today)} Bids</div>'
        if bids_today:
            for bid in bids_today:
                html += self._build_bid_card(bid, urgent=True)
        else:
            html += '<div class="no-bids">✓ No bids due today</div>'
        html += '</div>'
        
        # Tomorrow section
        html += f'<div class="section"><div class="section-title tomorrow">⏰ Due TOMORROW ({tomorrow_date}) - {len(bids_tomorrow)} Bids</div>'
        if bids_tomorrow:
            for bid in bids_tomorrow:
                html += self._build_bid_card(bid, urgent=False)
        else:
            html += '<div class="no-bids">✓ No bids due tomorrow</div>'
        html += '</div>'
        
        html += '<div class="footer"><p>Generated by <strong>Bid Notifications Service</strong></p></div></div></body></html>'
        return html
    
    def _build_bid_card(self, bid: Dict, urgent: bool = False) -> str:
        card_class = "bid-card urgent" if urgent else "bid-card"
        html = f'<div class="{card_class}">'
        html += f'<div class="bid-title">{bid.get("project_name", "Unknown Project")}</div>'
        html += f'<div class="bid-detail"><strong>GC:</strong> {bid.get("gc_company", "N/A")}</div>'
        if bid.get('gc_contact_name'):
            html += f'<div class="bid-detail"><strong>Contact:</strong> {bid["gc_contact_name"]}'
            if bid.get('gc_contact_email'): html += f' ({bid["gc_contact_email"]})'
            html += '</div>'
        if bid.get('project_address'):
            html += f'<div class="bid-detail"><strong>Address:</strong> {bid["project_address"]}</div>'
        html += '</div>'
        return html


def send_daily_email() -> Dict:
    """Send daily deadline email"""
    bids_today = get_bids_due_today()
    bids_tomorrow = get_bids_due_tomorrow()
    recipient = get_setting('email_recipient', 'info@allpaintingltd.com')
    
    report = DailyEmailReport(recipient_email=recipient)
    success = report.send_deadline_report(bids_today, bids_tomorrow)
    
    log_email_sent(recipient, len(bids_today), len(bids_tomorrow), 'success' if success else 'error')
    
    if success:
        set_setting('last_email_sent_date', datetime.now().strftime('%Y-%m-%d'))
    
    return {
        "success": success,
        "bids_today": len(bids_today),
        "bids_tomorrow": len(bids_tomorrow),
        "recipient": recipient
    }


def email_scheduler_loop():
    """Background loop for scheduled emails (from ai-agent-pipedrive/app.py)"""
    global _email_scheduler_running
    logger.info("Email scheduler started")
    
    while _email_scheduler_running:
        try:
            if get_setting('email_enabled', 'true') != 'true':
                time.sleep(300)
                continue
            
            now = datetime.now()
            send_time = get_setting('email_send_time', '07:00')
            send_hour, send_minute = map(int, send_time.split(':'))
            
            # Check if it's time (within 2-minute window)
            if now.hour == send_hour and now.minute >= send_minute and now.minute < send_minute + 2:
                last_sent = get_setting('last_email_sent_date', '')
                today = now.strftime('%Y-%m-%d')
                
                if last_sent != today:
                    logger.info("Sending scheduled daily email...")
                    result = send_daily_email()
                    logger.info(f"Scheduled email result: {result}")
            
            time.sleep(60)
        except Exception as e:
            logger.error(f"Email scheduler error: {e}")
            time.sleep(60)
    
    logger.info("Email scheduler stopped")


def start_email_scheduler():
    global _email_scheduler_thread, _email_scheduler_running
    if _email_scheduler_running: return
    _email_scheduler_running = True
    _email_scheduler_thread = threading.Thread(target=email_scheduler_loop, daemon=True)
    _email_scheduler_thread.start()


def stop_email_scheduler():
    global _email_scheduler_running
    _email_scheduler_running = False


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    return jsonify({
        "service": APP_NAME, "version": APP_VERSION, "port": PORT,
        "purpose": "Sends daily deadline reminder emails and other notifications."
    })


@app.route('/api/status')
def api_status():
    return jsonify({
        "service": APP_NAME,
        "email_enabled": get_setting('email_enabled', 'true') == 'true',
        "email_send_time": get_setting('email_send_time', '07:00'),
        "email_recipient": get_setting('email_recipient', 'info@allpaintingltd.com'),
        "last_email_sent_date": get_setting('last_email_sent_date', ''),
        "scheduler_running": _email_scheduler_running,
        "bids_due_today": len(get_bids_due_today()),
        "bids_due_tomorrow": len(get_bids_due_tomorrow())
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify({
            "email_enabled": get_setting('email_enabled', 'true') == 'true',
            "email_send_time": get_setting('email_send_time', '07:00'),
            "email_recipient": get_setting('email_recipient', 'info@allpaintingltd.com')
        })
    data = request.get_json() or {}
    if 'email_enabled' in data: set_setting('email_enabled', 'true' if data['email_enabled'] else 'false')
    if 'email_send_time' in data: set_setting('email_send_time', data['email_send_time'])
    if 'email_recipient' in data: set_setting('email_recipient', data['email_recipient'])
    return jsonify({"success": True, "message": "Settings updated"})


@app.route('/api/send-now', methods=['POST'])
def api_send_now():
    """Manually trigger the daily email (only once per day)"""
    # Check if already sent today
    last_sent = get_setting('last_email_sent_date', '')
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Allow force send via parameter
    data = request.get_json() or {}
    force = data.get('force', False)
    
    if last_sent == today and not force:
        return jsonify({
            'success': False,
            'skipped': True,
            'message': 'Email already sent today',
            'last_sent': last_sent
        })
    
    result = send_daily_email()
    if result['success']:
        return jsonify(result)
    return jsonify(result), 500


@app.route('/api/preview')
def api_preview():
    """Get preview data for the daily email"""
    bids_today = get_bids_due_today()
    bids_tomorrow = get_bids_due_tomorrow()
    return jsonify({
        "success": True,
        "bids_today": bids_today,
        "bids_tomorrow": bids_tomorrow,
        "today_count": len(bids_today),
        "tomorrow_count": len(bids_tomorrow)
    })


@app.route('/api/scheduler/start', methods=['POST'])
def api_start_scheduler():
    set_setting('email_enabled', 'true')
    start_email_scheduler()
    return jsonify({"success": True, "message": "Email scheduler started"})


@app.route('/api/scheduler/stop', methods=['POST'])
def api_stop_scheduler():
    set_setting('email_enabled', 'false')
    stop_email_scheduler()
    return jsonify({"success": True, "message": "Email scheduler stopped"})


if __name__ == '__main__':
    init_database()
    if get_setting('email_enabled', 'true') == 'true':
        start_email_scheduler()
    logger.info(f"Starting {APP_NAME} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
