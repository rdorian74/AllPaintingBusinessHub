#!/bin/bash
# All Painting Ltd - Payroll Automation System
# Startup Script

echo "================================================"
echo "   ALL PAINTING LTD - PAYROLL AUTOMATION"
echo "================================================"
echo ""

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Warning: ANTHROPIC_API_KEY environment variable not set."
    echo "Set it with: export ANTHROPIC_API_KEY='your-key-here'"
    echo ""
fi

# Create necessary directories
mkdir -p uploads data

# Check for dependencies
echo "Checking dependencies..."
pip3 show flask > /dev/null 2>&1 || {
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
}

# Start the application
echo ""
echo "Starting Payroll Application..."
echo "Open your browser to: http://localhost:5003"
echo ""
echo "Port assignments:"
echo "  - 5000: Estimate Generator"
echo "  - 5001: Invoice Generator"
echo "  - 5002: Estimate Automation Dashboard"
echo "  - 5003: Payroll Automation (this app)"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 app.py
