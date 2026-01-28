"""
Dashboard - Web interface for monitoring and control
WITH DELETE AND UPLOAD PDF FUNCTIONALITY
"""
from flask import Flask, render_template_string, jsonify, request
from datetime import datetime
from werkzeug.utils import secure_filename
import threading
import requests
import shutil
import os
import re
import config
from database import Database


app = Flask(__name__)
db = Database()

# Global state
automation_state = {
    "running": False,
    "paused": False,
    "last_check": None,
    "monitoring_thread": None
}

# Invoice Generator API URL
INVOICE_GENERATOR_API = "http://localhost:5001/api/generate-from-estimate"

# Estimate folders for saving uploaded PDFs
ESTIMATE_FOLDERS = [
    r"N:\Estimates\2026 All Painting Estimates",
    r"N:\Estimates\2025 All Painting Estimates",
]


# HTML Template for the dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Estimate Automation Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #333;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            background: #2B4C7E;
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 {
            font-size: 24px;
        }
        .status-badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
        }
        .status-running {
            background: #27ae60;
            color: white;
        }
        .status-paused {
            background: #f39c12;
            color: white;
        }
        .status-stopped {
            background: #e74c3c;
            color: white;
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .card .value {
            font-size: 32px;
            font-weight: bold;
            color: #2B4C7E;
        }
        .controls {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .controls h2 {
            margin-bottom: 15px;
            color: #2B4C7E;
        }
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            transition: all 0.3s;
        }
        .btn-primary {
            background: #2B4C7E;
            color: white;
        }
        .btn-primary:hover {
            background: #1a3a5c;
        }
        .btn-success {
            background: #27ae60;
            color: white;
        }
        .btn-success:hover {
            background: #1e8449;
        }
        .btn-warning {
            background: #f39c12;
            color: white;
        }
        .btn-warning:hover {
            background: #d68910;
        }
        .btn-danger {
            background: #e74c3c;
            color: white;
        }
        .btn-danger:hover {
            background: #c0392b;
        }
        .btn-invoice {
            background: #9b59b6;
            color: white;
        }
        .btn-invoice:hover {
            background: #7d3c98;
        }
        .btn-quickbooks {
            background: #2CA01C;
            color: white;
        }
        .btn-quickbooks:hover {
            background: #228B15;
        }
        .btn-upload {
            background: #3498db;
            color: white;
        }
        .btn-upload:hover {
            background: #2980b9;
        }
        .btn-small {
            padding: 6px 12px;
            font-size: 12px;
        }
        .btn-delete {
            background: #95a5a6;
            color: white;
            padding: 4px 8px;
            font-size: 11px;
        }
        .btn-delete:hover {
            background: #e74c3c;
        }
        .qb-link {
            color: #2CA01C;
            font-weight: bold;
            text-decoration: none;
        }
        .qb-link:hover {
            text-decoration: underline;
        }
        .manual-process {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        .manual-process input[type="text"] {
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            width: 200px;
            margin-right: 10px;
        }
        .upload-section {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }
        .upload-section h3 {
            margin-bottom: 10px;
            color: #2B4C7E;
        }
        .upload-area {
            border: 2px dashed #ddd;
            border-radius: 10px;
            padding: 30px;
            text-align: center;
            margin: 10px 0;
            transition: all 0.3s;
            cursor: pointer;
        }
        .upload-area:hover, .upload-area.dragover {
            border-color: #3498db;
            background: #f0f8ff;
        }
        .upload-area input[type="file"] {
            display: none;
        }
        .upload-area p {
            color: #666;
            margin: 10px 0;
        }
        .upload-area .upload-icon {
            font-size: 48px;
            color: #3498db;
        }
        .selected-file {
            background: #e8f4fc;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            display: none;
        }
        .selected-file.show {
            display: block;
        }
        .history {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .history h2 {
            margin-bottom: 15px;
            color: #2B4C7E;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: bold;
            color: #666;
        }
        tr:hover {
            background: #f8f9fa;
        }
        .status-completed {
            color: #27ae60;
            font-weight: bold;
        }
        .status-uploaded {
            color: #3498db;
            font-weight: bold;
        }
        .status-error {
            color: #e74c3c;
            font-weight: bold;
        }
        .status-pending {
            color: #f39c12;
            font-weight: bold;
        }
        .status-partial {
            color: #f39c12;
            font-weight: bold;
        }
        .status-invoiced {
            color: #9b59b6;
            font-weight: bold;
        }
        .action-links {
            white-space: nowrap;
        }
        .action-links a, .action-links button {
            margin-right: 8px;
            text-decoration: none;
        }
        .action-links a {
            color: #2B4C7E;
        }
        .action-links a:hover {
            text-decoration: underline;
        }
        .refresh-info {
            color: #666;
            font-size: 12px;
            margin-top: 10px;
        }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        #message {
            display: none;
        }
        .invoice-info {
            font-size: 11px;
            color: #9b59b6;
            margin-top: 3px;
        }
        /* Modal styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        .modal-content {
            background-color: white;
            margin: 15% auto;
            padding: 20px;
            border-radius: 10px;
            width: 400px;
            text-align: center;
        }
        .modal-content h3 {
            margin-bottom: 15px;
            color: #e74c3c;
        }
        .modal-content p {
            margin-bottom: 20px;
            color: #666;
        }
        .modal-buttons {
            display: flex;
            justify-content: center;
            gap: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎨 All Painting - Estimate Automation</h1>
            <span id="status-badge" class="status-badge status-stopped">Stopped</span>
        </header>
        
        <div id="message" class="alert"></div>
        
        <div class="cards">
            <div class="card">
                <h3>Total Processed</h3>
                <div class="value" id="stat-total">0</div>
            </div>
            <div class="card">
                <h3>Today</h3>
                <div class="value" id="stat-today">0</div>
            </div>
            <div class="card">
                <h3>Completed</h3>
                <div class="value" id="stat-completed">0</div>
            </div>
            <div class="card">
                <h3>Invoiced</h3>
                <div class="value" id="stat-invoiced">0</div>
            </div>
        </div>
        
        <div class="controls">
            <h2>Controls</h2>
            <div class="btn-group">
                <button class="btn-success" onclick="startMonitoring()">▶ Start Monitoring</button>
                <button class="btn-warning" onclick="pauseMonitoring()">⏸ Pause</button>
                <button class="btn-danger" onclick="stopMonitoring()">⏹ Stop</button>
                <button class="btn-primary" onclick="checkNow()">🔄 Check Now</button>
            </div>
            
            <div class="manual-process">
                <h3>Manual Process</h3>
                <p style="color: #666; margin: 10px 0;">Enter an estimate code to process manually (without waiting for email)</p>
                <input type="text" id="manual-code" placeholder="e.g., 25C-325">
                <button class="btn-primary" onclick="processManual()">Process Estimate</button>
            </div>
            
            <div class="upload-section">
                <h3>📤 Upload Estimate PDF</h3>
                <p style="color: #666; margin: 10px 0;">Upload an existing estimate PDF to track and generate invoice later</p>
                <div class="upload-area" id="uploadArea" onclick="document.getElementById('pdfFile').click();">
                    <div class="upload-icon">📄</div>
                    <p><strong>Click to select</strong> or drag & drop estimate PDF here</p>
                    <p style="font-size: 12px;">File name must contain estimate code (e.g., Estimate - 25C-325 - Project.pdf)</p>
                    <input type="file" id="pdfFile" accept=".pdf" onchange="handleFileSelect(event)">
                </div>
                <div class="selected-file" id="selectedFile">
                    <strong>Selected:</strong> <span id="fileName"></span>
                    <button class="btn-upload btn-small" onclick="uploadPdf()" style="margin-left: 10px;">Upload</button>
                    <button class="btn-danger btn-small" onclick="clearFile()">Cancel</button>
                </div>
            </div>
        </div>
        
        <div class="history">
            <h2>Recent Estimates</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date/Time</th>
                        <th>Estimate Code</th>
                        <th>Client</th>
                        <th>Project</th>
                        <th>Status</th>
                        <th>Invoice</th>
                        <th>QuickBooks</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="history-table">
                    <tr>
                        <td colspan="8" style="text-align: center; color: #666;">Loading...</td>
                    </tr>
                </tbody>
            </table>
            <p class="refresh-info">Auto-refreshes every 30 seconds. Last check: <span id="last-check">Never</span></p>
        </div>
    </div>
    
    <!-- Delete Confirmation Modal -->
    <div id="deleteModal" class="modal">
        <div class="modal-content">
            <h3>🗑️ Delete Estimate</h3>
            <p>Are you sure you want to delete estimate <strong id="deleteEstimateCode"></strong>?<br>This action cannot be undone.</p>
            <div class="modal-buttons">
                <button class="btn-danger" onclick="confirmDelete()">Yes, Delete</button>
                <button class="btn-primary" onclick="closeDeleteModal()">Cancel</button>
            </div>
        </div>
    </div>
    
    <script>
        let deleteEstimateId = null;
        let selectedFile = null;
        
        function showMessage(message, type) {
            const el = document.getElementById('message');
            el.textContent = message;
            el.className = 'alert alert-' + type;
            el.style.display = 'block';
            setTimeout(() => { el.style.display = 'none'; }, 5000);
        }
        
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    const badge = document.getElementById('status-badge');
                    if (data.paused) {
                        badge.textContent = 'Paused';
                        badge.className = 'status-badge status-paused';
                    } else if (data.running) {
                        badge.textContent = 'Running';
                        badge.className = 'status-badge status-running';
                    } else {
                        badge.textContent = 'Stopped';
                        badge.className = 'status-badge status-stopped';
                    }
                    document.getElementById('last-check').textContent = data.last_check || 'Never';
                });
        }
        
        function updateStats() {
            fetch('/api/stats')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('stat-total').textContent = data.total || 0;
                    document.getElementById('stat-today').textContent = data.today || 0;
                    document.getElementById('stat-completed').textContent = (data.by_status?.completed || 0) + (data.by_status?.uploaded || 0);
                    document.getElementById('stat-invoiced').textContent = data.by_status?.invoiced || 0;
                });
        }
        
        function updateHistory() {
            fetch('/api/history')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('history-table');
                    if (data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #666;">No estimates processed yet</td></tr>';
                        return;
                    }
                    
                    tbody.innerHTML = data.map(est => {
                        const statusClass = 'status-' + (est.status || 'pending');
                        const date = est.created_at ? new Date(est.created_at).toLocaleString() : '-';
                        
                        // Invoice column
                        let invoiceCol = '-';
                        if (est.invoice_number) {
                            invoiceCol = `<span class="status-invoiced">${est.invoice_number}</span>`;
                        } else if ((est.status === 'completed' || est.status === 'uploaded') && est.pdf_file_path) {
                            invoiceCol = `<button class="btn-invoice btn-small" onclick="generateInvoice(${est.id}, '${est.pdf_file_path.replace(/\\\\/g, '\\\\\\\\')}')">📄 Generate</button>`;
                        }
                        
                        // QuickBooks column
                        let qbCol = '-';
                        if (est.qb_invoice_id && est.qb_url) {
                            qbCol = `<a href="${est.qb_url}" target="_blank" class="qb-link">📗 View</a>`;
                        } else if (est.invoice_number && est.invoice_path) {
                            qbCol = `<button class="btn-quickbooks btn-small" onclick="sendToQuickBooks(${est.id})">📤 Send</button>`;
                        }
                        
                        // Client and Project - truncate if too long
                        const client = est.client_name ? (est.client_name.length > 25 ? est.client_name.substring(0, 25) + '...' : est.client_name) : '-';
                        const project = est.project_name ? (est.project_name.length > 30 ? est.project_name.substring(0, 30) + '...' : est.project_name) : '-';
                        
                        return `
                            <tr>
                                <td>${date}</td>
                                <td><strong>${est.estimate_code}</strong></td>
                                <td title="${est.client_name || ''}">${client}</td>
                                <td title="${est.project_name || ''}">${project}</td>
                                <td><span class="${statusClass}">${est.status || 'pending'}</span></td>
                                <td>${invoiceCol}</td>
                                <td>${qbCol}</td>
                                <td class="action-links">
                                    ${est.pdf_file_path ? `<a href="#" onclick="openFolder('${est.pdf_file_path.replace(/\\\\/g, '\\\\\\\\')}')">📁</a>` : ''}
                                    ${est.invoice_path ? `<a href="#" onclick="openFolder('${est.invoice_path.replace(/\\\\/g, '\\\\\\\\')}')">📄</a>` : ''}
                                    ${est.status === 'error' ? `<a href="#" onclick="retryEstimate(${est.id})">🔄</a>` : ''}
                                    <button class="btn-delete" onclick="showDeleteModal(${est.id}, '${est.estimate_code}')">🗑️</button>
                                </td>
                            </tr>
                        `;
                    }).join('');
                });
        }
        
        // File upload functions
        function handleFileSelect(event) {
            const file = event.target.files[0];
            if (file && file.type === 'application/pdf') {
                selectedFile = file;
                document.getElementById('fileName').textContent = file.name;
                document.getElementById('selectedFile').classList.add('show');
            } else {
                showMessage('Please select a PDF file', 'error');
            }
        }
        
        function clearFile() {
            selectedFile = null;
            document.getElementById('pdfFile').value = '';
            document.getElementById('selectedFile').classList.remove('show');
        }
        
        function uploadPdf() {
            if (!selectedFile) {
                showMessage('Please select a file first', 'error');
                return;
            }
            
            const formData = new FormData();
            formData.append('pdf', selectedFile);
            
            showMessage('Uploading estimate PDF...', 'success');
            
            fetch('/api/upload-estimate', {
                method: 'POST',
                body: formData
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showMessage(data.message, 'success');
                    clearFile();
                    updateHistory();
                    updateStats();
                } else {
                    showMessage(data.error || 'Upload failed', 'error');
                }
            })
            .catch(err => {
                showMessage('Error: ' + err.message, 'error');
            });
        }
        
        // Drag and drop
        const uploadArea = document.getElementById('uploadArea');
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });
        
        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.type === 'application/pdf') {
                selectedFile = file;
                document.getElementById('fileName').textContent = file.name;
                document.getElementById('selectedFile').classList.add('show');
            } else {
                showMessage('Please drop a PDF file', 'error');
            }
        });
        
        function showDeleteModal(id, code) {
            deleteEstimateId = id;
            document.getElementById('deleteEstimateCode').textContent = code;
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        function closeDeleteModal() {
            deleteEstimateId = null;
            document.getElementById('deleteModal').style.display = 'none';
        }
        
        function confirmDelete() {
            if (!deleteEstimateId) return;
            
            fetch('/api/delete/' + deleteEstimateId, { method: 'DELETE' })
                .then(r => r.json())
                .then(data => {
                    closeDeleteModal();
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateHistory();
                    updateStats();
                })
                .catch(err => {
                    closeDeleteModal();
                    showMessage('Error deleting estimate: ' + err.message, 'error');
                });
        }
        
        function startMonitoring() {
            fetch('/api/start', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateStatus();
                });
        }
        
        function pauseMonitoring() {
            fetch('/api/pause', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateStatus();
                });
        }
        
        function stopMonitoring() {
            fetch('/api/stop', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateStatus();
                });
        }
        
        function checkNow() {
            showMessage('Checking for new emails...', 'success');
            fetch('/api/check-now', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateHistory();
                    updateStats();
                });
        }
        
        function processManual() {
            const code = document.getElementById('manual-code').value.trim();
            if (!code) {
                showMessage('Please enter an estimate code', 'error');
                return;
            }
            
            showMessage('Processing estimate ' + code + '...', 'success');
            fetch('/api/process-manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code })
            })
            .then(r => r.json())
            .then(data => {
                showMessage(data.message, data.success ? 'success' : 'error');
                document.getElementById('manual-code').value = '';
                updateHistory();
                updateStats();
            });
        }
        
        function generateInvoice(estimateId, pdfPath) {
            showMessage('Generating invoice...', 'success');
            fetch('/api/generate-invoice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ estimate_id: estimateId, pdf_path: pdfPath })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Invoice ${data.invoice_number} generated successfully!`, 'success');
                } else {
                    showMessage(data.error || 'Failed to generate invoice', 'error');
                }
                updateHistory();
                updateStats();
            })
            .catch(err => {
                showMessage('Error: ' + err.message, 'error');
            });
        }
        
        function sendToQuickBooks(estimateId) {
            showMessage('Sending to QuickBooks...', 'success');
            fetch('/api/send-to-quickbooks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ estimate_id: estimateId })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Invoice sent to QuickBooks! Invoice #${data.qb_invoice_number}`, 'success');
                    // Open QuickBooks invoice in new tab
                    if (data.qb_url) {
                        window.open(data.qb_url, '_blank');
                    }
                } else {
                    showMessage(data.error || 'Failed to send to QuickBooks', 'error');
                }
                updateHistory();
            })
            .catch(err => {
                showMessage('Error: ' + err.message, 'error');
            });
        }
        
        function retryEstimate(id) {
            showMessage('Retrying estimate...', 'success');
            fetch('/api/retry/' + id, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    showMessage(data.message, data.success ? 'success' : 'error');
                    updateHistory();
                    updateStats();
                });
        }
        
        function openFolder(path) {
            fetch('/api/open-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });
        }
        
        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('deleteModal');
            if (event.target == modal) {
                closeDeleteModal();
            }
        }
        
        // Initial load
        updateStatus();
        updateStats();
        updateHistory();
        
        // Auto-refresh every 30 seconds
        setInterval(() => {
            updateStatus();
            updateStats();
            updateHistory();
        }, 30000);
    </script>
</body>
</html>
"""


def extract_estimate_code_from_filename(filename):
    """Extract estimate code from filename like 'Estimate - 25C-319 - Project.pdf'"""
    # Pattern: 2 digits (year) + C or R + optional dash + 3 digits
    pattern = r'(2[4-9][CR])-?(\d{3})'
    match = re.search(pattern, filename, re.IGNORECASE)
    if match:
        prefix = match.group(1).upper()
        number = match.group(2)
        return f"{prefix}-{number}"
    return None


def find_existing_estimate_pdf(filename, estimate_code):
    """
    Check if the estimate PDF already exists in the estimate folders.
    Returns the path if found, None otherwise.
    """
    # Check in all estimate folders
    for base_folder in ESTIMATE_FOLDERS:
        if not os.path.exists(base_folder):
            continue
        
        # Search in base folder
        full_path = os.path.join(base_folder, filename)
        if os.path.exists(full_path):
            return full_path
        
        # Search in subfolders
        for subfolder in os.listdir(base_folder):
            subfolder_path = os.path.join(base_folder, subfolder)
            if os.path.isdir(subfolder_path):
                full_path = os.path.join(subfolder_path, filename)
                if os.path.exists(full_path):
                    return full_path
                
                # Also search by estimate code in filename
                for file in os.listdir(subfolder_path):
                    if estimate_code in file and file.lower().endswith('.pdf'):
                        return os.path.join(subfolder_path, file)
    
    return None


def get_estimate_save_folder(estimate_code):
    """Get the folder where the estimate should be saved based on year prefix"""
    if estimate_code.startswith('26'):
        return ESTIMATE_FOLDERS[0]  # 2026 folder
    elif estimate_code.startswith('25'):
        return ESTIMATE_FOLDERS[1]  # 2025 folder
    else:
        return ESTIMATE_FOLDERS[0]  # Default to current year


def extract_client_project_from_pdf(pdf_path):
    """
    Extract client name and project name from estimate PDF.
    Returns tuple (client_name, project_name)
    """
    client_name = None
    project_name = None
    
    try:
        import pdfplumber
        
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > 0:
                text = pdf.pages[0].extract_text() or ""
                
                # Try to extract Company/Client
                import re
                
                # Pattern for "Company: XXX" format
                company_match = re.search(r'Company:\s*(.+?)(?:\s+Project:|$|\n)', text)
                if company_match:
                    client_name = company_match.group(1).strip()
                
                # Pattern for "Project: XXX" format  
                project_match = re.search(r'Project:\s*(.+?)(?:\s+Contact:|$|\n)', text)
                if project_match:
                    project_name = project_match.group(1).strip()
                
                # Alternative: Try "Project Reference:" format
                if not project_name:
                    proj_ref_match = re.search(r'Project Reference[:\s]*\n([^\n]+)', text, re.IGNORECASE)
                    if proj_ref_match:
                        project_name = proj_ref_match.group(1).strip()
                
                # If still no client, try to get from filename
                if not client_name:
                    filename = os.path.basename(pdf_path)
                    # Pattern: "Estimate - 25C-319 - ClientName - ..."
                    parts = filename.split(' - ')
                    if len(parts) >= 3:
                        client_name = parts[2].strip()
                
    except ImportError:
        # pdfplumber not installed, try to extract from filename
        filename = os.path.basename(pdf_path)
        parts = filename.split(' - ')
        if len(parts) >= 3:
            client_name = parts[2].strip()
        if len(parts) >= 4:
            project_name = parts[3].strip().replace('.pdf', '')
    except Exception as e:
        print(f"Warning: Could not extract client/project from PDF: {e}")
        # Fallback to filename
        filename = os.path.basename(pdf_path)
        parts = filename.split(' - ')
        if len(parts) >= 3:
            client_name = parts[2].strip()
        if len(parts) >= 4:
            project_name = parts[3].strip().replace('.pdf', '')
    
    return client_name, project_name


@app.route('/')
def dashboard():
    """Render the dashboard"""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/status')
def api_status():
    """Get current automation status"""
    return jsonify({
        "running": automation_state["running"],
        "paused": automation_state["paused"],
        "last_check": automation_state["last_check"]
    })


@app.route('/api/stats')
def api_stats():
    """Get processing statistics"""
    stats = db.get_statistics()
    return jsonify(stats)


@app.route('/api/history')
def api_history():
    """Get recent estimates"""
    return jsonify(db.get_recent_estimates(limit=50))


@app.route('/api/start', methods=['POST'])
def api_start():
    """Start monitoring"""
    automation_state["running"] = True
    automation_state["paused"] = False
    return jsonify({"success": True, "message": "Monitoring started"})


@app.route('/api/pause', methods=['POST'])
def api_pause():
    """Pause monitoring"""
    automation_state["paused"] = True
    return jsonify({"success": True, "message": "Monitoring paused"})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop monitoring"""
    automation_state["running"] = False
    automation_state["paused"] = False
    return jsonify({"success": True, "message": "Monitoring stopped"})


@app.route('/api/check-now', methods=['POST'])
def api_check_now():
    """Trigger immediate email check"""
    from main import process_new_estimates
    
    try:
        count = process_new_estimates()
        automation_state["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return jsonify({
            "success": True,
            "message": f"Check complete. Found {count} new estimates."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/process-manual', methods=['POST'])
def api_process_manual():
    """Process an estimate manually by code"""
    from main import process_estimate_by_code
    
    data = request.json
    code = data.get("code", "").strip().upper()
    
    if not code:
        return jsonify({"success": False, "message": "No estimate code provided"})
    
    try:
        result = process_estimate_by_code(code)
        if result.get("success"):
            return jsonify({
                "success": True,
                "message": f"Estimate {code} processed successfully!"
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get("error", "Unknown error")
            })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/upload-estimate', methods=['POST'])
def api_upload_estimate():
    """Upload an existing estimate PDF"""
    if 'pdf' not in request.files:
        return jsonify({"success": False, "error": "No file provided"})
    
    file = request.files['pdf']
    
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"})
    
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "error": "File must be a PDF"})
    
    # Extract estimate code from filename
    estimate_code = extract_estimate_code_from_filename(file.filename)
    
    if not estimate_code:
        return jsonify({
            "success": False, 
            "error": "Could not extract estimate code from filename. Please ensure filename contains code like '25C-319'"
        })
    
    filename = secure_filename(file.filename)
    # Restore original filename structure (secure_filename may alter it)
    filename = file.filename.replace('/', '_').replace('\\', '_')
    
    try:
        # Check if file already exists in estimate folders
        existing_path = find_existing_estimate_pdf(filename, estimate_code)
        
        if existing_path:
            # File exists, just add to database
            pdf_path = existing_path
            message = f"Estimate {estimate_code} found in existing folder and added to tracking"
        else:
            # File doesn't exist, save it
            save_folder = get_estimate_save_folder(estimate_code)
            
            if not os.path.exists(save_folder):
                os.makedirs(save_folder, exist_ok=True)
            
            pdf_path = os.path.join(save_folder, filename)
            file.save(pdf_path)
            message = f"Estimate {estimate_code} uploaded and saved successfully"
        
        # Extract client and project info from PDF
        client_name, project_name = extract_client_project_from_pdf(pdf_path)
        
        # Check if already in database
        existing_estimate = db.get_estimate_by_code(estimate_code)
        
        if existing_estimate:
            # Update existing record
            db.update_estimate(
                existing_estimate['id'],
                pdf_file_path=pdf_path,
                client_name=client_name,
                project_name=project_name,
                status='uploaded'
            )
        else:
            # Add new record
            estimate_id = db.add_estimate(
                estimate_code=estimate_code,
                email_subject="Uploaded PDF",
                client_name=client_name,
                project_name=project_name
            )
            db.update_estimate(
                estimate_id,
                pdf_file_path=pdf_path,
                status='uploaded'
            )
        
        return jsonify({
            "success": True,
            "message": message,
            "estimate_code": estimate_code,
            "pdf_path": pdf_path,
            "client_name": client_name,
            "project_name": project_name
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/generate-invoice', methods=['POST'])
def api_generate_invoice():
    """Generate invoice from estimate PDF"""
    data = request.json
    estimate_id = data.get("estimate_id")
    pdf_path = data.get("pdf_path")
    
    if not pdf_path:
        return jsonify({"success": False, "error": "No PDF path provided"})
    
    try:
        # Call the invoice generator API
        response = requests.post(
            INVOICE_GENERATOR_API,
            json={"estimate_pdf_path": pdf_path},
            timeout=120
        )
        
        result = response.json()
        
        if result.get("success"):
            # Update database with invoice info
            if estimate_id:
                db.update_estimate(
                    estimate_id,
                    status="invoiced",
                    invoice_number=result.get("invoice_number"),
                    invoice_path=result.get("invoice_path")
                )
            
            return jsonify({
                "success": True,
                "invoice_number": result.get("invoice_number"),
                "invoice_path": result.get("invoice_path"),
                "message": f"Invoice {result.get('invoice_number')} generated successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Unknown error from invoice generator")
            })
    
    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "Invoice Generator is not running. Please start runinvoicegenerator.bat"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# QuickBooks Sync API URL
QUICKBOOKS_SYNC_API = "http://localhost:5015/api/create-invoice"


@app.route('/api/send-to-quickbooks', methods=['POST'])
def api_send_to_quickbooks():
    """Send invoice to QuickBooks"""
    data = request.json
    estimate_id = data.get("estimate_id")
    
    if not estimate_id:
        return jsonify({"success": False, "error": "No estimate ID provided"})
    
    # Get estimate from database
    estimate = db.get_estimate(estimate_id)
    if not estimate:
        return jsonify({"success": False, "error": "Estimate not found"})
    
    if not estimate.get("invoice_number"):
        return jsonify({"success": False, "error": "Invoice not generated yet. Generate invoice first."})
    
    if estimate.get("qb_invoice_id"):
        return jsonify({
            "success": False, 
            "error": "Already sent to QuickBooks",
            "qb_url": estimate.get("qb_url")
        })
    
    try:
        # Extract invoice data from estimate PDF using invoice generator
        # Build the payload for QuickBooks
        qb_payload = {
            "invoice_number": estimate.get("invoice_number"),
            "estimate_number": estimate.get("estimate_code"),
            "client_company": estimate.get("client_name", ""),
            "project_name": estimate.get("project_name", ""),
            "pdf_path": estimate.get("invoice_path", "")
        }
        
        # Try to get more details from the invoice PDF if it exists
        invoice_path = estimate.get("invoice_path")
        if invoice_path and os.path.exists(invoice_path):
            # Extract data from invoice PDF
            extracted = extract_invoice_data_from_pdf(invoice_path)
            if extracted:
                qb_payload.update({
                    "client_company": extracted.get("client_company") or estimate.get("client_name", ""),
                    "client_contact": extracted.get("client_contact", ""),
                    "client_email": extracted.get("client_email", ""),
                    "client_phone": extracted.get("client_phone", ""),
                    "client_address": extracted.get("client_address", ""),
                    "project_address": extracted.get("project_address", ""),
                    "po_number": extracted.get("po_number", ""),
                    "line_items": extracted.get("line_items", []),
                    "subtotal": extracted.get("subtotal", 0)
                })
        
        # Call QuickBooks Sync API
        response = requests.post(
            QUICKBOOKS_SYNC_API,
            json=qb_payload,
            timeout=120
        )
        
        result = response.json()
        
        if result.get("success"):
            # Update database with QuickBooks info
            db.update_estimate(
                estimate_id,
                qb_invoice_id=result.get("qb_invoice_id"),
                qb_url=result.get("qb_url")
            )
            
            return jsonify({
                "success": True,
                "qb_invoice_id": result.get("qb_invoice_id"),
                "qb_invoice_number": result.get("qb_invoice_number"),
                "qb_url": result.get("qb_url"),
                "pdf_attached": result.get("pdf_attached", False),
                "message": f"Invoice sent to QuickBooks successfully"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get("error", "Unknown error from QuickBooks Sync")
            })
    
    except requests.exceptions.ConnectionError:
        return jsonify({
            "success": False,
            "error": "QuickBooks Sync is not running. Please start run_quickbooks_sync.bat (port 5015)"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


def extract_invoice_data_from_pdf(pdf_path):
    """Extract invoice data from PDF for QuickBooks"""
    try:
        import pdfplumber
        import re
        
        extracted = {
            "client_company": "",
            "client_contact": "",
            "client_email": "",
            "client_phone": "",
            "client_address": "",
            "project_name": "",
            "project_address": "",
            "po_number": "",
            "line_items": [],
            "subtotal": 0
        }
        
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) > 0:
                text = pdf.pages[0].extract_text() or ""
                
                print(f"📄 Extracting data from invoice PDF...")
                
                # Extract CLIENT INFORMATION section
                client_section = re.search(r'CLIENT INFORMATION\s*(.*?)(?=PROJECT|INVOICE SUMMARY)', text, re.DOTALL)
                if client_section:
                    client_text = client_section.group(1)
                    
                    # Company name
                    company_match = re.search(r'Company:\s*(.+?)(?:\n|$)', client_text)
                    if company_match:
                        extracted["client_company"] = company_match.group(1).strip()
                        print(f"   Company: {extracted['client_company']}")
                    
                    # Contact name
                    contact_match = re.search(r'Contact:\s*(.+?)(?:\n|$)', client_text)
                    if contact_match:
                        extracted["client_contact"] = contact_match.group(1).strip()
                        print(f"   Contact: {extracted['client_contact']}")
                    
                    # Email (in client section)
                    email_match = re.search(r'Email:\s*(\S+@\S+)', client_text)
                    if email_match:
                        extracted["client_email"] = email_match.group(1).strip()
                        print(f"   Email: {extracted['client_email']}")
                    
                    # Phone (in client section - get the one after client info, not the header phone)
                    phone_match = re.search(r'Phone:\s*([\d\-\(\)\s]+)', client_text)
                    if phone_match:
                        extracted["client_phone"] = phone_match.group(1).strip()
                        print(f"   Phone: {extracted['client_phone']}")
                    
                    # Address - everything between Address: and Phone: or Email:
                    address_match = re.search(r'Address:\s*(.+?)(?=Phone:|Email:|$)', client_text, re.DOTALL)
                    if address_match:
                        addr = address_match.group(1).strip()
                        # Clean up multi-line address
                        addr = re.sub(r'\s*\n\s*', ', ', addr)
                        extracted["client_address"] = addr
                        print(f"   Address: {extracted['client_address']}")
                
                # Extract PROJECT section
                project_section = re.search(r'PROJECT\s*(.*?)(?=INVOICE SUMMARY)', text, re.DOTALL)
                if project_section:
                    project_text = project_section.group(1)
                    
                    # Project name
                    project_match = re.search(r'Project:\s*(.+?)(?:\n|$)', project_text)
                    if project_match:
                        extracted["project_name"] = project_match.group(1).strip()
                        print(f"   Project: {extracted['project_name']}")
                    
                    # Project address
                    proj_addr_match = re.search(r'Address:\s*(.+?)(?:\n|P\.O\.|$)', project_text)
                    if proj_addr_match:
                        extracted["project_address"] = proj_addr_match.group(1).strip()
                        print(f"   Project Address: {extracted['project_address']}")
                    
                    # PO number
                    po_match = re.search(r'P\.?O\.?\s*#:?\s*([\w\-]+)', project_text)
                    if po_match:
                        extracted["po_number"] = po_match.group(1).strip()
                        print(f"   PO #: {extracted['po_number']}")
                
                # Extract subtotal
                subtotal_match = re.search(r'Subtotal\s*\$?([\d,]+\.?\d*)', text)
                if subtotal_match:
                    extracted["subtotal"] = float(subtotal_match.group(1).replace(',', ''))
                    print(f"   Subtotal: ${extracted['subtotal']}")
                
                # Extract line items from INVOICE SUMMARY table
                invoice_section = re.search(r'INVOICE SUMMARY\s*(.*?)(?=Subtotal|$)', text, re.DOTALL)
                if invoice_section:
                    lines = invoice_section.group(1).split('\n')
                    for line in lines:
                        # Match lines like "1 Painting of storefront walls $2,162.00"
                        item_match = re.match(r'^\s*(\d+)\s+(.+?)\s+\$?([\d,]+\.?\d*)\s*$', line.strip())
                        if item_match:
                            desc = item_match.group(2).strip()
                            amount = float(item_match.group(3).replace(',', ''))
                            if amount > 0 and len(desc) > 3:
                                extracted["line_items"].append({
                                    "description": desc,
                                    "amount": amount
                                })
                                print(f"   Line item: {desc} - ${amount}")
        
        return extracted
        
    except Exception as e:
        print(f"⚠️ Error extracting invoice data: {e}")
        import traceback
        traceback.print_exc()
        return None


@app.route('/api/delete/<int:estimate_id>', methods=['DELETE'])
def api_delete(estimate_id):
    """Delete an estimate from the database"""
    try:
        estimate = db.get_estimate(estimate_id)
        if not estimate:
            return jsonify({"success": False, "message": "Estimate not found"})
        
        estimate_code = estimate.get("estimate_code", "Unknown")
        
        # Delete from database
        db.delete_estimate(estimate_id)
        
        return jsonify({
            "success": True,
            "message": f"Estimate {estimate_code} deleted successfully"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/retry/<int:estimate_id>', methods=['POST'])
def api_retry(estimate_id):
    """Retry a failed estimate"""
    from main import process_estimate_by_code
    
    estimate = db.get_estimate(estimate_id)
    if not estimate:
        return jsonify({"success": False, "message": "Estimate not found"})
    
    try:
        result = process_estimate_by_code(estimate["estimate_code"])
        if result.get("success"):
            return jsonify({
                "success": True,
                "message": f"Estimate {estimate['estimate_code']} processed successfully!"
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get("error", "Unknown error")
            })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


@app.route('/api/open-folder', methods=['POST'])
def api_open_folder():
    """Open folder in Windows Explorer"""
    import subprocess
    import os
    
    data = request.json
    path = data.get("path", "")
    
    if path and os.path.exists(path):
        folder = os.path.dirname(path)
        subprocess.Popen(f'explorer "{folder}"')
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "Path not found"})


def get_automation_state():
    """Get the automation state (for use by main.py)"""
    return automation_state


def run_dashboard():
    """Run the dashboard server"""
    print(f"\n🌐 Dashboard starting on http://localhost:{config.DASHBOARD_PORT}")
    app.run(
        host=config.DASHBOARD_HOST,
        port=config.DASHBOARD_PORT,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    run_dashboard()
