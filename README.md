## Running the Project

The project contains two main applications:

* **Frontend:** React + Vite
* **Backend:** FastAPI

You need to run the frontend and backend in **separate terminals**.

### Prerequisites

Make sure you have installed:

* Python 3.10+
* Node.js
* npm
* Git

Check your installations:

```bash
python --version
node --version
npm --version
git --version
```

---

## 1. Clone the Repository

```bash
git clone <repository-url>
cd fiji-flood-risk-system
```

Switch to your assigned branch:

```bash
git switch <your-branch>
```

For example:

```bash
git switch rishi
```

---

## 2. Run the Backend

Open a terminal and enter the backend directory:

```bash
cd backend
```

### Create a Python Virtual Environment

Only required the first time:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
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

## 3. Run the Frontend

Open a **second terminal**.

From the main project directory:

```bash
cd frontend
```

Install the frontend dependencies:

```bash
npm install
```

This only needs to be done when setting up the project for the first time or when new packages are added.

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

## 4. Both Servers Must Be Running

You should have two terminals open:

```text
Terminal 1
└── FastAPI Backend
    └── http://127.0.0.1:8000

Terminal 2
└── React/Vite Frontend
    └── http://localhost:5173
```

The frontend sends requests to the FastAPI backend to retrieve or update data.

```text
Browser
   │
   ▼
React / Vite Frontend
localhost:5173
   │
   │ HTTP/API Request
   ▼
FastAPI Backend
localhost:8000
   │
   ▼
Database / AI Model / Weather Data
```

---

## Quick Start

After the initial setup, use these commands whenever you want to run the project.

### Terminal 1 — Backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

### Terminal 2 — Frontend

```bash
cd frontend
npm run dev
```

> **Important:** Do not close either terminal while working on the project. Both the frontend and backend need to be running for the full application to work.

