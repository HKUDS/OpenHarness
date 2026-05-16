#!/bin/bash
# Start OpenHarness web frontend with auto-build if needed

set -e

echo "🚀 Starting OpenHarness web frontend..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

echo "✅ Node.js version: $(node --version)"

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm first."
    exit 1
fi

echo "✅ npm version: $(npm --version)"

# Navigate to web frontend directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/../frontend/web"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 node_modules not found. Installing dependencies..."
    npm install
fi

# Check if dist exists and has content
if [ ! -d "dist" ] || [ -z "$(ls -A dist 2>/dev/null)" ]; then
    echo "🏗️  dist directory not found or empty. Building frontend..."
    npm run build
fi

echo "✅ Frontend ready!"
echo ""
echo "Starting web server..."
echo "Then open http://localhost:8080 in your browser."
echo ""

# Return to script directory and run the web server
cd "$SCRIPT_DIR/.."
exec oh web "$@"
