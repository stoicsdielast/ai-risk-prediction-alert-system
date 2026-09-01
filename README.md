# Running the Project

The project contains three main parts:

- **Frontend:** React + Vite
- **Backend:** FastAPI
- **Database:** PostgreSQL + PostGIS using Docker

For the full application to work, the database, backend, and frontend should all be running.

---

## Prerequisites

Make sure you have installed:

- Python 3.10+
- Node.js
- npm
- Git
- Docker Desktop

Check your installations:

```bash
python --version
node --version
npm --version
git --version
docker --version
docker compose version
```

---

## 1. Clone the Repository

```bash
git clone <repository-url>
cd ai-risk-prediction
```

Switch to your assigned branch:

```bash
git switch <your-branch>
```

For example:

```bash
git switch atharv
```

---

## 2. PostgreSQL/PostGIS Database Setup

The prototype uses PostgreSQL with the PostGIS extension.

The database runs in Docker so all team members can use the same database environment.

### Environment Configuration

Copy the example environment file.

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

### Linux/macOS

```bash
cp .env.example .env
```

Open `.env` and set your local database values.

The expected environment variables are:

```dotenv
POSTGRES_DB=floodrisk
POSTGRES_USER=floodadmin
POSTGRES_PASSWORD=your_local_password
POSTGRES_PORT=5433
```

Do not commit `.env` to Git.

The `.env.example` file contains safe example values and should be committed so other team members know which environment variables are required.

The default development database port is `5433`.

PostgreSQL runs on port `5432` inside the Docker container and is exposed on port `5433` on the host machine.

The host port can be changed using `POSTGRES_PORT` in the `.env` file if required.

### Start the Database

From the main project directory:

```bash
docker compose up -d
```

This starts the PostgreSQL/PostGIS database container.

### Verify the Database Container

Check that the database container is running:

```bash
docker compose ps
```

The `floodrisk-db` container should be running before starting the backend.

### Verify PostGIS

Run:

```bash
docker exec -it floodrisk-db psql -U floodadmin -d floodrisk -c "SELECT PostGIS_Version();"
```

A PostGIS version should be returned.

### Database Schema

The database initialization scripts are located in:

```text
database/init/
```

They create the PostGIS extension and the prototype tables:

- `locations`
- `weather_records`
- `predictions`
- `alerts`

The schema also defines:

- Primary keys
- Foreign keys
- Timestamp fields
- Flood-risk constraints
- Alert-status constraints
- Duplicate protection
- Latest weather indexes
- Latest prediction indexes
- PostGIS geographic coordinates
- Spatial index for location coordinates

The initialization scripts automatically run when Docker creates a new empty PostgreSQL volume.

### Seed Prototype Data

After the database is running, load the prototype Fiji location, weather, and flood-risk prediction data.

### Windows PowerShell

```powershell
Get-Content .\database\seed\seed.sql | docker exec -i floodrisk-db psql -U floodadmin -d floodrisk
```

The seed script can be rerun safely without duplicating the existing prototype location, weather, or prediction records.

The seed data includes examples of:

- Low flood risk
- Moderate flood risk
- High flood risk
- Very high flood risk

The weather and prediction values are prototype demonstration data and should not be treated as live Fiji weather or official flood-risk information.

### Stop the Database

```bash
docker compose down
```

The PostgreSQL data is stored in a Docker named volume.

Normal shutdown does not delete existing database data.

### Restart the Database

```bash
docker compose restart db
```

Existing database data should remain available after a restart.

### Reset the Database

To completely reset the local development database:

```bash
docker compose down -v
docker compose up -d
```

**Warning:** `docker compose down -v` deletes the local PostgreSQL Docker volume and all data stored in it.

After resetting, run the seed command again:

```powershell
Get-Content .\database\seed\seed.sql | docker exec -i floodrisk-db psql -U floodadmin -d floodrisk
```

---

## 3. Run the Backend

Open a new terminal and enter the backend directory:

```bash
cd backend
```

### Create a Python Virtual Environment

This is only required the first time.

```bash
python -m venv .venv
```

### Activate the Virtual Environment

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### Install Backend Dependencies

```bash
pip install -r requirements.txt
```

### Start FastAPI

From inside the `backend` directory:

```bash
uvicorn app.main:app --reload
```

The backend should run at:

```text
http://127.0.0.1:8000
```

FastAPI API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

Keep this terminal running.

---

## 4. Run the Frontend

Open another terminal.

From the main project directory:

```bash
cd frontend
```

Install frontend dependencies:

```bash
npm install
```

This normally only needs to be done during initial setup or when new frontend packages are added.

Start the Vite development server:

```bash
npm run dev
```

The frontend will usually run at:

```text
http://localhost:5173
```

Open this address in your browser.

---

## 5. Full Application Startup Order

For the complete application, start the services in this order:

```text
1. PostgreSQL/PostGIS database
2. FastAPI backend
3. React/Vite frontend
```

You should normally have three services running:

```text
Database
└── PostgreSQL/PostGIS
    └── localhost:5433

Backend
└── FastAPI
    └── http://127.0.0.1:8000

Frontend
└── React/Vite
    └── http://localhost:5173
```

The basic application flow is:

```text
Browser
   |
   v
React / Vite Frontend
localhost:5173
   |
   | HTTP/API requests
   v
FastAPI Backend
localhost:8000
   |
   v
PostgreSQL / PostGIS Database
localhost:5433
```

---

## Quick Start

After completing the initial setup, use the following commands when starting development.

### Terminal 1 — Database

From the main project directory:

```bash
docker compose up -d
```

### Terminal 2 — Backend

```bash
cd backend
```

Activate the virtual environment.

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Then start FastAPI:

```bash
uvicorn app.main:app --reload
```

### Terminal 3 — Frontend

```bash
cd frontend
npm run dev
```

Do not stop the database or backend while testing functionality that depends on stored data.

---

## Database Verification Commands

Check the database tables:

```bash
docker exec -it floodrisk-db psql -U floodadmin -d floodrisk -c "\dt"
```

Check the number of seeded records:

```bash
docker exec -it floodrisk-db psql -U floodadmin -d floodrisk -c "SELECT (SELECT COUNT(*) FROM locations) AS locations, (SELECT COUNT(*) FROM weather_records) AS weather_records, (SELECT COUNT(*) FROM predictions) AS predictions;"
```

Check flood-risk levels:

```bash
docker exec -it floodrisk-db psql -U floodadmin -d floodrisk -c "SELECT risk_level, COUNT(*) FROM predictions GROUP BY risk_level ORDER BY risk_level;"
```

Check PostGIS:

```bash
docker exec -it floodrisk-db psql -U floodadmin -d floodrisk -c "SELECT PostGIS_Version();"
```