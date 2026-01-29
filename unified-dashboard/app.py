"""
All Painting Ltd - Unified Business Hub
Professional dashboard integrating all microservices
Port: 5050
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import requests
from functools import wraps

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template, request, redirect, url_for

from hub_utils.service_manager import ServiceManager, load_services

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "unified-hub-secret-key")

CONFIG_PATH = REPO_ROOT / "hub-config" / "main_services.json"
RUNTIME_DIR = REPO_ROOT / "runtime"
LOGS_DIR = REPO_ROOT / "logs"

# Service endpoints for API aggregation
SERVICE_ENDPOINTS = {
    "ai-agent": "http://localhost:5011",
    "bid-addendum-agent": "http://localhost:5012",
    "bid-center": "http://localhost:3030",
    "bid-email-scanner": "http://localhost:3031",
    "bid-pipedrive-sync": "http://localhost:3032",
    "bid-calendar": "http://localhost:3033",
    "bid-notifications": "http://localhost:3034",
    "bid-quote-sent-mover": "http://localhost:3035",
    "bid-followup-creator": "http://localhost:3036",
    "estimate-generator": "http://localhost:5000",
    "invoice-generator": "http://localhost:5001",
    "invoice-converter": "http://localhost:5005",
    "followup-manager": "http://localhost:1000",
    "payroll-app": "http://localhost:5003",
    "quickbooks-sync": "http://localhost:5015",
}

# Service groupings for the dashboard
SERVICE_GROUPS = {
    "bid_management": {
        "name": "Bid Management",
        "icon": "briefcase",
        "services": ["bid-center", "bid-email-scanner", "bid-pipedrive-sync",
                     "bid-calendar", "bid-notifications", "bid-quote-sent-mover",
                     "bid-followup-creator", "bid-addendum-agent"]
    },
    "estimates": {
        "name": "Estimates",
        "icon": "file-text",
        "services": ["estimate-generator", "ai-agent"]
    },
    "invoicing": {
        "name": "Invoicing",
        "icon": "dollar-sign",
        "services": ["invoice-generator", "invoice-converter", "quickbooks-sync"]
    },
    "followups": {
        "name": "Follow-ups",
        "icon": "mail",
        "services": ["followup-manager"]
    },
    "payroll": {
        "name": "Payroll",
        "icon": "users",
        "services": ["payroll-app"]
    }
}


def get_service_manager():
    """Get or create ServiceManager instance."""
    config = load_services(CONFIG_PATH)
    return ServiceManager(
        services=config["services"],
        runtime_dir=RUNTIME_DIR,
        logs_dir=LOGS_DIR
    )


def safe_request(url, method="GET", timeout=5, **kwargs):
    """Make a safe HTTP request with error handling."""
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout, **kwargs)
        elif method == "POST":
            resp = requests.post(url, timeout=timeout, **kwargs)
        else:
            return None
        return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    except Exception:
        return None


# =============================================================================
# MAIN DASHBOARD ROUTES
# =============================================================================

@app.route("/")
def dashboard():
    """Main dashboard with overview of all services."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Calculate stats
    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("dashboard.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          service_groups=SERVICE_GROUPS,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="dashboard")


@app.route("/bids")
def bids_page():
    """Bid management page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Try to get bids from bid-email-scanner
    bids = []
    bids_data = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids", timeout=3)
    if bids_data and isinstance(bids_data, dict):
        bids = bids_data.get("bids", [])

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("bids.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          bids=bids,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="bids")


@app.route("/estimates")
def estimates_page():
    """Estimates management page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Try to get AI agent stats
    ai_stats = safe_request(f"{SERVICE_ENDPOINTS['ai-agent']}/api/stats", timeout=3)

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("estimates.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          ai_stats=ai_stats,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="estimates")


@app.route("/invoices")
def invoices_page():
    """Invoices management page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Try to get invoice counter
    counter_data = safe_request(f"{SERVICE_ENDPOINTS['invoice-generator']}/api/counter", timeout=3)

    # Try to get QB status
    qb_status = safe_request(f"{SERVICE_ENDPOINTS['quickbooks-sync']}/api/status", timeout=3)

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("invoices.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          counter_data=counter_data,
                          qb_status=qb_status,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="invoices")


@app.route("/followups")
def followups_page():
    """Follow-ups management page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Try to get followup data
    followups = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/followups/pending", timeout=3)
    estimates = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/estimates", timeout=3)

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("followups.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          followups=followups,
                          estimates=estimates,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="followups")


@app.route("/payroll")
def payroll_page():
    """Payroll management page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    # Try to get payroll stats
    payroll_stats = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/stats", timeout=3)
    pending = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/pending", timeout=3)

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("payroll.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          payroll_stats=payroll_stats,
                          pending_payments=pending,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="payroll")


@app.route("/services")
def services_page():
    """Service control page."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)

    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running

    return render_template("services.html",
                          hub_name=config["hub_name"],
                          services=config["services"],
                          statuses=statuses,
                          service_groups=SERVICE_GROUPS,
                          running_count=running,
                          stopped_count=stopped,
                          current_page="services")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route("/api/status")
def api_status():
    """Get all service statuses."""
    manager = get_service_manager()
    return jsonify(manager.get_all_statuses())


@app.route("/api/start/<service_id>", methods=["POST"])
def api_start_service(service_id):
    """Start a specific service."""
    manager = get_service_manager()
    try:
        result = manager.start_service(service_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/stop/<service_id>", methods=["POST"])
def api_stop_service(service_id):
    """Stop a specific service."""
    manager = get_service_manager()
    try:
        result = manager.stop_service(service_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/start-all", methods=["POST"])
def api_start_all():
    """Start all services."""
    manager = get_service_manager()
    results = {}
    for service_id in manager.services:
        try:
            results[service_id] = manager.start_service(service_id)
        except Exception as e:
            results[service_id] = {"success": False, "error": str(e)}
    return jsonify(results)


@app.route("/api/stop-all", methods=["POST"])
def api_stop_all():
    """Stop all services."""
    manager = get_service_manager()
    results = {}
    for service_id in manager.services:
        try:
            results[service_id] = manager.stop_service(service_id)
        except Exception as e:
            results[service_id] = {"success": False, "error": str(e)}
    return jsonify(results)


@app.route("/api/overview")
def api_overview():
    """Get dashboard overview data."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()

    # Aggregate data from services
    overview = {
        "services": {
            "running": sum(1 for s in statuses.values() if s),
            "stopped": sum(1 for s in statuses.values() if not s),
            "total": len(statuses)
        },
        "bids": {"active": 0, "due_today": 0, "due_tomorrow": 0},
        "estimates": {"pending_validation": 0, "validated_today": 0},
        "invoices": {"generated_today": 0, "pending_qb": 0},
        "followups": {"pending": 0, "overdue": 0},
        "payroll": {"pending_payments": 0}
    }

    # Try to get bid stats
    if statuses.get("bid-email-scanner"):
        bids_due_today = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids/due-today", timeout=2)
        if bids_due_today:
            overview["bids"]["due_today"] = len(bids_due_today.get("bids", []))

        bids_due_tomorrow = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids/due-tomorrow", timeout=2)
        if bids_due_tomorrow:
            overview["bids"]["due_tomorrow"] = len(bids_due_tomorrow.get("bids", []))

        all_bids = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids", timeout=2)
        if all_bids:
            overview["bids"]["active"] = len(all_bids.get("bids", []))

    # Try to get followup stats
    if statuses.get("followup-manager"):
        pending = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/followups/pending", timeout=2)
        if pending:
            overview["followups"]["pending"] = len(pending) if isinstance(pending, list) else pending.get("count", 0)

    # Try to get payroll stats
    if statuses.get("payroll-app"):
        payroll_pending = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/pending", timeout=2)
        if payroll_pending:
            overview["payroll"]["pending_payments"] = len(payroll_pending) if isinstance(payroll_pending, list) else 0

    return jsonify(overview)


@app.route("/api/activity")
def api_activity():
    """Get recent activity across services."""
    activity = []

    # This would aggregate recent activity from all services
    # For now, return placeholder
    activity = [
        {"time": datetime.now().isoformat(), "type": "info", "message": "Dashboard started"},
    ]

    return jsonify(activity)


# =============================================================================
# PROXY ENDPOINTS - Forward to underlying services
# =============================================================================

@app.route("/api/proxy/<service_id>/<path:endpoint>", methods=["GET", "POST"])
def api_proxy(service_id, endpoint):
    """Proxy requests to underlying services."""
    if service_id not in SERVICE_ENDPOINTS:
        return jsonify({"error": "Unknown service"}), 404

    url = f"{SERVICE_ENDPOINTS[service_id]}/{endpoint}"

    try:
        if request.method == "POST":
            resp = requests.post(url, json=request.get_json(), timeout=30)
        else:
            resp = requests.get(url, params=request.args, timeout=30)

        return jsonify(resp.json()) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def api_health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
