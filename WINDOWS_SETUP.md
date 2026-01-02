# Windows Setup Guide (Without Docker)

This guide explains how to run the NOC Agent AI project on Windows without Docker.

## Scripts Created

I've created PowerShell scripts that replicate what the Dockerfile does:

- `install_prerequisites.ps1` - Install Python, Node.js, and PostgreSQL using winget
- `setup_windows.ps1` - Initial setup (install dependencies)
- `set_env.ps1` - Configure environment variables
- `start_services.ps1` - Start all services automatically

## Prerequisites

### Method 1: Using PowerShell with winget (Recommended)

The fastest way to install prerequisites is using Windows Package Manager (winget):

```powershell
# Run the automated installation script
.\install_prerequisites.ps1
```

This will install:
- Python 3.12
- Node.js LTS
- PostgreSQL 16

**After installation:** Close and reopen PowerShell for PATH changes to take effect.

### Method 2: Manual Downloads (For non-admin users or if winget fails)

If you don't have admin access or winget fails, install manually:

#### Python (No admin required)
1. Download from [python.org/downloads](https://www.python.org/downloads/)
2. Run installer
3. **IMPORTANT:** Check these boxes:
   - ✅ "Install launcher for all users" (if available)
   - ✅ "Add Python to PATH"
   - Select "Install Now" OR "Customize Installation" → check "Install for all users" if you have permission, otherwise install to your user directory

#### Node.js (No admin required)
1. Download LTS version from [nodejs.org](https://nodejs.org/)
2. Run installer
3. Select "Automatically install necessary tools" if prompted
4. Installation will work without admin if needed

#### PostgreSQL (Admin usually required - alternative options)

**Option A: Request admin assistance** to install PostgreSQL 16

**Option B: Use portable PostgreSQL (no admin required)**
1. Download portable PostgreSQL from [PostgreSQL Binaries](https://www.enterprisedb.com/download-postgresql-binaries)
2. Extract to a folder (e.g., `C:\Users\YourName\postgresql`)
3. Initialize database:
   ```powershell
   cd C:\Users\YourName\postgresql\bin
   .\initdb.exe -D ..\data -U postgres -W -E UTF8
   ```
4. Start PostgreSQL:
   ```powershell
   .\pg_ctl.exe -D ..\data -l ..\logfile start
   ```
5. Add to PATH: Add `C:\Users\YourName\postgresql\bin` to your user PATH environment variable

**Option C: Use cloud PostgreSQL** (e.g., [ElephantSQL free tier](https://www.elephantsql.com/) or [Supabase](https://supabase.com/))
- Update connection strings in `set_env.ps1` to point to cloud database

### Additional Requirement

**OpenAI API Key** - Get from [OpenAI Platform](https://platform.openai.com/api-keys)

## Step-by-Step Setup

### 1. Install Prerequisites

**Option A: Using winget (Recommended)**
```powershell
.\install_prerequisites.ps1
# Close and reopen PowerShell after installation
```

**Option B: Manual installation**
Download and install from the links in the Prerequisites section above.

### 2. Configure PostgreSQL with pgvector

After installing PostgreSQL, create the database:

```powershell
psql -U postgres

# In psql prompt, run:
CREATE USER noc_ai WITH PASSWORD 'noc_ai_password';
CREATE DATABASE noc_ai OWNER noc_ai;
\c noc_ai
CREATE EXTENSION vector;
\q
```

Initialize the schema:
```powershell
psql -U noc_ai -d noc_ai -f db\schema.sql
```

### 3. Run Setup Script

```powershell
# If you get execution policy error, run first:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run setup
.\setup_windows.ps1
```

This will:
- Create a Python virtual environment
- Install all Python dependencies
- Create necessary directories

### 4. Configure Environment Variables

Edit `set_env.ps1` and update your OpenAI API key:

```powershell
# Find this line and replace with your actual key
$env:OPENAI_API_KEY = "sk-your-actual-api-key-here"
```

### 5. Start All Services

```powershell
.\start_services.ps1
```

This will open 3 new windows:
- AI Service (port 8001)
- Ingestion Service (port 8002)
- React UI (port 5173)

### 6. Access the Application

Open your browser and go to: `http://localhost:5173`

## Manual Service Startup (Alternative)

If you prefer to run services manually in separate terminals:

**Terminal 1 - AI Service:**
```powershell
.\set_env.ps1
.\venv\Scripts\Activate.ps1
uvicorn ai_service.main:app --host 0.0.0.0 --port 8001
```

**Terminal 2 - Ingestion Service:**
```powershell
.\set_env.ps1
.\venv\Scripts\Activate.ps1
uvicorn ingestion.main:app --host 0.0.0.0 --port 8002
```

**Terminal 3 - React UI:**
```powershell
cd ui
npm install  # first time only
npm run dev
```

## Optional: Ingest Sample Data

After services are running:

```powershell
.\set_env.ps1
.\venv\Scripts\Activate.ps1
python scripts\data\ingest_runbooks.py --dir runbooks
```

## Troubleshooting

### PowerShell Execution Policy Error
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Python not found
Make sure Python is added to PATH during installation, or add it manually:
- Go to System Properties → Environment Variables
- Add Python installation directory to PATH

### PostgreSQL not found
Add PostgreSQL bin directory to PATH:
- Default: `C:\Program Files\PostgreSQL\16\bin`

### Port already in use
Check if another service is using ports 8001, 8002, or 5173:
```powershell
netstat -ano | findstr :8001
```

Kill the process:
```powershell
taskkill /PID <process_id> /F
```

### Module import errors
Reinstall dependencies:
```powershell
.\venv\Scripts\Activate.ps1
pip install --no-cache-dir -r requirements.txt --force-reinstall
```

## What Each Script Does

### install_prerequisites.ps1
Automates prerequisite installation using winget:
- Checks for winget availability
- Installs Python 3.12
- Installs Node.js LTS
- Installs PostgreSQL 16
- Automatically configures PATH

### setup_windows.ps1
Replicates Dockerfile commands:
- Creates Python virtual environment (replaces Docker container)
- Installs dependencies (replaces `RUN pip install`)
- Creates logs directory (replaces Docker volumes)

### set_env.ps1
Replicates docker-compose environment variables:
- Sets database connection strings
- Sets OpenAI API key
- Sets service configuration

### start_services.ps1
Replicates docker-compose service orchestration:
- Starts AI service (replaces `ai-service` container)
- Starts ingestion service (replaces `ingestion-service` container)
- Starts React UI

## Services Running

After successful startup:

| Service | URL | Description |
|---------|-----|-------------|
| AI Service | http://localhost:8001 | Main AI backend API |
| Ingestion Service | http://localhost:8002 | Data ingestion API |
| React UI | http://localhost:5173 | Web interface |
| PostgreSQL | localhost:5432 | Database with pgvector |

Check health:
```powershell
curl http://localhost:8001/api/v1/health
```
