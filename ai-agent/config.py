"""
Configuration for AI Agent Service
All Painting Ltd.
"""
import os

# =============================================================================
# FLASK SETTINGS
# =============================================================================

PORT = 5011
HOST = "0.0.0.0"
DEBUG = False

# =============================================================================
# ANTHROPIC API SETTINGS
# =============================================================================

# Get API key from environment variable
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Model to use for validation
# claude-sonnet-4-20250514 is fast and cost-effective for validation tasks
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"

# Maximum tokens for response
MAX_TOKENS = 4000

# =============================================================================
# VALIDATION SETTINGS
# =============================================================================

# Minimum confidence score to pass validation (0-100)
MIN_CONFIDENCE_SCORE = 80

# Required fields that must be present in the estimate
REQUIRED_FIELDS = [
    "client_email",
    "client_name", 
    "project_name",
    "estimate_code"
]

# =============================================================================
# AUTO-CORRECTION SETTINGS
# =============================================================================

# Enable auto-correction (regenerate PDF if correctable issues found)
AUTO_CORRECTION_ENABLED = True

# Maximum number of regeneration attempts
MAX_REGENERATION_ATTEMPTS = 3

# Estimate Generator API URL (for regeneration requests)
ESTIMATE_GENERATOR_URL = "http://localhost:5000/api/generate"

# =============================================================================
# COST TRACKING
# =============================================================================

# Approximate costs per 1000 tokens (USD) - update as needed
# These are estimates for Claude Sonnet
COST_PER_1K_INPUT_TOKENS = 0.003
COST_PER_1K_OUTPUT_TOKENS = 0.015

# =============================================================================
# DATABASE
# =============================================================================

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "agent_history.db")

# =============================================================================
# LOGGING
# =============================================================================

LOG_FILE = os.path.join(os.path.dirname(__file__), "agent.log")
LOG_LEVEL = "INFO"
