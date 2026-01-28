# Bid/Addendum Email Forwarding Agent

**All Painting Ltd.**

Automatically detects and forwards bid invitations, addendums, and clarifications to Ian.

## Changelog

### Version 2.0 (January 2025)

**Bug Fixes:**
1. **Forward drafts now preserve attachments** - Changed from creating new drafts to creating proper forwards that maintain all original attachments from the bid email.

2. **Fixed duplicate bid/addendum detection** - Added multiple layers of protection:
   - Check by `internet_message_id` (stable across forwards)
   - Check for similar subject/sender within 2 hours
   - Improved Claude prompt to correctly categorize emails that mention addenda vs ARE addendums

3. **Fixed infinite loop from manual forwards** - Added comprehensive checks:
   - Detects if email is FROM internal addresses (info@, estimates@, etc.)
   - Detects if Ian is already in TO/CC recipients
   - Detects emails with "NEW BID DETECTED" or "ADDENDUM DETECTED" in subject
   - Checks for FW:/Fwd: prefixes combined with internal recipients

4. **Updated draft message wording** - Now includes friendly greeting:
   > "Hi Ian, this just arrived. Please take a look at the summary below."

**Technical Improvements:**
- Added `internet_message_id` tracking in processing log
- Added database indexes for faster duplicate detection
- Added `to_addresses` to Claude analysis for better loop detection
- Improved Claude prompt with clearer categorization rules

## Features

- **Email Monitoring**: Polls `info@allpaintingltd.com` every 5 minutes
- **Keyword Detection**: Free local scan before calling Claude API
- **Claude Verification**: AI validates if email is a legitimate bid
- **Smart Deduplication**: Tracks bids and recognizes addendums to existing projects
- **Draft Mode**: Creates drafts for review before going live
- **Active Mode**: Forwards emails automatically
- **Bid Tracker Database**: Tracks all projects, addendums, due dates
- **GC Contacts Database**: Builds a database of general contractors over time
- **Web Dashboard**: Monitor activity, costs, and manage settings

## Installation

1. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```
   Or run `install.bat` on Windows.

2. **Set environment variables:**
   ```
   set AZURE_CLIENT_SECRET=your_azure_secret_here
   set ANTHROPIC_API_KEY=your_anthropic_key_here
   ```

3. **Run the agent:**
   ```
   python main.py
   ```
   Or run `run_bid_agent.bat` on Windows.

4. **Open the dashboard:**
   Go to `http://localhost:5012`

## Configuration

Edit `config.py` to customize:

- `CHECK_INTERVAL_SECONDS`: How often to check (default: 300 = 5 minutes)
- `OPERATION_MODE`: "draft" or "active"
- `DRAFTS_FOLDER_NAME`: Folder for drafts (default: "Draft-New Bid or Addendum")
- `FORWARD_TO_EMAIL`: Where to forward (default: ianc@allpaintingltd.com)
- `BID_KEYWORDS`: Keywords to detect

## How It Works

```
Email arrives at info@allpaintingltd.com
         │
         ▼
   Keyword scan (free)
         │
   Match? ─── No ──▶ [Skip - not logged]
         │
         ▼
   From Ian? ─── Yes ──▶ [Skip - loop protection]
         │
         ▼
   Claude verifies:
   • New bid / addendum / clarification?
   • From GC or legit source?
   • Not newsletter/spam?
         │
   Valid? ─── No ──▶ [Log: Skipped with reason]
         │
         ▼
   Update Bid Tracker:
   • New project? Create entry
   • Existing project? Update addendum count
         │
         ▼
   Update GC Contacts database
         │
         ▼
   [Draft Mode] ──▶ Create draft in "Draft-New Bid or Addendum" folder
   [Active Mode] ──▶ Forward to Ian with AI-generated note
```

## Database Tables

### bid_tracker
- Project name, GC info, due dates
- Addendum tracking
- All related email IDs

### processing_log
- Every email processed
- Status (forwarded/skipped/draft_created)
- Skip reasons
- Claude analysis

### gc_contacts
- General contractor database
- Built automatically over time
- Tracks bid count per company

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Agent status and stats |
| `/api/set-mode` | POST | Set draft/active mode |
| `/api/bids` | GET | Recent bids |
| `/api/bids/open` | GET | Open bids only |
| `/api/processing-log` | GET | Email processing history |
| `/api/gc-contacts` | GET | GC database |
| `/api/costs` | GET | API cost summary |
| `/api/check-now` | POST | Trigger immediate check |

## Costs

- **Free**: Keyword scanning, database operations
- **Claude API**: ~$0.005-$0.01 per email that passes keyword scan

## Files

```
bid-addendum-agent/
├── config.py          # Configuration
├── outlook_client.py  # Microsoft Graph API
├── email_monitor.py   # Email detection logic
├── bid_analyzer.py    # Claude API integration
├── database.py        # SQLite database
├── main.py            # Entry point + dashboard
├── requirements.txt   # Dependencies
├── install.bat        # Windows installer
├── run_bid_agent.bat  # Windows launcher
└── bid_agent.db       # SQLite database (created on first run)
```

## Troubleshooting

### "AZURE_CLIENT_SECRET not configured"
Set the environment variable with your Azure app secret.

### "ANTHROPIC_API_KEY not configured"
Set the environment variable with your Anthropic API key.

### Emails not being detected
- Check the dashboard processing log for skip reasons
- Verify keywords in `config.py`
- Try "Check Now" button with a longer time range

### Drafts not appearing
- Check that the folder "Draft-New Bid or Addendum" exists in Outlook
- The folder is created automatically on first use

## Future Enhancements

- Calendar integration (auto-create bid due date reminders)
- Weekly summary reports
- Bid submission tracking
- Urgent bid alerts (due within 48 hours)
