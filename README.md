# Flood Risk Prediction and Community Alert System

AI-powered flood risk prediction system designed for Fiji.

## Documentation

- [Presentation handbook: project, architecture, security, privacy, demo, and deployment](docs/PRESENTATION_HANDBOOK.md)
- [Authentication system: how it works](docs/AUTHENTICATION_WORKFLOW.md)
- [Frontend prototype: architecture, setup, and demo guide](docs/PROTOTYPE_UI.md)
- [Frontend setup and usage](frontend/README.md)
- [Backend setup and API usage](backend/README.md)

## Project Modules

1. Flood Risk Dashboard
2. Weather Data Management
3. AI Flood Risk Prediction
4. Flood Mapping
5. Alert System and System Testing

## Technology Stack

### Frontend
- React
- TypeScript
- Vite

### Backend
- FastAPI
- Python

### AI
- Python
- Pandas
- Scikit-learn

### Database
- PostgreSQL

## Development

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The current React milestone includes registration, login, protected navigation,
MET-admin account review, a public Fiji weather/risk map, an admin overview, and
a demonstration alert-review workflow. Flood-domain data and alert actions are
clearly labelled local prototype data. See the [prototype guide](docs/PROTOTYPE_UI.md)
for the exact live-versus-demo boundary and walkthrough.

### Backend authentication

The backend authentication milestones implement registration, login, JWT
access tokens, protected routes, server-side roles, and MET admin account
review using PostgreSQL, SQLAlchemy, and Argon2. See the
[backend authentication guide](backend/README.md) for setup, usage, testing,
API examples, database verification, and troubleshooting.
