"""
Configuration for Bid/Addendum Email Forwarding Agent
All Painting Ltd.
"""
import os

# =============================================================================
# MICROSOFT GRAPH API CREDENTIALS
# =============================================================================
# Same credentials as Estimate Automation (AllPainting Estimate Automation app)

AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "YOUR_SECRET_HERE")

# The email account to monitor
MONITORED_EMAIL = "info@allpaintingltd.com"

# =============================================================================
# IAN'S EMAIL ADDRESSES (EXCLUDE FROM FORWARDING)
# =============================================================================
# Don't forward emails FROM these addresses (loop protection)

IAN_EMAILS = [
    "emeraldpainting@gmail.com",
    "ianc@allpaintingltd.com"
]

# Forward TO this address
FORWARD_TO_EMAIL = "ianc@allpaintingltd.com"

# =============================================================================
# INTERNAL EMAIL ADDRESSES (FOR LOOP PROTECTION)
# =============================================================================
# If email is FROM these addresses or TO Ian, it's internal/outbound - skip it

INTERNAL_EMAILS = [
    "info@allpaintingltd.com",
    "estimates@allpaintingltd.com",
    "ianc@allpaintingltd.com",
    "emeraldpainting@gmail.com",
    "rod@allpaintingltd.com"
]

# =============================================================================
# BID/TENDER KEYWORDS
# =============================================================================
# Case-insensitive, partial matches allowed
# Comprehensive list including plurals and variations

BID_KEYWORDS = [
    # Core bid terms
    "bid", "bids", "bidding", "bidder", "bidders",
    "tender", "tenders", "tendering",
    "addendum", "addenda", "addendums",
    
    # RFx terms
    "rfp", "rfps",
    "rfq", "rfqs", 
    "rfi", "rfis",
    "itt", "itts",
    "itb", "itbs",
    
    # Full phrases
    "invitation to bid", "invitations to bid",
    "invitation to tender", "invitations to tender",
    "request for proposal", "request for proposals",
    "request for quote", "request for quotes",
    "request for quotation", "request for quotations",
    "request for information",
    
    # Deadline terms
    "bid due", "bid deadline", "bid closing",
    "tender due", "tender deadline", "tender closing",
    "submission deadline", "closing date",
    
    # Process terms
    "pre-qualification", "prequalification", "pre-qual", "prequal",
    "bid submission", "tender submission",
    "bid documents", "tender documents",
    "bid package", "tender package",
    
    # Clarification terms
    "clarification", "clarifications",
    "site meeting", "site visit",
    "mandatory meeting",
    "pre-bid meeting", "pre-tender meeting",
    
    # Amendment terms
    "amendment", "amendments",
    "revision", "revisions",
    "updated bid", "revised bid",
]

# =============================================================================
# OPERATION MODE
# =============================================================================
# "draft" = Create drafts in info@ for review (testing phase)
# "active" = Forward emails directly to Ian

OPERATION_MODE = "draft"  # Start in draft mode for testing

# =============================================================================
# DRAFT FOLDER
# =============================================================================
# Folder name for drafts (will be created if doesn't exist)

DRAFTS_FOLDER_NAME = "Draft-New Bid or Addendum"

# =============================================================================
# MONITORING SETTINGS
# =============================================================================

CHECK_INTERVAL_SECONDS = 300  # 5 minutes

# =============================================================================
# ANTHROPIC API SETTINGS
# =============================================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4000

# Cost tracking (per 1M tokens)
COST_PER_1M_INPUT_TOKENS = 3.00
COST_PER_1M_OUTPUT_TOKENS = 15.00

# =============================================================================
# DATABASE
# =============================================================================

DATABASE_PATH = os.environ.get(
    "BID_ADDENDUM_DB_PATH",
    os.path.join(os.path.dirname(__file__), "bid_agent.db"),
)

# =============================================================================
# DASHBOARD SETTINGS
# =============================================================================

DASHBOARD_PORT = 5012
DASHBOARD_HOST = "0.0.0.0"

# =============================================================================
# LOGGING
# =============================================================================

LOG_FILE = os.path.join(os.path.dirname(__file__), "bid_agent.log")
LOG_LEVEL = "INFO"
