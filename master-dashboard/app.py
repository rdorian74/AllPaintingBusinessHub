"""
All Painting Ltd - Master Service Dashboard
Controls all microservices from a single interface.
Port: 5099 (default)

Self-contained single file - no external templates or modules needed.
Just Flask + standard library.
"""

from flask import Flask, render_template_string, jsonify
import subprocess
import socket
import os
import sys
import time
import signal
import json

app = Flask(__name__)

# Auto-detect repo root from this script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)

# ---------------------------------------------------------------------------
# Service configuration - all 16 services
# Paths are relative to REPO_ROOT; resolved at runtime.
# ---------------------------------------------------------------------------
SERVICES = {
    'ai-agent': {
        'name': 'AI Agent',
        'port': 5011,
        'path': 'ai-agent',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'bid-addendum-agent': {
        'name': 'Bid/Addendum Agent',
        'port': 5012,
        'path': 'bid-addendum-agent',
        'script': 'main.py',
        'has_venv': True,
        'has_ui': True,
    },
    'bid-center': {
        'name': 'Bid Center',
        'port': 3030,
        'path': os.path.join('bid-system-v2', 'bid-center'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'bid-email-scanner': {
        'name': 'Bid Email Scanner',
        'port': 3031,
        'path': os.path.join('bid-system-v2', 'bid-email-scanner'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'bid-pipedrive-sync': {
        'name': 'Bid Pipedrive Sync',
        'port': 3032,
        'path': os.path.join('bid-system-v2', 'bid-pipedrive-sync'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'bid-calendar': {
        'name': 'Bid Calendar',
        'port': 3033,
        'path': os.path.join('bid-system-v2', 'bid-calendar'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'bid-notifications': {
        'name': 'Bid Notifications',
        'port': 3034,
        'path': os.path.join('bid-system-v2', 'bid-notifications'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'bid-quote-sent-mover': {
        'name': 'Bid Quote Sent Mover',
        'port': 3035,
        'path': os.path.join('bid-system-v2', 'bid-quote-sent-mover'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'bid-followup-creator': {
        'name': 'Bid Follow-up Creator',
        'port': 3036,
        'path': os.path.join('bid-system-v2', 'bid-followup-creator'),
        'script': 'app.py',
        'has_venv': True,
        'has_ui': False,
    },
    'estimate-generator': {
        'name': 'Estimate Generator',
        'port': 5000,
        'path': 'estimate-generator',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'invoice-generator': {
        'name': 'Invoice Generator',
        'port': 5001,
        'path': 'invoice-generator',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'invoice-converter': {
        'name': 'Invoice Converter',
        'port': 5005,
        'path': 'invoice_converter',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'followup-manager': {
        'name': 'Follow Up Manager',
        'port': 1000,
        'path': 'followup-manager',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'payroll-app': {
        'name': 'Payroll App',
        'port': 5003,
        'path': 'payroll_app',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
    'quickbooks-sync': {
        'name': 'QuickBooks Sync',
        'port': 5015,
        'path': 'quickbooks-sync',
        'script': 'app.py',
        'has_venv': True,
        'has_ui': True,
    },
}


# ---------------------------------------------------------------------------
# Service management helpers
# ---------------------------------------------------------------------------
def _service_path(service):
    """Get the full filesystem path for a service."""
    return os.path.join(REPO_ROOT, service['path'])


def is_port_in_use(port):
    """Check if a port is in use."""
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


def get_service_status(service_id):
    """Get status of a service by checking its port."""
    service = SERVICES.get(service_id)
    if not service:
        return False
    return is_port_in_use(service['port'])


def get_all_statuses():
    """Get status of all services."""
    return {sid: get_service_status(sid) for sid in SERVICES}


def _find_python(service_path, has_venv):
    """Find the right Python executable for a service."""
    if has_venv:
        if os.name == 'nt':
            venv_python = os.path.join(service_path, 'venv', 'Scripts', 'python.exe')
        else:
            venv_python = os.path.join(service_path, 'venv', 'bin', 'python')
        if os.path.exists(venv_python):
            return venv_python
    return sys.executable


def start_service(service_id):
    """Start a service."""
    service = SERVICES[service_id]
    path = _service_path(service)
    script = service['script']
    python_exe = _find_python(path, service.get('has_venv', False))

    if os.name == 'nt':
        # Windows: open a new cmd window for the service
        title = f"{service['name']} - Port {service['port']}"
        batch_cmd = f'cd /d "{path}" && "{python_exe}" {script}'
        full_cmd = f'start "{title}" cmd /k "{batch_cmd}"'
        subprocess.Popen(full_cmd, shell=True)
    else:
        # Linux/Mac: run in background, redirect output to log file
        log_dir = os.path.join(REPO_ROOT, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f'{service_id}.log')
        log_handle = open(log_file, 'a')
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        proc = subprocess.Popen(
            [python_exe, script],
            cwd=path,
            stdout=log_handle,
            stderr=log_handle,
            env=env,
            start_new_session=True,
        )
        # Save PID for later stop
        _save_pid(service_id, proc.pid)

    return {'success': True}


def stop_service(service_id):
    """Stop a service by killing the process on its port."""
    service = SERVICES[service_id]
    port = service['port']

    if os.name == 'nt':
        # Windows: kill by port using PowerShell
        if port:
            ps_cmd = (
                f"$c = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue "
                f"| Where-Object {{ $_.State -eq 'Listen' }}; "
                f"if ($c) {{ Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }}"
            )
            subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True)
    else:
        # Linux: kill by saved PID or by port
        pid = _load_pid(service_id)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            _save_pid(service_id, None)
        # Also try lsof as fallback
        if port:
            try:
                subprocess.run(
                    ['fuser', '-k', f'{port}/tcp'],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass

    return {'success': True}


# Simple PID tracking for Linux (Windows uses port-based kill)
_PID_FILE = os.path.join(BASE_DIR, 'service_pids.json')


def _load_pid(service_id):
    try:
        with open(_PID_FILE, 'r') as f:
            pids = json.load(f)
        return pids.get(service_id)
    except Exception:
        return None


def _save_pid(service_id, pid):
    try:
        pids = {}
        if os.path.exists(_PID_FILE):
            with open(_PID_FILE, 'r') as f:
                pids = json.load(f)
        if pid is None:
            pids.pop(service_id, None)
        else:
            pids[service_id] = pid
        with open(_PID_FILE, 'w') as f:
            json.dump(pids, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTML template - fully inline, no external files needed
# ---------------------------------------------------------------------------
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>All Painting Ltd - Business Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a24;
            --bg-card-hover: #22222e;
            --accent-green: #00ff88;
            --accent-green-dim: #00ff8833;
            --accent-red: #ff4466;
            --accent-red-dim: #ff446633;
            --accent-blue: #4488ff;
            --text-primary: #ffffff;
            --text-secondary: #888899;
            --border-color: #2a2a3a;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        body::before {
            content: '';
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background-image:
                linear-gradient(var(--border-color) 1px, transparent 1px),
                linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
            background-size: 50px 50px;
            opacity: 0.3;
            pointer-events: none;
            z-index: 0;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 40px 20px; position: relative; z-index: 1; }
        .header { text-align: center; margin-bottom: 50px; }
        .logo { font-family: 'JetBrains Mono', monospace; font-size: 14px; color: var(--accent-green); letter-spacing: 4px; text-transform: uppercase; margin-bottom: 10px; }
        .title { font-size: 42px; font-weight: 700; background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 10px; }
        .subtitle { color: var(--text-secondary); font-size: 16px; }
        .master-controls { display: flex; justify-content: center; gap: 20px; margin-bottom: 50px; }
        .master-btn { font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 600; padding: 16px 40px; border: none; border-radius: 8px; cursor: pointer; transition: all 0.3s ease; text-transform: uppercase; letter-spacing: 2px; }
        .master-btn.start-all { background: linear-gradient(135deg, #00ff88, #00cc66); color: #000; box-shadow: 0 4px 20px var(--accent-green-dim); }
        .master-btn.start-all:hover { transform: translateY(-2px); box-shadow: 0 8px 30px var(--accent-green-dim); }
        .master-btn.stop-all { background: linear-gradient(135deg, #ff4466, #cc3355); color: #fff; box-shadow: 0 4px 20px var(--accent-red-dim); }
        .master-btn.stop-all:hover { transform: translateY(-2px); box-shadow: 0 8px 30px var(--accent-red-dim); }
        .master-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none !important; }
        .status-summary { display: flex; justify-content: center; gap: 40px; margin-bottom: 40px; padding: 20px; background: var(--bg-secondary); border-radius: 12px; border: 1px solid var(--border-color); }
        .status-item { text-align: center; }
        .status-count { font-family: 'JetBrains Mono', monospace; font-size: 36px; font-weight: 700; }
        .status-count.running { color: var(--accent-green); }
        .status-count.stopped { color: var(--accent-red); }
        .status-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 2px; margin-top: 5px; }
        .services-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
        .service-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; transition: all 0.3s ease; }
        .service-card:hover { background: var(--bg-card-hover); transform: translateY(-2px); border-color: var(--text-secondary); }
        .service-card.running { border-left: 3px solid var(--accent-green); }
        .service-card.stopped { border-left: 3px solid var(--accent-red); }
        .service-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; }
        .service-name { font-size: 18px; font-weight: 600; }
        .service-status { display: flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; }
        .status-dot.running { background: var(--accent-green); box-shadow: 0 0 10px var(--accent-green); animation: pulse 2s infinite; }
        .status-dot.stopped { background: var(--accent-red); }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .service-info { display: flex; gap: 20px; margin-bottom: 20px; font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--text-secondary); }
        .service-actions { display: flex; gap: 10px; }
        .service-btn { flex: 1; font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; padding: 10px 16px; border: none; border-radius: 6px; cursor: pointer; transition: all 0.2s ease; text-transform: uppercase; letter-spacing: 1px; }
        .service-btn.start { background: var(--accent-green-dim); color: var(--accent-green); border: 1px solid var(--accent-green); }
        .service-btn.start:hover:not(:disabled) { background: var(--accent-green); color: #000; }
        .service-btn.stop { background: var(--accent-red-dim); color: var(--accent-red); border: 1px solid var(--accent-red); }
        .service-btn.stop:hover:not(:disabled) { background: var(--accent-red); color: #fff; }
        .service-btn.open { background: transparent; color: var(--accent-blue); border: 1px solid var(--accent-blue); }
        .service-btn.open:hover:not(:disabled) { background: var(--accent-blue); color: #fff; }
        .service-btn:disabled { opacity: 0.3; cursor: not-allowed; }
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid transparent; border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .toast-container { position: fixed; bottom: 20px; right: 20px; z-index: 1000; }
        .toast { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px 20px; margin-top: 10px; font-size: 14px; animation: slideIn 0.3s ease; display: flex; align-items: center; gap: 10px; }
        .toast.success { border-left: 3px solid var(--accent-green); }
        .toast.error { border-left: 3px solid var(--accent-red); }
        @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @media (max-width: 768px) { .title { font-size: 28px; } .master-controls { flex-direction: column; } .status-summary { flex-direction: column; gap: 20px; } .services-grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo">All Painting Ltd</div>
            <h1 class="title">Business Hub</h1>
            <p class="subtitle">Service Control Center</p>
        </header>

        <div class="master-controls">
            <button class="master-btn start-all" onclick="startAll()">Start All Services</button>
            <button class="master-btn stop-all" onclick="stopAll()">Stop All Services</button>
        </div>

        <div class="status-summary">
            <div class="status-item">
                <div class="status-count running" id="running-count">0</div>
                <div class="status-label">Running</div>
            </div>
            <div class="status-item">
                <div class="status-count stopped" id="stopped-count">0</div>
                <div class="status-label">Stopped</div>
            </div>
        </div>

        <div class="services-grid" id="services-grid"></div>
    </div>

    <div class="toast-container" id="toast-container"></div>

    <script>
        const services = {{ services | tojson }};
        let statuses = {};
        let loading = {};

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = 'toast ' + type;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        function renderServices() {
            const grid = document.getElementById('services-grid');
            let html = '';
            let runningCount = 0, stoppedCount = 0;

            for (const [id, svc] of Object.entries(services)) {
                const up = statuses[id] || false;
                const busy = loading[id] || false;
                if (up) runningCount++; else stoppedCount++;

                html += '<div class="service-card ' + (up ? 'running' : 'stopped') + '">'
                    + '<div class="service-header">'
                    + '  <div class="service-name">' + svc.name + '</div>'
                    + '  <div class="service-status">'
                    + '    <div class="status-dot ' + (up ? 'running' : 'stopped') + '"></div>'
                    + '    ' + (up ? 'Running' : 'Stopped')
                    + '  </div>'
                    + '</div>'
                    + '<div class="service-info"><span>:' + svc.port + '</span></div>'
                    + '<div class="service-actions">'
                    + '  <button class="service-btn start" onclick="startService(\'' + id + '\')" '
                    +       (up || busy ? 'disabled' : '') + '>'
                    +       (busy ? '<span class="spinner"></span>' : '') + 'Start</button>'
                    + '  <button class="service-btn stop" onclick="stopService(\'' + id + '\')" '
                    +       (!up || busy ? 'disabled' : '') + '>Stop</button>'
                    + (svc.has_ui
                        ? '  <button class="service-btn open" onclick="window.open(\'http://localhost:' + svc.port + '\')" '
                        +       (!up ? 'disabled' : '') + '>Open</button>'
                        : '')
                    + '</div></div>';
            }
            grid.innerHTML = html;
            document.getElementById('running-count').textContent = runningCount;
            document.getElementById('stopped-count').textContent = stoppedCount;
        }

        async function fetchStatuses() {
            try {
                const r = await fetch('/api/status');
                statuses = await r.json();
                renderServices();
            } catch (e) {
                console.error('Status fetch error:', e);
            }
        }

        async function startService(id) {
            loading[id] = true; renderServices();
            try {
                const r = await fetch('/api/start/' + id, { method: 'POST' });
                const d = await r.json();
                showToast(d.success ? services[id].name + ' started' : 'Failed: ' + (d.error || ''), d.success ? 'success' : 'error');
            } catch (e) { showToast('Error starting ' + services[id].name, 'error'); }
            loading[id] = false;
            setTimeout(fetchStatuses, 1500);
        }

        async function stopService(id) {
            loading[id] = true; renderServices();
            try {
                const r = await fetch('/api/stop/' + id, { method: 'POST' });
                const d = await r.json();
                showToast(d.success ? services[id].name + ' stopped' : 'Failed: ' + (d.error || ''), d.success ? 'success' : 'error');
            } catch (e) { showToast('Error stopping ' + services[id].name, 'error'); }
            loading[id] = false;
            setTimeout(fetchStatuses, 500);
        }

        async function startAll() {
            const btn = document.querySelector('.start-all');
            btn.disabled = true; btn.textContent = 'Starting...';
            try {
                await fetch('/api/start-all', { method: 'POST' });
                showToast('Starting all services...');
            } catch (e) { showToast('Error starting services', 'error'); }
            btn.disabled = false; btn.textContent = 'Start All Services';
            setTimeout(fetchStatuses, 3000);
        }

        async function stopAll() {
            const btn = document.querySelector('.stop-all');
            btn.disabled = true; btn.textContent = 'Stopping...';
            try {
                await fetch('/api/stop-all', { method: 'POST' });
                showToast('Stopping all services...');
            } catch (e) { showToast('Error stopping services', 'error'); }
            btn.disabled = false; btn.textContent = 'Stop All Services';
            setTimeout(fetchStatuses, 1000);
        }

        fetchStatuses();
        setInterval(fetchStatuses, 5000);
    </script>
</body>
</html>
'''


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, services=SERVICES)


@app.route('/api/status')
def api_status():
    return jsonify(get_all_statuses())


@app.route('/api/start/<service_id>', methods=['POST'])
def api_start(service_id):
    if service_id not in SERVICES:
        return jsonify({'success': False, 'error': 'Unknown service'})
    try:
        result = start_service(service_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/stop/<service_id>', methods=['POST'])
def api_stop(service_id):
    if service_id not in SERVICES:
        return jsonify({'success': False, 'error': 'Unknown service'})
    try:
        result = stop_service(service_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/start-all', methods=['POST'])
def api_start_all():
    results = []
    for service_id in SERVICES:
        if not get_service_status(service_id):
            try:
                result = start_service(service_id)
                results.append({'service': service_id, 'success': True})
                time.sleep(0.5)
            except Exception as e:
                results.append({'service': service_id, 'success': False, 'error': str(e)})
    return jsonify({'success': True, 'results': results})


@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    results = []
    for service_id in SERVICES:
        try:
            result = stop_service(service_id)
            results.append({'service': service_id, 'success': True})
        except Exception as e:
            results.append({'service': service_id, 'success': False, 'error': str(e)})
    return jsonify({'success': True, 'results': results})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('MASTER_DASHBOARD_PORT', '5099'))
    print('=' * 60)
    print('  ALL PAINTING LTD - BUSINESS HUB')
    print(f'  http://localhost:{port}')
    print(f'  Repo root: {REPO_ROOT}')
    print(f'  Services: {len(SERVICES)}')
    print('=' * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
