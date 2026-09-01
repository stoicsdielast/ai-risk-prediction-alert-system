"""
Data models for the Fiji Flood Risk Prediction and Community Alert System
"""
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


# Alert-related types
AlertSeverity = Literal["low", "moderate", "high", "very_high"]
AlertStatus = Literal["pending", "approved", "suppressed", "resolved"]
AlertSource = Literal["model", "manual"]
AuditAction = Literal["approve", "suppress", "edit", "create"]


class Alert(BaseModel):
    """Alert domain model"""
    id: str
    location_id: str
    location_name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    confidence: float  # 0.0-1.0
    source: AlertSource
    predicted_at: Optional[str] = None  # ISO 8601
    created_at: str
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    suppressed_by: Optional[str] = None
    suppressed_at: Optional[str] = None
    suppression_reason: Optional[str] = None
    updated_at: str


class Metrics(BaseModel):
    """Dashboard metrics snapshot"""
    pending_alerts: int
    active_alerts: int
    monitored_locations: int
    pending_users: int


class AuditLogEntry(BaseModel):
    """Audit trail record"""
    id: str
    action: AuditAction
    admin_id: str
    admin_name: str
    alert_id: Optional[str] = None
    timestamp: str  # ISO 8601
    details: str


class Admin(BaseModel):
    """Authenticated admin user"""
    id: str
    name: str
    email: str
    initials: str
    role: str


# Request payloads
class ApproveAlertRequest(BaseModel):
    """Request to approve an alert"""
    alert_id: str
    admin_id: str
    timestamp: str


class SuppressAlertRequest(BaseModel):
    """Request to suppress an alert"""
    alert_id: str
    reason: str = Field(..., min_length=1, max_length=500)
    admin_id: str
    timestamp: str


class EditAlertRequest(BaseModel):
    """Request to edit an alert"""
    alert_id: str
    admin_id: str
    timestamp: str
    severity: Optional[AlertSeverity] = None
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response"""
    status: str
    message: str
    details: Optional[str] = None
