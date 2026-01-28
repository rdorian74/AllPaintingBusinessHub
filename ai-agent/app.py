"""
AI Agent Service - Flask API
All Painting Ltd.

Validates estimate PDFs before sending to clients.

Features:
- PDF validation with Claude AI
- Word vs PDF comparison
- Auto-correction (regenerate if issues found)
- Cost tracking
"""
from flask import Flask, request, jsonify, render_template_string
import config
import database as db
from validator import validate_estimate
from datetime import datetime

app = Flask(__name__)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route("/api/validate", methods=["POST"])
def validate():
    """
    Validate an estimate PDF
    
    Expected JSON payload:
    {
        "pdf_path": "/path/to/estimate.pdf",
        "extracted_data": {...},
        "estimate_code": "25C-319",
        "word_path": "/path/to/original.docx"  (optional, for comparison)
    }
    
    Returns:
    {
        "passed": true/false,
        "issues": ["issue1", "issue2"],
        "confidence_score": 0-100,
        "cost": 0.00,
        "action_recommended": "send" | "draft" | "review",
        "attempts": 1,
        "auto_corrected": false
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        pdf_path = data.get("pdf_path")
        extracted_data = data.get("extracted_data", {})
        estimate_code = data.get("estimate_code", "UNKNOWN")
        word_path = data.get("word_path")  # Optional - for Word vs PDF comparison
        
        if not pdf_path:
            return jsonify({"error": "pdf_path is required"}), 400
        
        print(f"\n🤖 Validating estimate {estimate_code}...")
        print(f"   PDF: {pdf_path}")
        if word_path:
            print(f"   Word: {word_path}")
        
        # Run validation (with auto-correction if enabled)
        result = validate_estimate(
            pdf_path=pdf_path,
            extracted_data=extracted_data,
            estimate_code=estimate_code,
            word_path=word_path
        )
        
        # Determine recommended action
        if not result["passed"]:
            action = "review"
        elif result["confidence_score"] >= config.MIN_CONFIDENCE_SCORE:
            action = "send"  # Ready for auto-send if in auto mode
        else:
            action = "draft"  # Create draft for review
        
        result["action_recommended"] = action
        
        # Log to database
        db.add_validation(
            estimate_code=estimate_code,
            pdf_path=pdf_path,
            passed=result["passed"],
            issues=result.get("issues", []),
            confidence_score=result.get("confidence_score", 0),
            action_taken=action,
            cost_usd=result.get("cost", 0),
            input_tokens=result.get("input_tokens", 0),
            output_tokens=result.get("output_tokens", 0),
            processing_time_ms=result.get("processing_time_ms", 0),
            attempts=result.get("attempts", 1),
            auto_corrected=result.get("auto_corrected", False)
        )
        
        # Log summary
        if result.get("auto_corrected"):
            print(f"   ✅ Result: PASSED (auto-corrected after {result.get('attempts')} attempts)")
        elif result["passed"]:
            print(f"   ✅ Result: PASSED, confidence={result['confidence_score']}%")
        else:
            print(f"   ❌ Result: FAILED, issues={result.get('issues', [])}")
        
        return jsonify(result)
    
    except Exception as e:
        print(f"❌ Error in /api/validate: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/status", methods=["GET"])
def status():
    """Get agent status"""
    try:
        stats = db.get_stats()
        mode = db.get_setting("mode", "review")
        
        return jsonify({
            "running": True,
            "mode": mode,
            "stats": stats,
            "api_configured": bool(config.ANTHROPIC_API_KEY),
            "auto_correction_enabled": config.AUTO_CORRECTION_ENABLED,
            "max_attempts": config.MAX_REGENERATION_ATTEMPTS,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/set-mode", methods=["POST"])
def set_mode():
    """
    Set the operation mode
    
    Expected JSON payload:
    {
        "mode": "review" | "auto"
    }
    """
    try:
        data = request.get_json()
        mode = data.get("mode")
        
        if mode not in ["review", "auto"]:
            return jsonify({"error": "Mode must be 'review' or 'auto'"}), 400
        
        db.set_setting("mode", mode)
        
        print(f"🔄 Mode changed to: {mode}")
        
        return jsonify({
            "success": True,
            "mode": mode,
            "message": f"Mode set to {mode}"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
def history():
    """Get validation history"""
    try:
        limit = request.args.get("limit", 50, type=int)
        records = db.get_validation_history(limit)
        return jsonify(records)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/costs", methods=["GET"])
def costs():
    """Get cost summary"""
    try:
        return jsonify({
            "today": db.get_costs("today"),
            "week": db.get_costs("week"),
            "month": db.get_costs("month"),
            "total": db.get_costs("total")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
def stats():
    """Get statistics"""
    try:
        return jsonify(db.get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def get_settings():
    """Get current settings"""
    try:
        return jsonify({
            "mode": db.get_setting("mode", "review"),
            "auto_correction_enabled": config.AUTO_CORRECTION_ENABLED,
            "max_regeneration_attempts": config.MAX_REGENERATION_ATTEMPTS,
            "min_confidence_score": config.MIN_CONFIDENCE_SCORE
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# DASHBOARD
# =============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Agent Dashboard - All Painting Ltd</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        
        .header {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px 30px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 24px; }
        .header .status {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #00ff88;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        .card h2 {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #888;
            margin-bottom: 15px;
        }
        
        .mode-selector {
            display: flex;
            gap: 10px;
        }
        .mode-btn {
            flex: 1;
            padding: 15px;
            border: 2px solid rgba(255,255,255,0.2);
            background: transparent;
            color: #fff;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .mode-btn:hover { border-color: rgba(255,255,255,0.5); }
        .mode-btn.active {
            background: #4CAF50;
            border-color: #4CAF50;
        }
        .mode-btn.auto.active {
            background: #ff9800;
            border-color: #ff9800;
        }
        
        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }
        .stat {
            text-align: center;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        .stat-value { font-size: 28px; font-weight: bold; color: #00ff88; }
        .stat-label { font-size: 12px; color: #888; margin-top: 5px; }
        
        .cost-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .cost-item:last-child { border-bottom: none; }
        .cost-value { font-weight: bold; color: #00ff88; }
        
        .history-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            margin-bottom: 10px;
        }
        .history-item .code { font-weight: bold; }
        .history-item .time { color: #888; font-size: 12px; }
        .history-item .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
        }
        .status-badge.passed { background: #4CAF50; }
        .status-badge.failed { background: #f44336; }
        .status-badge.corrected { background: #2196F3; }
        
        .confidence-bar {
            height: 6px;
            background: rgba(255,255,255,0.1);
            border-radius: 3px;
            margin-top: 5px;
            overflow: hidden;
        }
        .confidence-fill {
            height: 100%;
            background: linear-gradient(90deg, #ff9800, #4CAF50);
            border-radius: 3px;
            transition: width 0.3s;
        }
        
        .api-warning {
            background: rgba(255,152,0,0.2);
            border: 1px solid #ff9800;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }
        
        .feature-badge {
            display: inline-block;
            padding: 4px 8px;
            background: rgba(33, 150, 243, 0.3);
            border-radius: 4px;
            font-size: 11px;
            margin-left: 10px;
        }
        
        .attempts-badge {
            font-size: 10px;
            color: #2196F3;
            margin-left: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>🤖 AI Agent Dashboard</h1>
                <span class="feature-badge">Auto-Correction Enabled</span>
            </div>
            <div class="status">
                <div class="status-dot"></div>
                <span>Agent Active</span>
            </div>
        </div>
        
        <div id="api-warning" class="api-warning" style="display: none;">
            ⚠️ <strong>API Key not configured.</strong> 
            Set ANTHROPIC_API_KEY environment variable for AI validation.
        </div>
        
        <div class="grid">
            <!-- Mode Selection -->
            <div class="card">
                <h2>Operation Mode</h2>
                <div class="mode-selector">
                    <button class="mode-btn review" onclick="setMode('review')">
                        📝 Review Mode<br>
                        <small>Create drafts for review</small>
                    </button>
                    <button class="mode-btn auto" onclick="setMode('auto')">
                        ⚡ Auto Mode<br>
                        <small>Send emails directly</small>
                    </button>
                </div>
            </div>
            
            <!-- Statistics -->
            <div class="card">
                <h2>Statistics</h2>
                <div class="stat-grid">
                    <div class="stat">
                        <div class="stat-value" id="total-validations">0</div>
                        <div class="stat-label">Total Validated</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="success-rate">0%</div>
                        <div class="stat-label">Success Rate</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="today-count">0</div>
                        <div class="stat-label">Today</div>
                    </div>
                    <div class="stat">
                        <div class="stat-value" id="auto-corrected">0</div>
                        <div class="stat-label">Auto-Corrected</div>
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
            
            <!-- Recent Activity -->
            <div class="card" style="grid-column: span 2;">
                <h2>Recent Activity</h2>
                <div id="history-list">
                    <p style="color: #888;">No validations yet</p>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentMode = 'review';
        
        async function loadStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                currentMode = data.mode;
                updateModeButtons();
                
                // Show API warning if not configured
                document.getElementById('api-warning').style.display = 
                    data.api_configured ? 'none' : 'block';
                
                // Update stats
                if (data.stats) {
                    document.getElementById('total-validations').textContent = data.stats.total_validations;
                    document.getElementById('success-rate').textContent = data.stats.success_rate + '%';
                    document.getElementById('today-count').textContent = data.stats.today_count;
                    document.getElementById('auto-corrected').textContent = data.stats.auto_corrected || 0;
                }
            } catch (e) {
                console.error('Error loading status:', e);
            }
        }
        
        async function loadCosts() {
            try {
                const res = await fetch('/api/costs');
                const data = await res.json();
                
                document.getElementById('cost-today').textContent = '$' + data.today.total_cost.toFixed(2);
                document.getElementById('cost-week').textContent = '$' + data.week.total_cost.toFixed(2);
                document.getElementById('cost-month').textContent = '$' + data.month.total_cost.toFixed(2);
                document.getElementById('cost-total').textContent = '$' + data.total.total_cost.toFixed(2);
            } catch (e) {
                console.error('Error loading costs:', e);
            }
        }
        
        async function loadHistory() {
            try {
                const res = await fetch('/api/history?limit=10');
                const data = await res.json();
                
                const list = document.getElementById('history-list');
                
                if (data.length === 0) {
                    list.innerHTML = '<p style="color: #888;">No validations yet</p>';
                    return;
                }
                
                list.innerHTML = data.map(item => {
                    const time = new Date(item.created_at).toLocaleTimeString();
                    const date = new Date(item.created_at).toLocaleDateString();
                    let statusClass = item.validation_passed ? 'passed' : 'failed';
                    let statusText = item.validation_passed ? '✓ Passed' : '✗ Failed';
                    
                    if (item.auto_corrected) {
                        statusClass = 'corrected';
                        statusText = '🔄 Auto-Fixed';
                    }
                    
                    const attemptsText = item.attempts > 1 ? 
                        `<span class="attempts-badge">(${item.attempts} attempts)</span>` : '';
                    
                    return `
                        <div class="history-item">
                            <div>
                                <div class="code">${item.estimate_code} ${attemptsText}</div>
                                <div class="time">${date} ${time}</div>
                            </div>
                            <div style="text-align: right;">
                                <div class="status-badge ${statusClass}">${statusText}</div>
                                <div class="confidence-bar" style="width: 100px;">
                                    <div class="confidence-fill" style="width: ${item.confidence_score}%"></div>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (e) {
                console.error('Error loading history:', e);
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
                }
            } catch (e) {
                console.error('Error setting mode:', e);
            }
        }
        
        // Initial load
        loadStatus();
        loadCosts();
        loadHistory();
        
        // Refresh every 30 seconds
        setInterval(() => {
            loadStatus();
            loadCosts();
            loadHistory();
        }, 30000);
    </script>
</body>
</html>
"""


@app.route("/")
def dashboard():
    """Serve the dashboard"""
    return render_template_string(DASHBOARD_HTML)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point"""
    print("\n" + "="*60)
    print("ALL PAINTING LTD - AI AGENT SERVICE")
    print("="*60)
    print(f"Port: {config.PORT}")
    print(f"Dashboard: http://localhost:{config.PORT}")
    print(f"API Endpoint: http://localhost:{config.PORT}/api/validate")
    print("-"*60)
    
    if config.ANTHROPIC_API_KEY:
        print(f"✅ Anthropic API Key: Configured")
        print(f"   Model: {config.ANTHROPIC_MODEL}")
    else:
        print(f"⚠️  Anthropic API Key: NOT CONFIGURED")
        print(f"   Set ANTHROPIC_API_KEY environment variable")
        print(f"   Basic validation will still work")
    
    print("-"*60)
    print(f"🔄 Auto-Correction: {'ENABLED' if config.AUTO_CORRECTION_ENABLED else 'DISABLED'}")
    if config.AUTO_CORRECTION_ENABLED:
        print(f"   Max Attempts: {config.MAX_REGENERATION_ATTEMPTS}")
        print(f"   Estimate Generator: {config.ESTIMATE_GENERATOR_URL}")
    
    print("="*60)
    
    # Initialize database
    db.init_database()
    
    # Run Flask app
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
    main()
