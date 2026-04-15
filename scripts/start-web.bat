@echo off
REM Start OpenHarness web frontend with auto-build if needed

echo 🚀 Starting OpenHarness web frontend...

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Node.js is not installed. Please install Node.js 18+ first.
    exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo ✅ Node.js version: %NODE_VERSION%

REM Check if npm is installed
where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ npm is not installed. Please install npm first.
    exit /b 1
)

for /f "tokens=*" %%i in ('npm --version') do set NPM_VERSION=%%i
echo ✅ npm version: %NPM_VERSION%

REM Navigate to web frontend directory
cd /d "%~dp0..\frontend\web"

REM Check if node_modules exists
if not exist "node_modules" (
    echo 📦 node_modules not found. Installing dependencies...
    call npm install
)

REM Check if dist exists and has content
if not exist "dist" (
    echo 🏗️  dist directory not found. Building frontend...
    call npm run build
    goto :start_server
)

REM Check if dist is empty
dir /b dist | findstr /r "." >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 🏗️  dist directory is empty. Building frontend...
    call npm run build
)

:start_server
echo ✅ Frontend ready!
echo.
echo Starting web server...
echo Then open http://localhost:8080 in your browser.
echo.

REM Return to script directory and run the web server
cd /d "%~dp0.."
call oh web %*
