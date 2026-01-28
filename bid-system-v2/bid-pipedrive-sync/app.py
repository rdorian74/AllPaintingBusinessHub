"""
Bid Pipedrive Sync - All Painting Ltd. | Port: 3032
v2.1.0 - IMPROVED DUPLICATE DETECTION:
- Pre-check with exact/fuzzy string matching BEFORE AI
- Track pipedrive_deal_id in bid_tracker for visual status
- "Already Exists" status shown in dashboard when duplicate found
"""

import os, json, sqlite3, logging, requests, time, threading, re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import Flask, jsonify, request
from difflib import SequenceMatcher

# =============================================================================
# CONFIGURATION
# =============================================================================
PORT = 3032
APP_NAME = "Bid Pipedrive Sync"
APP_VERSION = "2.1.0"

BID_TRACKER_DB = os.environ.get('BID_TRACKER_DB_PATH',
    os.path.join(os.path.dirname(__file__), "..", "bid-email-scanner", "bid_tracker.db"))
LOCAL_DB = os.path.join(os.path.dirname(__file__), "pipedrive_sync.db")

PIPEDRIVE_API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
PIPEDRIVE_DOMAIN = os.environ.get("PIPEDRIVE_DOMAIN", "allpainting")
PIPEDRIVE_PIPELINE_NAME = "Pipeline"
PIPEDRIVE_STAGE_NAME = "Quote Requested"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

DUPLICATE_THRESHOLD = 75
FUZZY_MATCH_THRESHOLD = 0.85

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
_scheduler_running = False
_scheduler_thread = None

# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================
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
    cursor.execute('''CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bid_tracker_id INTEGER, pipedrive_deal_id INTEGER,
        action TEXT, status TEXT, message TEXT, duplicate_info TEXT,
        synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    for key, value in {'auto_sync_enabled': 'false', 'sync_interval': '900'}.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()
    ensure_bid_tracker_columns()
    logger.info("Database initialized")

def ensure_bid_tracker_columns():
    """Add pipedrive tracking columns to bid_tracker if they don't exist"""
    conn = get_bid_tracker_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(bid_tracker)")
    existing_cols = {row['name'] for row in cursor.fetchall()}
    for col_name, col_type in [('pipedrive_deal_id', 'INTEGER'), ('pipedrive_status', 'TEXT'),
                                ('pipedrive_synced_at', 'TIMESTAMP'), ('pipedrive_match_info', 'TEXT')]:
        if col_name not in existing_cols:
            try:
                cursor.execute(f'ALTER TABLE bid_tracker ADD COLUMN {col_name} {col_type}')
                logger.info(f"Added column {col_name}")
            except: pass
    conn.commit()
    conn.close()

def update_bid_pipedrive_status(bid_id: int, deal_id: int = None, status: str = 'pending', match_info: dict = None):
    conn = get_bid_tracker_connection()
    if not conn: return
    cursor = conn.cursor()
    cursor.execute('''UPDATE bid_tracker SET pipedrive_deal_id = ?, pipedrive_status = ?, 
        pipedrive_synced_at = ?, pipedrive_match_info = ? WHERE id = ?''',
        (deal_id, status, datetime.now().isoformat() if status != 'pending' else None,
         json.dumps(match_info) if match_info else None, bid_id))
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = None) -> Optional[str]:
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

def is_auto_sync_enabled() -> bool:
    return get_setting('auto_sync_enabled', 'false').lower() == 'true'

def get_sync_interval() -> int:
    return int(get_setting('sync_interval', '900'))

def get_all_bids() -> List[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_bid_by_id(bid_id: int) -> Optional[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return None
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bid_tracker WHERE id = ?', (bid_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_synced_bid_ids() -> List[int]:
    conn = get_bid_tracker_connection()
    if not conn:
        conn = get_local_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT bid_tracker_id FROM sync_log WHERE status = "success"')
        rows = cursor.fetchall()
        conn.close()
        return [row['bid_tracker_id'] for row in rows]
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM bid_tracker WHERE pipedrive_status IN ("synced", "duplicate")')
    rows = cursor.fetchall()
    conn.close()
    return [row['id'] for row in rows]

def get_unsynced_bids() -> List[Dict]:
    conn = get_bid_tracker_connection()
    if not conn: return []
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM bid_tracker WHERE pipedrive_status IS NULL 
        OR pipedrive_status = 'pending' OR pipedrive_status = 'error' ORDER BY created_at DESC''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def log_sync(bid_tracker_id: int, pipedrive_deal_id: int, action: str, status: str, message: str, duplicate_info: dict = None):
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO sync_log (bid_tracker_id, pipedrive_deal_id, action, status, message, duplicate_info)
        VALUES (?, ?, ?, ?, ?, ?)''', (bid_tracker_id, pipedrive_deal_id, action, status, message,
        json.dumps(duplicate_info) if duplicate_info else None))
    conn.commit()
    conn.close()

def get_sync_log(limit: int = 100) -> List[Dict]:
    conn = get_local_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sync_log ORDER BY synced_at DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# =============================================================================
# PIPEDRIVE CLIENT
# =============================================================================
class PipedriveClient:
    def __init__(self, api_token: str = None, domain: str = None):
        self.api_token = api_token or PIPEDRIVE_API_TOKEN
        self.domain = domain or PIPEDRIVE_DOMAIN
        self.base_url_v1 = f"https://{self.domain}.pipedrive.com/api/v1"
        self._pipelines_cache = None
        self._stages_cache = {}
    
    def _request(self, endpoint: str, method: str = 'GET', data: dict = None, params: dict = None) -> Optional[Dict]:
        url = f"{self.base_url_v1}/{endpoint}"
        if params is None: params = {}
        params['api_token'] = self.api_token
        try:
            if method == 'GET': response = requests.get(url, params=params, timeout=30)
            elif method == 'POST': response = requests.post(url, params=params, json=data, headers={'Content-Type': 'application/json'}, timeout=30)
            elif method == 'PUT': response = requests.put(url, params=params, json=data, headers={'Content-Type': 'application/json'}, timeout=30)
            else: return None
            if response.status_code == 429:
                time.sleep(int(response.headers.get('Retry-After', 60)))
                return self._request(endpoint, method, data, params)
            response.raise_for_status()
            result = response.json()
            return result.get('data') if result.get('success') else None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    def get_pipelines(self, force_refresh: bool = False) -> List[Dict]:
        if self._pipelines_cache is None or force_refresh:
            self._pipelines_cache = self._request('pipelines') or []
        return self._pipelines_cache
    
    def get_pipeline_by_name(self, name: str) -> Optional[Dict]:
        for p in self.get_pipelines():
            if p.get('name', '').lower() == name.lower(): return p
        return None
    
    def get_stages(self, pipeline_id: int, force_refresh: bool = False) -> List[Dict]:
        key = str(pipeline_id)
        if key not in self._stages_cache or force_refresh:
            self._stages_cache[key] = self._request('stages', params={'pipeline_id': pipeline_id}) or []
        return self._stages_cache.get(key, [])
    
    def get_stage_by_name(self, pipeline_id: int, stage_name: str) -> Optional[Dict]:
        for s in self.get_stages(pipeline_id):
            if s.get('name', '').lower() == stage_name.lower(): return s
        return None
    
    def get_first_stage(self, pipeline_id: int) -> Optional[Dict]:
        stages = self.get_stages(pipeline_id)
        return min(stages, key=lambda s: s.get('order_nr', 999)) if stages else None
    
    def get_deals(self, pipeline_id: int = None, status: str = 'all_not_deleted', limit: int = 500) -> List[Dict]:
        params = {'status': status, 'limit': limit}
        if pipeline_id: params['pipeline_id'] = pipeline_id
        all_deals, start = [], 0
        while True:
            params['start'] = start
            result = self._request('deals', params=params)
            if not result: break
            all_deals.extend(result)
            if len(result) < limit: break
            start += limit
        return all_deals
    
    def create_deal(self, title: str, pipeline_id: int = None, stage_id: int = None,
                    person_id: int = None, org_id: int = None, expected_close_date: str = None, **extra) -> Optional[Dict]:
        data = {'title': title}
        if pipeline_id: data['pipeline_id'] = pipeline_id
        if stage_id: data['stage_id'] = stage_id
        if person_id: data['person_id'] = person_id
        if org_id: data['org_id'] = org_id
        if expected_close_date: data['expected_close_date'] = expected_close_date
        data.update(extra)
        return self._request('deals', method='POST', data=data)
    
    def add_note_to_deal(self, deal_id: int, content: str) -> Optional[Dict]:
        return self._request('notes', method='POST', data={'deal_id': deal_id, 'content': content})
    
    def search_organizations(self, term: str, limit: int = 10) -> List[Dict]:
        result = self._request('itemSearch', params={'term': term, 'item_types': 'organization', 'limit': limit})
        return [item['item'] for item in result.get('items', [])] if result else []
    
    def create_organization(self, name: str) -> Optional[Dict]:
        return self._request('organizations', method='POST', data={'name': name})
    
    def find_or_create_organization(self, name: str) -> Optional[Dict]:
        for org in self.search_organizations(name, limit=5):
            if org.get('name', '').lower() == name.lower(): return org
        return self.create_organization(name)
    
    def search_persons(self, term: str, limit: int = 10) -> List[Dict]:
        result = self._request('itemSearch', params={'term': term, 'item_types': 'person', 'limit': limit})
        return [item['item'] for item in result.get('items', [])] if result else []
    
    def create_person(self, name: str, email: str = None, org_id: int = None) -> Optional[Dict]:
        data = {'name': name}
        if email: data['email'] = [{'value': email, 'primary': True}]
        if org_id: data['org_id'] = org_id
        return self._request('persons', method='POST', data=data)
    
    def find_or_create_person(self, name: str, email: str = None, org_id: int = None) -> Optional[Dict]:
        if email:
            for person in self.search_persons(email, limit=5):
                emails = person.get('email', [])
                if isinstance(emails, list):
                    for e in emails:
                        if e.get('value', '').lower() == email.lower(): return person
        for person in self.search_persons(name, limit=5):
            if person.get('name', '').lower() == name.lower(): return person
        return self.create_person(name, email=email, org_id=org_id)
    
    def test_connection(self) -> Dict:
        result = self._request('users/me')
        if result: return {'success': True, 'user': result.get('name'), 'company': result.get('company_name')}
        return {'success': False, 'error': 'Failed to connect'}

# =============================================================================
# DUPLICATE CHECKER - Multi-tier detection
# =============================================================================
def normalize_text(text: str) -> str:
    if not text: return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    for prefix in ['nb -', 'nb-', 'new bid:', 'new bid -']:
        if text.startswith(prefix): text = text[len(prefix):].strip()
    return text

def fuzzy_match(s1: str, s2: str) -> float:
    if not s1 or not s2: return 0.0
    return SequenceMatcher(None, normalize_text(s1), normalize_text(s2)).ratio()

def extract_address_key(address: str) -> str:
    if not address: return ""
    return normalize_text(address).split(',')[0].strip()

class DuplicateChecker:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
    
    def check_for_duplicate(self, new_bid: Dict, existing_deals: List[Dict]) -> Tuple[bool, Optional[Dict], int, str]:
        """Returns: (is_duplicate, matching_deal, confidence, method)"""
        if not existing_deals: return False, None, 0, 'no_existing_deals'
        
        # TIER 1: Pre-check with string matching
        pre_match, pre_deal, pre_conf, pre_method = self._pre_check(new_bid, existing_deals)
        if pre_match and pre_conf >= 90:
            logger.info(f"Pre-check match: {pre_method} ({pre_conf}%)")
            return True, pre_deal, pre_conf, pre_method
        
        # TIER 2: AI check
        if self.api_key:
            ai_dup, ai_match, ai_conf = self._ai_check(new_bid, existing_deals)
            if ai_dup and ai_conf >= DUPLICATE_THRESHOLD:
                logger.info(f"AI match: {ai_conf}%")
                return True, ai_match, ai_conf, 'ai_match'
        
        # Medium confidence pre-check (75-89%)
        if pre_match and pre_conf >= 75:
            return True, pre_deal, pre_conf, pre_method
        
        return False, None, 0, 'no_match'
    
    def _pre_check(self, new_bid: Dict, existing_deals: List[Dict]) -> Tuple[bool, Optional[Dict], int, str]:
        project_name = normalize_text(new_bid.get('project_name', ''))
        gc_company = normalize_text(new_bid.get('gc_company', ''))
        address = extract_address_key(new_bid.get('project_address', ''))
        
        best_match, best_conf, best_method = None, 0, 'no_match'
        
        for deal in existing_deals:
            deal_title = normalize_text(deal.get('title', ''))
            deal_org = normalize_text(deal.get('org_name', ''))
            if not deal_org and isinstance(deal.get('organization'), dict):
                deal_org = normalize_text(deal['organization'].get('name', ''))
            
            # Check 1: Exact project name in title
            if project_name and len(project_name) > 5 and project_name in deal_title:
                if 95 > best_conf:
                    best_match, best_conf, best_method = deal, 95, 'exact_project_name'
                continue
            
            # Check 2: GC + similar project
            if gc_company and gc_company in deal_org:
                sim = fuzzy_match(project_name, deal_title)
                if sim > 0.7:
                    conf = min(int(85 + (sim - 0.7) * 50), 98)
                    if conf > best_conf:
                        best_match, best_conf, best_method = deal, conf, 'gc_and_project'
                    continue
            
            # Check 3: Address match
            if address and len(address) > 10 and address in deal_title:
                if 92 > best_conf:
                    best_match, best_conf, best_method = deal, 92, 'exact_address'
                continue
            
            # Check 4: Fuzzy title match
            sim = fuzzy_match(project_name, deal_title)
            if sim > FUZZY_MATCH_THRESHOLD:
                conf = int(sim * 100)
                if conf > best_conf:
                    best_match, best_conf, best_method = deal, conf, 'fuzzy_title'
        
        return (True, best_match, best_conf, best_method) if best_match else (False, None, 0, 'no_match')
    
    def _ai_check(self, new_bid: Dict, existing_deals: List[Dict]) -> Tuple[bool, Optional[Dict], int]:
        prompt = f"""Check if this bid is a DUPLICATE of existing Pipedrive deals for a painting company.

NEW BID:
- Project: {new_bid.get('project_name', 'N/A')}
- GC: {new_bid.get('gc_company', 'N/A')}
- Address: {new_bid.get('project_address', 'N/A')}
- Due: {new_bid.get('bid_due_date', 'N/A')}

EXISTING DEALS:
"""
        for i, d in enumerate(existing_deals[:50]):
            org = d.get('org_name') or (d.get('organization', {}).get('name', 'N/A') if isinstance(d.get('organization'), dict) else 'N/A')
            prompt += f"#{i+1} (ID:{d.get('id')}): {d.get('title', 'N/A')} | Org: {org}\n"
        
        prompt += """\nA duplicate = SAME PROJECT (building/address), not just same GC.
Respond JSON only: {"is_duplicate": true/false, "matching_deal_id": <id or null>, "confidence": <0-100>, "reason": "<brief>"}"""
        
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=self.api_key)
            response = client.messages.create(model=CLAUDE_MODEL, max_tokens=512, messages=[{"role": "user", "content": prompt}])
            text = response.content[0].text.strip()
            if text.startswith('```'): text = '\n'.join(text.split('\n')[1:-1])
            result = json.loads(text)
            is_dup, conf, match_id = result.get('is_duplicate', False), result.get('confidence', 0), result.get('matching_deal_id')
            match = next((d for d in existing_deals if d.get('id') == match_id), None) if match_id and is_dup else None
            logger.info(f"AI Check: dup={is_dup}, conf={conf}, reason={result.get('reason', 'N/A')}")
            return is_dup, match, conf
        except Exception as e:
            logger.error(f"AI check failed: {e}")
            return False, None, 0

# =============================================================================
# BID DEAL MAPPER
# =============================================================================
class BidDealMapper:
    @staticmethod
    def map_bid_to_deal(bid: Dict) -> Dict:
        parts = ["NB"]
        if bid.get('gc_company'): parts.append(bid['gc_company'])
        if bid.get('project_name'): parts.append(bid['project_name'])
        if bid.get('project_address'):
            addr = bid['project_address'][:50] + "..." if len(bid['project_address']) > 50 else bid['project_address']
            parts.append(addr)
        title = " - ".join(parts) if len(parts) > 1 else f"NB - {bid.get('project_name', 'Unknown')}"
        
        note_parts = []
        if bid.get('project_name'): note_parts.append(f"📋 Project: {bid['project_name']}")
        if bid.get('gc_company'): note_parts.append(f"🏢 GC: {bid['gc_company']}")
        if bid.get('project_address'): note_parts.append(f"📍 Address: {bid['project_address']}")
        if bid.get('scope_of_work'): note_parts.append(f"🎨 Scope: {bid['scope_of_work']}")
        if bid.get('gc_contact_name'): note_parts.append(f"👤 Contact: {bid['gc_contact_name']}")
        if bid.get('gc_contact_email'): note_parts.append(f"📧 Email: {bid['gc_contact_email']}")
        if bid.get('bid_due_date'):
            due = bid['bid_due_date']
            if bid.get('bid_due_time'): due += f" at {bid['bid_due_time']}"
            note_parts.append(f"⏰ Due: {due}")
        
        return {'title': title, 'expected_close_date': bid.get('bid_due_date'), 'note_content': '\n'.join(note_parts),
                'gc_company': bid.get('gc_company'), 'gc_contact_name': bid.get('gc_contact_name'), 'gc_contact_email': bid.get('gc_contact_email')}

# =============================================================================
# DEAL SYNC SERVICE
# =============================================================================
class DealSyncService:
    def __init__(self):
        self.pd = PipedriveClient()
        self.checker = DuplicateChecker()
        self._pipeline_id = None
        self._stage_id = None
        self._deals_cache = None
        self._cache_time = None
    
    def initialize(self) -> bool:
        try:
            pipeline = self.pd.get_pipeline_by_name(PIPEDRIVE_PIPELINE_NAME)
            if not pipeline:
                logger.error(f"Pipeline '{PIPEDRIVE_PIPELINE_NAME}' not found")
                return False
            self._pipeline_id = pipeline.get('id')
            stage = self.pd.get_stage_by_name(self._pipeline_id, PIPEDRIVE_STAGE_NAME)
            self._stage_id = stage.get('id') if stage else self.pd.get_first_stage(self._pipeline_id).get('id')
            logger.info(f"Initialized: pipeline={self._pipeline_id}, stage={self._stage_id}")
            return True
        except Exception as e:
            logger.error(f"Init failed: {e}")
            return False
    
    def get_existing_deals(self, force_refresh: bool = False) -> List[Dict]:
        now = time.time()
        if not force_refresh and self._deals_cache and self._cache_time and (now - self._cache_time < 300):
            return self._deals_cache
        self._deals_cache = self.pd.get_deals(pipeline_id=self._pipeline_id) if self._pipeline_id else []
        self._cache_time = now
        return self._deals_cache
    
    def sync_bid(self, bid: Dict) -> Dict:
        if not self._pipeline_id:
            return {'success': False, 'action': 'error', 'deal_id': None, 'message': 'Not initialized'}
        
        bid_id = bid.get('id')
        
        # CHECK IF ALREADY PROCESSED - Don't sync again!
        current_status = bid.get('pipedrive_status')
        if current_status == 'synced':
            logger.info(f"Skipping {bid.get('project_name')} - already synced (deal {bid.get('pipedrive_deal_id')})")
            return {'success': True, 'action': 'skipped', 'deal_id': bid.get('pipedrive_deal_id'), 
                    'message': 'Already synced to Pipedrive'}
        if current_status == 'duplicate':
            logger.info(f"Skipping {bid.get('project_name')} - already marked as duplicate (deal {bid.get('pipedrive_deal_id')})")
            return {'success': True, 'action': 'skipped', 'deal_id': bid.get('pipedrive_deal_id'),
                    'message': 'Already exists in Pipedrive (duplicate)'}
        
        try:
            existing = self.get_existing_deals(force_refresh=True)
            logger.info(f"Syncing: {bid.get('project_name')} | {len(existing)} existing deals")
            
            is_dup, match, conf, method = self.checker.check_for_duplicate(bid, existing)
            
            if is_dup and conf >= DUPLICATE_THRESHOLD:
                logger.info(f"DUPLICATE via {method} ({conf}%) - {match.get('title')}")
                deal_data = BidDealMapper.map_bid_to_deal(bid)
                note = f"🔄 **Duplicate Detected** ({method}, {conf}%)\n\nNew email received {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{deal_data.get('note_content', '')}"
                self.pd.add_note_to_deal(match['id'], note)
                update_bid_pipedrive_status(bid_id, match.get('id'), 'duplicate', {'method': method, 'confidence': conf, 'deal_title': match.get('title')})
                return {'success': True, 'action': 'duplicate', 'deal_id': match['id'],
                        'message': f"Already exists in Pipedrive ({method}, {conf}%)", 'duplicate_info': {'title': match.get('title'), 'confidence': conf}}
            
            # Create new
            logger.info("No duplicate - creating new deal")
            result = self._create_new(bid)
            if result['success']:
                update_bid_pipedrive_status(bid_id, result.get('deal_id'), 'synced')
            else:
                update_bid_pipedrive_status(bid_id, None, 'error', {'message': result.get('message')})
            return result
        except Exception as e:
            logger.error(f"Sync error: {e}")
            update_bid_pipedrive_status(bid_id, None, 'error', {'message': str(e)})
            return {'success': False, 'action': 'error', 'deal_id': None, 'message': str(e)}
    
    def _create_new(self, bid: Dict) -> Dict:
        deal_data = BidDealMapper.map_bid_to_deal(bid)
        org_id = None
        if deal_data.get('gc_company'):
            org = self.pd.find_or_create_organization(deal_data['gc_company'])
            if org: org_id = org.get('id')
        person_id = None
        if deal_data.get('gc_contact_name') or deal_data.get('gc_contact_email'):
            person = self.pd.find_or_create_person(deal_data.get('gc_contact_name', 'Unknown'), deal_data.get('gc_contact_email'), org_id)
            if person: person_id = person.get('id')
        new_deal = self.pd.create_deal(title=deal_data['title'], pipeline_id=self._pipeline_id, stage_id=self._stage_id,
                                       person_id=person_id, org_id=org_id, expected_close_date=deal_data.get('expected_close_date'))
        if new_deal:
            if deal_data.get('note_content'):
                self.pd.add_note_to_deal(new_deal['id'], f"📋 **Bid Details**\n\n{deal_data['note_content']}")
            logger.info(f"Created deal {new_deal['id']}: {deal_data['title']}")
            self._deals_cache = None
            return {'success': True, 'action': 'created', 'deal_id': new_deal['id'], 'message': f"Created: {deal_data['title']}"}
        return {'success': False, 'action': 'error', 'deal_id': None, 'message': 'Failed to create deal'}
    
    def batch_sync(self, bids: List[Dict]) -> Dict:
        summary = {'total': len(bids), 'created': 0, 'duplicates': 0, 'skipped': 0, 'errors': 0, 'results': []}
        for bid in bids:
            result = self.sync_bid(bid)
            summary['results'].append({'bid_id': bid.get('id'), 'project_name': bid.get('project_name'), **result})
            if result['success']:
                if result['action'] == 'created': summary['created'] += 1
                elif result['action'] == 'duplicate': summary['duplicates'] += 1
                elif result['action'] == 'skipped': summary['skipped'] += 1
            else: summary['errors'] += 1
        return summary

_sync_service = None
def get_sync_service() -> DealSyncService:
    global _sync_service
    if _sync_service is None:
        _sync_service = DealSyncService()
        _sync_service.initialize()
    return _sync_service

# =============================================================================
# SCHEDULER
# =============================================================================
def scheduler_loop():
    global _scheduler_running
    logger.info("Auto-sync scheduler started")
    service = DealSyncService()
    if not service.initialize():
        _scheduler_running = False
        return
    while _scheduler_running:
        try:
            if not is_auto_sync_enabled(): break
            interval = get_sync_interval()
            unsynced = get_unsynced_bids()
            if unsynced:
                logger.info(f"Auto-sync: {len(unsynced)} unsynced")
                summary = service.batch_sync(unsynced)
                for r in summary['results']:
                    log_sync(r.get('bid_id'), r.get('deal_id'), r.get('action'), 'success' if r.get('success') else 'error', f"[AUTO] {r.get('message', '')}")
                logger.info(f"Auto-sync: {summary['created']} created, {summary['duplicates']} duplicates")
            set_setting('last_auto_sync_check', datetime.now().isoformat())
            remaining = interval
            while remaining > 0 and _scheduler_running:
                time.sleep(min(10, remaining))
                remaining -= 10
        except Exception as e:
            logger.error(f"Auto-sync error: {e}")
            time.sleep(60)
    logger.info("Scheduler stopped")

def start_scheduler():
    global _scheduler_thread, _scheduler_running
    if _scheduler_running: return
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    _scheduler_thread.start()

def stop_scheduler():
    global _scheduler_running
    _scheduler_running = False

# =============================================================================
# API ROUTES
# =============================================================================
@app.route('/')
def index():
    return jsonify({"service": APP_NAME, "version": APP_VERSION, "port": PORT})

@app.route('/api/status')
def api_status():
    return jsonify({"service": APP_NAME, "version": APP_VERSION, "pipedrive_configured": bool(PIPEDRIVE_API_TOKEN),
        "ai_configured": bool(ANTHROPIC_API_KEY), "total_bids": len(get_all_bids()), "synced_count": len(get_synced_bid_ids()),
        "pending_count": len(get_unsynced_bids()), "auto_sync_enabled": is_auto_sync_enabled(),
        "scheduler_running": _scheduler_running, "sync_interval": get_sync_interval()})

@app.route('/api/test-connection')
def api_test_connection():
    return jsonify(PipedriveClient().test_connection())

@app.route('/api/debug-deals')
def api_debug_deals():
    try:
        service = DealSyncService()
        if not service.initialize():
            return jsonify({"success": False, "error": "Failed to initialize"})
        existing = service.get_existing_deals(force_refresh=True)
        return jsonify({"success": True, "pipeline_id": service._pipeline_id, "stage_id": service._stage_id,
            "existing_deals_count": len(existing), "deals_sample": [{"id": d.get("id"), "title": d.get("title", "")[:60]} for d in existing[:20]]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/check-duplicate/<int:bid_id>')
def api_check_duplicate(bid_id):
    bid = get_bid_by_id(bid_id)
    if not bid: return jsonify({"success": False, "error": "Bid not found"}), 404
    try:
        service = get_sync_service()
        existing = service.get_existing_deals(force_refresh=True)
        is_dup, match, conf, method = service.checker.check_for_duplicate(bid, existing)
        return jsonify({"success": True, "bid_id": bid_id, "project_name": bid.get('project_name'),
            "is_duplicate": is_dup, "confidence": conf, "method": method,
            "matching_deal": {"id": match.get('id'), "title": match.get('title')} if match else None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sync', methods=['POST'])
def api_sync():
    try:
        service = get_sync_service()
        unsynced = get_unsynced_bids()
        if not unsynced:
            return jsonify({'success': True, 'message': 'No bids to sync', 'summary': {'total': 0, 'created': 0, 'duplicates': 0, 'errors': 0}})
        summary = service.batch_sync(unsynced)
        for r in summary['results']:
            log_sync(r.get('bid_id'), r.get('deal_id'), r.get('action'), 'success' if r.get('success') else 'error', f"[MANUAL] {r.get('message', '')}")
        return jsonify({'success': True, 'summary': summary})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sync/<int:bid_id>', methods=['POST'])
def api_sync_single(bid_id):
    bid = get_bid_by_id(bid_id)
    if not bid: return jsonify({"success": False, "error": "Bid not found"}), 404
    result = get_sync_service().sync_bid(bid)
    log_sync(bid_id, result.get('deal_id'), result.get('action'), 'success' if result.get('success') else 'error', result.get('message'))
    return jsonify(result)

@app.route('/api/unsynced')
def api_unsynced():
    return jsonify({"success": True, "bids": get_unsynced_bids()})

@app.route('/api/log')
def api_log():
    return jsonify({"success": True, "log": get_sync_log(request.args.get('limit', 100, type=int))})

@app.route('/api/settings/auto-sync', methods=['GET', 'POST'])
def api_auto_sync():
    if request.method == 'GET':
        return jsonify({'enabled': is_auto_sync_enabled(), 'interval': get_sync_interval(), 'scheduler_running': _scheduler_running})
    data = request.get_json() or {}
    if 'enabled' in data:
        set_setting('auto_sync_enabled', 'true' if data['enabled'] else 'false')
        if data['enabled']: start_scheduler()
        else: stop_scheduler()
    if 'interval' in data:
        set_setting('sync_interval', str(data['interval']))
    return jsonify({'success': True, 'enabled': is_auto_sync_enabled(), 'scheduler_running': _scheduler_running})

@app.route('/api/bids/status')
def api_bids_status():
    """Get all bids with their Pipedrive sync status for dashboard"""
    bids = get_all_bids()
    return jsonify({"success": True, "bids": [{
        "id": b.get('id'), "project_name": b.get('project_name'), "gc_company": b.get('gc_company'),
        "pipedrive_status": b.get('pipedrive_status', 'pending'), "pipedrive_deal_id": b.get('pipedrive_deal_id'),
        "pipedrive_match_info": json.loads(b['pipedrive_match_info']) if b.get('pipedrive_match_info') else None
    } for b in bids]})

@app.route('/api/reset-status/<int:bid_id>', methods=['POST'])
def api_reset_status(bid_id):
    """Reset a bid's sync status to allow re-syncing"""
    update_bid_pipedrive_status(bid_id, None, 'pending', None)
    return jsonify({"success": True, "message": "Status reset to pending"})

if __name__ == '__main__':
    init_database()
    if PIPEDRIVE_API_TOKEN: get_sync_service()
    if is_auto_sync_enabled(): start_scheduler()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=True)
