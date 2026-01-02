# Environment Variables Configuration (PowerShell)
# Edit this file with your actual values, then run: .\set_env.ps1

Write-Host "Setting environment variables..." -ForegroundColor Yellow

# Database configuration
$env:DATABASE_URL = "postgresql://noc_ai:noc_ai_password@localhost:5432/noc_ai"
$env:POSTGRES_HOST = "localhost"
$env:POSTGRES_PORT = "5432"
$env:POSTGRES_DB = "noc_ai"
$env:POSTGRES_USER = "noc_ai"
$env:POSTGRES_PASSWORD = "noc_ai_password"

# OpenAI API Key - REPLACE WITH YOUR ACTUAL KEY
$env:OPENAI_API_KEY = "sk-your-api-key-here"

# Service configuration
$env:AI_SERVICE_HOST = "0.0.0.0"
$env:AI_SERVICE_PORT = "8001"
$env:INGESTION_SERVICE_HOST = "0.0.0.0"
$env:INGESTION_SERVICE_PORT = "8002"
$env:LOG_LEVEL = "INFO"

# Database pool settings (optional)
$env:DB_POOL_MIN = "5"
$env:DB_POOL_MAX = "20"
$env:DB_POOL_WAIT_TIMEOUT = "30"

Write-Host "Environment variables set for current session" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Don't forget to update OPENAI_API_KEY with your actual key!" -ForegroundColor Red
Write-Host ""
Write-Host "These variables are only set for the current PowerShell session." -ForegroundColor Yellow
Write-Host "Run this script in each terminal where you start a service." -ForegroundColor Yellow
