"""
All Painting Ltd - Business Hub
Controls selected microservices from a single interface.
Port: 5099 (default)
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from flask import Flask, jsonify, render_template_string

from hub_utils.service_manager import ServiceManager, load_services
from flask import Flask, jsonify, render_template_string

from hub_utils.service_manager import ServiceManager, load_services

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

app = Flask(__name__)

CONFIG_PATH = (REPO_ROOT / "hub-config" / "main_services.json").resolve()
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
    <title>All Painting Ltd - Master Dashboard</title>
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
            --accent-yellow: #ffaa00;
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
        
        /* Animated background grid */
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image: 
                linear-gradient(var(--border-color) 1px, transparent 1px),
                linear-gradient(90deg, var(--border-color) 1px, transparent 1px);
            background-size: 50px 50px;
            opacity: 0.3;
            pointer-events: none;
            z-index: 0;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 40px 20px;
            position: relative;
            z-index: 1;
        }
        
        /* Header */
        .header {
            text-align: center;
            margin-bottom: 50px;
        }
        
        .logo {
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            color: var(--accent-green);
            letter-spacing: 4px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        
        .title {
            font-size: 42px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--text-primary) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        
        .subtitle {
            color: var(--text-secondary);
            font-size: 16px;
        }
        
        /* Master Controls */
        .master-controls {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 50px;
        }
        
        .master-btn {
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            font-weight: 600;
            padding: 16px 40px;
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
        
        .master-btn.start-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px var(--accent-green-dim);
        }
        
        .master-btn.stop-all {
            background: linear-gradient(135deg, #ff4466 0%, #cc3355 100%);
            color: #fff;
            box-shadow: 0 4px 20px var(--accent-red-dim);
        }
        
        .master-btn.stop-all:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px var(--accent-red-dim);
        }
        
        .master-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        /* Status summary */
        .status-summary {
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-bottom: 40px;
            padding: 20px;
            background: var(--bg-secondary);
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }
        
        .status-item {
            text-align: center;
        }
        
        .status-count {
            font-family: 'JetBrains Mono', monospace;
            font-size: 36px;
            font-weight: 700;
        }
        
        .status-count.running {
            color: var(--accent-green);
        }
        
        .status-count.stopped {
            color: var(--accent-red);
        }
        
        .status-label {
            font-size: 12px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-top: 5px;
        }
        
        /* Services grid */
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
        }
        
        .service-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .service-card:hover {
            background: var(--bg-card-hover);
            transform: translateY(-2px);
            border-color: var(--text-secondary);
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
            margin-bottom: 16px;
        }
        
        .service-name {
            font-size: 18px;
            font-weight: 600;
        }
        
        .service-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        .status-dot.running {
            background: var(--accent-green);
            box-shadow: 0 0 10px var(--accent-green);
        }
        
        .status-dot.stopped {
            background: var(--accent-red);
            animation: none;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .service-info {
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-secondary);
        }
        
        .service-info span {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        
        .service-actions {
            display: flex;
            gap: 10px;
        }
        
        .service-btn {
            flex: 1;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            font-weight: 600;
            padding: 10px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .service-btn.start {
            background: var(--accent-green-dim);
            color: var(--accent-green);
            border: 1px solid var(--accent-green);
        }
        
        .service-btn.start:hover:not(:disabled) {
            background: var(--accent-green);
            color: #000;
        }
        
        .service-btn.stop {
            background: var(--accent-red-dim);
            color: var(--accent-red);
            border: 1px solid var(--accent-red);
        }
        
        .service-btn.stop:hover:not(:disabled) {
            background: var(--accent-red);
            color: #fff;
        }
        
        .service-btn.open {
            background: transparent;
            color: var(--accent-blue);
            border: 1px solid var(--accent-blue);
        }
        
        .service-btn.open:hover:not(:disabled) {
            background: var(--accent-blue);
            color: #fff;
        }
        
        .service-btn:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }
        
        /* Loading spinner */
        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid transparent;
            border-top-color: currentColor;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Toast notifications */
        .toast-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 1000;
        }
        
        .toast {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 16px 20px;
            margin-top: 10px;
            font-size: 14px;
            animation: slideIn 0.3s ease;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .toast.success {
            border-left: 3px solid var(--accent-green);
        }
        
        .toast.error {
            border-left: 3px solid var(--accent-red);
        }
        
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .title {
                font-size: 28px;
            }
            
            .master-controls {
                flex-direction: column;
            }
            
            .status-summary {
                flex-direction: column;
                gap: 20px;
            }
            
            .services-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo">All Painting Ltd</div>
            <h1 class="title">{{ hub_name }}</h1>
            <p class="subtitle">Service Control Center</p>
        </header>
        
        <div class="master-controls">
            <button class="master-btn start-all" onclick="startAll()">
                ▶ Start All Services
            </button>
            <button class="master-btn stop-all" onclick="stopAll()">
                ■ Stop All Services
            </button>
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
        
        <div class="services-grid" id="services-grid">
            <!-- Services will be rendered here -->
        </div>
    </div>
    
    <div class="toast-container" id="toast-container"></div>
    
    <script>
        const services = {{ services | tojson }};
        let statuses = {};
        let loading = {};
        
        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `
                <span>${type === 'success' ? '✓' : '✗'}</span>
                <span>${message}</span>
            `;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }
        
        function renderServices() {
            const grid = document.getElementById('services-grid');
            let html = '';
            
            let runningCount = 0;
            let stoppedCount = 0;
            
            for (const [id, service] of Object.entries(services)) {
                const isRunning = statuses[id] || false;
                const isLoading = loading[id] || false;
                
                if (isRunning) runningCount++;
                else stoppedCount++;
                
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
                                ${isLoading ? '<span class="spinner"></span>' : ''}Start
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
            document.getElementById('running-count').textContent = runningCount;
            document.getElementById('stopped-count').textContent = stoppedCount;
        }
        
        async function fetchStatuses() {
            try {
                const response = await fetch('/api/status');
                statuses = await response.json();
                renderServices();
            } catch (error) {
                console.error('Error fetching statuses:', error);
            }
        }
        
        async function startService(id) {
            loading[id] = true;
            renderServices();
            
            try {
                const response = await fetch(`/api/start/${id}`, { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    showToast(`${services[id].name} started`);
                } else {
                    showToast(`Failed to start ${services[id].name}`, 'error');
                }
            } catch (error) {
                showToast(`Error starting ${services[id].name}`, 'error');
            }
            
            loading[id] = false;
            setTimeout(fetchStatuses, 1000);
        }
        
        async function stopService(id) {
            loading[id] = true;
            renderServices();
            
            try {
                const response = await fetch(`/api/stop/${id}`, { method: 'POST' });
                const result = await response.json();
                
                if (result.success) {
                    showToast(`${services[id].name} stopped`);
                } else {
                    showToast(`Failed to stop ${services[id].name}`, 'error');
                }
            } catch (error) {
                showToast(`Error stopping ${services[id].name}`, 'error');
            }
            
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
            const btn = document.querySelector('.start-all');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Starting...';
            
            try {
                const response = await fetch('/api/start-all', { method: 'POST' });
                const result = await response.json();
                showToast('All services started');
            } catch (error) {
                showToast('Error starting services', 'error');
            }
            
            btn.disabled = false;
            btn.innerHTML = '▶ Start All Services';
            setTimeout(fetchStatuses, 2000);
        }
        
        async function stopAll() {
            const btn = document.querySelector('.stop-all');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Stopping...';
            
            try {
                const response = await fetch('/api/stop-all', { method: 'POST' });
                const result = await response.json();
                showToast('All services stopped');
            } catch (error) {
                showToast('Error stopping services', 'error');
            }
            
            btn.disabled = false;
            btn.innerHTML = '■ Stop All Services';
            setTimeout(fetchStatuses, 1000);
        }
        
        // Initial load and polling
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
    port = int(os.environ.get("MASTER_DASHBOARD_PORT", "5099"))
    print(f"  http://localhost:{port}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)
