#!/bin/bash
# Run the Chainlit UI for Procast AI

# Set defaults
export PROCAST_API_URL="${PROCAST_API_URL:-http://localhost:8000}"
export PROCAST_USER_EMAIL="${PROCAST_USER_EMAIL:-jamestraynor@example.com}"
export PROCAST_USER_ID="${PROCAST_USER_ID:-chainlit-user}"

echo "Starting Procast AI Chat UI..."
echo "  API URL: $PROCAST_API_URL"
echo "  User Email: $PROCAST_USER_EMAIL"
echo ""

cd "$(dirname "$0")"
chainlit run app.py --port 8080
