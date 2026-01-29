"""
All Painting Ltd - Unified Business Hub
Professional dashboard integrating all microservices
Port: 5050
"""

import os
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import requests
except ImportError:
    requests = None

from flask import Flask, jsonify, render_template, request

from hub_utils.service_manager import ServiceManager, load_services

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "unified-hub-secret-key")

CONFIG_PATH = REPO_ROOT / "hub-config" / "main_services.json"
RUNTIME_DIR = REPO_ROOT / "runtime"
LOGS_DIR = REPO_ROOT / "logs"

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
    config = load_services(CONFIG_PATH)
    return ServiceManager(
        services=config["services"],
        runtime_dir=RUNTIME_DIR,
        logs_dir=LOGS_DIR
    )


def safe_request(url, method="GET", timeout=5, **kwargs):
    if requests is None:
        return None
    try:
        if method == "GET":
            resp = requests.get(url, timeout=timeout, **kwargs)
        elif method == "POST":
            resp = requests.post(url, timeout=timeout, **kwargs)
        else:
            return None
        ct = resp.headers.get("content-type", "")
        return resp.json() if "json" in ct else resp.text
    except Exception:
        return None


def _base_context(current_page):
    """Build the base context dict every page needs."""
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
    config = load_services(CONFIG_PATH)
    running = sum(1 for s in statuses.values() if s)
    stopped = len(statuses) - running
    return {
        "hub_name": config.get("hub_name", "Business Hub"),
        "services": config.get("services", {}),
        "statuses": statuses,
        "service_groups": SERVICE_GROUPS,
        "running_count": running,
        "stopped_count": stopped,
        "current_page": current_page,
    }


# =============================================================================
# PAGE ROUTES - all wrapped in try/except to never return 500
# =============================================================================

@app.route("/")
def dashboard():
    try:
        ctx = _base_context("dashboard")
        return render_template("dashboard.html", **ctx)
    except Exception as e:
        return f"<h1>Dashboard Error</h1><pre>{e}</pre>", 500


@app.route("/bids")
def bids_page():
    try:
        ctx = _base_context("bids")
        bids = []
        data = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids", timeout=3)
        if isinstance(data, dict):
            bids = data.get("bids", [])
        ctx["bids"] = bids
        return render_template("bids.html", **ctx)
    except Exception as e:
        return f"<h1>Bids Error</h1><pre>{e}</pre>", 500


@app.route("/estimates")
def estimates_page():
    try:
        ctx = _base_context("estimates")
        ctx["ai_stats"] = safe_request(f"{SERVICE_ENDPOINTS['ai-agent']}/api/stats", timeout=3)
        return render_template("estimates.html", **ctx)
    except Exception as e:
        return f"<h1>Estimates Error</h1><pre>{e}</pre>", 500


@app.route("/invoices")
def invoices_page():
    try:
        ctx = _base_context("invoices")
        ctx["counter_data"] = safe_request(f"{SERVICE_ENDPOINTS['invoice-generator']}/api/counter", timeout=3)
        ctx["qb_status"] = safe_request(f"{SERVICE_ENDPOINTS['quickbooks-sync']}/api/status", timeout=3)
        return render_template("invoices.html", **ctx)
    except Exception as e:
        return f"<h1>Invoices Error</h1><pre>{e}</pre>", 500


@app.route("/followups")
def followups_page():
    try:
        ctx = _base_context("followups")
        ctx["followups"] = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/followups/pending", timeout=3)
        ctx["estimates"] = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/estimates", timeout=3)
        return render_template("followups.html", **ctx)
    except Exception as e:
        return f"<h1>Follow-ups Error</h1><pre>{e}</pre>", 500


@app.route("/payroll")
def payroll_page():
    try:
        ctx = _base_context("payroll")
        ctx["payroll_stats"] = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/stats", timeout=3)
        ctx["pending_payments"] = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/pending", timeout=3)
        return render_template("payroll.html", **ctx)
    except Exception as e:
        return f"<h1>Payroll Error</h1><pre>{e}</pre>", 500


@app.route("/services")
def services_page():
    try:
        ctx = _base_context("services")
        return render_template("services.html", **ctx)
    except Exception as e:
        return f"<h1>Services Error</h1><pre>{e}</pre>", 500


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.route("/api/status")
def api_status():
    manager = get_service_manager()
    return jsonify(manager.get_all_statuses())


@app.route("/api/start/<service_id>", methods=["POST"])
def api_start_service(service_id):
    manager = get_service_manager()
    try:
        return jsonify(manager.start_service(service_id))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/stop/<service_id>", methods=["POST"])
def api_stop_service(service_id):
    manager = get_service_manager()
    try:
        return jsonify(manager.stop_service(service_id))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/start-all", methods=["POST"])
def api_start_all():
    manager = get_service_manager()
    results = {}
    for sid in manager.services:
        try:
            results[sid] = manager.start_service(sid)
        except Exception as e:
            results[sid] = {"success": False, "error": str(e)}
    return jsonify(results)


@app.route("/api/stop-all", methods=["POST"])
def api_stop_all():
    manager = get_service_manager()
    results = {}
    for sid in manager.services:
        try:
            results[sid] = manager.stop_service(sid)
        except Exception as e:
            results[sid] = {"success": False, "error": str(e)}
    return jsonify(results)


@app.route("/api/overview")
def api_overview():
    manager = get_service_manager()
    statuses = manager.get_all_statuses()
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
    try:
        if statuses.get("bid-email-scanner"):
            r = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids/due-today", timeout=2)
            if isinstance(r, dict):
                overview["bids"]["due_today"] = len(r.get("bids", []))
            r = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids/due-tomorrow", timeout=2)
            if isinstance(r, dict):
                overview["bids"]["due_tomorrow"] = len(r.get("bids", []))
            r = safe_request(f"{SERVICE_ENDPOINTS['bid-email-scanner']}/api/bids", timeout=2)
            if isinstance(r, dict):
                overview["bids"]["active"] = len(r.get("bids", []))
        if statuses.get("followup-manager"):
            r = safe_request(f"{SERVICE_ENDPOINTS['followup-manager']}/api/followups/pending", timeout=2)
            if isinstance(r, list):
                overview["followups"]["pending"] = len(r)
            elif isinstance(r, dict):
                overview["followups"]["pending"] = r.get("count", 0)
        if statuses.get("payroll-app"):
            r = safe_request(f"{SERVICE_ENDPOINTS['payroll-app']}/api/pending", timeout=2)
            if isinstance(r, list):
                overview["payroll"]["pending_payments"] = len(r)
    except Exception:
        pass
    return jsonify(overview)


@app.route("/api/proxy/<service_id>/<path:endpoint>", methods=["GET", "POST"])
def api_proxy(service_id, endpoint):
    if service_id not in SERVICE_ENDPOINTS:
        return jsonify({"error": "Unknown service"}), 404
    url = f"{SERVICE_ENDPOINTS[service_id]}/{endpoint}"
    try:
        if request.method == "POST":
            resp = requests.post(url, json=request.get_json(), timeout=30)
        else:
            resp = requests.get(url, params=request.args, timeout=30)
        ct = resp.headers.get("content-type", "")
        return (jsonify(resp.json()), resp.status_code) if "json" in ct else (resp.text, resp.status_code)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/health")
def api_health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"\n{'='*60}")
    print("ALL PAINTING LTD - UNIFIED BUSINESS HUB")
    print(f"{'='*60}")
    print(f"Dashboard: http://localhost:{port}")
    print(f"{'='*60}\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
