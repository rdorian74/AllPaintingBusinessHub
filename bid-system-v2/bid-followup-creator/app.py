"""
Bid Follow-Up Creator - All Painting Ltd.
Port: 3036

PURPOSE: Creates follow-up email activities in Pipedrive for deals in 
"Quote Sent & Decision Pending" stage. Schedules activities 20 days after
the last email activity date. Tracks Follow Up 1, 2, 3, etc.

Only creates activities for deals without pending activities.
"""

import os
import json
import sqlite3
import logging
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Flask, jsonify, request, render_template_string

# =============================================================================
# CONFIGURATION
# =============================================================================

PORT = 3036
APP_NAME = "Bid Follow-Up Creator"
APP_VERSION = "1.0.0"

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "followup_creator.db")

# Pipedrive
PIPEDRIVE_API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
PIPEDRIVE_DOMAIN = os.environ.get("PIPEDRIVE_DOMAIN", "allpainting")
PIPEDRIVE_PIPELINE_NAME = "Pipeline"
PIPEDRIVE_BASE_URL = f"https://{PIPEDRIVE_DOMAIN}.pipedrive.com/api/v1"

# Target stage to monitor
TARGET_STAGE = "Quote Sent & Decision Pending"

# Follow-up settings
FOLLOWUP_DAYS = 20  # Days after last email to schedule follow-up

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
    
    # Follow-up tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS followup_tracker (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER UNIQUE,
            deal_title TEXT,
            followup_number INTEGER DEFAULT 0,
            last_followup_date TEXT,
            next_followup_date TEXT,
            activity_id INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Activity log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            action TEXT,
            deal_id INTEGER,
            deal_title TEXT,
            followup_number INTEGER,
            status TEXT,
            message TEXT
        )
    ''')
    
    # Default settings
    defaults = {
        'auto_scan_enabled': 'false',
        'scan_interval_minutes': '60',
        'followup_days': '20'
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


def get_followup_tracker() -> List[Dict]:
    """Get all tracked follow-ups"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM followup_tracker 
        ORDER BY updated_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_followup_by_deal(deal_id: int) -> Optional[Dict]:
    """Get follow-up record for a specific deal"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM followup_tracker WHERE deal_id = ?', (deal_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_followup(deal_id: int, deal_title: str, followup_number: int, 
                    followup_date: str, activity_id: int = None, status: str = 'pending'):
    """Insert or update follow-up record"""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    existing = get_followup_by_deal(deal_id)
    if existing:
        cursor.execute('''
            UPDATE followup_tracker 
            SET deal_title = ?, followup_number = ?, last_followup_date = ?,
                activity_id = ?, status = ?, updated_at = ?
            WHERE deal_id = ?
        ''', (deal_title, followup_number, followup_date, activity_id, status, now, deal_id))
    else:
        cursor.execute('''
            INSERT INTO followup_tracker 
            (deal_id, deal_title, followup_number, last_followup_date, activity_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (deal_id, deal_title, followup_number, followup_date, activity_id, status, now, now))
    
    conn.commit()
    conn.close()


def log_activity(action: str, deal_id: int = None, deal_title: str = None,
                 followup_number: int = None, status: str = None, message: str = None):
    """Log activity for dashboard"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO activity_log (timestamp, action, deal_id, deal_title, followup_number, status, message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().isoformat(), action, deal_id, deal_title, followup_number, status, message))
    conn.commit()
    conn.close()


def get_activity_log(limit: int = 100) -> List[Dict]:
    """Get recent activity log"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# PIPEDRIVE API CLIENT
# =============================================================================

class PipedriveClient:
    def __init__(self):
        self.api_token = PIPEDRIVE_API_TOKEN
        self.base_url = PIPEDRIVE_BASE_URL
        self._pipeline_id = None
        self._stage_id = None
    
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
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s")
                time.sleep(retry_after)
                return self._request(endpoint, method, data, params)
            
            response.raise_for_status()
            result = response.json()
            return result.get('data') if result.get('success') else None
        except Exception as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def test_connection(self) -> Dict:
        result = self._request('users/me')
        if result:
            return {'success': True, 'user': result.get('name'), 'company': result.get('company_name')}
        return {'success': False, 'error': 'Failed to connect'}
    
    def get_pipelines(self) -> List[Dict]:
        return self._request('pipelines') or []
    
    def get_pipeline_by_name(self, name: str) -> Optional[Dict]:
        for p in self.get_pipelines():
            if p.get('name', '').lower() == name.lower():
                return p
        return None
    
    def get_stages(self, pipeline_id: int) -> List[Dict]:
        return self._request('stages', params={'pipeline_id': pipeline_id}) or []
    
    def get_stage_by_name(self, pipeline_id: int, stage_name: str) -> Optional[Dict]:
        for s in self.get_stages(pipeline_id):
            if s.get('name', '').lower() == stage_name.lower():
                return s
        return None
    
    def initialize(self) -> bool:
        """Initialize pipeline and stage IDs"""
        pipeline = self.get_pipeline_by_name(PIPEDRIVE_PIPELINE_NAME)
        if not pipeline:
            logger.error(f"Pipeline '{PIPEDRIVE_PIPELINE_NAME}' not found")
            return False
        
        self._pipeline_id = pipeline['id']
        
        stage = self.get_stage_by_name(self._pipeline_id, TARGET_STAGE)
        if not stage:
            logger.error(f"Stage '{TARGET_STAGE}' not found")
            return False
        
        self._stage_id = stage['id']
        logger.info(f"Initialized: Pipeline={self._pipeline_id}, Stage={self._stage_id}")
        return True
    
    def get_deals_in_stage(self) -> List[Dict]:
        """Get all deals in the target stage"""
        if not self._stage_id:
            if not self.initialize():
                return []
        
        all_deals = []
        start = 0
        limit = 100
        
        while True:
            params = {
                'stage_id': self._stage_id,
                'status': 'open',
                'start': start,
                'limit': limit
            }
            result = self._request('deals', params=params)
            if not result:
                break
            all_deals.extend(result)
            if len(result) < limit:
                break
            start += limit
        
        return all_deals
    
    def get_deal_activities(self, deal_id: int) -> List[Dict]:
        """Get all activities for a deal"""
        all_activities = []
        start = 0
        limit = 100
        
        while True:
            params = {
                'start': start,
                'limit': limit
            }
            result = self._request(f'deals/{deal_id}/activities', params=params)
            if not result:
                break
            all_activities.extend(result)
            if len(result) < limit:
                break
            start += limit
        
        return all_activities
    
    def get_deal_details(self, deal_id: int) -> Optional[Dict]:
        """Get detailed deal information"""
        return self._request(f'deals/{deal_id}')
    
    def create_activity(self, deal_id: int, subject: str, activity_type: str = 'email',
                       due_date: str = None, note: str = None) -> Optional[Dict]:
        """Create an activity for a deal"""
        data = {
            'subject': subject,
            'type': activity_type,
            'deal_id': deal_id,
            'done': 0  # Not done (pending)
        }
        
        if due_date:
            data['due_date'] = due_date
        
        if note:
            data['note'] = note
        
        return self._request('activities', method='POST', data=data)


# =============================================================================
# FOLLOW-UP LOGIC
# =============================================================================

class FollowUpService:
    def __init__(self):
        self.pd = PipedriveClient()
    
    def initialize(self) -> bool:
        return self.pd.initialize()
    
    def get_last_email_activity(self, deal_id: int) -> Optional[Dict]:
        """Get the most recent email activity for a deal"""
        activities = self.pd.get_deal_activities(deal_id)
        
        # Filter for email activities and sort by due_date descending
        email_activities = [a for a in activities if a.get('type') == 'email']
        
        if not email_activities:
            return None
        
        # Sort by due_date or add_time
        email_activities.sort(
            key=lambda x: x.get('due_date') or x.get('add_time', ''),
            reverse=True
        )
        
        return email_activities[0]
    
    def get_last_followup_number(self, deal_id: int) -> int:
        """Get the last follow-up number from existing activities"""
        activities = self.pd.get_deal_activities(deal_id)
        
        # Look for "Follow Up N" pattern in subjects
        import re
        max_followup = 0
        
        for activity in activities:
            subject = activity.get('subject', '')
            match = re.search(r'Follow\s*Up\s*(\d+)', subject, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                max_followup = max(max_followup, num)
        
        return max_followup
    
    def has_pending_activity(self, deal_id: int) -> bool:
        """Check if deal has any pending (not done) activities"""
        activities = self.pd.get_deal_activities(deal_id)
        
        for activity in activities:
            if not activity.get('done'):
                return True
        
        return False
    
    def create_deal_summary(self, deal: Dict) -> str:
        """Create a summary note for the activity"""
        title = deal.get('title', 'Unknown Deal')
        org = deal.get('org_name', 'Unknown Organization')
        value = deal.get('value', 0)
        currency = deal.get('currency', 'CAD')
        
        # Get person info
        person_name = deal.get('person_name', 'Unknown Contact')
        
        summary = f"""📋 **Deal Summary**

**Project:** {title}
**Organization:** {org}
**Contact:** {person_name}
**Value:** {currency} {value:,.2f}

This is a scheduled follow-up activity. Please reach out to the client regarding their quote status.
"""
        return summary
    
    def process_deal(self, deal: Dict) -> Dict:
        """Process a single deal for follow-up creation"""
        deal_id = deal['id']
        deal_title = deal.get('title', 'Unknown')
        
        result = {
            'deal_id': deal_id,
            'deal_title': deal_title,
            'action': None,
            'success': False,
            'message': ''
        }
        
        # Check if deal has pending activities
        if self.has_pending_activity(deal_id):
            result['action'] = 'skipped'
            result['success'] = True
            result['message'] = 'Has pending activity'
            return result
        
        # Get last email activity
        last_email = self.get_last_email_activity(deal_id)
        
        if not last_email:
            result['action'] = 'skipped'
            result['success'] = True
            result['message'] = 'No email activity found'
            return result
        
        # Calculate follow-up date (20 days after last email)
        last_email_date_str = last_email.get('due_date') or last_email.get('add_time', '')[:10]
        
        try:
            last_email_date = datetime.strptime(last_email_date_str, '%Y-%m-%d')
        except:
            result['action'] = 'error'
            result['message'] = f'Invalid date: {last_email_date_str}'
            return result
        
        followup_days = int(get_setting('followup_days', str(FOLLOWUP_DAYS)))
        followup_date = last_email_date + timedelta(days=followup_days)
        followup_date_str = followup_date.strftime('%Y-%m-%d')
        
        # Get next follow-up number
        current_followup = self.get_last_followup_number(deal_id)
        next_followup = current_followup + 1
        
        # Create subject
        subject = f"Follow Up {next_followup}"
        
        # Create summary note
        deal_details = self.pd.get_deal_details(deal_id) or deal
        note = self.create_deal_summary(deal_details)
        
        # Create the activity
        activity = self.pd.create_activity(
            deal_id=deal_id,
            subject=subject,
            activity_type='email',
            due_date=followup_date_str,
            note=note
        )
        
        if activity:
            result['action'] = 'created'
            result['success'] = True
            result['followup_number'] = next_followup
            result['followup_date'] = followup_date_str
            result['activity_id'] = activity.get('id')
            result['message'] = f'Created {subject} for {followup_date_str}'
            
            # Update tracker
            upsert_followup(
                deal_id=deal_id,
                deal_title=deal_title,
                followup_number=next_followup,
                followup_date=followup_date_str,
                activity_id=activity.get('id'),
                status='created'
            )
            
            log_activity(
                action='create_followup',
                deal_id=deal_id,
                deal_title=deal_title,
                followup_number=next_followup,
                status='success',
                message=result['message']
            )
        else:
            result['action'] = 'error'
            result['message'] = 'Failed to create activity'
            
            log_activity(
                action='create_followup',
                deal_id=deal_id,
                deal_title=deal_title,
                status='error',
                message=result['message']
            )
        
        return result
    
    def scan_and_create_followups(self) -> Dict:
        """Scan all deals in target stage and create follow-ups"""
        global _last_scan_time, _last_scan_result
        
        logger.info("Starting follow-up scan...")
        _last_scan_time = datetime.now().isoformat()
        
        summary = {
            'timestamp': _last_scan_time,
            'deals_scanned': 0,
            'followups_created': 0,
            'skipped': 0,
            'errors': 0,
            'results': []
        }
        
        if not self.initialize():
            summary['error'] = 'Failed to initialize Pipedrive connection'
            return summary
        
        deals = self.pd.get_deals_in_stage()
        summary['deals_scanned'] = len(deals)
        
        logger.info(f"Found {len(deals)} deals in '{TARGET_STAGE}' stage")
        
        for deal in deals:
            result = self.process_deal(deal)
            summary['results'].append(result)
            
            if result['action'] == 'created':
                summary['followups_created'] += 1
            elif result['action'] == 'skipped':
                summary['skipped'] += 1
            elif result['action'] == 'error':
                summary['errors'] += 1
        
        log_activity(
            action='scan_complete',
            status='success',
            message=f"Scanned {summary['deals_scanned']} deals, created {summary['followups_created']} follow-ups"
        )
        
        _last_scan_result = summary
        logger.info(f"Scan complete: {summary['followups_created']} created, {summary['skipped']} skipped, {summary['errors']} errors")
        
        return summary


# =============================================================================
# BACKGROUND SCANNER
# =============================================================================

def scanner_loop():
    """Background scanner loop"""
    global _scanner_running
    
    logger.info("Follow-up scanner started")
    service = FollowUpService()
    
    while _scanner_running:
        try:
            if get_setting('auto_scan_enabled', 'false').lower() != 'true':
                time.sleep(10)
                continue
            
            interval_minutes = int(get_setting('scan_interval_minutes', '60'))
            
            service.scan_and_create_followups()
            
            # Sleep for interval
            remaining = interval_minutes * 60
            while remaining > 0 and _scanner_running:
                time.sleep(min(10, remaining))
                remaining -= 10
                
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            time.sleep(60)
    
    logger.info("Scanner stopped")


def start_scanner():
    global _scanner_thread, _scanner_running
    if _scanner_running:
        return
    _scanner_running = True
    _scanner_thread = threading.Thread(target=scanner_loop, daemon=True)
    _scanner_thread.start()
    logger.info("Scanner thread started")


def stop_scanner():
    global _scanner_running
    _scanner_running = False


# =============================================================================
# HTML TEMPLATES
# =============================================================================

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Follow-Up Creator - All Painting Ltd.</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <style>
        .status-badge { padding: 2px 8px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
        .status-created { background: #dcfce7; color: #166534; }
        .status-skipped { background: #fef3c7; color: #92400e; }
        .status-error { background: #fee2e2; color: #991b1b; }
        .status-pending { background: #e0e7ff; color: #3730a3; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-gradient-to-r from-purple-900 to-purple-800 text-white shadow-lg">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex justify-between items-center">
                <div>
                    <h1 class="text-2xl font-bold">📨 Follow-Up Creator</h1>
                    <p class="text-purple-200 text-sm">All Painting Ltd. - Automated Follow-Up Activities</p>
                </div>
                <div class="flex gap-4">
                    <a href="http://localhost:3030" class="px-4 py-2 rounded hover:bg-purple-700">← Bid Center</a>
                </div>
            </div>
        </div>
    </nav>

    <main class="max-w-7xl mx-auto px-4 py-8">
        <!-- Status Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-gray-500 text-sm">Connection</h3>
                <p class="text-xl font-bold" id="connection-status">Checking...</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-gray-500 text-sm">Auto-Scan</h3>
                <p class="text-xl font-bold" id="auto-scan-status">-</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-gray-500 text-sm">Last Scan</h3>
                <p class="text-xl font-bold" id="last-scan">Never</p>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <h3 class="text-gray-500 text-sm">Total Follow-Ups Created</h3>
                <p class="text-xl font-bold text-purple-600" id="total-followups">-</p>
            </div>
        </div>

        <!-- Controls -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4">Controls</h2>
            <div class="flex flex-wrap gap-4 items-center">
                <button onclick="runScan()" class="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700">
                    🔍 Scan Now
                </button>
                <div class="flex items-center gap-2">
                    <label class="text-sm text-gray-600">Auto-Scan:</label>
                    <input type="checkbox" id="auto-scan-toggle" onchange="toggleAutoScan()" class="w-5 h-5">
                </div>
                <div class="flex items-center gap-2">
                    <label class="text-sm text-gray-600">Interval:</label>
                    <select id="interval-select" onchange="updateInterval()" class="border rounded px-3 py-1">
                        <option value="30">30 min</option>
                        <option value="60">1 hour</option>
                        <option value="120">2 hours</option>
                        <option value="240">4 hours</option>
                    </select>
                </div>
                <div class="flex items-center gap-2">
                    <label class="text-sm text-gray-600">Follow-up Days:</label>
                    <input type="number" id="followup-days" value="20" min="1" max="90" 
                           class="border rounded px-3 py-1 w-20" onchange="updateFollowupDays()">
                </div>
            </div>
        </div>

        <!-- Follow-Up Tracker Table -->
        <div class="bg-white rounded-lg shadow p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4">Follow-Up Tracker</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-3 text-left">Deal</th>
                            <th class="px-4 py-3 text-left">Follow-Up #</th>
                            <th class="px-4 py-3 text-left">Follow-Up Date</th>
                            <th class="px-4 py-3 text-left">Status</th>
                            <th class="px-4 py-3 text-left">Last Updated</th>
                        </tr>
                    </thead>
                    <tbody id="tracker-table">
                        <tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Activity Log -->
        <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-xl font-semibold mb-4">Activity Log</h2>
            <div class="overflow-x-auto max-h-96 overflow-y-auto">
                <table class="w-full text-sm">
                    <thead class="bg-gray-50 sticky top-0">
                        <tr>
                            <th class="px-4 py-3 text-left">Time</th>
                            <th class="px-4 py-3 text-left">Action</th>
                            <th class="px-4 py-3 text-left">Deal</th>
                            <th class="px-4 py-3 text-left">Follow-Up #</th>
                            <th class="px-4 py-3 text-left">Message</th>
                        </tr>
                    </thead>
                    <tbody id="activity-log">
                        <tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </main>

    <script>
        const API_BASE = '';
        
        async function loadStatus() {
            try {
                const resp = await fetch(`${API_BASE}/api/status`);
                const data = await resp.json();
                
                document.getElementById('connection-status').textContent = 
                    data.pipedrive_connected ? '✅ Connected' : '❌ Not Connected';
                document.getElementById('connection-status').className = 
                    `text-xl font-bold ${data.pipedrive_connected ? 'text-green-600' : 'text-red-600'}`;
                
                document.getElementById('auto-scan-status').textContent = 
                    data.auto_scan_enabled ? '✅ Enabled' : '⏸️ Disabled';
                document.getElementById('auto-scan-toggle').checked = data.auto_scan_enabled;
                
                document.getElementById('last-scan').textContent = 
                    data.last_scan_time ? new Date(data.last_scan_time).toLocaleString() : 'Never';
                
                document.getElementById('total-followups').textContent = data.total_followups || '0';
                
                document.getElementById('interval-select').value = data.scan_interval_minutes || '60';
                document.getElementById('followup-days').value = data.followup_days || '20';
            } catch (e) {
                console.error('Failed to load status:', e);
            }
        }
        
        async function loadTracker() {
            try {
                const resp = await fetch(`${API_BASE}/api/tracker`);
                const data = await resp.json();
                
                const tbody = document.getElementById('tracker-table');
                if (!data.tracker || data.tracker.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">No follow-ups tracked yet</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.tracker.map(row => `
                    <tr class="border-t hover:bg-gray-50">
                        <td class="px-4 py-3">
                            <a href="https://allpainting.pipedrive.com/deal/${row.deal_id}" 
                               target="_blank" class="text-purple-600 hover:underline">
                                ${escapeHtml(row.deal_title || 'Unknown')}
                            </a>
                        </td>
                        <td class="px-4 py-3 font-semibold text-purple-700">Follow Up ${row.followup_number}</td>
                        <td class="px-4 py-3">${row.last_followup_date || '-'}</td>
                        <td class="px-4 py-3">
                            <span class="status-badge status-${row.status}">${row.status}</span>
                        </td>
                        <td class="px-4 py-3 text-gray-500">${formatDate(row.updated_at)}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Failed to load tracker:', e);
            }
        }
        
        async function loadActivityLog() {
            try {
                const resp = await fetch(`${API_BASE}/api/activity-log`);
                const data = await resp.json();
                
                const tbody = document.getElementById('activity-log');
                if (!data.log || data.log.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">No activity yet</td></tr>';
                    return;
                }
                
                tbody.innerHTML = data.log.map(row => `
                    <tr class="border-t hover:bg-gray-50">
                        <td class="px-4 py-3 text-gray-500">${formatDate(row.timestamp)}</td>
                        <td class="px-4 py-3">${row.action}</td>
                        <td class="px-4 py-3">${escapeHtml(row.deal_title || '-')}</td>
                        <td class="px-4 py-3">${row.followup_number ? `Follow Up ${row.followup_number}` : '-'}</td>
                        <td class="px-4 py-3 text-gray-600">${escapeHtml(row.message || '')}</td>
                    </tr>
                `).join('');
            } catch (e) {
                console.error('Failed to load activity log:', e);
            }
        }
        
        async function runScan() {
            try {
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = '⏳ Scanning...';
                
                const resp = await fetch(`${API_BASE}/api/scan`, { method: 'POST' });
                const data = await resp.json();
                
                alert(`Scan complete!\\n\\nDeals scanned: ${data.deals_scanned}\\nFollow-ups created: ${data.followups_created}\\nSkipped: ${data.skipped}\\nErrors: ${data.errors}`);
                
                loadStatus();
                loadTracker();
                loadActivityLog();
            } catch (e) {
                alert('Scan failed: ' + e.message);
            } finally {
                event.target.disabled = false;
                event.target.textContent = '🔍 Scan Now';
            }
        }
        
        async function toggleAutoScan() {
            const enabled = document.getElementById('auto-scan-toggle').checked;
            await fetch(`${API_BASE}/api/settings/auto-scan`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            loadStatus();
        }
        
        async function updateInterval() {
            const interval = document.getElementById('interval-select').value;
            await fetch(`${API_BASE}/api/settings/interval`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ interval: parseInt(interval) })
            });
        }
        
        async function updateFollowupDays() {
            const days = document.getElementById('followup-days').value;
            await fetch(`${API_BASE}/api/settings/followup-days`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ days: parseInt(days) })
            });
        }
        
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function formatDate(dateStr) {
            if (!dateStr) return '-';
            return new Date(dateStr).toLocaleString();
        }
        
        // Initial load
        loadStatus();
        loadTracker();
        loadActivityLog();
        
        // Refresh every 30 seconds
        setInterval(() => {
            loadStatus();
            loadTracker();
            loadActivityLog();
        }, 30000);
    </script>
</body>
</html>
'''


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/status')
def api_status():
    pd = PipedriveClient()
    connection = pd.test_connection()
    
    # Count total follow-ups created
    tracker = get_followup_tracker()
    total_followups = sum(1 for t in tracker if t.get('status') == 'created')
    
    return jsonify({
        'service': APP_NAME,
        'version': APP_VERSION,
        'pipedrive_connected': connection.get('success', False),
        'auto_scan_enabled': get_setting('auto_scan_enabled', 'false').lower() == 'true',
        'scanner_running': _scanner_running,
        'scan_interval_minutes': get_setting('scan_interval_minutes', '60'),
        'followup_days': get_setting('followup_days', str(FOLLOWUP_DAYS)),
        'last_scan_time': _last_scan_time,
        'total_followups': total_followups
    })


@app.route('/api/test-connection')
def api_test_connection():
    pd = PipedriveClient()
    return jsonify(pd.test_connection())


@app.route('/api/tracker')
def api_tracker():
    return jsonify({
        'success': True,
        'tracker': get_followup_tracker()
    })


@app.route('/api/activity-log')
def api_activity_log():
    limit = request.args.get('limit', 100, type=int)
    return jsonify({
        'success': True,
        'log': get_activity_log(limit)
    })


@app.route('/api/scan', methods=['POST'])
def api_scan():
    service = FollowUpService()
    result = service.scan_and_create_followups()
    return jsonify(result)


@app.route('/api/settings/auto-scan', methods=['GET', 'POST'])
def api_auto_scan():
    if request.method == 'GET':
        return jsonify({
            'enabled': get_setting('auto_scan_enabled', 'false').lower() == 'true',
            'scanner_running': _scanner_running
        })
    
    data = request.get_json() or {}
    if 'enabled' in data:
        enabled = data['enabled']
        set_setting('auto_scan_enabled', 'true' if enabled else 'false')
        
        if enabled:
            start_scanner()
        else:
            stop_scanner()
    
    return jsonify({
        'success': True,
        'enabled': get_setting('auto_scan_enabled', 'false').lower() == 'true',
        'scanner_running': _scanner_running
    })


@app.route('/api/settings/interval', methods=['POST'])
def api_interval():
    data = request.get_json() or {}
    if 'interval' in data:
        set_setting('scan_interval_minutes', str(data['interval']))
    return jsonify({'success': True})


@app.route('/api/settings/followup-days', methods=['POST'])
def api_followup_days():
    data = request.get_json() or {}
    if 'days' in data:
        set_setting('followup_days', str(data['days']))
    return jsonify({'success': True})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    init_database()
    
    # Start scanner if auto-scan is enabled
    if get_setting('auto_scan_enabled', 'false').lower() == 'true':
        start_scanner()
    
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
