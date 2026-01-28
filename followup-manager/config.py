"""
Follow Up Manager - Configuration
All Painting Ltd.
"""
import os

# App
APP_NAME = "Follow Up Manager"
PORT = 1000
DEBUG = False

# Azure/Graph API
AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TOKEN_URL = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
MONITORED_EMAIL = "info@allpaintingltd.com"

# Claude API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Follow-up Settings
DEFAULT_FIRST_FOLLOWUP_DAYS = 17
DEFAULT_SUBSEQUENT_FOLLOWUP_DAYS = 10
MAX_FOLLOWUPS_BEFORE_ALERT = 4

# Email
MAX_EMAIL_BODY_CHARS = 50000
EMAIL_SIGNATURE = """Best regards,
Rod Rivas
Director | All Painting Ltd.
📞 Office: 604-525-1403
📱 Cell: 604-765-9779
🌐 https://allpaintingltd.com/"""

# Database
DATABASE_PATH = os.environ.get(
    "FOLLOWUP_MANAGER_DB_PATH",
    os.path.join(os.path.dirname(__file__), "followup_manager.db"),
)

# Patterns - includes optional -A, -B, -C suffix for multi-contractor estimates
ESTIMATE_CODE_PATTERN = r"(2[4-9][CRcr])[-\s]?(\d{3})(?:[-\s]?([A-Za-z]))?"
REVISION_PATTERN = r"(Rev\.?\s*\d+|Revised?\s*\d*|Revision\s*\d+|R\d+)"
SUBJECT_PATTERN = r"Estimate\s*-?\s*"

# Status
STATUS_WAITING = "waiting"
STATUS_IN_CONVERSATION = "in_conversation"
STATUS_WON = "won"
STATUS_LOST = "lost"

# Status Colors (for UI)
STATUS_COLORS = {
    "waiting": {"bg": "bg-blue-100", "text": "text-blue-800"},
    "in_conversation": {"bg": "bg-yellow-100", "text": "text-yellow-800"},
    "won": {"bg": "bg-green-100", "text": "text-green-800"},
    "lost": {"bg": "bg-red-100", "text": "text-red-800"},
    "draft_ready": {"bg": "bg-purple-100", "text": "text-purple-800"},
}

# Scan Intervals (for UI dropdown)
SCAN_INTERVALS = {
    "30 minutes": 30,
    "1 hour": 60,
    "2 hours": 120,
    "4 hours": 240,
}

# Backfill Options (days)
BACKFILL_OPTIONS = [30, 60, 90, 180]
