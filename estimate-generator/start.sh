#!/bin/bash

# All Painting Ltd - Estimate Generator Startup Script

echo "=================================="
echo "All Painting Ltd"
echo "Estimate Generator"
echo "=================================="
echo ""

# Check if ANTHROPIC_API_KEY is set
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ERROR: ANTHROPIC_API_KEY not set"
    echo ""
    echo "Please set your API key:"
    echo "  export ANTHROPIC_API_KEY='your-api-key-here'"
    echo ""
    echo "Get your API key at: https://console.anthropic.com/"
    exit 1
fi

echo "✅ API key found"
echo "🚀 Starting server..."
echo ""

python3 app.py
