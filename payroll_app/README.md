# ALL PAINTING LTD - PAYROLL AUTOMATION SYSTEM

A comprehensive payroll processing application with AI-powered PDF extraction, TD e-Transfer automation, employee management, and payment history tracking.

## Features

### 📤 Upload & Extract
- Upload payroll PDFs from Eileen Law (thirtyeight00@gmail.com)
- AI-powered extraction using Claude Vision (handles scanned PDFs)
- Automatic duplicate detection via file hashing
- Extracts: Employee name, NET PAY, hours, deductions, pay period

### 👥 Employee Management
- Store e-Transfer email addresses
- Custom security questions per employee
- Mark employees as "Auto-deposit enabled"
- View payment history per employee

### 📊 Dashboard
- Pending payments ready for processing
- One-click batch e-Transfer processing
- Real-time payment totals
- Month/Year statistics

### 📋 Payment History
- Complete searchable history
- Filter by employee, status, date range
- Export to CSV
- Track sent vs pending payments

### ⚙️ Settings
- Default security question/answer
- TD account configuration
- Payment message template
- Email notification toggle

## Installation

### Prerequisites
- Python 3.10+
- pip package manager
- Tesseract OCR (for scanned PDFs)
- Poppler utils (for PDF processing)

### Install Dependencies

```bash
# System dependencies (Ubuntu/Debian)
sudo apt-get install -y poppler-utils tesseract-ocr

# Python dependencies
pip install flask pdfplumber anthropic pdf2image pytesseract selenium playwright
```

### Set Up API Key

```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

Or add to `.env` file:
```
ANTHROPIC_API_KEY=your-api-key-here
```

## Running the Application

```bash
cd payroll_app
python app.py
```

The app will run at `http://localhost:5003`

**Port Assignments (All Painting Apps):**
- Port 5000: Estimate Generator
- Port 5001: Invoice Generator
- Port 5002: Estimate Automation Dashboard
- Port 5003: Payroll Automation (this app)

## Usage Workflow

### 1. Upload Payroll Files
1. Navigate to **Upload** tab
2. Drag & drop PDF files from Eileen Law
3. System extracts employee data and NET PAY amounts
4. Review extraction results

### 2. Configure Employees (First Time)
1. Go to **Employees** tab
2. Click on each employee
3. Add their e-Transfer email address
4. Optionally set custom security question/answer
5. Mark as "Auto-deposit" if applicable

### 3. Process Payments
1. Return to **Dashboard**
2. Review pending payments
3. Select payments to process (or "Select All")
4. Click **Process Selected**
5. Review confirmation modal
6. Click **Proceed to TD**

### 4. TD E-Transfer Flow
1. TD EasyWeb opens in new window
2. Log in manually (credentials never stored)
3. Follow the payment list shown in app
4. Click **Mark as Complete** when done

### 5. Email Notification
- After marking complete, summary email sent to info@allpaintingltd.com
- Includes: All employees, amounts, dates, totals

## Project Structure

```
payroll_app/
├── app.py              # Main Flask application
├── templates/          # HTML templates
│   ├── base.html       # Base template with branding
│   ├── index.html      # Dashboard
│   ├── upload.html     # File upload page
│   ├── upload_results.html
│   ├── employees.html  # Employee list
│   ├── employee_detail.html
│   ├── history.html    # Payment history
│   └── settings.html   # App settings
├── uploads/            # Uploaded PDF files
├── data/               # SQLite database
└── static/             # CSS/JS assets
```

## Database Schema

### employees
- id, name, employee_code
- etransfer_email
- security_question, security_answer
- auto_deposit (boolean)
- active, created_at, updated_at

### payroll_files
- id, filename, file_hash (unique)
- pay_date, pay_period
- total_amount, employee_count
- processed_at, status

### payments
- id, employee_id, employee_name
- amount, pay_date, pay_period
- regular_hours, overtime_hours, stat_hours
- vacation_pay, gross_pay, deductions, net_pay
- file_id, status (pending/sent)
- sent_at, confirmation_number

### settings
- key, value, updated_at

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard |
| `/upload` | GET/POST | Upload payroll files |
| `/employees` | GET | Employee list |
| `/employee/<id>` | GET/POST | Employee details |
| `/history` | GET | Payment history |
| `/settings` | GET/POST | App settings |
| `/process` | POST | Prepare payments for processing |
| `/mark_sent` | POST | Mark payments as sent |
| `/api/pending` | GET | JSON of pending payments |
| `/api/stats` | GET | JSON of dashboard stats |

## Sample Extracted Data

From PRISCILLIANO_FLORES_1_15_26.pdf:
```json
{
    "employee_name": "PRISCILLIANO FLORES",
    "employee_code": "PF1115",
    "pay_date": "2026-01-15",
    "pay_period": "DEC 29 - JAN 11",
    "regular_hours": 52.0,
    "stat_hours": 8.0,
    "vacation_pay": 84.0,
    "gross_pay": 2100.0,
    "total_deductions": 389.48,
    "net_pay": 1710.52
}
```

## Security Notes

- **No stored banking credentials** - You log into TD manually each time
- **File hashing** prevents duplicate processing
- **Local SQLite database** - data stays on your machine
- **API key** should be kept secure (use environment variables)

## Email Configuration

- **Source Email**: thirtyeight00@gmail.com (Eileen Law payroll files)
- **Notification Email**: info@allpaintingltd.com (payment summaries)

## Troubleshooting

### PDF Text Not Extracting
- Ensure poppler-utils and tesseract-ocr are installed
- The app falls back to image-based extraction automatically

### API Errors
- Verify ANTHROPIC_API_KEY is set
- Check API usage limits

### Database Issues
- Delete `data/payroll.db` to reset
- Database recreates on next startup

## Support

Built for All Painting Ltd by Claude AI
1001-115 Schoolhouse Road, Coquitlam, BC V3K 4X8

© 2026 All Painting Ltd
