#!/bin/bash
# Install web frontend dependencies and build

set -e

echo "🔧 Installing OpenHarness web frontend dependencies..."

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
cd "$(dirname "$0")/../frontend/web"

# Install dependencies
echo "📦 Installing npm dependencies..."
npm install

# Build for production
echo "🏗️  Building frontend..."
npm run build

echo "✅ Web frontend installation complete!"
echo ""
echo "To start the web server, run:"
echo "  oh web"
echo ""
echo "Then open http://localhost:8080 in your browser."
