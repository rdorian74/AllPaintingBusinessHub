"""
QuickBooks Sync - Configuration
Fill in your credentials from Intuit Developer Portal
"""

# =============================================================================
# QUICKBOOKS API CREDENTIALS
# Get these from: https://developer.intuit.com → Your App → Keys and credentials
# =============================================================================

# Your App's Client ID
CLIENT_ID = "ABrrxiTUjCVZGuQTpSeIdlp3PphM6BDdySR567l3rR4qYGm5cB"

# Your App's Client Secret
CLIENT_SECRET = "Jxxx57PRp9canaMb3hOKg1PvCyKP4Wb7xWrKqZwv"

# Your QuickBooks Company ID (Realm ID)
# Get from Sandbox: https://developer.intuit.com/app/developer/sandbox
# The number in the URL when you open the sandbox company
COMPANY_ID = "9341456226841044"

# =============================================================================
# ENVIRONMENT SETTINGS
# =============================================================================

# Set to True for sandbox (testing), False for production (real QuickBooks)
USE_SANDBOX = True

# OAuth URLs (automatically set based on USE_SANDBOX)
if USE_SANDBOX:
    QBO_BASE_URL = "https://sandbox-quickbooks.api.intuit.com"
else:
    QBO_BASE_URL = "https://quickbooks.api.intuit.com"

# OAuth endpoints (same for sandbox and production)
AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

# =============================================================================
# APP SETTINGS
# =============================================================================

# Redirect URI - must match what you set in Intuit Developer Portal
REDIRECT_URI = "http://localhost:5015/callback"

# OAuth scopes
SCOPES = "com.intuit.quickbooks.accounting"

# Flask server settings
HOST = "0.0.0.0"
PORT = 5015

# Token storage file
TOKEN_FILE = "qb_tokens.json"

# =============================================================================
# DEFAULT INVOICE SETTINGS
# =============================================================================

# Default item name for invoice line items (will be created if doesn't exist)
DEFAULT_ITEM_NAME = "Painting Services"

# Payment terms (Net 30, Due on Receipt, etc.)
# This should match a term name in your QuickBooks
DEFAULT_PAYMENT_TERM = "Due on receipt"
