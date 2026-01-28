"""
Main Entry Point - Bid/Addendum Email Forwarding Agent
All Painting Ltd.

Runs the email monitoring loop and web dashboard.
"""
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string
from email_monitor import BidEmailMonitor
from database import Database
import config

app = Flask(__name__)
monitor = None
db = None
is_running = False
last_check_time = None
last_check_results = []


# =============================================================================
# MONITORING LOOP
# =============================================================================

def monitoring_loop():
    """Main monitoring loop - runs every 5 minutes"""
    global monitor, is_running, last_check_time, last_check_results
    
    print("\n" + "="*60)
    print("STARTING MONITORING LOOP")
    print(f"Check interval: {config.CHECK_INTERVAL_SECONDS} seconds ({config.CHECK_INTERVAL_SECONDS//60} minutes)")
    print("="*60)
    
    while is_running:
        try:
            print(f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for new bid emails...")
            
            results = monitor.check_for_new_bids()
            last_check_time = datetime.now()
            last_check_results = results
            
            # Summary
            forwarded = sum(1 for r in results if r.get("status") == "forwarded")
            drafted = sum(1 for r in results if r.get("status") == "draft_created")
            skipped = sum(1 for r in results if r.get("status") == "skipped")
            
            if results:
                print(f"\n📊 Check complete: {len(results)} emails processed")
                print(f"   Forwarded: {forwarded} | Drafts: {drafted} | Skipped: {skipped}")
            else:
                print(f"   No new emails to process")
            
        except Exception as e:
            print(f"❌ Error in monitoring loop: {e}")
            import traceback
            traceback.print_exc()
        
        # Wait for next check
        print(f"\n⏳ Next check in {config.CHECK_INTERVAL_SECONDS} seconds...")
        
        # Sleep in small increments so we can stop quickly
        for _ in range(config.CHECK_INTERVAL_SECONDS):
            if not is_running:
                break
            time.sleep(1)


def start_monitoring():
    """Start the monitoring thread"""
    global monitor, db, is_running
    
    monitor = BidEmailMonitor()
    db = Database()
    is_running = True
    
    thread = threading.Thread(target=monitoring_loop, daemon=True)
    thread.start()
    
    return thread


def stop_monitoring():
    """Stop the monitoring thread"""
    global is_running
    is_running = False


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route("/api/status")
def api_status():
    """Get agent status"""
    mode = db.get_setting("mode", config.OPERATION_MODE)
    stats = db.get_statistics()
    
    return jsonify({
        "running": is_running,
        "mode": mode,
        "last_check": last_check_time.isoformat() if last_check_time else None,
        "check_interval_seconds": config.CHECK_INTERVAL_SECONDS,
        "stats": stats,
        "api_configured": bool(config.ANTHROPIC_API_KEY),
        "forward_to": config.FORWARD_TO_EMAIL,
        "monitored_email": config.MONITORED_EMAIL
    })


@app.route("/api/set-mode", methods=["POST"])
def api_set_mode():
    """Set operation mode (draft/active)"""
    data = request.get_json()
    mode = data.get("mode")
    
    if mode not in ["draft", "active"]:
        return jsonify({"error": "Mode must be 'draft' or 'active'"}), 400
    
    db.set_setting("mode", mode)
    print(f"🔄 Mode changed to: {mode}")
    
    return jsonify({"success": True, "mode": mode})


@app.route("/api/bids")
def api_bids():
    """Get recent bids"""
    limit = request.args.get("limit", 50, type=int)
    bids = db.get_recent_bids(limit=limit)
    return jsonify(bids)


@app.route("/api/bids/open")
def api_open_bids():
    """Get open bids"""
    bids = db.get_open_bids()
    return jsonify(bids)


@app.route("/api/processing-log")
def api_processing_log():
    """Get processing log"""
    limit = request.args.get("limit", 100, type=int)
    status = request.args.get("status")
    logs = db.get_processing_log(limit=limit, status_filter=status)
    return jsonify(logs)


@app.route("/api/gc-contacts")
def api_gc_contacts():
    """Get GC contacts"""
    contacts = db.get_gc_contacts()
    return jsonify(contacts)


@app.route("/api/costs")
def api_costs():
    """Get cost summary"""
    return jsonify({
        "today": db.get_costs("today"),
        "week": db.get_costs("week"),
        "month": db.get_costs("month"),
        "total": db.get_costs("total")
    })


@app.route("/api/check-now", methods=["POST"])
def api_check_now():
    """Trigger immediate check"""
    global last_check_time, last_check_results
    
    try:
        results = monitor.check_for_new_bids(minutes_back=60)
        last_check_time = datetime.now()
        last_check_results = results
        
        return jsonify({
            "success": True,
            "emails_processed": len(results),
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/db/bid-tracker")
def api_db_bid_tracker():
    """Get all bid tracker entries"""
    limit = request.args.get("limit", 100, type=int)
    bids = db.get_recent_bids(limit=limit)
    return jsonify(bids)


@app.route("/api/db/bid-tracker/<int:bid_id>")
def api_db_bid_detail(bid_id):
    """Get a specific bid by ID"""
    bid = db.get_bid(bid_id)
    if bid:
        return jsonify(bid)
    return jsonify({"error": "Bid not found"}), 404


@app.route("/api/db/processing-log")
def api_db_processing_log():
    """Get all processing log entries"""
    limit = request.args.get("limit", 200, type=int)
    status = request.args.get("status")
    logs = db.get_processing_log(limit=limit, status_filter=status)
    return jsonify(logs)


@app.route("/api/db/gc-contacts")
def api_db_gc_contacts():
    """Get all GC contacts"""
    limit = request.args.get("limit", 200, type=int)
    contacts = db.get_gc_contacts(limit=limit)
    return jsonify(contacts)


@app.route("/api/db/export/<table_name>")
def api_db_export(table_name):
    """Export a table as CSV"""
    import csv
    import io
    
    valid_tables = ["bid_tracker", "processing_log", "gc_contacts"]
    if table_name not in valid_tables:
        return jsonify({"error": f"Invalid table. Choose from: {valid_tables}"}), 400
    
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={table_name}.csv"}
    )


# =============================================================================
# DASHBOARD
# =============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Bid/Addendum Agent - All Painting Ltd</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        
        h1 { margin-bottom: 5px; }
        .subtitle { color: #8ab4f8; margin-bottom: 20px; }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        .card h2 { 
            font-size: 14px; 
            text-transform: uppercase; 
            color: #8ab4f8;
            margin-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 10px;
        }
        
        .mode-buttons { display: flex; gap: 10px; margin-bottom: 15px; }
        .mode-btn {
            flex: 1;
            padding: 12px;
            border: 2px solid #8ab4f8;
            background: transparent;
            color: #fff;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .mode-btn:hover { background: rgba(138,180,248,0.2); }
        .mode-btn.active { background: #8ab4f8; color: #0d1b2a; }
        .mode-btn small { display: block; font-size: 10px; opacity: 0.8; }
        
        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }
        .stat { text-align: center; }
        .stat-value { font-size: 28px; font-weight: bold; color: #8ab4f8; }
        .stat-label { font-size: 12px; color: #aaa; }
        
        .cost-item { 
            display: flex; 
            justify-content: space-between; 
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .cost-value { color: #4ade80; font-weight: bold; }
        
        .log-item {
            padding: 12px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .log-item .subject { font-weight: bold; margin-bottom: 5px; }
        .log-item .meta { font-size: 12px; color: #aaa; }
        .log-item .status { 
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }
        .status.forwarded, .status.draft_created { background: #4ade80; color: #000; }
        .status.skipped { background: #f59e0b; color: #000; }
        .status.error { background: #ef4444; color: #fff; }
        
        .bid-item {
            padding: 12px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .bid-item .project { font-weight: bold; color: #8ab4f8; }
        .bid-item .gc { font-size: 14px; }
        .bid-item .due { font-size: 12px; color: #f59e0b; }
        .bid-item .addendum { 
            display: inline-block;
            padding: 2px 6px;
            background: #8ab4f8;
            color: #000;
            border-radius: 4px;
            font-size: 11px;
            margin-left: 10px;
        }
        
        .btn {
            padding: 10px 20px;
            background: #8ab4f8;
            color: #0d1b2a;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn:hover { background: #a8c8ff; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-indicator.running { background: #4ade80; }
        .status-indicator.stopped { background: #ef4444; }
        
        .last-check { font-size: 12px; color: #aaa; margin-top: 10px; }
        
        #log-list, #bids-list { max-height: 400px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Bid/Addendum Agent</h1>
        <p class="subtitle">All Painting Ltd. - Email Monitoring System</p>
        
        <div style="margin-bottom: 20px;">
            <a href="/database" style="color: #8ab4f8; text-decoration: none; padding: 8px 16px; border: 1px solid #8ab4f8; border-radius: 4px;">🗄️ View Database</a>
        </div>
        
        <div class="grid">
            <!-- Status & Mode -->
            <div class="card">
                <h2>Agent Status</h2>
                <p>
                    <span class="status-indicator" id="status-indicator"></span>
                    <span id="status-text">Loading...</span>
                </p>
                <p class="last-check">Last check: <span id="last-check">Never</span></p>
                <p class="last-check">Monitoring: <span id="monitored-email">-</span></p>
                <p class="last-check">Forward to: <span id="forward-to">-</span></p>
                
                <div style="margin-top: 15px;">
                    <button class="btn" onclick="checkNow()" id="check-btn">Check Now</button>
                </div>
            </div>
            
            <!-- Mode Selection -->
            <div class="card">
                <h2>Operation Mode</h2>
                <div class="mode-buttons">
                    <button class="mode-btn draft" onclick="setMode('draft')">
                        📝 Draft Mode
                        <small>Create drafts for review</small>
                    </button>
                    <button class="mode-btn active" onclick="setMode('active')">
                        📤 Active Mode
                        <small>Forward automatically</small>
                    </button>
                </div>
                <p style="font-size: 12px; color: #aaa;">
                    Current mode: <strong id="current-mode">-</strong>
                </p>
            </div>
            
            <!-- Statistics -->
            <div class="card">
                <h2>Statistics</h2>
                <div class="stat-grid">
                    <div class="stat">
                        <div class="stat-value" id="total-bids">0</div>
                        <div class="stat-label">Total Bids</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="open-bids">0</div>
                        <div class="stat-label">Open Bids</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="emails-today">0</div>
                        <div class="stat-label">Emails Today</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="gc-contacts">0</div>
                        <div class="stat-label">GC Contacts</div>
                    </div>
                </div>
            </div>
            
            <!-- Costs -->
            <div class="card">
                <h2>API Costs</h2>
                <div class="cost-item">
                    <span>Today</span>
                    <span class="cost-value" id="cost-today">$0.00</span>
                </div>
                <div class="cost-item">
                    <span>This Week</span>
                    <span class="cost-value" id="cost-week">$0.00</span>
                </div>
                <div class="cost-item">
                    <span>This Month</span>
                    <span class="cost-value" id="cost-month">$0.00</span>
                </div>
                <div class="cost-item">
                    <span>Total</span>
                    <span class="cost-value" id="cost-total">$0.00</span>
                </div>
            </div>
            
            <!-- Open Bids -->
            <div class="card" style="grid-column: span 1;">
                <h2>Open Bids</h2>
                <div id="bids-list">
                    <p style="color: #888;">No bids yet</p>
                </div>
            </div>
            
            <!-- Recent Activity -->
            <div class="card" style="grid-column: span 1;">
                <h2>Recent Activity</h2>
                <div id="log-list">
                    <p style="color: #888;">No activity yet</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMode = 'draft';
        
        async function loadStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                currentMode = data.mode;
                updateModeButtons();
                
                document.getElementById('current-mode').textContent = data.mode.toUpperCase();
                document.getElementById('status-indicator').className = 
                    'status-indicator ' + (data.running ? 'running' : 'stopped');
                document.getElementById('status-text').textContent = 
                    data.running ? 'Running' : 'Stopped';
                document.getElementById('last-check').textContent = 
                    data.last_check ? new Date(data.last_check).toLocaleString() : 'Never';
                document.getElementById('monitored-email').textContent = data.monitored_email;
                document.getElementById('forward-to').textContent = data.forward_to;
                
                if (data.stats) {
                    document.getElementById('total-bids').textContent = data.stats.total_bids;
                    document.getElementById('open-bids').textContent = data.stats.open_bids;
                    document.getElementById('emails-today').textContent = data.stats.emails_today;
                    document.getElementById('gc-contacts').textContent = data.stats.gc_contacts;
                }
            } catch (e) {
                console.error('Error loading status:', e);
            }
        }
        
        async function loadCosts() {
            try {
                const res = await fetch('/api/costs');
                const data = await res.json();
                
                document.getElementById('cost-today').textContent = '$' + data.today.total_cost.toFixed(4);
                document.getElementById('cost-week').textContent = '$' + data.week.total_cost.toFixed(4);
                document.getElementById('cost-month').textContent = '$' + data.month.total_cost.toFixed(4);
                document.getElementById('cost-total').textContent = '$' + data.total.total_cost.toFixed(4);
            } catch (e) {
                console.error('Error loading costs:', e);
            }
        }
        
        async function loadBids() {
            try {
                const res = await fetch('/api/bids/open');
                const bids = await res.json();
                
                const list = document.getElementById('bids-list');
                
                if (bids.length === 0) {
                    list.innerHTML = '<p style="color: #888;">No open bids</p>';
                    return;
                }
                
                list.innerHTML = bids.slice(0, 10).map(bid => {
                    const dueDate = bid.bid_due_date ? new Date(bid.bid_due_date).toLocaleDateString() : 'No date';
                    const addendum = bid.current_addendum > 0 ? 
                        `<span class="addendum">Add #${bid.current_addendum}</span>` : '';
                    
                    return `
                        <div class="bid-item">
                            <div class="project">${bid.project_name || 'Unknown Project'} ${addendum}</div>
                            <div class="gc">${bid.gc_company || 'Unknown GC'}</div>
                            <div class="due">Due: ${dueDate} ${bid.bid_due_time || ''}</div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error loading bids:', e);
            }
        }
        
        async function loadLogs() {
            try {
                const res = await fetch('/api/processing-log?limit=20');
                const logs = await res.json();
                
                const list = document.getElementById('log-list');
                
                if (logs.length === 0) {
                    list.innerHTML = '<p style="color: #888;">No activity yet</p>';
                    return;
                }
                
                list.innerHTML = logs.map(log => {
                    const time = new Date(log.created_at).toLocaleString();
                    return `
                        <div class="log-item">
                            <div class="subject">${log.subject || 'No subject'}</div>
                            <div class="meta">
                                <span class="status ${log.status}">${log.status}</span>
                                From: ${log.from_address || 'Unknown'}
                            </div>
                            <div class="meta">${time}</div>
                            ${log.skip_reason ? `<div class="meta" style="color: #f59e0b;">Reason: ${log.skip_reason}</div>` : ''}
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error loading logs:', e);
            }
        }
        
        function updateModeButtons() {
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            document.querySelector(`.mode-btn.${currentMode}`).classList.add('active');
        }
        
        async function setMode(mode) {
            try {
                const res = await fetch('/api/set-mode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                
                if (res.ok) {
                    currentMode = mode;
                    updateModeButtons();
                    document.getElementById('current-mode').textContent = mode.toUpperCase();
                }
            } catch (e) {
                console.error('Error setting mode:', e);
            }
        }
        
        async function checkNow() {
            const btn = document.getElementById('check-btn');
            btn.disabled = true;
            btn.textContent = 'Checking...';
            
            try {
                const res = await fetch('/api/check-now', { method: 'POST' });
                const data = await res.json();
                
                if (data.success) {
                    alert(`Checked! Processed ${data.emails_processed} emails.`);
                    loadStatus();
                    loadLogs();
                    loadBids();
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                }
            } catch (e) {
                alert('Error: ' + e.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Check Now';
            }
        }
        
        // Initial load
        loadStatus();
        loadCosts();
        loadBids();
        loadLogs();
        
        // Refresh every 30 seconds
        setInterval(() => {
            loadStatus();
            loadCosts();
            loadBids();
            loadLogs();
        }, 30000);
    </script>
</body>
</html>
"""


DATABASE_VIEWER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Database Viewer - Bid/Addendum Agent</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #1e3a5f 0%, #0d1b2a 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1600px; margin: 0 auto; }
        
        h1 { margin-bottom: 5px; }
        .subtitle { color: #8ab4f8; margin-bottom: 20px; }
        
        .nav { margin-bottom: 20px; }
        .nav a { 
            color: #8ab4f8; 
            text-decoration: none; 
            margin-right: 20px;
            padding: 8px 16px;
            border: 1px solid #8ab4f8;
            border-radius: 4px;
        }
        .nav a:hover { background: rgba(138,180,248,0.2); }
        .nav a.active { background: #8ab4f8; color: #0d1b2a; }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab {
            padding: 10px 20px;
            background: rgba(255,255,255,0.1);
            border: none;
            color: #fff;
            border-radius: 8px 8px 0 0;
            cursor: pointer;
        }
        .tab:hover { background: rgba(255,255,255,0.2); }
        .tab.active { background: #8ab4f8; color: #0d1b2a; }
        
        .table-container {
            background: rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            overflow-x: auto;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { 
            background: rgba(0,0,0,0.3); 
            color: #8ab4f8;
            font-weight: bold;
            position: sticky;
            top: 0;
        }
        tr:hover { background: rgba(255,255,255,0.05); }
        
        .status { 
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }
        .status.forwarded, .status.draft_created, .status.open { background: #4ade80; color: #000; }
        .status.skipped { background: #f59e0b; color: #000; }
        .status.closed { background: #888; color: #fff; }
        
        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .btn {
            padding: 8px 16px;
            background: #8ab4f8;
            color: #0d1b2a;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            text-decoration: none;
        }
        .btn:hover { background: #a8c8ff; }
        .btn-sm { padding: 4px 10px; font-size: 12px; }
        
        .count { color: #aaa; font-size: 14px; }
        
        .truncate { 
            max-width: 200px; 
            white-space: nowrap; 
            overflow: hidden; 
            text-overflow: ellipsis; 
        }
        .truncate:hover {
            white-space: normal;
            overflow: visible;
        }
        
        .loading { text-align: center; padding: 40px; color: #888; }
        
        #table-data { max-height: 70vh; overflow-y: auto; }
        
        .detail-modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .detail-modal.show { display: flex; }
        .detail-content {
            background: #1e3a5f;
            padding: 30px;
            border-radius: 12px;
            max-width: 800px;
            max-height: 80vh;
            overflow-y: auto;
            width: 90%;
        }
        .detail-content h2 { margin-bottom: 20px; color: #8ab4f8; }
        .detail-row { 
            display: flex; 
            padding: 8px 0; 
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .detail-label { width: 150px; color: #8ab4f8; font-weight: bold; }
        .detail-value { flex: 1; word-break: break-word; }
        .close-btn {
            position: absolute;
            top: 20px;
            right: 30px;
            font-size: 30px;
            cursor: pointer;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🗄️ Database Viewer</h1>
        <p class="subtitle">Bid/Addendum Agent - All Painting Ltd.</p>
        
        <div class="nav">
            <a href="/">← Back to Dashboard</a>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="loadTable('bid_tracker')">📋 Bid Tracker</button>
            <button class="tab" onclick="loadTable('processing_log')">📝 Processing Log</button>
            <button class="tab" onclick="loadTable('gc_contacts')">🏢 GC Contacts</button>
        </div>
        
        <div class="table-container">
            <div class="toolbar">
                <span class="count" id="row-count">Loading...</span>
                <div>
                    <a class="btn btn-sm" id="export-btn" href="#" download>📥 Export CSV</a>
                    <button class="btn btn-sm" onclick="loadCurrentTable()">🔄 Refresh</button>
                </div>
            </div>
            <div id="table-data">
                <div class="loading">Loading...</div>
            </div>
        </div>
    </div>
    
    <!-- Detail Modal -->
    <div class="detail-modal" id="detail-modal">
        <span class="close-btn" onclick="closeModal()">&times;</span>
        <div class="detail-content" id="detail-content">
        </div>
    </div>
    
    <script>
        let currentTable = 'bid_tracker';
        
        const tableColumns = {
            'bid_tracker': ['id', 'project_name', 'gc_company', 'bid_due_date', 'bid_due_time', 'current_addendum', 'status', 'gc_contact_email', 'project_type', 'created_at'],
            'processing_log': ['id', 'subject', 'from_address', 'status', 'category', 'skip_reason', 'cost_usd', 'created_at'],
            'gc_contacts': ['id', 'company_name', 'email_domain', 'contact_name', 'contact_email', 'bid_count', 'first_seen_date', 'last_seen_date']
        };
        
        function loadTable(tableName) {
            currentTable = tableName;
            
            // Update tab styles
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            // Update export link
            document.getElementById('export-btn').href = `/api/db/export/${tableName}`;
            
            loadCurrentTable();
        }
        
        async function loadCurrentTable() {
            const container = document.getElementById('table-data');
            container.innerHTML = '<div class="loading">Loading...</div>';
            
            try {
                const endpoint = currentTable === 'bid_tracker' ? '/api/db/bid-tracker' :
                                 currentTable === 'processing_log' ? '/api/db/processing-log' :
                                 '/api/db/gc-contacts';
                
                const res = await fetch(endpoint + '?limit=500');
                const data = await res.json();
                
                document.getElementById('row-count').textContent = `${data.length} rows`;
                
                if (data.length === 0) {
                    container.innerHTML = '<div class="loading">No data yet</div>';
                    return;
                }
                
                const columns = tableColumns[currentTable];
                
                let html = '<table><thead><tr>';
                columns.forEach(col => {
                    html += `<th>${col.replace(/_/g, ' ').toUpperCase()}</th>`;
                });
                html += '<th>ACTIONS</th></tr></thead><tbody>';
                
                data.forEach(row => {
                    html += '<tr>';
                    columns.forEach(col => {
                        let value = row[col] !== null && row[col] !== undefined ? row[col] : '-';
                        
                        // Format specific columns
                        if (col === 'status') {
                            value = `<span class="status ${value}">${value}</span>`;
                        } else if (col === 'cost_usd' && value !== '-') {
                            value = '$' + parseFloat(value).toFixed(4);
                        } else if (col === 'subject' || col === 'skip_reason' || col === 'project_name') {
                            value = `<span class="truncate" title="${value}">${value}</span>`;
                        }
                        
                        html += `<td>${value}</td>`;
                    });
                    html += `<td><button class="btn btn-sm" onclick="showDetail('${currentTable}', ${row.id})">View</button></td>`;
                    html += '</tr>';
                });
                
                html += '</tbody></table>';
                container.innerHTML = html;
                
            } catch (e) {
                container.innerHTML = `<div class="loading">Error: ${e.message}</div>`;
            }
        }
        
        async function showDetail(table, id) {
            const modal = document.getElementById('detail-modal');
            const content = document.getElementById('detail-content');
            
            try {
                let data;
                if (table === 'bid_tracker') {
                    const res = await fetch(`/api/db/bid-tracker/${id}`);
                    data = await res.json();
                } else {
                    // For other tables, find in current data
                    const endpoint = table === 'processing_log' ? '/api/db/processing-log' : '/api/db/gc-contacts';
                    const res = await fetch(endpoint);
                    const allData = await res.json();
                    data = allData.find(r => r.id === id);
                }
                
                if (!data) {
                    content.innerHTML = '<h2>Not Found</h2>';
                    modal.classList.add('show');
                    return;
                }
                
                let html = `<h2>${table.replace(/_/g, ' ').toUpperCase()} #${id}</h2>`;
                
                for (const [key, value] of Object.entries(data)) {
                    let displayValue = value;
                    if (value === null || value === undefined) {
                        displayValue = '<em style="color:#888">null</em>';
                    } else if (typeof value === 'object') {
                        displayValue = `<pre style="white-space:pre-wrap;font-size:12px">${JSON.stringify(value, null, 2)}</pre>`;
                    }
                    html += `
                        <div class="detail-row">
                            <div class="detail-label">${key}</div>
                            <div class="detail-value">${displayValue}</div>
                        </div>
                    `;
                }
                
                content.innerHTML = html;
                modal.classList.add('show');
                
            } catch (e) {
                content.innerHTML = `<h2>Error</h2><p>${e.message}</p>`;
                modal.classList.add('show');
            }
        }
        
        function closeModal() {
            document.getElementById('detail-modal').classList.remove('show');
        }
        
        // Close modal on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
        
        // Initial load
        document.getElementById('export-btn').href = '/api/db/export/bid_tracker';
        loadCurrentTable();
    </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    """Serve the dashboard"""
    return render_template_string(DASHBOARD_HTML)


@app.route("/database")
def database_viewer():
    """Serve the database viewer page"""
    return render_template_string(DATABASE_VIEWER_HTML)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    global db
    
    print("\n" + "="*60)
    print("ALL PAINTING LTD - BID/ADDENDUM AGENT")
    print("="*60)
    print(f"Dashboard: http://localhost:{config.DASHBOARD_PORT}")
    print(f"Monitoring: {config.MONITORED_EMAIL}")
    print(f"Forward To: {config.FORWARD_TO_EMAIL}")
    print(f"Check Interval: {config.CHECK_INTERVAL_SECONDS} seconds")
    print("-"*60)
    
    if config.ANTHROPIC_API_KEY:
        print(f"✅ Anthropic API Key: Configured")
        print(f"   Model: {config.ANTHROPIC_MODEL}")
    else:
        print(f"⚠️  Anthropic API Key: NOT CONFIGURED")
        print(f"   Set ANTHROPIC_API_KEY environment variable")
    
    if config.AZURE_CLIENT_SECRET and config.AZURE_CLIENT_SECRET != "YOUR_SECRET_HERE":
        print(f"✅ Azure Client Secret: Configured")
    else:
        print(f"⚠️  Azure Client Secret: NOT CONFIGURED")
        print(f"   Set AZURE_CLIENT_SECRET environment variable")
    
    print("-"*60)
    print(f"📝 Operation Mode: {config.OPERATION_MODE}")
    print(f"📁 Drafts Folder: {config.DRAFTS_FOLDER_NAME}")
    print("="*60)
    
    # Initialize database
    db = Database()
    
    # Start monitoring thread
    start_monitoring()
    
    # Run Flask app
    app.run(host=config.DASHBOARD_HOST, port=config.DASHBOARD_PORT, debug=False)


if __name__ == "__main__":
    main()
