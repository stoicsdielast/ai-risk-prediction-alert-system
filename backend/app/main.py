from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.alerts import admin_router as admin_alert_router
from app.api.routes.alerts import public_router as public_alert_router
from app.api.routes.auth import router as auth_router
from app.api.routes.locations import router as locations_router

app = FastAPI(
    title="Fiji Flood Risk API",
    description="Backend API for the Fiji Flood Risk Prediction and Community Alert System",
    version="0.1.0",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(admin_alert_router)
app.include_router(public_alert_router)
app.include_router(locations_router)


@app.get("/")
def root():
    return {
        "message": "Fiji Flood Risk API is running"
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy"
    }


@app.get("/api/risk/{location}")
def get_flood_risk(location: str):
    # Dummy response for now.
    # Your AI model will eventually generate this.
    return {
        "location": location,
        "risk_level": "HIGH",
        "probability": 0.82
    }
