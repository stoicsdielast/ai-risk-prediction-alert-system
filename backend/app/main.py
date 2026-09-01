from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional, Literal

from app.models import (
    Alert,
    Metrics,
    AuditLogEntry,
    ApproveAlertRequest,
    SuppressAlertRequest,
    EditAlertRequest,
    ErrorResponse,
)
from app.storage import storage

app = FastAPI(
    title="Fiji Flood Risk API",
    description="Backend API for the Fiji Flood Risk Prediction and Community Alert System",
    version="0.1.0",
)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Base endpoints
# ============================================================================


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


# ============================================================================
# Alert endpoints
# ============================================================================


@app.get("/api/alerts", response_model=list[Alert])
def get_alerts(status: Optional[str] = Query(None)):
    """
    Get alerts, optionally filtered by status
    
    Query Parameters:
    - status: Filter by status ("pending", "approved", "suppressed", "resolved")
    
    Returns: List of alerts
    """
    alerts = list(storage.alerts.values())
    
    if status:
        alerts = [a for a in alerts if a.status == status]
    
    return alerts


@app.get("/api/alerts/{alert_id}", response_model=Alert)
def get_alert(alert_id: str):
    """
    Get a specific alert by ID
    
    Returns: Alert details
    Raises: 404 if alert not found
    """
    alert = storage.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert


@app.post("/api/alerts/{alert_id}/approve", response_model=Alert)
def approve_alert(alert_id: str, request: ApproveAlertRequest):
    """
    Approve an alert (REQ-40)
    
    Request body:
    - alert_id: Alert ID
    - admin_id: Admin user ID
    - timestamp: ISO 8601 timestamp of action
    
    Returns: Updated alert
    Raises: 404 if alert not found, 400 if invalid status
    """
    alert = storage.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    
    if alert.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve alert with status '{alert.status}'. Only pending alerts can be approved."
        )
    
    # For demo, use the admin_id as admin_name; in production, look up from user table
    admin_name = "Aryan S." if request.admin_id == "550e8400-e29b-41d4-a716-446655440000" else f"Admin {request.admin_id[:8]}"
    
    updated_alert = storage.approve_alert(alert_id, request.admin_id, admin_name, request.timestamp)
    return updated_alert


@app.post("/api/alerts/{alert_id}/suppress", response_model=Alert)
def suppress_alert(alert_id: str, request: SuppressAlertRequest):
    """
    Suppress an alert with a reason (REQ-44, REQ-45)
    
    Request body:
    - alert_id: Alert ID
    - reason: Suppression reason (required, non-empty)
    - admin_id: Admin user ID
    - timestamp: ISO 8601 timestamp of action
    
    Returns: Updated alert
    Raises: 404 if alert not found, 400 if invalid status or empty reason
    """
    alert = storage.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    
    if alert.status in ["suppressed", "resolved"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot suppress alert with status '{alert.status}'."
        )
    
    if not request.reason or not request.reason.strip():
        raise HTTPException(
            status_code=400,
            detail="Suppression reason is required and cannot be empty."
        )
    
    # For demo, use the admin_id as admin_name; in production, look up from user table
    admin_name = "Aryan S." if request.admin_id == "550e8400-e29b-41d4-a716-446655440000" else f"Admin {request.admin_id[:8]}"
    
    updated_alert = storage.suppress_alert(alert_id, request.reason, request.admin_id, admin_name, request.timestamp)
    return updated_alert


@app.patch("/api/alerts/{alert_id}/edit", response_model=Alert)
def edit_alert(alert_id: str, request: EditAlertRequest):
    """
    Edit an alert's severity and/or message (REQ-41)
    
    Request body:
    - alert_id: Alert ID
    - severity: New severity level ("low", "moderate", "high", "very_high") - optional
    - message: New alert message - optional
    - admin_id: Admin user ID
    - timestamp: ISO 8601 timestamp of action
    
    Returns: Updated alert
    Raises: 404 if alert not found, 400 if no changes provided
    """
    alert = storage.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    
    if request.severity is None and request.message is None:
        raise HTTPException(
            status_code=400,
            detail="At least one field (severity or message) must be provided for edit."
        )
    
    # For demo, use the admin_id as admin_name; in production, look up from user table
    admin_name = "Aryan S." if request.admin_id == "550e8400-e29b-41d4-a716-446655440000" else f"Admin {request.admin_id[:8]}"
    
    updated_alert = storage.edit_alert(
        alert_id,
        request.severity,
        request.message,
        request.admin_id,
        admin_name,
        request.timestamp
    )
    return updated_alert


# ============================================================================
# Metrics endpoint
# ============================================================================


@app.get("/api/metrics", response_model=Metrics)
def get_metrics():
    """
    Get dashboard metrics (REQ-32)
    
    Returns:
    - pending_alerts: Number of pending alerts
    - active_alerts: Number of active (approved) alerts
    - monitored_locations: Number of monitored locations
    - pending_users: Number of pending user approvals
    """
    metrics_data = storage.get_metrics()
    return Metrics(**metrics_data)


# ============================================================================
# Audit log endpoint
# ============================================================================


@app.get("/api/audit-log", response_model=list[AuditLogEntry])
def get_audit_log(limit: int = Query(10, ge=1, le=100), sort: Literal["asc", "desc"] = Query("desc")):
    """
    Get audit log entries (REQ-42, REQ-47, REQ-53)
    
    Query Parameters:
    - limit: Number of entries to return (1-100, default 10)
    - sort: Sort order ("asc" or "desc", default "desc")
    
    Returns: List of audit log entries
    """
    entries = storage.get_audit_log(limit=limit, sort=sort)
    return entries