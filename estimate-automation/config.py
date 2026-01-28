"""
Configuration for All Painting Estimate Automation System
"""
import os

# =============================================================================
# MICROSOFT GRAPH API CREDENTIALS
# =============================================================================
# Get these from Azure Portal > App Registrations > AllPainting Estimate Automation

AZURE_CLIENT_ID = "a44dcdf2-049b-43ba-96e8-0c7b46775b9b"
AZURE_TENANT_ID = "24369179-e3ed-4829-ba28-02803471ac00"
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "YOUR_SECRET_HERE")

# The email account to monitor
MONITORED_EMAIL = "info@allpaintingltd.com"

# =============================================================================
# IAN'S EMAIL ADDRESSES
# =============================================================================
# Emails from these addresses will be checked for estimate notifications

IAN_EMAILS = [
    "emeraldpainting@gmail.com",
    "ianc@allpaintingltd.com"
]

# =============================================================================
# KEYWORDS TO IDENTIFY ESTIMATE EMAILS
# =============================================================================
# If an email from Ian contains any of these keywords, it's likely an estimate

ESTIMATE_KEYWORDS = [
    "breakout",
    "estimate",
    "drawings are in the folders",
    "takeoff"
]

# =============================================================================
# FILE PATHS
# =============================================================================
# Where to search for Word documents

ESTIMATE_FOLDERS = [
    r"N:\Estimates\2026 All Painting Estimates",
    r"N:\Estimates\2025 All Painting Estimates"
]

# =============================================================================
# ESTIMATE GENERATOR API
# =============================================================================
# URL of the estimate generator Flask app

ESTIMATE_GENERATOR_URL = "http://localhost:5000/api/generate"
ESTIMATE_GENERATOR_HEALTH_URL = "http://localhost:5000/api/health"

# =============================================================================
# MONITORING SETTINGS
# =============================================================================
# How often to check for new emails (in seconds)

CHECK_INTERVAL_SECONDS = 180  # 3 minutes

# =============================================================================
# OUTLOOK DRAFT SETTINGS
# =============================================================================
# Name of the folder for automated drafts

DRAFTS_FOLDER_NAME = "Drafts - Estimates"

# =============================================================================
# DASHBOARD SETTINGS
# =============================================================================

DASHBOARD_PORT = 5002
DASHBOARD_HOST = "0.0.0.0"

# =============================================================================
# DATABASE / HISTORY
# =============================================================================
# SQLite database to track processed estimates

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "estimate_history.db")

# =============================================================================
# LOGGING
# =============================================================================

LOG_FILE = os.path.join(os.path.dirname(__file__), "automation.log")
LOG_LEVEL = "INFO"

# =============================================================================
# AI AGENT SETTINGS (NEW)
# =============================================================================
# Configuration for the AI validation agent

# Enable/disable the AI Agent
# Set to False to use the original flow (always create drafts)
AI_AGENT_ENABLED = True

# Operation mode:
# - "review": AI validates, then creates draft for Rodrigo to review (DEFAULT)
# - "auto": AI validates, if OK sends email automatically
AI_AGENT_MODE = "review"

# AI Agent API endpoint
AI_AGENT_API_URL = "http://localhost:5011/api/validate"

# Timeout for AI Agent API calls (seconds)
AI_AGENT_TIMEOUT = 60

# If True, continue with draft creation when AI Agent is unavailable
# If False, stop processing and notify error
AI_AGENT_FALLBACK_TO_DRAFT = True
