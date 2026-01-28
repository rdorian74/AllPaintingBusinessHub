"""
ALL PAINTING LTD - PAYROLL AUTOMATION SYSTEM
=============================================
Comprehensive payroll processing with AI-powered PDF extraction,
TD e-Transfer automation, and payment history tracking.

Author: Built for Rodrigo @ All Painting Ltd
"""

import os
import sqlite3
import json
import re
import hashlib
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, send_file
import pdfplumber
import anthropic
from pdf2image import convert_from_path
import base64
import io

app = Flask(__name__)
app.secret_key = 'all_painting_payroll_2026_secure_key'

# Configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')
DB_PATH = os.path.join(DATA_FOLDER, 'payroll.db')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_FOLDER, exist_ok=True)

# Email configuration for Eileen Law's payroll files
EILEEN_EMAIL = 'thirtyeight00@gmail.com'
NOTIFICATION_EMAIL = 'info@allpaintingltd.com'

# Initialize Anthropic client
client = anthropic.Anthropic()

def init_db():
    """Initialize the SQLite database with all required tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Employees table - stores employee info and e-Transfer emails
    c.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            employee_code TEXT,
            etransfer_email TEXT,
            security_question TEXT,
            security_answer TEXT,
            auto_deposit INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Payroll files table - tracks processed files to prevent duplicates
    c.execute('''
        CREATE TABLE IF NOT EXISTS payroll_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            file_hash TEXT UNIQUE NOT NULL,
            pay_date TEXT,
            pay_period TEXT,
            total_amount REAL,
            employee_count INTEGER,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'processed'
        )
    ''')
    
    # Payments table - detailed payment history
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            employee_name TEXT NOT NULL,
            amount REAL NOT NULL,
            pay_date TEXT,
            pay_period TEXT,
            regular_hours REAL,
            overtime_hours REAL,
            stat_hours REAL,
            vacation_pay REAL,
            gross_pay REAL,
            deductions REAL,
            net_pay REAL,
            file_id INTEGER,
            status TEXT DEFAULT 'pending',
            sent_at TIMESTAMP,
            confirmation_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (file_id) REFERENCES payroll_files(id)
        )
    ''')
    
    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insert default settings if not exist
    default_settings = [
        ('default_security_question', 'What company is this payment from?'),
        ('default_security_answer', 'allpainting'),
        ('td_account_name', 'Business Chequing'),
        ('message_template', 'All Painting Ltd - Payroll {period}'),
        ('email_notifications', '1'),
    ]
    
    for key, value in default_settings:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_file_hash(filepath):
    """Calculate MD5 hash of a file for duplicate detection."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read(65536)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(65536)
    return hasher.hexdigest()

def extract_payroll_data_with_ai(pdf_path):
    """
    Use Claude AI to extract payroll data from PDF.
    Returns structured data with employee info and payment details.
    Handles both text-based and image-based (scanned) PDFs.
    """
    import base64
    from pdf2image import convert_from_path
    
    # First, try to extract text from PDF
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n\n"
    
    # If no text found, use OCR/vision approach
    if not full_text.strip():
        try:
            # Convert PDF to images
            images = convert_from_path(pdf_path, dpi=150)
            
            # Convert first page (usually the pay stub) to base64
            import io
            image_contents = []
            
            for i, img in enumerate(images[:2]):  # Process first 2 pages max
                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                img_base64 = base64.standard_b64encode(buffer.getvalue()).decode('utf-8')
                image_contents.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_base64
                    }
                })
            
            # Add text prompt
            image_contents.append({
                "type": "text",
                "text": """Extract payroll information from this pay stub image. Return ONLY a JSON object with no additional text.

Return a JSON object with these exact fields:
{
    "employee_name": "Full name exactly as shown",
    "employee_code": "Employee ID/code if present (e.g., PF1115)",
    "pay_date": "Pay date in YYYY-MM-DD format",
    "pay_period": "Pay period description (e.g., DEC 29 - JAN 11)",
    "regular_rate": hourly rate as number,
    "regular_hours": regular hours as number,
    "overtime_hours": overtime hours as number,
    "stat_hours": statutory holiday hours as number,
    "regular_pay": regular earnings as number,
    "overtime_pay": overtime earnings as number,
    "stat_pay": stat pay as number,
    "vacation_pay": vacation pay as number,
    "gross_pay": total earnings before deductions as number,
    "income_tax": income tax deduction as number,
    "ei_deduction": EI deduction as number,
    "cpp_deduction": CPP deduction as number,
    "total_deductions": total deductions as number,
    "net_pay": final net pay amount as number
}

Important: net_pay is the most critical field - this is what will be e-Transferred.
Return ONLY the JSON object, no other text."""
            })
            
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": image_contents}]
            )
            
            result_text = response.content[0].text.strip()
            
        except Exception as e:
            return None, f"Could not process PDF as image: {str(e)}"
    else:
        # Use text-based extraction
        prompt = f"""Extract payroll information from this pay stub document. Return ONLY a JSON object with no additional text.

Document text:
{full_text}

Return a JSON object with these exact fields:
{{
    "employee_name": "Full name exactly as shown",
    "employee_code": "Employee ID/code if present (e.g., PF1115)",
    "pay_date": "Pay date in YYYY-MM-DD format",
    "pay_period": "Pay period description (e.g., DEC 29 - JAN 11)",
    "regular_rate": hourly rate as number,
    "regular_hours": regular hours as number,
    "overtime_hours": overtime hours as number,
    "stat_hours": statutory holiday hours as number,
    "regular_pay": regular earnings as number,
    "overtime_pay": overtime earnings as number,
    "stat_pay": stat pay as number,
    "vacation_pay": vacation pay as number,
    "gross_pay": total earnings before deductions as number,
    "income_tax": income tax deduction as number,
    "ei_deduction": EI deduction as number,
    "cpp_deduction": CPP deduction as number,
    "total_deductions": total deductions as number,
    "net_pay": final net pay amount as number
}}

Important: net_pay is the most critical field - this is what will be e-Transferred.
Return ONLY the JSON object, no other text."""

        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
        except Exception as e:
            return None, f"AI extraction error: {str(e)}"
    
    try:
        # Clean up potential markdown formatting
        if result_text.startswith('```'):
            result_text = re.sub(r'^```json?\n?', '', result_text)
            result_text = re.sub(r'\n?```$', '', result_text)
        
        data = json.loads(result_text)
        return data, None
        
    except json.JSONDecodeError as e:
        return None, f"Failed to parse AI response as JSON: {str(e)}\nResponse was: {result_text[:200]}"
    except Exception as e:
        return None, f"AI extraction error: {str(e)}"

def check_duplicate_file(file_hash):
    """
    Check if a file has already been processed AND paid.
    Returns: 
        - None if file can be uploaded (not seen before, or seen but payment deleted)
        - 'sent' if file was already paid (block upload)
        - 'pending' if file has a pending payment (block upload)
    """
    conn = get_db()
    
    # Check if file exists
    file_record = conn.execute(
        'SELECT * FROM payroll_files WHERE file_hash = ?', 
        (file_hash,)
    ).fetchone()
    
    if not file_record:
        conn.close()
        return None  # File never uploaded, allow
    
    # File exists - check if there's an associated payment
    payment = conn.execute(
        'SELECT * FROM payments WHERE file_id = ?',
        (file_record['id'],)
    ).fetchone()
    
    conn.close()
    
    if not payment:
        # File record exists but payment was deleted - allow re-upload
        # Clean up the orphaned file record
        conn = get_db()
        conn.execute('DELETE FROM payroll_files WHERE id = ?', (file_record['id'],))
        conn.commit()
        conn.close()
        return None  # Allow upload
    
    # Payment exists - check status
    return payment['status']  # 'sent' or 'pending'

def get_or_create_employee(name, employee_code=None):
    """Get existing employee or create new one."""
    conn = get_db()
    
    # Normalize name for comparison
    normalized_name = name.strip().upper()
    
    employee = conn.execute(
        'SELECT * FROM employees WHERE UPPER(name) = ?',
        (normalized_name,)
    ).fetchone()
    
    if employee:
        conn.close()
        return dict(employee)
    
    # Create new employee
    conn.execute(
        '''INSERT INTO employees (name, employee_code) VALUES (?, ?)''',
        (name.strip(), employee_code)
    )
    conn.commit()
    
    employee = conn.execute(
        'SELECT * FROM employees WHERE UPPER(name) = ?',
        (normalized_name,)
    ).fetchone()
    conn.close()
    
    return dict(employee)

def get_previous_payment(employee_name):
    """Get the most recent previous payment for comparison."""
    conn = get_db()
    result = conn.execute('''
        SELECT * FROM payments 
        WHERE UPPER(employee_name) = UPPER(?)
        ORDER BY created_at DESC
        LIMIT 1 OFFSET 1
    ''', (employee_name,)).fetchone()
    conn.close()
    return dict(result) if result else None

def get_setting(key):
    """Get a setting value."""
    conn = get_db()
    result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return result['value'] if result else None

def update_setting(key, value):
    """Update a setting value."""
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
    ''', (key, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def send_email_summary(payments, total_amount):
    """Send email summary of completed payroll payments."""
    # Build email content
    pay_date = payments[0]['pay_date'] if payments else datetime.now().strftime('%Y-%m-%d')
    pay_period = payments[0]['pay_period'] if payments else 'Current Period'
    
    subject = f"All Painting Ltd - Payroll Completed - {pay_date}"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .header {{ background: #1a365d; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background: #f5f5f5; }}
            .total {{ font-weight: bold; background: #e8f4f8; }}
            .footer {{ background: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>ALL PAINTING LTD</h1>
            <h2>Payroll Payment Summary</h2>
        </div>
        <div class="content">
            <p><strong>Pay Date:</strong> {pay_date}</p>
            <p><strong>Pay Period:</strong> {pay_period}</p>
            <p><strong>Processed:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <table>
                <tr>
                    <th>Employee</th>
                    <th>Net Pay</th>
                    <th>Status</th>
                </tr>
    """
    
    for payment in payments:
        status_color = '#28a745' if payment['status'] == 'sent' else '#ffc107'
        html_content += f"""
                <tr>
                    <td>{payment['employee_name']}</td>
                    <td>${payment['net_pay']:,.2f}</td>
                    <td style="color: {status_color};">{payment['status'].upper()}</td>
                </tr>
        """
    
    html_content += f"""
                <tr class="total">
                    <td>TOTAL</td>
                    <td>${total_amount:,.2f}</td>
                    <td>{len(payments)} payments</td>
                </tr>
            </table>
            
            <p>This is an automated notification from the All Painting Ltd Payroll System.</p>
        </div>
        <div class="footer">
            All Painting Ltd - 1001-115 Schoolhouse Road, Coquitlam, BC V3K 4X8
        </div>
    </body>
    </html>
    """
    
    return {
        'to': NOTIFICATION_EMAIL,
        'subject': subject,
        'html': html_content,
        'text': f"Payroll completed for {pay_date}. {len(payments)} payments totaling ${total_amount:,.2f}"
    }

# Initialize database on startup
init_db()

# ============== ROUTES ==============

@app.route('/')
def index():
    """Main dashboard showing current payroll status."""
    conn = get_db()
    
    # Get pending payments with employee details including security Q&A
    pending = conn.execute('''
        SELECT p.*, e.etransfer_email, e.auto_deposit, e.security_question, e.security_answer
        FROM payments p
        LEFT JOIN employees e ON p.employee_id = e.id
        WHERE p.status = 'pending'
        ORDER BY p.created_at DESC
    ''').fetchall()
    
    # Get recent completed payments
    recent = conn.execute('''
        SELECT * FROM payments
        WHERE status = 'sent'
        ORDER BY sent_at DESC
        LIMIT 10
    ''').fetchall()
    
    # Get statistics
    stats = {
        'pending_count': len(pending),
        'pending_total': sum(p['net_pay'] for p in pending),
        'this_month_total': conn.execute('''
            SELECT COALESCE(SUM(net_pay), 0) FROM payments
            WHERE status = 'sent' AND strftime('%Y-%m', sent_at) = strftime('%Y-%m', 'now')
        ''').fetchone()[0],
        'this_year_total': conn.execute('''
            SELECT COALESCE(SUM(net_pay), 0) FROM payments
            WHERE status = 'sent' AND strftime('%Y', sent_at) = strftime('%Y', 'now')
        ''').fetchone()[0],
    }
    
    conn.close()
    
    return render_template('index.html', 
                          pending=pending, 
                          recent=recent, 
                          stats=stats)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """Upload and process payroll PDFs."""
    if request.method == 'POST':
        if 'files' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('files')
        results = []
        
        for file in files:
            if file.filename == '':
                continue
            
            if not file.filename.lower().endswith('.pdf'):
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': 'Not a PDF file'
                })
                continue
            
            # Save file
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            
            # Check for duplicate
            file_hash = get_file_hash(filepath)
            dup_status = check_duplicate_file(file_hash)
            
            if dup_status == 'sent':
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': 'Payment already SENT for this file - cannot re-upload'
                })
                os.remove(filepath)
                continue
            elif dup_status == 'pending':
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': 'Payment already PENDING for this file - delete it first if you want to re-upload'
                })
                os.remove(filepath)
                continue
            
            # Extract data with AI
            data, error = extract_payroll_data_with_ai(filepath)
            
            if error:
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': error
                })
                continue
            
            # Get or create employee
            employee = get_or_create_employee(
                data.get('employee_name', 'Unknown'),
                data.get('employee_code')
            )
            
            # Check for previous payment for comparison
            previous = get_previous_payment(data['employee_name'])
            
            conn = get_db()
            
            # Record the file
            cursor = conn.execute('''
                INSERT INTO payroll_files (filename, file_hash, pay_date, pay_period, total_amount, employee_count)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (file.filename, file_hash, data.get('pay_date'), data.get('pay_period'), data.get('net_pay')))
            file_id = cursor.lastrowid
            
            # Record the payment
            conn.execute('''
                INSERT INTO payments (
                    employee_id, employee_name, amount, pay_date, pay_period,
                    regular_hours, overtime_hours, stat_hours, vacation_pay,
                    gross_pay, deductions, net_pay, file_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (
                employee['id'],
                data['employee_name'],
                data['net_pay'],
                data.get('pay_date'),
                data.get('pay_period'),
                data.get('regular_hours', 0),
                data.get('overtime_hours', 0),
                data.get('stat_hours', 0),
                data.get('vacation_pay', 0),
                data.get('gross_pay', 0),
                data.get('total_deductions', 0),
                data['net_pay'],
                file_id
            ))
            
            conn.commit()
            conn.close()
            
            results.append({
                'filename': file.filename,
                'success': True,
                'data': data,
                'employee': employee,
                'previous': previous,
                'change': data['net_pay'] - previous['net_pay'] if previous else None
            })
        
        return render_template('upload_results.html', results=results)
    
    return render_template('upload.html')

@app.route('/employees', methods=['GET', 'POST'])
def employees():
    """Manage employee e-Transfer information."""
    conn = get_db()
    
    if request.method == 'POST':
        # Add new employee
        name = request.form.get('name', '').strip()
        if name:
            try:
                conn.execute('''
                    INSERT INTO employees (name, employee_code, etransfer_email, auto_deposit)
                    VALUES (?, ?, ?, ?)
                ''', (
                    name,
                    request.form.get('employee_code', '').strip() or None,
                    request.form.get('etransfer_email', '').strip() or None,
                    1 if request.form.get('auto_deposit') else 0
                ))
                conn.commit()
                flash(f'Employee "{name}" added successfully', 'success')
            except sqlite3.IntegrityError:
                flash(f'Employee "{name}" already exists', 'error')
        else:
            flash('Employee name is required', 'error')
    
    employees = conn.execute('''
        SELECT e.*, 
               (SELECT COUNT(*) FROM payments WHERE employee_id = e.id) as payment_count,
               (SELECT SUM(net_pay) FROM payments WHERE employee_id = e.id AND status = 'sent') as total_paid
        FROM employees e
        WHERE active = 1
        ORDER BY name
    ''').fetchall()
    conn.close()
    return render_template('employees.html', employees=employees)

@app.route('/employee/<int:id>', methods=['GET', 'POST'])
def employee_detail(id):
    """View/edit employee details."""
    conn = get_db()
    
    if request.method == 'POST':
        # Check if this is a delete request
        if request.form.get('action') == 'delete':
            conn.execute('DELETE FROM employees WHERE id = ?', (id,))
            conn.commit()
            conn.close()
            flash('Employee deleted successfully', 'success')
            return redirect(url_for('employees'))
        
        # Update employee
        conn.execute('''
            UPDATE employees SET
                name = ?,
                employee_code = ?,
                etransfer_email = ?,
                security_question = ?,
                security_answer = ?,
                auto_deposit = ?,
                updated_at = ?
            WHERE id = ?
        ''', (
            request.form.get('name', '').strip(),
            request.form.get('employee_code', '').strip() or None,
            request.form.get('etransfer_email'),
            request.form.get('security_question'),
            request.form.get('security_answer'),
            1 if request.form.get('auto_deposit') else 0,
            datetime.now().isoformat(),
            id
        ))
        conn.commit()
        flash('Employee updated successfully', 'success')
    
    employee = conn.execute('SELECT * FROM employees WHERE id = ?', (id,)).fetchone()
    payments = conn.execute('''
        SELECT * FROM payments WHERE employee_id = ?
        ORDER BY created_at DESC LIMIT 20
    ''', (id,)).fetchall()
    
    conn.close()
    return render_template('employee_detail.html', employee=employee, payments=payments)

@app.route('/history')
def history():
    """View complete payment history."""
    conn = get_db()
    
    # Filter parameters
    employee = request.args.get('employee')
    status = request.args.get('status')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    query = 'SELECT * FROM payments WHERE 1=1'
    params = []
    
    if employee:
        query += ' AND UPPER(employee_name) LIKE UPPER(?)'
        params.append(f'%{employee}%')
    
    if status:
        query += ' AND status = ?'
        params.append(status)
    
    if date_from:
        query += ' AND pay_date >= ?'
        params.append(date_from)
    
    if date_to:
        query += ' AND pay_date <= ?'
        params.append(date_to)
    
    query += ' ORDER BY created_at DESC LIMIT 100'
    
    payments = conn.execute(query, params).fetchall()
    
    # Get all employees for filter dropdown
    employees = conn.execute('SELECT DISTINCT employee_name FROM payments ORDER BY employee_name').fetchall()
    
    # Statistics
    stats = {
        'total_payments': len(payments),
        'total_amount': sum(p['net_pay'] for p in payments),
    }
    
    conn.close()
    return render_template('history.html', 
                          payments=payments, 
                          employees=employees,
                          stats=stats,
                          filters={
                              'employee': employee,
                              'status': status,
                              'date_from': date_from,
                              'date_to': date_to
                          })

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """Application settings."""
    conn = get_db()
    
    if request.method == 'POST':
        for key in ['default_security_question', 'default_security_answer', 
                    'td_account_name', 'message_template', 'email_notifications']:
            value = request.form.get(key, '')
            conn.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, datetime.now().isoformat()))
        conn.commit()
        flash('Settings saved successfully', 'success')
    
    settings = {}
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    for row in rows:
        settings[row['key']] = row['value']
    
    conn.close()
    return render_template('settings.html', settings=settings)

@app.route('/process', methods=['POST'])
def process_payments():
    """Process selected payments - generates TD automation data."""
    payment_ids = request.form.getlist('payment_ids')
    
    if not payment_ids:
        return jsonify({'success': False, 'error': 'No payments selected'})
    
    conn = get_db()
    
    payments_to_process = []
    missing_emails = []
    
    for pid in payment_ids:
        payment = conn.execute('''
            SELECT p.*, e.etransfer_email, e.security_question, e.security_answer, e.auto_deposit
            FROM payments p
            LEFT JOIN employees e ON p.employee_id = e.id
            WHERE p.id = ?
        ''', (pid,)).fetchone()
        
        if payment:
            payment_dict = dict(payment)
            
            # Check for e-Transfer email
            if not payment_dict.get('etransfer_email') and not payment_dict.get('auto_deposit'):
                missing_emails.append(payment_dict['employee_name'])
            else:
                payments_to_process.append(payment_dict)
    
    conn.close()
    
    if missing_emails:
        return jsonify({
            'success': False,
            'error': f'Missing e-Transfer email for: {", ".join(missing_emails)}',
            'missing_emails': missing_emails
        })
    
    # Generate message template
    message_template = get_setting('message_template') or 'All Painting Ltd - Payroll {period}'
    
    # Prepare automation data
    automation_data = {
        'payments': payments_to_process,
        'total': sum(p['net_pay'] for p in payments_to_process),
        'count': len(payments_to_process),
        'default_security_question': get_setting('default_security_question'),
        'default_security_answer': get_setting('default_security_answer'),
        'td_account': get_setting('td_account_name'),
        'message_template': message_template
    }
    
    return jsonify({
        'success': True,
        'data': automation_data
    })

# Global variable to hold Selenium automation instance
td_automation_instance = None

@app.route('/start_automation', methods=['POST'])
def start_automation():
    """Start the Selenium browser for TD automation."""
    global td_automation_instance
    
    try:
        from td_automation import TDAutomation
        
        # Close existing instance if any
        if td_automation_instance:
            try:
                td_automation_instance.close()
            except:
                pass
        
        # Start new browser
        td_automation_instance = TDAutomation()
        td_automation_instance.start_browser()
        td_automation_instance.open_td_login()
        
        return jsonify({
            'success': True,
            'message': 'Browser opened. Please log into TD EasyWeb.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/check_td_login', methods=['GET'])
def check_td_login():
    """Check if user has logged into TD."""
    global td_automation_instance
    
    if not td_automation_instance:
        return jsonify({'logged_in': False, 'error': 'No browser session'})
    
    try:
        logged_in = td_automation_instance.is_logged_in()
        return jsonify({'logged_in': logged_in})
    except Exception as e:
        return jsonify({'logged_in': False, 'error': str(e)})

@app.route('/fill_etransfer', methods=['POST'])
def fill_etransfer():
    """Fill the e-Transfer form for one payment."""
    global td_automation_instance
    
    if not td_automation_instance:
        return jsonify({'success': False, 'error': 'No browser session'})
    
    data = request.json
    
    try:
        # Navigate to e-Transfer page if needed
        td_automation_instance.navigate_to_etransfer()
        time.sleep(2)
        
        # Get default security settings
        default_sq = get_setting('default_security_question') or ''
        default_sa = get_setting('default_security_answer') or ''
        
        # Use custom or default security
        sq = data.get('security_question') or default_sq
        sa = data.get('security_answer') or default_sa
        
        # Skip security if auto-deposit
        if data.get('auto_deposit'):
            sq = ''
            sa = ''
        
        # Build message
        message_template = get_setting('message_template') or 'All Painting Ltd - Payroll'
        message = message_template.replace('{period}', data.get('pay_period', ''))
        
        result = td_automation_instance.fill_etransfer_form(
            recipient_email=data['etransfer_email'],
            amount=data['net_pay'],
            recipient_name=data['employee_name'],
            message=message,
            security_question=sq,
            security_answer=sa
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/confirm_sent', methods=['POST'])
def confirm_sent():
    """User confirms they clicked Send in TD."""
    global td_automation_instance
    
    data = request.json
    payment_id = data.get('payment_id')
    
    if not payment_id:
        return jsonify({'success': False, 'error': 'No payment ID'})
    
    try:
        # Update payment status
        conn = get_db()
        conn.execute('''
            UPDATE payments SET
                status = 'sent',
                sent_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), payment_id))
        conn.commit()
        conn.close()
        
        # Try to click "Send Another" in TD
        if td_automation_instance:
            try:
                td_automation_instance.click_send_another()
            except:
                pass
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/close_automation', methods=['POST'])
def close_automation():
    """Close the Selenium browser."""
    global td_automation_instance
    
    if td_automation_instance:
        try:
            td_automation_instance.close()
        except:
            pass
        td_automation_instance = None
    
    return jsonify({'success': True})

@app.route('/mark_sent', methods=['POST'])
def mark_sent():
    """Mark payments as sent after TD automation completes."""
    data = request.json
    payment_ids = data.get('payment_ids', [])
    
    if not payment_ids:
        return jsonify({'success': False, 'error': 'No payment IDs provided'})
    
    conn = get_db()
    
    payments = []
    total = 0
    
    for pid in payment_ids:
        conn.execute('''
            UPDATE payments SET
                status = 'sent',
                sent_at = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), pid))
        
        payment = conn.execute('SELECT * FROM payments WHERE id = ?', (pid,)).fetchone()
        if payment:
            payments.append(dict(payment))
            total += payment['net_pay']
    
    conn.commit()
    conn.close()
    
    # Generate email summary
    email_data = send_email_summary(payments, total)
    
    return jsonify({
        'success': True,
        'marked_count': len(payment_ids),
        'total_amount': total,
        'email_summary': email_data
    })

@app.route('/delete_payment', methods=['POST'])
def delete_payment():
    """Delete a pending payment."""
    data = request.json
    payment_id = data.get('payment_id')
    
    if not payment_id:
        return jsonify({'success': False, 'error': 'No payment ID provided'})
    
    conn = get_db()
    
    # Check if payment exists and is pending
    payment = conn.execute('SELECT * FROM payments WHERE id = ? AND status = ?', (payment_id, 'pending')).fetchone()
    
    if not payment:
        conn.close()
        return jsonify({'success': False, 'error': 'Payment not found or already sent'})
    
    # Delete the payment
    conn.execute('DELETE FROM payments WHERE id = ?', (payment_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'deleted_id': payment_id
    })

@app.route('/mark_single_sent', methods=['POST'])
def mark_single_sent():
    """Mark a single payment as sent."""
    data = request.json
    payment_id = data.get('payment_id')
    
    if not payment_id:
        return jsonify({'success': False, 'error': 'No payment ID provided'})
    
    conn = get_db()
    
    # Check if payment exists and is pending
    payment = conn.execute('SELECT * FROM payments WHERE id = ? AND status = ?', (payment_id, 'pending')).fetchone()
    
    if not payment:
        conn.close()
        return jsonify({'success': False, 'error': 'Payment not found or already sent'})
    
    # Mark as sent
    conn.execute('''
        UPDATE payments SET
            status = 'sent',
            sent_at = ?
        WHERE id = ?
    ''', (datetime.now().isoformat(), payment_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'payment_id': payment_id
    })

@app.route('/api/pending')
def api_pending():
    """API endpoint for pending payments."""
    conn = get_db()
    pending = conn.execute('''
        SELECT p.*, e.etransfer_email
        FROM payments p
        LEFT JOIN employees e ON p.employee_id = e.id
        WHERE p.status = 'pending'
    ''').fetchall()
    conn.close()
    
    return jsonify({
        'payments': [dict(p) for p in pending],
        'total': sum(p['net_pay'] for p in pending),
        'count': len(pending)
    })

@app.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics."""
    conn = get_db()
    
    stats = {
        'pending_total': conn.execute(
            'SELECT COALESCE(SUM(net_pay), 0) FROM payments WHERE status = "pending"'
        ).fetchone()[0],
        'pending_count': conn.execute(
            'SELECT COUNT(*) FROM payments WHERE status = "pending"'
        ).fetchone()[0],
        'month_total': conn.execute('''
            SELECT COALESCE(SUM(net_pay), 0) FROM payments
            WHERE status = 'sent' AND strftime('%Y-%m', sent_at) = strftime('%Y-%m', 'now')
        ''').fetchone()[0],
        'year_total': conn.execute('''
            SELECT COALESCE(SUM(net_pay), 0) FROM payments
            WHERE status = 'sent' AND strftime('%Y', sent_at) = strftime('%Y', 'now')
        ''').fetchone()[0],
        'employee_count': conn.execute(
            'SELECT COUNT(*) FROM employees WHERE active = 1'
        ).fetchone()[0],
    }
    
    conn.close()
    return jsonify(stats)

if __name__ == '__main__':
    print("=" * 60)
    print("   ALL PAINTING LTD - PAYROLL AUTOMATION SYSTEM")
    print("=" * 60)
    print(f"   Dashboard: http://localhost:5003")
    print("   Press Ctrl+C to stop")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5003)
