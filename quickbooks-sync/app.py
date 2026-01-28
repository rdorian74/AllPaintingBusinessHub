"""
QuickBooks Sync Service - Flask Application
Provides API endpoints for creating invoices in QuickBooks
"""

from flask import Flask, request, jsonify, redirect, render_template_string
import os
import json
from datetime import datetime
import config
from qb_auth import QBAuth
from qb_client import QBClient


app = Flask(__name__)
auth = QBAuth()


# =============================================================================
# HTML TEMPLATES
# =============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuickBooks Sync - All Painting</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #333;
            padding: 20px;
        }
        .container { max-width: 800px; margin: 0 auto; }
        header {
            background: #2CA01C;
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
        }
        header h1 { font-size: 24px; margin-bottom: 5px; }
        header p { opacity: 0.9; }
        .card {
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        .card h2 {
            color: #2CA01C;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }
        .status-badge {
            display: inline-block;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 14px;
            margin: 10px 0;
        }
        .status-connected { background: #27ae60; color: white; }
        .status-disconnected { background: #e74c3c; color: white; }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            text-decoration: none;
            transition: all 0.3s;
            margin: 5px;
        }
        .btn-primary { background: #2CA01C; color: white; }
        .btn-primary:hover { background: #228B15; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-danger:hover { background: #c0392b; }
        .btn-info { background: #3498db; color: white; }
        .btn-info:hover { background: #2980b9; }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }
        .info-row:last-child { border-bottom: none; }
        .info-label { color: #666; }
        .info-value { font-weight: bold; }
        .alert {
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .alert-info { background: #cce5ff; color: #004085; border: 1px solid #b8daff; }
        code {
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
        }
        .endpoint {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
        }
        .endpoint code {
            display: block;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📗 QuickBooks Sync</h1>
            <p>All Painting Ltd - Invoice Integration</p>
        </header>
        
        {% if message %}
        <div class="alert alert-{{ message_type }}">{{ message }}</div>
        {% endif %}
        
        <div class="card">
            <h2>Connection Status</h2>
            
            {% if authenticated %}
            <span class="status-badge status-connected">✅ Connected</span>
            
            <div class="info-row">
                <span class="info-label">Company:</span>
                <span class="info-value">{{ company_name }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Environment:</span>
                <span class="info-value">{{ 'Sandbox (Testing)' if sandbox else 'Production' }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Token Status:</span>
                <span class="info-value">{{ token_status }}</span>
            </div>
            
            <div style="margin-top: 20px;">
                <a href="/test-connection" class="btn btn-info">🔍 Test Connection</a>
                <a href="/disconnect" class="btn btn-danger">🔌 Disconnect</a>
            </div>
            
            {% else %}
            <span class="status-badge status-disconnected">❌ Not Connected</span>
            <p style="margin: 15px 0;">Click the button below to connect your QuickBooks account.</p>
            <a href="/authorize" class="btn btn-primary">🔗 Connect to QuickBooks</a>
            {% endif %}
        </div>
        
        <div class="card">
            <h2>API Endpoints</h2>
            <p style="color: #666; margin-bottom: 15px;">Use these endpoints from your other applications:</p>
            
            <div class="endpoint">
                <strong>Create Invoice in QuickBooks</strong>
                <code>POST http://localhost:{{ port }}/api/create-invoice</code>
            </div>
            
            <div class="endpoint">
                <strong>Check Connection Status</strong>
                <code>GET http://localhost:{{ port }}/api/status</code>
            </div>
            
            <div class="endpoint">
                <strong>Health Check</strong>
                <code>GET http://localhost:{{ port }}/api/health</code>
            </div>
        </div>
        
        <div class="card">
            <h2>Configuration</h2>
            <div class="info-row">
                <span class="info-label">Client ID:</span>
                <span class="info-value">{{ client_id_preview }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Company ID:</span>
                <span class="info-value">{{ company_id }}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Redirect URI:</span>
                <span class="info-value">{{ redirect_uri }}</span>
            </div>
        </div>
    </div>
</body>
</html>
"""


# =============================================================================
# WEB ROUTES
# =============================================================================

@app.route('/')
def dashboard():
    """Main dashboard"""
    authenticated = auth.is_authenticated()
    auth_status = auth.get_auth_status()
    
    # Get company info if connected
    company_name = "Unknown"
    if authenticated:
        try:
            client = QBClient()
            result = client.test_connection()
            if result['success']:
                company_name = result.get('company_name', 'Unknown')
        except:
            pass
    
    return render_template_string(
        DASHBOARD_HTML,
        authenticated=authenticated,
        company_name=company_name,
        sandbox=config.USE_SANDBOX,
        token_status=auth_status.get('message', 'Unknown'),
        port=config.PORT,
        client_id_preview=config.CLIENT_ID[:10] + '...' if len(config.CLIENT_ID) > 10 else config.CLIENT_ID,
        company_id=config.COMPANY_ID,
        redirect_uri=config.REDIRECT_URI,
        message=request.args.get('message'),
        message_type=request.args.get('type', 'info')
    )


@app.route('/authorize')
def authorize():
    """Start OAuth authorization flow"""
    auth_url = auth.get_authorization_url()
    print(f"🔗 Redirecting to QuickBooks authorization...")
    return redirect(auth_url)


@app.route('/callback')
def callback():
    """OAuth callback handler"""
    # Check for errors
    error = request.args.get('error')
    if error:
        error_desc = request.args.get('error_description', 'Unknown error')
        return redirect(f'/?message={error_desc}&type=error')
    
    # Get authorization code
    code = request.args.get('code')
    state = request.args.get('state')
    realm_id = request.args.get('realmId')
    
    if not code:
        return redirect('/?message=No authorization code received&type=error')
    
    # Exchange code for tokens
    success, message = auth.exchange_code_for_tokens(code)
    
    if success:
        # Update company ID if provided
        if realm_id and realm_id != config.COMPANY_ID:
            print(f"ℹ️ Company ID from callback: {realm_id}")
            print(f"   Config Company ID: {config.COMPANY_ID}")
        
        return redirect('/?message=Successfully connected to QuickBooks!&type=success')
    else:
        return redirect(f'/?message={message}&type=error')


@app.route('/disconnect')
def disconnect():
    """Disconnect from QuickBooks"""
    auth.revoke_tokens()
    return redirect('/?message=Disconnected from QuickBooks&type=info')


@app.route('/test-connection')
def test_connection():
    """Test the QuickBooks connection"""
    if not auth.is_authenticated():
        return redirect('/?message=Not connected. Please authorize first.&type=error')
    
    try:
        client = QBClient()
        result = client.test_connection()
        
        if result['success']:
            return redirect(f'/?message=Connection successful! Company: {result["company_name"]}&type=success')
        else:
            return redirect(f'/?message={result["message"]}&type=error')
    except Exception as e:
        return redirect(f'/?message=Error: {str(e)}&type=error')


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/api/health', methods=['GET'])
def api_health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'quickbooks-sync',
        'authenticated': auth.is_authenticated(),
        'environment': 'sandbox' if config.USE_SANDBOX else 'production',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/status', methods=['GET'])
def api_status():
    """Get detailed connection status"""
    auth_status = auth.get_auth_status()
    
    response = {
        'authenticated': auth_status['authenticated'],
        'message': auth_status.get('message'),
        'environment': 'sandbox' if config.USE_SANDBOX else 'production',
        'company_id': config.COMPANY_ID
    }
    
    if auth_status['authenticated']:
        response['expires_at'] = auth_status.get('expires_at')
        response['expires_in_minutes'] = auth_status.get('expires_in_minutes')
        
        # Try to get company name
        try:
            client = QBClient()
            result = client.test_connection()
            if result['success']:
                response['company_name'] = result.get('company_name')
        except:
            pass
    
    return jsonify(response)


@app.route('/api/create-invoice', methods=['POST'])
def api_create_invoice():
    """
    Create an invoice in QuickBooks
    
    Expected JSON payload:
    {
        "invoice_number": "26C-004",
        "estimate_number": "25C-326",
        "client_company": "Guildford Town Centre Limited",
        "client_contact": "Curtis Darrah",
        "client_email": "c.darrah@jll.com",
        "client_phone": "604-374-8095",
        "client_address": "10355 152nd Street, Surrey, BC, V3R 7C1",
        "project_name": "Painting walls",
        "project_address": "10355 152nd St., Suite 2695, Surrey",
        "po_number": "2026-049",
        "line_items": [
            {"description": "Painting of storefront walls - Guildford Town Centre", "amount": 2162.00}
        ],
        "subtotal": 2162.00,
        "pdf_path": "\\\\path\\to\\invoice.pdf"  // Optional - attach PDF
    }
    
    Returns:
    {
        "success": true,
        "qb_invoice_id": "123",
        "qb_invoice_number": "26C-004",
        "qb_url": "https://app.sandbox.qbo.intuit.com/app/invoice?txnId=123",
        "pdf_attached": true
    }
    """
    
    # Check authentication
    if not auth.is_authenticated():
        return jsonify({
            'success': False,
            'error': 'Not authenticated. Please authorize at http://localhost:5015'
        }), 401
    
    # Get request data
    data = request.get_json()
    if not data:
        return jsonify({
            'success': False,
            'error': 'No JSON data provided'
        }), 400
    
    # Validate required fields
    if not data.get('client_company') and not data.get('client_contact'):
        return jsonify({
            'success': False,
            'error': 'Either client_company or client_contact is required'
        }), 400
    
    if not data.get('subtotal') and not data.get('line_items'):
        return jsonify({
            'success': False,
            'error': 'Either subtotal or line_items is required'
        }), 400
    
    try:
        client = QBClient()
        
        # Get PDF path if provided
        pdf_path = data.get('pdf_path') or data.get('invoice_path')
        
        # Create invoice
        result = client.create_invoice_from_estimate(data, pdf_path)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/find-customer', methods=['GET'])
def api_find_customer():
    """Find a customer by name or email"""
    
    if not auth.is_authenticated():
        return jsonify({
            'success': False,
            'error': 'Not authenticated'
        }), 401
    
    name = request.args.get('name')
    email = request.args.get('email')
    
    if not name and not email:
        return jsonify({
            'success': False,
            'error': 'Provide name or email parameter'
        }), 400
    
    try:
        client = QBClient()
        
        customer = None
        if name:
            customer = client.find_customer_by_name(name)
        elif email:
            customer = client.find_customer_by_email(email)
        
        if customer:
            return jsonify({
                'success': True,
                'found': True,
                'customer': {
                    'id': customer['Id'],
                    'display_name': customer['DisplayName'],
                    'company_name': customer.get('CompanyName'),
                    'email': customer.get('PrimaryEmailAddr', {}).get('Address')
                }
            })
        else:
            return jsonify({
                'success': True,
                'found': False,
                'message': 'Customer not found'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/test', methods=['GET'])
def api_test():
    """Test API connection"""
    
    if not auth.is_authenticated():
        return jsonify({
            'success': False,
            'error': 'Not authenticated'
        }), 401
    
    try:
        client = QBClient()
        result = client.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("\n" + "="*60)
    print("QUICKBOOKS SYNC SERVICE")
    print("All Painting Ltd - Invoice Integration")
    print("="*60)
    print(f"🌐 Dashboard: http://localhost:{config.PORT}")
    print(f"📡 Environment: {'Sandbox' if config.USE_SANDBOX else 'Production'}")
    print(f"🔑 Client ID: {config.CLIENT_ID[:10]}..." if config.CLIENT_ID else "⚠️ Client ID not configured!")
    print(f"🏢 Company ID: {config.COMPANY_ID}" if config.COMPANY_ID else "⚠️ Company ID not configured!")
    
    if auth.is_authenticated():
        print("✅ Authentication: Connected")
    else:
        print("❌ Authentication: Not connected - visit dashboard to authorize")
    
    print("="*60 + "\n")
    
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=True
    )
