# Bid System v2.0 - All Painting Ltd.

A microservices-based bid management system that **inherits all logic** from the original `ai-agent-pipedrive` monolith.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BID CENTER (Port 3030)                       │
│              Central Dashboard - Web UI                          │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ Email Scanner │    │ Pipedrive     │    │   Calendar    │
│  (Port 3031)  │    │ Sync (3032)   │    │  (Port 3033)  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────────────┐
                    │  Notifications  │
                    │   (Port 3034)   │
                    └─────────────────┘
```

## Services

### 1. Bid Email Scanner (Port 3031)
**Purpose:** Monitors `info@allpaintingltd.com` for bid invitations using Microsoft Graph API.

**Inherited from:** `ai-agent-pipedrive/backfill.py`
- OutlookGraphClient for email access
- BidEmailAnalyzer with Claude AI for intelligent extraction
- Complete bid classification prompt (valid/invalid emails)
- Date extraction logic with all format support
- GC contact extraction (ignoring tracking emails)
- Duplicate detection against existing bids

**Key Features:**
- Keyword scanning before AI analysis (cost optimization)
- Full email body analysis (not just preview)
- Addendum detection and bid updates
- Background auto-scanning

### 2. Pipedrive Sync (Port 3032)
**Purpose:** Syncs bids to Pipedrive CRM with AI-powered duplicate detection.

**Inherited from:** `ai-agent-pipedrive/pipedrive_sync/`
- `pipedrive_client.py` - Full Pipedrive API client
- `ai_checker.py` - AI duplicate detection
- `deal_sync.py` - Deal sync service

**Key Features:**
- Deal title format: `NB - GC Company - Project Name - Address`
- Organization/Person creation with deduplication
- Email thread linking to deals
- Note creation with bid details
- 75% confidence threshold for duplicates
- Background auto-sync scheduler

### 3. Calendar (Port 3033)
**Purpose:** Creates Outlook calendar events for bid deadlines.

**Inherited from:** `ai-agent-pipedrive/outlook_calendar.py`
- Microsoft Graph API integration
- Duplicate event detection
- Configurable reminders (1 day default)

**Key Features:**
- Pacific Standard Time timezone
- "Bid Deadline" category
- Full bid details in event body
- Event deduplication

### 4. Notifications (Port 3034)
**Purpose:** Sends daily deadline reminder emails.

**Inherited from:** `ai-agent-pipedrive/daily_email.py`
- HTML email template
- Bids due today/tomorrow sections
- High importance for urgent deadlines

**Key Features:**
- Scheduled sending (default 7:00 AM)
- Manual trigger support
- Email logging

### 5. Bid Center (Port 3030)
**Purpose:** Central dashboard for all services.

**Features:**
- Service health monitoring
- Quick stats (total bids, pending sync, due today)
- Quick actions (scan, sync, send email)
- Activity log from sync operations

## Environment Variables

```bash
# Microsoft Graph API (required for email/calendar)
AZURE_CLIENT_SECRET=your_azure_client_secret

# Anthropic Claude API (required for AI features)
ANTHROPIC_API_KEY=your_anthropic_api_key

# Pipedrive API (required for CRM sync)
PIPEDRIVE_API_TOKEN=your_pipedrive_token
PIPEDRIVE_DOMAIN=allpainting

# Optional: Custom bid tracker database path
BID_TRACKER_DB_PATH=C:\Scripts\bid-system\bid-email-scanner\bid_tracker.db
```

## Quick Start

1. Install dependencies for each service:
```bash
pip install flask requests anthropic
```

2. Start services (in separate terminals or use START_ALL.bat):
```bash
# Terminal 1 - Email Scanner
cd bid-email-scanner && python app.py

# Terminal 2 - Pipedrive Sync
cd bid-pipedrive-sync && python app.py

# Terminal 3 - Calendar
cd bid-calendar && python app.py

# Terminal 4 - Notifications
cd bid-notifications && python app.py

# Terminal 5 - Dashboard
cd bid-center && python app.py
```

3. Open dashboard: http://localhost:3030

## API Endpoints

### Email Scanner (3031)
- `GET /api/status` - Scanner status
- `POST /api/scan` - Trigger email scan
- `POST /api/preview` - Preview (keyword scan only)
- `GET /api/bids` - List all bids
- `GET /api/bids/<id>` - Get single bid
- `DELETE /api/bids/<id>` - Delete bid
- `GET/POST /api/settings` - Scanner settings

### Pipedrive Sync (3032)
- `GET /api/status` - Sync status
- `GET /api/test-connection` - Test Pipedrive
- `POST /api/sync` - Sync all unsynced
- `POST /api/sync/<id>` - Sync single bid
- `GET /api/unsynced` - List unsynced bids
- `GET /api/log` - Sync history
- `GET/POST /api/settings/auto-sync` - Auto-sync settings

### Calendar (3033)
- `GET /api/status` - Calendar status
- `POST /api/create/<id>` - Create event for bid
- `GET /api/status/<id>` - Check if bid has event
- `GET /api/bids/due-today` - Bids due today
- `GET /api/bids/due-tomorrow` - Bids due tomorrow
- `GET/POST /api/settings` - Calendar settings

### Notifications (3034)
- `GET /api/status` - Notification status
- `POST /api/send-now` - Send daily email now
- `GET /api/preview` - Preview email data
- `GET/POST /api/settings` - Email settings

## Database Files

Each service maintains its own database:
- `bid-email-scanner/bid_tracker.db` - Main bid database (shared)
- `bid-pipedrive-sync/pipedrive_sync.db` - Sync log
- `bid-calendar/calendar_events.db` - Calendar event log
- `bid-notifications/notifications.db` - Email log

## Migration from ai-agent-pipedrive

This system preserves **all** logic from the original monolith:

| Original File | Migrated To |
|--------------|-------------|
| `app.py` (routes) | Split across all services |
| `backfill.py` | `bid-email-scanner/app.py` |
| `pipedrive_sync/*` | `bid-pipedrive-sync/app.py` |
| `outlook_calendar.py` | `bid-calendar/app.py` |
| `daily_email.py` | `bid-notifications/app.py` |
| `database.py` | Distributed to each service |
| `config.py` | Each service has its own config |

## Key Preserved Features

✅ Complete Claude AI prompt for email classification
✅ All date format recognition patterns
✅ GC contact email filtering (tracking emails ignored)
✅ AI duplicate detection with 75% threshold
✅ Deal title format: NB - GC - Project - Address
✅ Email thread linking to deals
✅ Calendar event deduplication
✅ HTML email template for notifications
✅ Background schedulers for auto-sync and emails
