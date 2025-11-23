# NOC Agent AI - Web UI

Simple, minimalist React.js UI for the NOC Agent AI system.

## Features

- 📋 **Incident List** - View all incidents with policy badges
- 🔍 **Incident Detail** - Full triage and resolution details
- ✅ **Approval Workflow** - Approve incidents and generate resolution
- 🎨 **Minimalist Design** - Clean, simple interface

## Quick Start

```bash
cd ui
npm install
npm start
```

The app will open at http://localhost:3000

## Configuration

Set `REACT_APP_API_URL` in `.env` file if API is not on `http://localhost:8001`:

```
REACT_APP_API_URL=http://localhost:8001/api/v1
```

## Usage

1. **View Incidents**: See all incidents in a grid view
2. **Create Triage**: Click "+ New Triage" to create a new alert triage
3. **View Details**: Click any incident card to see full details
4. **Get Resolution**: Click "Get Resolution" button (may require approval)
5. **Approve**: If approval required, approve via the approval form

## API Integration

The UI uses the following endpoints:
- `GET /api/v1/incidents` - List incidents
- `GET /api/v1/incidents/{id}` - Get incident details
- `POST /api/v1/triage` - Create triage
- `POST /api/v1/resolution?incident_id={id}` - Get resolution
- `PUT /api/v1/incidents/{id}/feedback` - Submit feedback/approval

