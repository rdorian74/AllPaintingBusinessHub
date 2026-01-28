"""
Follow Up Manager - Main Flask Application
All Painting Ltd. - January 2026

Port: 1000
Database: SQLite (followup_manager.db)
"""
import os
import io
import zipfile
import logging
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, Response, send_file

from config import APP_NAME, PORT, DEBUG, SCAN_INTERVALS, BACKFILL_OPTIONS, STATUS_COLORS
from database import (
    init_database, get_all_estimates, get_estimate, update_estimate, delete_estimate,
    get_communications_for_estimate, get_followups_for_estimate,
    get_all_settings, get_setting, set_setting, get_database_stats,
    export_to_csv, export_to_sql, get_db_last_update, clear_database
)

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize database
logger.info("Initializing database...")
init_database()
logger.info("Database initialized successfully")

# Lazy load heavy modules
_scanner = None
_engine = None
_scheduler_running = False
_scheduler_thread = None

def get_scanner():
    global _scanner
    if _scanner is None:
        logger.info("Loading email scanner module...")
        from email_scanner import get_email_scanner
        _scanner = get_email_scanner()
        logger.info("Email scanner loaded")
    return _scanner

def get_engine():
    global _engine
    if _engine is None:
        logger.info("Loading followup engine module...")
        from followup_engine import get_followup_engine
        _engine = get_followup_engine()
        logger.info("Followup engine loaded")
    return _engine

# ============ View Routes ============

@app.route("/")
def dashboard():
    """Main dashboard view"""
    logger.info("Dashboard accessed")
    status_filter = request.args.get("status", "all")
    estimates = get_all_estimates(status_filter=status_filter)
    stats = get_database_stats()
    settings = get_all_settings()
    
    # Get calendar data for next 3 days
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
    day_after = (now + timedelta(days=2)).strftime('%Y-%m-%d')
    
    # Get all active estimates for calendar
    all_estimates = get_all_estimates(status_filter="all")
    
    # Filter estimates by next_followup_date and check if draft ready
    calendar_today = []
    calendar_tomorrow = []
    calendar_day_after = []
    
    for est in all_estimates:
        if est.get("status") in ["won", "lost"] or est.get("stop_followup"):
            continue
        
        next_date = est.get("next_followup_date")
        if not next_date:
            continue
        
        # Check if there's a draft ready for this estimate
        followups = get_followups_for_estimate(est["id"])
        est["draft_ready"] = any(f.get("status") == "draft_ready" for f in followups)
        
        if next_date == today or next_date < today:  # Include overdue in today
            calendar_today.append(est)
        elif next_date == tomorrow:
            calendar_tomorrow.append(est)
        elif next_date == day_after:
            calendar_day_after.append(est)
    
    return render_template(
        "index.html",
        estimates=estimates,
        stats=stats,
        settings=settings,
        status_filter=status_filter,
        status_colors=STATUS_COLORS,
        scan_intervals=SCAN_INTERVALS,
        backfill_options=BACKFILL_OPTIONS,
        app_name=APP_NAME,
        now=now,
        timedelta=timedelta,
        calendar_today=calendar_today,
        calendar_tomorrow=calendar_tomorrow,
        calendar_day_after=calendar_day_after
    )

@app.route("/estimate/<int:estimate_id>")
def estimate_detail(estimate_id):
    """Estimate detail view with conversation history"""
    logger.info(f"Viewing estimate detail: {estimate_id}")
    estimate = get_estimate(estimate_id)
    if not estimate:
        return jsonify({"error": "Estimate not found"}), 404
    
    communications = get_communications_for_estimate(estimate_id)
    followups = get_followups_for_estimate(estimate_id)
    
    return jsonify({
        "estimate": estimate,
        "communications": communications,
        "followups": followups
    })

# ============ Estimates API ============

@app.route("/api/estimates")
def api_list_estimates():
    """List all estimates with optional filtering"""
    status_filter = request.args.get("status", "all")
    logger.info(f"API: Listing estimates with filter: {status_filter}")
    estimates = get_all_estimates(status_filter=status_filter)
    stats = get_database_stats()
    return jsonify({"estimates": estimates, "stats": stats})

@app.route("/api/estimates/<int:estimate_id>")
def api_get_estimate(estimate_id):
    """Get single estimate with communications"""
    logger.info(f"API: Getting estimate {estimate_id}")
    estimate = get_estimate(estimate_id)
    if not estimate:
        return jsonify({"error": "Estimate not found"}), 404
    
    communications = get_communications_for_estimate(estimate_id)
    followups = get_followups_for_estimate(estimate_id)
    
    return jsonify({
        "estimate": estimate,
        "communications": communications,
        "followups": followups
    })

@app.route("/api/estimates/<int:estimate_id>", methods=["PATCH"])
def api_update_estimate(estimate_id):
    """Update estimate status or other fields"""
    data = request.get_json()
    logger.info(f"API: Updating estimate {estimate_id} with {data}")
    
    estimate = get_estimate(estimate_id)
    if not estimate:
        return jsonify({"error": "Estimate not found"}), 404
    
    update_estimate(estimate_id, data)
    logger.info(f"Estimate {estimate_id} updated successfully")
    return jsonify({"success": True, "estimate": get_estimate(estimate_id)})

@app.route("/api/estimates/<int:estimate_id>", methods=["DELETE"])
def api_delete_estimate(estimate_id):
    """Delete an estimate"""
    logger.info(f"API: Deleting estimate {estimate_id}")
    estimate = get_estimate(estimate_id)
    if not estimate:
        return jsonify({"error": "Estimate not found"}), 404
    
    delete_estimate(estimate_id)
    logger.info(f"Estimate {estimate_id} deleted")
    return jsonify({"success": True})

@app.route("/api/estimates/<int:estimate_id>/delay", methods=["POST"])
def api_delay_estimate(estimate_id):
    """Delay follow-up by X days"""
    data = request.get_json()
    days = data.get("days", 7)
    logger.info(f"API: Delaying estimate {estimate_id} by {days} days")
    
    result = get_engine().delay_followup(estimate_id, days)
    return jsonify(result)

@app.route("/api/estimates/<int:estimate_id>/stop", methods=["POST"])
def api_stop_followups(estimate_id):
    """Stop follow-ups for an estimate"""
    logger.info(f"API: Stopping followups for estimate {estimate_id}")
    result = get_engine().stop_followups(estimate_id)
    return jsonify(result)

@app.route("/api/estimates/<int:estimate_id>/resume", methods=["POST"])
def api_resume_followups(estimate_id):
    """Resume follow-ups for an estimate"""
    logger.info(f"API: Resuming followups for estimate {estimate_id}")
    result = get_engine().resume_followups(estimate_id)
    return jsonify(result)

@app.route("/api/estimates/bulk", methods=["POST"])
def api_bulk_update():
    """Bulk update multiple estimates"""
    data = request.get_json()
    ids = data.get("ids", [])
    action = data.get("action")
    logger.info(f"API: Bulk action '{action}' on {len(ids)} estimates")
    
    results = []
    for est_id in ids:
        try:
            if action == "mark_won":
                update_estimate(est_id, {"status": "won"})
            elif action == "mark_lost":
                update_estimate(est_id, {"status": "lost"})
            elif action == "mark_on_hold":
                update_estimate(est_id, {"status": "on_hold"})
            elif action == "stop_followups":
                get_engine().stop_followups(est_id)
            elif action == "delete":
                delete_estimate(est_id)
            elif action == "delay":
                days = data.get("days", 7)
                get_engine().delay_followup(est_id, days)
            
            results.append({"id": est_id, "success": True})
            logger.info(f"  - Estimate {est_id}: {action} successful")
        except Exception as e:
            results.append({"id": est_id, "success": False, "error": str(e)})
            logger.error(f"  - Estimate {est_id}: {action} failed - {e}")
    
    return jsonify({"results": results})

# ============ Scanning API ============

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Manual email scan"""
    data = request.get_json() or {}
    days_back = data.get("days_back", 7)
    logger.info(f"API: Starting email scan for last {days_back} days...")
    
    try:
        result = get_scanner().scan(days_back=days_back)
        logger.info(f"Scan complete: {result.get('new_estimates', 0)} new estimates, {result.get('new_communications', 0)} new communications")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Scan failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/scan/auto", methods=["POST", "GET"])
def api_auto_scan():
    """
    Automated daily scan - checks last 1 day only.
    Called by Windows Task Scheduler at beginning of day.
    GET allowed for easy task scheduler setup.
    """
    logger.info("API: Starting automated daily scan (1 day)...")
    
    try:
        result = get_scanner().scan(days_back=1)
        logger.info(f"Auto scan complete: {result.get('new_estimates', 0)} new, {result.get('drafts_generated', 0)} drafts")
        return jsonify({
            "success": True,
            "scan_time": datetime.now().isoformat(),
            "new_estimates": result.get("new_estimates", 0),
            "drafts_generated": result.get("drafts_generated", 0),
            "errors": result.get("errors", [])
        })
    except Exception as e:
        logger.error(f"Auto scan failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/backfill", methods=["POST"])
def api_backfill():
    """Initial backfill scan"""
    data = request.get_json() or {}
    days = data.get("days", 90)
    logger.info(f"API: Starting backfill scan for last {days} days...")
    
    try:
        result = get_scanner().scan(days_back=days, backfill=True)
        logger.info(f"Backfill complete: {result.get('new_estimates', 0)} new estimates, {result.get('new_communications', 0)} new communications")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/scan/status")
def api_scan_status():
    """Get scan status"""
    last_scan = get_setting("last_scan_date")
    backfill_done = get_setting("backfill_completed") == "true"
    
    return jsonify({
        "last_scan": last_scan,
        "backfill_completed": backfill_done
    })

# ============ Follow-ups API ============

@app.route("/api/followups/pending")
def api_pending_followups():
    """Get estimates needing follow-up"""
    logger.info("API: Getting pending followups")
    pending = get_engine().get_pending_followups()
    logger.info(f"Found {len(pending)} pending followups")
    return jsonify({"pending": pending})

@app.route("/api/followups/<int:estimate_id>/generate", methods=["POST"])
def api_generate_draft(estimate_id):
    """Generate follow-up draft"""
    logger.info(f"API: Generating draft for estimate {estimate_id}...")
    try:
        result = get_engine().generate_draft(estimate_id)
        if result.get("success"):
            logger.info(f"Draft generated successfully for estimate {estimate_id}")
        else:
            logger.warning(f"Draft generation issue: {result.get('error')}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"Draft generation failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/followups/<int:followup_id>/draft")
def api_get_draft(followup_id):
    """Get draft content"""
    logger.info(f"API: Getting draft {followup_id}")
    from database import get_connection
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM followups WHERE id = ?", (followup_id,))
        row = cursor.fetchone()
    
    if not row:
        return jsonify({"error": "Followup not found"}), 404
    
    return jsonify(dict(row))

@app.route("/api/followups/check-sent", methods=["POST"])
def api_check_sent():
    """Check for sent drafts"""
    logger.info("API: Checking for sent drafts...")
    try:
        sent = get_engine().check_sent_drafts()
        logger.info(f"Found {len(sent)} sent drafts")
        return jsonify({"sent": sent})
    except Exception as e:
        logger.error(f"Check sent drafts failed: {e}")
        return jsonify({"error": str(e)}), 500

# ============ Settings API ============

@app.route("/api/settings")
def api_get_settings():
    """Get all settings"""
    settings = get_all_settings()
    return jsonify(settings)

@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    """Update settings"""
    data = request.get_json()
    logger.info(f"API: Updating settings: {data}")
    
    for key, value in data.items():
        set_setting(key, value)
    
    logger.info("Settings updated successfully")
    return jsonify({"success": True, "settings": get_all_settings()})

@app.route("/api/settings/autoscan", methods=["POST"])
def api_toggle_autoscan():
    """Toggle auto-scan"""
    data = request.get_json()
    enabled = data.get("enabled", False)
    logger.info(f"API: Auto-scan {'enabled' if enabled else 'disabled'}")
    
    set_setting("auto_mode", "true" if enabled else "false")
    
    return jsonify({"success": True, "auto_mode": enabled})

# ============ Export API ============

@app.route("/api/export/csv")
def api_export_csv():
    """Export database to CSV files (zipped)"""
    logger.info("API: Exporting database to CSV...")
    try:
        csv_files = export_to_csv()
        
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for filename, content in csv_files.items():
                zf.writestr(filename, content)
        
        memory_file.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"CSV export complete: {len(csv_files)} files")
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'followup_manager_export_{timestamp}.zip'
        )
    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/sql")
def api_export_sql():
    """Export database to SQL file"""
    logger.info("API: Exporting database to SQL...")
    try:
        sql_content = export_to_sql()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info("SQL export complete")
        return Response(
            sql_content,
            mimetype='text/sql',
            headers={
                'Content-Disposition': f'attachment; filename=followup_manager_export_{timestamp}.sql'
            }
        )
    except Exception as e:
        logger.error(f"SQL export failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/db/stats")
def api_db_stats():
    """Get database statistics"""
    stats = get_database_stats()
    return jsonify(stats)

@app.route("/api/db/last-update")
def api_db_last_update():
    """Get last database update timestamp"""
    last_update = get_db_last_update()
    return jsonify({"last_update": last_update})

@app.route("/api/db/clear", methods=["POST"])
def api_clear_database():
    """Clear all data from database"""
    logger.warning("API: Clearing database - all data will be deleted!")
    try:
        clear_database()
        logger.info("Database cleared successfully")
        return jsonify({"success": True, "message": "Database cleared"})
    except Exception as e:
        logger.error(f"Clear database failed: {e}")
        return jsonify({"error": str(e)}), 500

# ============ Daily Scheduler ============

def run_daily_scan():
    """Execute the daily scan (1 day lookback)"""
    logger.info("SCHEDULER: Running daily auto-scan...")
    try:
        scanner = get_scanner()
        result = scanner.scan(days_back=1)
        logger.info(f"SCHEDULER: Complete - {result.get('new_estimates', 0)} new, {result.get('drafts_generated', 0)} drafts")
        set_setting("last_auto_scan", datetime.now().isoformat())
    except Exception as e:
        logger.error(f"SCHEDULER: Scan failed - {e}")

def scheduler_loop():
    """Background thread that checks if it's time to run daily scan"""
    global _scheduler_running
    last_run_date = None
    
    logger.info("SCHEDULER: Started")
    
    while _scheduler_running:
        try:
            # Check if enabled
            enabled = get_setting("daily_scan_enabled") == "true"
            if not enabled:
                time.sleep(60)
                continue
            
            # Get scheduled time
            scan_time = get_setting("daily_scan_time") or "07:00"
            
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            
            # Parse scheduled time
            try:
                hour, minute = map(int, scan_time.split(":"))
            except:
                hour, minute = 7, 0
            
            scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Check if it's time and we haven't run today
            if now >= scheduled and last_run_date != today:
                logger.info(f"SCHEDULER: Triggering daily scan at {scan_time}")
                run_daily_scan()
                last_run_date = today
            
            # Sleep for 60 seconds before checking again
            time.sleep(60)
            
        except Exception as e:
            logger.error(f"SCHEDULER: Error - {e}")
            time.sleep(60)
    
    logger.info("SCHEDULER: Stopped")

def start_scheduler():
    """Start the background scheduler thread"""
    global _scheduler_running, _scheduler_thread
    
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    
    _scheduler_running = True
    _scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    _scheduler_thread.start()
    logger.info("SCHEDULER: Thread started")

def stop_scheduler():
    """Stop the background scheduler thread"""
    global _scheduler_running
    _scheduler_running = False
    logger.info("SCHEDULER: Stopping...")

@app.route("/api/scheduler/status")
def api_scheduler_status():
    """Get scheduler status"""
    enabled = get_setting("daily_scan_enabled") == "true"
    scan_time = get_setting("daily_scan_time") or "07:00"
    last_auto = get_setting("last_auto_scan")
    
    return jsonify({
        "enabled": enabled,
        "scan_time": scan_time,
        "last_auto_scan": last_auto,
        "thread_running": _scheduler_thread.is_alive() if _scheduler_thread else False
    })

# ============ Main ============

if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  {APP_NAME}")
    print(f"  All Painting Ltd.")
    print(f"{'='*50}")
    print(f"  Running on: http://localhost:{PORT}")
    print(f"  Debug mode: {DEBUG}")
    print(f"  Database: followup_manager.db")
    print(f"{'='*50}\n")
    
    # Start the daily scheduler
    start_scheduler()
    
    logger.info(f"Starting {APP_NAME} on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)
