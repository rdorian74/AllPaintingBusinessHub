"""
Bid Center - All Painting Ltd.
Port: 3030

PURPOSE: Central dashboard for managing bids across all microservices.
Provides a unified UI to monitor email scanning, Pipedrive sync, calendar events, and notifications.

This is the ONLY service with a web UI - all others are API-only.
"""

import os
import logging
import requests
from datetime import datetime
from flask import Flask, render_template, jsonify, request

PORT = 3030
APP_NAME = "Bid Center"
APP_VERSION = "2.0.0"

# Microservice endpoints
SERVICES = {
    'email_scanner': 'http://localhost:3031',
    'pipedrive_sync': 'http://localhost:3032',
    'calendar': 'http://localhost:3033',
    'notifications': 'http://localhost:3034',
    'quote_sent_mover': 'http://localhost:3035',
    'followup_creator': 'http://localhost:3036'
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)


def call_service(service: str, endpoint: str, method: str = 'GET', data: dict = None, timeout: int = None) -> dict:
    """Call a microservice endpoint"""
    base_url = SERVICES.get(service)
    if not base_url:
        return {"error": f"Unknown service: {service}"}
    
    url = f"{base_url}{endpoint}"
    
    # Use longer timeout for scan operations
    if timeout is None:
        timeout = 300 if '/scan' in endpoint else 30
    
    try:
        if method == 'GET':
            response = requests.get(url, timeout=timeout)
        elif method == 'POST':
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, json=data if data else {}, headers=headers, timeout=timeout)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        return response.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Service {service} not available", "offline": True}
    except requests.exceptions.Timeout:
        return {"error": f"Service {service} timed out after {timeout}s", "timeout": True}
    except Exception as e:
        return {"error": str(e)}


def check_service_health(service: str) -> dict:
    """Check if a service is running"""
    result = call_service(service, '/api/status')
    return {
        "name": service,
        "online": 'error' not in result or 'offline' not in result,
        "status": result
    }


# =============================================================================
# WEB ROUTES
# =============================================================================

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')


@app.route('/bids')
def bids_page():
    """Bids management page"""
    return render_template('bids.html')


@app.route('/sync')
def sync_page():
    """Pipedrive sync page"""
    return render_template('sync.html')


@app.route('/calendar')
def calendar_page():
    """Calendar events page"""
    return render_template('calendar.html')


@app.route('/notifications')
def notifications_page():
    """Notifications settings page"""
    return render_template('notifications.html')


@app.route('/quote-sent')
def quote_sent_page():
    """Quote Sent Mover page"""
    return render_template('quote-sent.html')


# =============================================================================
# API ROUTES - Dashboard
# =============================================================================

@app.route('/api/status')
def api_status():
    """Get status of all services"""
    services_status = {}
    for service in SERVICES.keys():
        services_status[service] = check_service_health(service)
    
    return jsonify({
        "dashboard": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
        "services": services_status
    })


@app.route('/api/health')
def api_health():
    """Quick health check"""
    return jsonify({"status": "ok", "service": APP_NAME, "version": APP_VERSION})


# =============================================================================
# API ROUTES - Proxy to Email Scanner
# =============================================================================

@app.route('/api/bids')
def api_get_bids():
    return jsonify(call_service('email_scanner', '/api/bids'))


@app.route('/api/bids/<int:bid_id>')
def api_get_bid(bid_id):
    return jsonify(call_service('email_scanner', f'/api/bids/{bid_id}'))


@app.route('/api/bids/<int:bid_id>', methods=['DELETE'])
def api_delete_bid(bid_id):
    return jsonify(call_service('email_scanner', f'/api/bids/{bid_id}', method='POST'))


@app.route('/api/scan', methods=['POST'])
def api_scan():
    data = request.get_json() or {}
    return jsonify(call_service('email_scanner', '/api/scan', method='POST', data=data))


@app.route('/api/scan/preview', methods=['POST'])
def api_scan_preview():
    data = request.get_json() or {}
    return jsonify(call_service('email_scanner', '/api/preview', method='POST', data=data))


@app.route('/api/scanner/status')
def api_scanner_status():
    return jsonify(call_service('email_scanner', '/api/status'))


@app.route('/api/scanner/settings', methods=['GET', 'POST'])
def api_scanner_settings():
    if request.method == 'GET':
        return jsonify(call_service('email_scanner', '/api/settings'))
    return jsonify(call_service('email_scanner', '/api/settings', method='POST', data=request.get_json()))


@app.route('/api/scanner/rescan-bid/<int:bid_id>', methods=['POST'])
def api_rescan_bid(bid_id):
    return jsonify(call_service('email_scanner', f'/api/rescan-bid/{bid_id}', method='POST'))


# =============================================================================
# API ROUTES - Proxy to Pipedrive Sync
# =============================================================================

@app.route('/api/sync', methods=['POST'])
def api_sync():
    return jsonify(call_service('pipedrive_sync', '/api/sync', method='POST'))


@app.route('/api/sync/<int:bid_id>', methods=['POST'])
def api_sync_single(bid_id):
    return jsonify(call_service('pipedrive_sync', f'/api/sync/{bid_id}', method='POST'))


@app.route('/api/sync/status')
def api_sync_status():
    return jsonify(call_service('pipedrive_sync', '/api/status'))


@app.route('/api/sync/unsynced')
def api_unsynced():
    return jsonify(call_service('pipedrive_sync', '/api/unsynced'))


@app.route('/api/sync/log')
def api_sync_log():
    return jsonify(call_service('pipedrive_sync', '/api/log'))


@app.route('/api/sync/settings', methods=['GET', 'POST'])
def api_sync_settings():
    if request.method == 'GET':
        return jsonify(call_service('pipedrive_sync', '/api/settings/auto-sync'))
    return jsonify(call_service('pipedrive_sync', '/api/settings/auto-sync', method='POST', data=request.get_json()))


@app.route('/api/pipedrive/test')
def api_pipedrive_test():
    return jsonify(call_service('pipedrive_sync', '/api/test-connection'))


@app.route('/api/pipedrive/deals')
def api_pipedrive_deals():
    return jsonify(call_service('pipedrive_sync', '/api/deals'))


@app.route('/api/sync/reset/<int:bid_id>', methods=['POST'])
def api_reset_sync_status(bid_id):
    """Reset a bid's sync status to allow re-syncing"""
    return jsonify(call_service('pipedrive_sync', f'/api/reset-status/{bid_id}', method='POST'))


# =============================================================================
# API ROUTES - Proxy to Calendar
# =============================================================================

@app.route('/api/calendar/create/<int:bid_id>', methods=['POST'])
def api_create_calendar(bid_id):
    data = request.get_json() or {}
    return jsonify(call_service('calendar', f'/api/create/{bid_id}', method='POST', data=data))


@app.route('/api/calendar/status/<int:bid_id>')
def api_calendar_status(bid_id):
    return jsonify(call_service('calendar', f'/api/status/{bid_id}'))


@app.route('/api/calendar/settings', methods=['GET', 'POST'])
def api_calendar_settings():
    if request.method == 'GET':
        return jsonify(call_service('calendar', '/api/settings'))
    return jsonify(call_service('calendar', '/api/settings', method='POST', data=request.get_json()))


@app.route('/api/bids/due-today')
def api_bids_due_today():
    return jsonify(call_service('calendar', '/api/bids/due-today'))


@app.route('/api/bids/due-tomorrow')
def api_bids_due_tomorrow():
    return jsonify(call_service('calendar', '/api/bids/due-tomorrow'))


# =============================================================================
# API ROUTES - Proxy to Notifications
# =============================================================================

@app.route('/api/notifications/status')
def api_notifications_status():
    return jsonify(call_service('notifications', '/api/status'))


@app.route('/api/notifications/settings', methods=['GET', 'POST'])
def api_notifications_settings():
    if request.method == 'GET':
        return jsonify(call_service('notifications', '/api/settings'))
    return jsonify(call_service('notifications', '/api/settings', method='POST', data=request.get_json()))


@app.route('/api/notifications/send-now', methods=['POST'])
def api_send_notification():
    return jsonify(call_service('notifications', '/api/send-now', method='POST'))


@app.route('/api/notifications/preview')
def api_notifications_preview():
    return jsonify(call_service('notifications', '/api/preview'))


# =============================================================================
# API ROUTES - Proxy to Quote Sent Mover
# =============================================================================

@app.route('/api/quote-sent/status')
def api_quote_sent_status():
    return jsonify(call_service('quote_sent_mover', '/api/status'))


@app.route('/api/quote-sent/test-outlook')
def api_quote_sent_test_outlook():
    return jsonify(call_service('quote_sent_mover', '/api/test-outlook'))


@app.route('/api/quote-sent/test-pipedrive')
def api_quote_sent_test_pipedrive():
    return jsonify(call_service('quote_sent_mover', '/api/test-pipedrive'))


@app.route('/api/quote-sent/settings', methods=['GET', 'POST'])
def api_quote_sent_settings():
    if request.method == 'GET':
        return jsonify(call_service('quote_sent_mover', '/api/settings'))
    return jsonify(call_service('quote_sent_mover', '/api/settings', method='POST', data=request.get_json()))


@app.route('/api/quote-sent/candidates', methods=['POST'])
def api_quote_sent_candidates():
    return jsonify(call_service('quote_sent_mover', '/api/candidates', method='POST', data=request.get_json(), timeout=120))


@app.route('/api/quote-sent/process-single', methods=['POST'])
def api_quote_sent_process_single():
    return jsonify(call_service('quote_sent_mover', '/api/process-single', method='POST', data=request.get_json(), timeout=60))


@app.route('/api/quote-sent/process-batch', methods=['POST'])
def api_quote_sent_process_batch():
    return jsonify(call_service('quote_sent_mover', '/api/process-batch', method='POST', data=request.get_json(), timeout=300))


@app.route('/api/quote-sent/reset-single', methods=['POST'])
def api_quote_sent_reset_single():
    return jsonify(call_service('quote_sent_mover', '/api/reset-single', method='POST', data=request.get_json()))


@app.route('/api/quote-sent/activity-log')
def api_quote_sent_activity_log():
    return jsonify(call_service('quote_sent_mover', '/api/activity-log'))


@app.route('/api/quote-sent/scan', methods=['POST'])
def api_quote_sent_scan():
    return jsonify(call_service('quote_sent_mover', '/api/scan', method='POST', data=request.get_json(), timeout=300))


@app.route('/api/quote-sent/ignore-email', methods=['POST'])
def api_quote_sent_ignore_email():
    return jsonify(call_service('quote_sent_mover', '/api/ignore-email', method='POST', data=request.get_json()))


@app.route('/api/quote-sent/create-deal', methods=['POST'])
def api_quote_sent_create_deal():
    return jsonify(call_service('quote_sent_mover', '/api/create-deal', method='POST', data=request.get_json(), timeout=60))


# =============================================================================
# API ROUTES - Sequence Orchestrator
# =============================================================================

import threading
import time

# In-memory storage for sequence settings (persists while app runs)
_sequence_settings = {
    'email_scan': False,
    'pipedrive_sync': False,
    'quote_sent_mover': False,
    'calendar': False,
    'notifications': False
}

# Scheduler state
_scheduler_settings = {
    'enabled': False,
    'interval_minutes': 60,  # Default 1 hour
    'days_to_scan': 1  # Default 1 day
}
_scheduler_thread = None
_scheduler_running = False
_last_scheduled_run = None

# Available intervals (in minutes)
INTERVAL_OPTIONS = [
    {'value': 30, 'label': '30 minutes'},
    {'value': 60, 'label': '1 hour'},
    {'value': 120, 'label': '2 hours'},
    {'value': 180, 'label': '3 hours'},
    {'value': 240, 'label': '4 hours'},
    {'value': 300, 'label': '5 hours'},
    {'value': 360, 'label': '6 hours'},
    {'value': 420, 'label': '7 hours'},
    {'value': 480, 'label': '8 hours'},
    {'value': 540, 'label': '9 hours'},
    {'value': 600, 'label': '10 hours'},
]

# Available days to scan options
DAYS_OPTIONS = [
    {'value': 1, 'label': '1 day'},
    {'value': 3, 'label': '3 days'},
    {'value': 7, 'label': '7 days'},
    {'value': 14, 'label': '14 days'},
    {'value': 30, 'label': '30 days'},
]


def run_sequence_internal():
    """Internal function to run the sequence (used by scheduler)
    
    Execution order based on dependencies:
    Step 1: Email Scan (produces bids)
    Step 2: Calendar, Pipedrive Sync, Notifications (all depend on Email Scan, can run in parallel conceptually)
    Step 3: Quote Sent Mover (depends on Pipedrive Sync)
    """
    global _last_scheduled_run
    results = {
        'started_at': datetime.now().isoformat(),
        'steps': {},
        'success': True
    }
    
    days_to_scan = _scheduler_settings.get('days_to_scan', 1)
    
    # Step 1: Email Scan
    if _sequence_settings.get('email_scan'):
        logger.info(f"Sequence Step 1: Running Email Scan (last {days_to_scan} days)...")
        result = call_service('email_scanner', '/api/scan', method='POST', 
                             data={'days_back': days_to_scan}, timeout=300)
        results['steps']['email_scan'] = {
            'executed': True,
            'success': 'error' not in result,
            'result': result
        }
    else:
        results['steps']['email_scan'] = {'executed': False, 'skipped': True}
    
    # Step 2a: Calendar (depends on Email Scan)
    if _sequence_settings.get('calendar'):
        logger.info("Sequence Step 2: Running Calendar Sync...")
        bids_result = call_service('email_scanner', '/api/bids')
        if 'bids' in bids_result:
            for bid in bids_result['bids']:
                if bid.get('due_date'):
                    call_service('calendar', f'/api/create/{bid["id"]}', method='POST', timeout=30)
        results['steps']['calendar'] = {'executed': True, 'success': True}
    else:
        results['steps']['calendar'] = {'executed': False, 'skipped': True}
    
    # Step 2b: Pipedrive Sync (depends on Email Scan)
    if _sequence_settings.get('pipedrive_sync'):
        logger.info("Sequence Step 2: Running Pipedrive Sync...")
        result = call_service('pipedrive_sync', '/api/sync', method='POST', timeout=300)
        results['steps']['pipedrive_sync'] = {
            'executed': True,
            'success': 'error' not in result,
            'result': result
        }
    else:
        results['steps']['pipedrive_sync'] = {'executed': False, 'skipped': True}
    
    # Step 2c: Notifications (depends on Email Scan)
    if _sequence_settings.get('notifications'):
        logger.info("Sequence Step 2: Running Notifications...")
        result = call_service('notifications', '/api/send-now', method='POST', timeout=60)
        results['steps']['notifications'] = {
            'executed': True,
            'success': 'error' not in result,
            'result': result
        }
    else:
        results['steps']['notifications'] = {'executed': False, 'skipped': True}
    
    # Step 3: Quote Sent Mover (depends on Pipedrive Sync)
    if _sequence_settings.get('quote_sent_mover'):
        logger.info(f"Sequence Step 3: Running Quote Sent Mover (last {days_to_scan} days)...")
        result = call_service('quote_sent_mover', '/api/scan', method='POST',
                             data={'days_back': days_to_scan}, timeout=300)
        results['steps']['quote_sent_mover'] = {
            'executed': True,
            'success': 'error' not in result,
            'result': result
        }
    else:
        results['steps']['quote_sent_mover'] = {'executed': False, 'skipped': True}
    
    results['completed_at'] = datetime.now().isoformat()
    _last_scheduled_run = results
    return results


def scheduler_loop():
    """Background scheduler loop"""
    global _scheduler_running
    while _scheduler_running:
        if _scheduler_settings['enabled']:
            logger.info(f"Scheduler: Running sequence (interval: {_scheduler_settings['interval_minutes']} min)")
            try:
                run_sequence_internal()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            # Sleep for interval (check every 10 seconds if we should stop)
            sleep_remaining = _scheduler_settings['interval_minutes'] * 60
            while sleep_remaining > 0 and _scheduler_running and _scheduler_settings['enabled']:
                time.sleep(min(10, sleep_remaining))
                sleep_remaining -= 10
        else:
            time.sleep(10)  # Check every 10 seconds if scheduler was re-enabled


def start_scheduler():
    """Start the background scheduler"""
    global _scheduler_thread, _scheduler_running
    if _scheduler_running:
        return
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    _scheduler_thread.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the background scheduler"""
    global _scheduler_running
    _scheduler_running = False
    logger.info("Scheduler stopped")

@app.route('/api/sequence/settings', methods=['GET', 'POST'])
def api_sequence_settings():
    """Get or update sequence step settings"""
    global _sequence_settings
    if request.method == 'GET':
        return jsonify(_sequence_settings)
    
    data = request.get_json() or {}
    for key in _sequence_settings.keys():
        if key in data:
            _sequence_settings[key] = bool(data[key])
    return jsonify(_sequence_settings)


@app.route('/api/sequence/scheduler', methods=['GET', 'POST'])
def api_sequence_scheduler():
    """Get or update scheduler settings"""
    global _scheduler_settings
    if request.method == 'GET':
        return jsonify({
            'enabled': _scheduler_settings['enabled'],
            'interval_minutes': _scheduler_settings['interval_minutes'],
            'days_to_scan': _scheduler_settings['days_to_scan'],
            'intervals': INTERVAL_OPTIONS,
            'days_options': DAYS_OPTIONS,
            'scheduler_running': _scheduler_running,
            'last_run': _last_scheduled_run
        })
    
    data = request.get_json() or {}
    if 'enabled' in data:
        _scheduler_settings['enabled'] = bool(data['enabled'])
        if _scheduler_settings['enabled'] and not _scheduler_running:
            start_scheduler()
    if 'interval_minutes' in data:
        _scheduler_settings['interval_minutes'] = int(data['interval_minutes'])
    if 'days_to_scan' in data:
        _scheduler_settings['days_to_scan'] = int(data['days_to_scan'])
    
    return jsonify({
        'enabled': _scheduler_settings['enabled'],
        'interval_minutes': _scheduler_settings['interval_minutes'],
        'days_to_scan': _scheduler_settings['days_to_scan'],
        'scheduler_running': _scheduler_running
    })


@app.route('/api/sequence/run', methods=['POST'])
def api_run_sequence():
    """Run the enabled sequence steps manually"""
    results = run_sequence_internal()
    return jsonify(results)


if __name__ == '__main__':
    logger.info(f"Starting {APP_NAME} on port {PORT}")
    start_scheduler()  # Start scheduler on app start
    app.run(host='0.0.0.0', port=PORT, debug=True)
