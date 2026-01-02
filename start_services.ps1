# Start all services in separate windows (PowerShell)

Write-Host "=== Starting NOC Agent AI Services ===" -ForegroundColor Green

# Check if virtual environment exists
if (-Not (Test-Path "venv\Scripts\activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found. Run setup_windows.ps1 first" -ForegroundColor Red
    exit 1
}

# Load environment variables
if (Test-Path "set_env.ps1") {
    Write-Host "Loading environment variables..." -ForegroundColor Yellow
    . .\set_env.ps1
} else {
    Write-Host "WARNING: set_env.ps1 not found. Make sure environment variables are set!" -ForegroundColor Yellow
}

# Start AI Service in new window
Write-Host "`nStarting AI Service on port 8001..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @"
-NoExit
-Command
& {
    `$host.ui.RawUI.WindowTitle = 'NOC AI - AI Service (Port 8001)'
    Write-Host '=== AI Service ===' -ForegroundColor Green
    . .\set_env.ps1
    . venv\Scripts\Activate.ps1
    uvicorn ai_service.main:app --host 0.0.0.0 --port 8001
}
"@

Start-Sleep -Seconds 2

# Start Ingestion Service in new window
Write-Host "Starting Ingestion Service on port 8002..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @"
-NoExit
-Command
& {
    `$host.ui.RawUI.WindowTitle = 'NOC AI - Ingestion Service (Port 8002)'
    Write-Host '=== Ingestion Service ===' -ForegroundColor Cyan
    . .\set_env.ps1
    . venv\Scripts\Activate.ps1
    uvicorn ingestion.main:app --host 0.0.0.0 --port 8002
}
"@

Start-Sleep -Seconds 2

# Start UI in new window
Write-Host "Starting React UI on port 5173..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList @"
-NoExit
-Command
& {
    `$host.ui.RawUI.WindowTitle = 'NOC AI - React UI (Port 5173)'
    Write-Host '=== React UI ===' -ForegroundColor Magenta
    cd ui
    npm run dev
}
"@

Write-Host "`n=== All services started ===" -ForegroundColor Green
Write-Host "`nServices:" -ForegroundColor Cyan
Write-Host "  - AI Service:       http://localhost:8001"
Write-Host "  - Ingestion Service: http://localhost:8002"
Write-Host "  - React UI:         http://localhost:5173"
Write-Host "`nPress Ctrl+C in each window to stop the services"
