# NOC Agent AI - Install Prerequisites (PowerShell with winget)
# This script installs Python, Node.js, and PostgreSQL using Windows Package Manager
# IMPORTANT: Run PowerShell as Administrator

Write-Host "=== NOC Agent AI - Installing Prerequisites ===" -ForegroundColor Green
Write-Host "This will install Python, Node.js, and PostgreSQL using winget`n" -ForegroundColor Cyan

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "INFO: Not running as Administrator - will attempt user-level installations" -ForegroundColor Cyan
    Write-Host "Installing packages for current user only (using --scope user)`n" -ForegroundColor Yellow
    $scope = "--scope user"
} else {
    Write-Host "Running as Administrator - will install system-wide`n" -ForegroundColor Green
    $scope = ""
}

# Check if winget is available
Write-Host "`nChecking for winget (Windows Package Manager)..." -ForegroundColor Yellow
try {
    $wingetVersion = winget --version
    Write-Host "Found winget: $wingetVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: winget not found." -ForegroundColor Red
    Write-Host "Please install App Installer from Microsoft Store or upgrade to Windows 10 (1809+)" -ForegroundColor Yellow
    Write-Host "Alternative: Install manually from WINDOWS_SETUP.md" -ForegroundColor Yellow
    exit 1
}

# Install Python 3.12
Write-Host "`nInstalling Python 3.12..." -ForegroundColor Yellow
if ($scope -eq "--scope user") {
    winget install Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements
} else {
    winget install Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
}
if ($LASTEXITCODE -eq 0) {
    Write-Host "Python installed successfully" -ForegroundColor Green
} else {
    Write-Host "Python may already be installed or installation failed (exit code: $LASTEXITCODE)" -ForegroundColor Yellow
}

# Install Node.js LTS
Write-Host "`nInstalling Node.js LTS..." -ForegroundColor Yellow
if ($scope -eq "--scope user") {
    winget install OpenJS.NodeJS.LTS -e --scope user --accept-package-agreements --accept-source-agreements
} else {
    winget install OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
}
if ($LASTEXITCODE -eq 0) {
    Write-Host "Node.js installed successfully" -ForegroundColor Green
} else {
    Write-Host "Node.js may already be installed or installation failed (exit code: $LASTEXITCODE)" -ForegroundColor Yellow
}

# Install PostgreSQL
Write-Host "`nInstalling PostgreSQL..." -ForegroundColor Yellow
if ($scope -eq "--scope user") {
    Write-Host "WARNING: PostgreSQL may require admin privileges" -ForegroundColor Yellow
    Write-Host "If installation fails, use portable PostgreSQL or cloud database (see WINDOWS_SETUP.md)" -ForegroundColor Cyan
    winget install PostgreSQL.PostgreSQL -e --scope user --accept-package-agreements --accept-source-agreements
} else {
    Write-Host "NOTE: You may be prompted to set a password for the 'postgres' user" -ForegroundColor Cyan
    winget install PostgreSQL.PostgreSQL -e --accept-package-agreements --accept-source-agreements
}
if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL installed successfully" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL installation failed or already installed (exit code: $LASTEXITCODE)" -ForegroundColor Yellow
    if ($scope -eq "--scope user") {
        Write-Host "`nAlternative PostgreSQL options (no admin required):" -ForegroundColor Cyan
        Write-Host "1. Portable PostgreSQL - Download from https://www.enterprisedb.com/download-postgresql-binaries" -ForegroundColor White
        Write-Host "2. Cloud PostgreSQL - Use ElephantSQL (https://www.elephantsql.com/) or Supabase (https://supabase.com/)" -ForegroundColor White
        Write-Host "See WINDOWS_SETUP.md for detailed instructions" -ForegroundColor White
    }
}

Write-Host "`n=== Installation Complete ===" -ForegroundColor Green
Write-Host "`nIMPORTANT: Close and reopen PowerShell for PATH changes to take effect`n" -ForegroundColor Cyan

Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Close this PowerShell window" -ForegroundColor White
Write-Host "2. Open a new PowerShell window" -ForegroundColor White
Write-Host "3. Verify installations:" -ForegroundColor White
Write-Host "   python --version" -ForegroundColor Gray
Write-Host "   node --version" -ForegroundColor Gray
Write-Host "   psql --version" -ForegroundColor Gray
Write-Host "4. Configure PostgreSQL (see WINDOWS_SETUP.md)" -ForegroundColor White
Write-Host "5. Run setup_windows.ps1" -ForegroundColor White
