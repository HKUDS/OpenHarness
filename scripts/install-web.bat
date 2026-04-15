@echo off
REM Install web frontend dependencies and build

echo 🔧 Installing OpenHarness web frontend dependencies...

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

REM Install dependencies
echo 📦 Installing npm dependencies...
call npm install

REM Build for production
echo 🏗️  Building frontend...
call npm run build

echo ✅ Web frontend installation complete!
echo.
echo To start the web server, run:
echo   oh web
echo.
echo Then open http://localhost:8080 in your browser.
pause
