# Install pgvector extension for PostgreSQL (Windows)
# This script downloads and installs pgvector for local PostgreSQL

Write-Host "=== Installing pgvector for PostgreSQL ===" -ForegroundColor Green

# Configuration - Update this if your PostgreSQL is in a different location
$pgPath = "C:\Users\rdarak\Downloads\postgresql\pgsql"
$pgVectorVersion = "v0.5.1"
$pgVectorUrl = "https://github.com/pgvector/pgvector/releases/download/$pgVectorVersion/pgvector-$pgVectorVersion-windows-x64-pg16.zip"

# Check if PostgreSQL directory exists
if (-Not (Test-Path $pgPath)) {
    Write-Host "ERROR: PostgreSQL not found at: $pgPath" -ForegroundColor Red
    Write-Host "Please update the `$pgPath variable in this script with your PostgreSQL location" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found PostgreSQL at: $pgPath" -ForegroundColor Green

# Download pgvector
Write-Host "`nDownloading pgvector $pgVectorVersion..." -ForegroundColor Yellow
$tempDir = "$env:TEMP\pgvector_install"
$zipFile = "$tempDir\pgvector.zip"

# Create temp directory
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    Invoke-WebRequest -Uri $pgVectorUrl -OutFile $zipFile
    Write-Host "Download complete" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to download pgvector" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Extract zip
Write-Host "`nExtracting pgvector..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $zipFile -DestinationPath $tempDir -Force
    Write-Host "Extraction complete" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to extract pgvector" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

# Copy files to PostgreSQL directories
Write-Host "`nInstalling pgvector files..." -ForegroundColor Yellow

# Copy DLL file
$dllSource = "$tempDir\lib\vector.dll"
$dllDest = "$pgPath\lib\"
if (Test-Path $dllSource) {
    Copy-Item $dllSource -Destination $dllDest -Force
    Write-Host "Copied vector.dll to $dllDest" -ForegroundColor Green
} else {
    Write-Host "ERROR: vector.dll not found in download" -ForegroundColor Red
    exit 1
}

# Copy extension files
$extSource = "$tempDir\share\extension\vector*"
$extDest = "$pgPath\share\extension\"
if (Test-Path "$tempDir\share\extension") {
    Copy-Item $extSource -Destination $extDest -Force
    Write-Host "Copied extension files to $extDest" -ForegroundColor Green
} else {
    Write-Host "ERROR: Extension files not found in download" -ForegroundColor Red
    exit 1
}

# Clean up temp files
Remove-Item -Recurse -Force $tempDir
Write-Host "`nCleaned up temporary files" -ForegroundColor Green

# Check if PostgreSQL is running
Write-Host "`nChecking PostgreSQL status..." -ForegroundColor Yellow
$pgCtl = "$pgPath\bin\pg_ctl.exe"
$pgData = "$pgPath\data"

if (Test-Path $pgCtl) {
    $status = & $pgCtl -D $pgData status 2>&1
    if ($status -like "*server is running*") {
        Write-Host "PostgreSQL is running - restart required" -ForegroundColor Yellow
        Write-Host "`nRestarting PostgreSQL..." -ForegroundColor Yellow
        & $pgCtl -D $pgData restart
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PostgreSQL restarted successfully" -ForegroundColor Green
        } else {
            Write-Host "WARNING: Failed to restart PostgreSQL" -ForegroundColor Yellow
            Write-Host "Please restart manually: cd $pgPath\bin && .\pg_ctl.exe -D ..\data restart" -ForegroundColor Yellow
        }
    } else {
        Write-Host "PostgreSQL is not running - no restart needed" -ForegroundColor Green
    }
} else {
    Write-Host "WARNING: pg_ctl not found - cannot restart PostgreSQL automatically" -ForegroundColor Yellow
}

Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host "`nNext steps:" -ForegroundColor Cyan
Write-Host "1. Connect to your database:" -ForegroundColor White
Write-Host "   psql -U postgres -d noc_ai" -ForegroundColor Gray
Write-Host "2. Create the extension:" -ForegroundColor White
Write-Host "   CREATE EXTENSION vector;" -ForegroundColor Gray
Write-Host "3. Verify installation:" -ForegroundColor White
Write-Host "   \dx vector" -ForegroundColor Gray
