from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.alerts import admin_router as admin_alert_router
from app.api.routes.alerts import public_router as public_alert_router
from app.api.routes.auth import router as auth_router
from app.api.routes.locations import admin_router as admin_location_router
from app.api.routes.locations import router as locations_router
from app.api.routes.predictions import router as predictions_router
from app.api.routes.synthetic import router as synthetic_router
from app.api.routes.synthetic_research import router as synthetic_research_router
from app.api.routes.weather import router as weather_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.analytics import router as analytics_router

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
app.include_router(admin_location_router)
app.include_router(predictions_router)
app.include_router(synthetic_router)
app.include_router(synthetic_research_router)
app.include_router(weather_router)
app.include_router(notifications_router)
app.include_router(analytics_router)


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
    raise HTTPException(410, "Placeholder retired. Use /api/locations for persisted map data or authenticated /api/predictions/generate for explicit V1 research inference.")
