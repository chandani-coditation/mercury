# NOC Agent AI - Windows Setup Script (PowerShell)
# This script replicates what the Dockerfile does

Write-Host "=== NOC Agent AI - Windows Setup ===" -ForegroundColor Green

# Check if Python is installed
Write-Host "`nChecking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host "Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Python not found. Please install Python 3.9+ from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# Check if PostgreSQL client is available
Write-Host "`nChecking PostgreSQL client..." -ForegroundColor Yellow
try {
    $pgVersion = psql --version
    Write-Host "Found: $pgVersion" -ForegroundColor Green
} catch {
    Write-Host "WARNING: psql not found. Install PostgreSQL or add it to PATH" -ForegroundColor Yellow
}

# Create virtual environment if it doesn't exist
if (-Not (Test-Path "venv")) {
    Write-Host "`nCreating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "`nVirtual environment already exists" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "`nActivating virtual environment..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "`nUpgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install Python dependencies
Write-Host "`nInstalling Python dependencies from requirements.txt..." -ForegroundColor Yellow
pip install --no-cache-dir -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host "Dependencies installed successfully" -ForegroundColor Green
} else {
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    exit 1
}

# Create logs directory if it doesn't exist
if (-Not (Test-Path "logs")) {
    Write-Host "`nCreating logs directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "logs"
}

Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Set your environment variables (see set_env.ps1)"
Write-Host "2. Initialize database: psql -U noc_ai -d noc_ai -f db\schema.sql"
Write-Host "3. Run services using start_services.ps1"
