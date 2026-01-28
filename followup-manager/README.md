# Follow Up Manager

**All Painting Ltd. - Automated Estimate Follow-up System**

Version 1.0 | January 2026

---

## Overview

Follow Up Manager is a standalone Flask application that automates estimate follow-ups for All Painting Ltd. It scans Outlook emails, extracts PDF estimate data, tracks conversations, and generates AI-powered follow-up drafts.

### Key Features

- ✅ Scans Outlook Sent/Inbox for estimate emails
- ✅ Extracts estimate details from attached PDFs
- ✅ AI-powered conversation analysis and status determination
- ✅ Automatic follow-up draft generation (unique each time)
- ✅ Calendar integration for visual reminders
- ✅ Dashboard with full conversation history
- ✅ Export to CSV and SQL formats
- ✅ Database update timestamp tracking

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

```bash
# Windows
set AZURE_CLIENT_SECRET=your_azure_secret_here
set ANTHROPIC_API_KEY=your_claude_api_key_here

# Linux/Mac
export AZURE_CLIENT_SECRET=your_azure_secret_here
export ANTHROPIC_API_KEY=your_claude_api_key_here
```

### 3. Start the Application

**Windows:**
Double-click `START_FOLLOWUP.bat`

**Command Line:**
```bash
python app.py
```

### 4. Access Dashboard

Open your browser to: **http://localhost:1000**

---

## Configuration

### Azure Credentials (config.py)

| Setting | Value |
|---------|-------|
| AZURE_CLIENT_ID | a44dcdf2-049b-43ba-96e8-0c7b46775b9b |
| AZURE_TENANT_ID | 24369179-e3ed-4829-ba28-02803471ac00 |
| AZURE_CLIENT_SECRET | (set as environment variable) |

### Application Settings

| Setting | Default | Description |
|---------|---------|-------------|
| PORT | 1000 | Application port |
| MONITORED_EMAIL | info@allpaintingltd.com | Email account to monitor |
| FIRST_FOLLOWUP_DAYS | 17 | Days before first follow-up |
| SUBSEQUENT_FOLLOWUP_DAYS | 10 | Days between subsequent follow-ups |
| MAX_FOLLOWUPS_BEFORE_ALERT | 4 | Alert after this many follow-ups |

---

## Dashboard Features

### Status Filters

| Status | Color | Description |
|--------|-------|-------------|
| Waiting | Blue | Estimate sent, awaiting response |
| In Conversation | Yellow | Client responded, no decision yet |
| On Hold | Gray | Project delayed or under review |
| Draft Ready | Purple | AI draft waiting in Outlook |
| Won | Green | Project awarded |
| Lost | Red | Project lost or cancelled |

### Actions

- **Scan Now**: Check Outlook for new emails (last 30 days)
- **Backfill**: Import historical estimates (30-365 days)
- **Export CSV**: Download all data as CSV files
- **Export SQL**: Download database as SQL statements
- **Generate Draft**: Create AI-powered follow-up email

### Row Actions

- View Conversation: Full email history
- Mark as Won/Lost/On Hold
- Delay Follow-up: Postpone by X days
- Stop/Resume Follow-ups
- Delete estimate

---

## API Endpoints

### Estimates

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/estimates | List all estimates |
| GET | /api/estimates/:id | Get estimate with communications |
| PATCH | /api/estimates/:id | Update estimate |
| DELETE | /api/estimates/:id | Delete estimate |
| POST | /api/estimates/:id/delay | Delay follow-up |
| POST | /api/estimates/bulk | Bulk update |

### Scanning

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/scan | Manual email scan |
| POST | /api/backfill | Historical backfill |
| GET | /api/scan/status | Get scan status |

### Follow-ups

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/followups/pending | Get pending follow-ups |
| POST | /api/followups/:id/generate | Generate draft |
| GET | /api/followups/:id/draft | Get draft content |

### Export

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/export/csv | Download CSV (zipped) |
| GET | /api/export/sql | Download SQL file |
| GET | /api/db/stats | Database statistics |
| GET | /api/db/last-update | Last update timestamp |

---

## Database Schema

### estimates
- id, estimate_code (unique), estimate_date, gc_company
- contact_name, contact_email, contact_phone, client_address
- project_name, project_address, scope_summary, total_amount
- status, revision_number, last_contact_date, next_followup_date
- followup_count, stop_followup, created_at, updated_at

### communications
- id, estimate_id (FK), email_id (unique), conversation_id
- direction, subject, body_text, body_preview
- from_email, to_email, email_date
- has_attachment, is_followup, followup_number, ai_analysis

### followups
- id, estimate_id (FK), followup_number, scheduled_date
- draft_content, draft_subject, draft_created_at
- outlook_draft_id, sent_at, calendar_event_id, status

### settings
- key, value, updated_at

---

## File Structure

```
followup-manager/
├── app.py              # Main Flask application
├── config.py           # Configuration settings
├── database.py         # SQLite operations
├── outlook_client.py   # Microsoft Graph API
├── pdf_extractor.py    # PDF parsing
├── ai_analyzer.py      # Claude API integration
├── email_scanner.py    # Email scanning logic
├── followup_engine.py  # Follow-up scheduling
├── calendar_manager.py # Calendar operations
├── followup_manager.db # SQLite database
├── templates/
│   └── index.html      # Dashboard template
├── requirements.txt    # Python dependencies
├── START_FOLLOWUP.bat  # Windows start script
├── STOP_FOLLOWUP.bat   # Windows stop script
└── README.md           # This file
```

---

## Troubleshooting

### "Failed to obtain access token"
- Check AZURE_CLIENT_SECRET environment variable
- Verify Azure app registration permissions

### "Anthropic API error"
- Check ANTHROPIC_API_KEY environment variable
- Verify API key has sufficient credits

### No estimates found after scan
- Ensure emails have "Estimate - CODE - " in subject
- Check that estimate code matches pattern (e.g., 26C-022)

### PDF extraction fails
- Ensure PDF is not password-protected
- Check pdfplumber is installed: `pip install pdfplumber`

---

## Support

For issues or questions, contact the development team.

**All Painting Ltd.**  
(604) 525-1403  
info@allpaintingltd.com
