"""
All Painting Ltd - Business Subhub
Secondary services dashboard (no dependency on the main hub).
Port: 5100 (default)
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template_string

from hub_utils.service_manager import ServiceManager, load_services

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

app = Flask(__name__)

CONFIG_PATH = (REPO_ROOT / "hub-config" / "subhub_services.json").resolve()
config_data = load_services(CONFIG_PATH)
SERVICES = config_data["services"]
HUB_NAME = config_data["hub_name"]

manager = ServiceManager(
    SERVICES,
    runtime_dir=BASE_DIR / "runtime",
    logs_dir=BASE_DIR / "logs",
)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ hub_name }}</title>
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
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
        }
        
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background-image: 
                linear-gradient(var(--border-color) 1px, transparent 1px),
                linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
            background-size: 50px 50px;
            opacity: 0.3;
            pointer-events: none;
            z-index: 0;
        }
        
        .container {
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 20px;
            position: relative;
            z-index: 1;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .logo {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--accent-blue);
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .title {
            font-size: 36px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 14px;
        }
        
        .master-controls {
            display: flex;
            justify-content: center;
            gap: 16px;
            margin-bottom: 40px;
        }
        
        .master-btn {
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            font-weight: 600;
            padding: 14px 32px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        
        .master-btn.start-all {
            background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%);
            color: #000;
            box-shadow: 0 4px 20px var(--accent-green-dim);
        }
        
        .master-btn.stop-all {
            background: linear-gradient(135deg, #ff4466 0%, #cc3355 100%);
            color: #fff;
            box-shadow: 0 4px 20px var(--accent-red-dim);
        }
        
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }
        
        .service-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            transition: all 0.3s ease;
        }
        
        .service-card.running {
            border-left: 3px solid var(--accent-green);
        }
        
        .service-card.stopped {
            border-left: 3px solid var(--accent-red);
        }
        
        .service-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }
        
        .service-name {
            font-size: 16px;
            font-weight: 600;
        }
        
        .service-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            text-transform: uppercase;
        }
        
        .status-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
        }
        
        .status-dot.running {
            background: var(--accent-green);
        }
        
        .status-dot.stopped {
            background: var(--accent-red);
        }
        
        .service-info {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 14px;
        }
        
        .service-actions {
            display: flex;
            gap: 8px;
        }
        
        .service-btn {
            flex: 1;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            font-weight: 600;
            padding: 8px 12px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .service-btn.start {
            background: var(--accent-green-dim);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }
        
        .service-btn.stop {
            background: var(--accent-red-dim);
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
        }
        
        .service-btn.open {
            background: transparent;
            color: var(--accent-blue);
            border: 1px solid var(--accent-blue);
        }
        
        .service-btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }
        
        @media (max-width: 768px) {
            .master-controls {
                flex-direction: column;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo">All Painting Ltd</div>
            <h1 class="title">{{ hub_name }}</h1>
            <p class="subtitle">Secondary Services Control Center</p>
        </header>
        
        <div class="master-controls">
            <button class="master-btn start-all" onclick="startAll()">▶ Start All</button>
            <button class="master-btn stop-all" onclick="stopAll()">■ Stop All</button>
        </div>
        
        <div class="services-grid" id="services-grid"></div>
    </div>
    <script>
        const services = {{ services | tojson }};
        let statuses = {};
        let loading = {};
        
        function renderServices() {
            const grid = document.getElementById('services-grid');
            let html = '';
            
            for (const [id, service] of Object.entries(services)) {
                const isRunning = statuses[id] || false;
                const isLoading = loading[id] || false;
                
                html += `
                    <div class="service-card ${isRunning ? 'running' : 'stopped'}">
                        <div class="service-header">
                            <div class="service-name">${service.name}</div>
                            <div class="service-status">
                                <div class="status-dot ${isRunning ? 'running' : 'stopped'}"></div>
                                ${isRunning ? 'Running' : 'Stopped'}
                            </div>
                        </div>
                        <div class="service-info">
                            ${service.port ? `<span>:${service.port}</span>` : '<span>Background</span>'}
                        </div>
                        <div class="service-actions">
                            <button class="service-btn start"
                                    onclick="startService('${id}')"
                                    ${isRunning || isLoading ? 'disabled' : ''}>
                                Start
                            </button>
                            <button class="service-btn stop"
                                    onclick="stopService('${id}')"
                                    ${!isRunning || isLoading ? 'disabled' : ''}>
                                Stop
                            </button>
                            ${service.has_ui ? `
                                <button class="service-btn open"
                                        onclick="openService('${id}')"
                                        ${!isRunning ? 'disabled' : ''}>
                                    Open
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
            }
            
            grid.innerHTML = html;
        }
        
        async function fetchStatuses() {
            const response = await fetch('/api/status');
            statuses = await response.json();
            renderServices();
        }
        
        async function startService(id) {
            loading[id] = true;
            renderServices();
            await fetch(`/api/start/${id}`, { method: 'POST' });
            loading[id] = false;
            setTimeout(fetchStatuses, 1000);
        }
        
        async function stopService(id) {
            loading[id] = true;
            renderServices();
            await fetch(`/api/stop/${id}`, { method: 'POST' });
            loading[id] = false;
            setTimeout(fetchStatuses, 500);
        }
        
        function openService(id) {
            const port = services[id].port;
            if (port) {
                window.open(`http://localhost:${port}`, '_blank');
            }
        }
        
        async function startAll() {
            await fetch('/api/start-all', { method: 'POST' });
            setTimeout(fetchStatuses, 1500);
        }
        
        async function stopAll() {
            await fetch('/api/stop-all', { method: 'POST' });
            setTimeout(fetchStatuses, 500);
        }
        
        fetchStatuses();
        setInterval(fetchStatuses, 5000);
    </script>
</body>
</html>
'''


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, services=SERVICES, hub_name=HUB_NAME)


@app.route('/api/status')
def api_status():
    return jsonify(manager.get_all_statuses())


@app.route('/api/start/<service_id>', methods=['POST'])
def api_start(service_id):
    if service_id not in SERVICES:
        return jsonify({'success': False, 'error': 'Unknown service'})
    try:
        result = manager.start_service(service_id)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/stop/<service_id>', methods=['POST'])
def api_stop(service_id):
    if service_id not in SERVICES:
        return jsonify({'success': False, 'error': 'Unknown service'})
    try:
        result = manager.stop_service(service_id)
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/start-all', methods=['POST'])
def api_start_all():
    results = []
    for service_id in SERVICES:
        if not manager.get_status(service_id):
            try:
                result = manager.start_service(service_id)
                results.append({'service': service_id, 'success': True, 'result': result})
            except Exception as e:
                results.append({'service': service_id, 'success': False, 'error': str(e)})
    return jsonify({'success': True, 'results': results})


@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    results = []
    for service_id in SERVICES:
        try:
            result = manager.stop_service(service_id)
            results.append({'service': service_id, 'success': True, 'result': result})
        except Exception as e:
            results.append({'service': service_id, 'success': False, 'error': str(e)})
    return jsonify({'success': True, 'results': results})


if __name__ == '__main__':
    print("=" * 60)
    print(f"  ALL PAINTING LTD - {HUB_NAME}")
    port = int(os.environ.get("SUBHUB_DASHBOARD_PORT", "5100"))
    print(f"  http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
