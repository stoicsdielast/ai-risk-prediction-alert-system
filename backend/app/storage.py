"""
In-memory data storage for the Fiji Flood Risk Prediction and Community Alert System
This can be replaced with a real database (PostgreSQL, etc.) in production.
"""
from datetime import datetime
from typing import Optional, List
from uuid import uuid4
from app.models import Alert, AuditLogEntry, AlertStatus, AlertSeverity, AlertSource


class InMemoryStorage:
    """Simple in-memory storage for alerts and audit logs"""
    
    def __init__(self):
        self.alerts: dict[str, Alert] = {}
        self.audit_log: list[AuditLogEntry] = []
        self._initialize_sample_data()
    
    def _initialize_sample_data(self):
        """Initialize with sample pending alerts for demo"""
        # Sample pending alert 1
        alert1_id = "alert-001"
        self.alerts[alert1_id] = Alert(
            id=alert1_id,
            location_id="loc-ba-river",
            location_name="Ba River",
            severity="very_high",
            status="pending",
            message="Severe flooding expected in the next 6 hours due to heavy rainfall in the upstream catchment area.",
            confidence=0.91,
            source="model",
            predicted_at="2026-09-01T08:12:00Z",
            created_at="2026-09-01T07:45:00Z",
            created_by=None,
            approved_by=None,
            approved_at=None,
            suppressed_by=None,
            suppressed_at=None,
            suppression_reason=None,
            updated_at="2026-09-01T07:45:00Z",
        )
        
        # Sample pending alert 2
        alert2_id = "alert-002"
        self.alerts[alert2_id] = Alert(
            id=alert2_id,
            location_id="loc-rewa-river",
            location_name="Rewa River",
            severity="high",
            status="pending",
            message="Moderate to heavy rainfall expected with localized flooding in low-lying areas.",
            confidence=0.78,
            source="model",
            predicted_at="2026-09-01T08:30:00Z",
            created_at="2026-09-01T08:00:00Z",
            created_by=None,
            approved_by=None,
            approved_at=None,
            suppressed_by=None,
            suppressed_at=None,
            suppression_reason=None,
            updated_at="2026-09-01T08:00:00Z",
        )
        
        # Sample pending alert 3
        alert3_id = "alert-003"
        self.alerts[alert3_id] = Alert(
            id=alert3_id,
            location_id="loc-sigatoka-river",
            location_name="Sigatoka River",
            severity="moderate",
            status="pending",
            message="Light to moderate rainfall expected. River levels may rise slightly.",
            confidence=0.65,
            source="model",
            predicted_at="2026-09-01T09:00:00Z",
            created_at="2026-09-01T08:15:00Z",
            created_by=None,
            approved_by=None,
            approved_at=None,
            suppressed_by=None,
            suppressed_at=None,
            suppression_reason=None,
            updated_at="2026-09-01T08:15:00Z",
        )
        
        # Add some sample audit log entries
        self.audit_log = [
            AuditLogEntry(
                id=str(uuid4()),
                action="create",
                admin_id="admin-001",
                admin_name="System",
                alert_id=alert1_id,
                timestamp="2026-09-01T07:45:00Z",
                details="Alert created from model prediction",
            ),
            AuditLogEntry(
                id=str(uuid4()),
                action="create",
                admin_id="admin-001",
                admin_name="System",
                alert_id=alert2_id,
                timestamp="2026-09-01T08:00:00Z",
                details="Alert created from model prediction",
            ),
            AuditLogEntry(
                id=str(uuid4()),
                action="create",
                admin_id="admin-001",
                admin_name="System",
                alert_id=alert3_id,
                timestamp="2026-09-01T08:15:00Z",
                details="Alert created from model prediction",
            ),
        ]
    
    def get_pending_alerts(self) -> List[Alert]:
        """Get all pending alerts"""
        return [alert for alert in self.alerts.values() if alert.status == "pending"]
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get a single alert by ID"""
        return self.alerts.get(alert_id)
    
    def update_alert(self, alert_id: str, **kwargs) -> Optional[Alert]:
        """Update an alert with new values"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        # Update only provided fields
        update_data = {k: v for k, v in kwargs.items() if v is not None}
        alert = alert.model_copy(update={**update_data, "updated_at": datetime.utcnow().isoformat() + "Z"})
        self.alerts[alert_id] = alert
        return alert
    
    def approve_alert(self, alert_id: str, admin_id: str, admin_name: str, timestamp: str) -> Optional[Alert]:
        """Approve an alert"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        updated_alert = self.update_alert(
            alert_id,
            status="approved",
            approved_by=admin_id,
            approved_at=timestamp,
        )
        
        # Log to audit trail
        self.audit_log.append(
            AuditLogEntry(
                id=str(uuid4()),
                action="approve",
                admin_id=admin_id,
                admin_name=admin_name,
                alert_id=alert_id,
                timestamp=timestamp,
                details=f"approved {alert.location_name} alert",
            )
        )
        
        return updated_alert
    
    def suppress_alert(
        self, alert_id: str, reason: str, admin_id: str, admin_name: str, timestamp: str
    ) -> Optional[Alert]:
        """Suppress an alert with a reason"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        updated_alert = self.update_alert(
            alert_id,
            status="suppressed",
            suppressed_by=admin_id,
            suppressed_at=timestamp,
            suppression_reason=reason,
        )
        
        # Log to audit trail
        self.audit_log.append(
            AuditLogEntry(
                id=str(uuid4()),
                action="suppress",
                admin_id=admin_id,
                admin_name=admin_name,
                alert_id=alert_id,
                timestamp=timestamp,
                details=f"suppressed {alert.location_name} alert: {reason[:50]}...",
            )
        )
        
        return updated_alert
    
    def edit_alert(
        self,
        alert_id: str,
        severity: Optional[AlertSeverity],
        message: Optional[str],
        admin_id: str,
        admin_name: str,
        timestamp: str,
    ) -> Optional[Alert]:
        """Edit an alert's severity and/or message"""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        update_dict = {}
        if severity is not None:
            update_dict["severity"] = severity
        if message is not None:
            update_dict["message"] = message
        
        updated_alert = self.update_alert(alert_id, **update_dict)
        
        # Log to audit trail
        changes = []
        if severity is not None:
            changes.append(f"severity: {alert.severity} → {severity}")
        if message is not None:
            changes.append("message updated")
        
        self.audit_log.append(
            AuditLogEntry(
                id=str(uuid4()),
                action="edit",
                admin_id=admin_id,
                admin_name=admin_name,
                alert_id=alert_id,
                timestamp=timestamp,
                details=f"edited {alert.location_name} alert: {', '.join(changes)}",
            )
        )
        
        return updated_alert
    
    def get_audit_log(self, limit: int = 10, sort: str = "desc") -> List[AuditLogEntry]:
        """Get audit log entries"""
        entries = self.audit_log.copy()
        if sort == "desc":
            entries.reverse()
        return entries[:limit]
    
    def get_metrics(self) -> dict:
        """Calculate current metrics"""
        pending = len([a for a in self.alerts.values() if a.status == "pending"])
        active = len([a for a in self.alerts.values() if a.status == "approved"])
        locations = len(set(a.location_id for a in self.alerts.values()))
        # Pending users is a placeholder - would come from user management in real system
        pending_users = 0
        
        return {
            "pending_alerts": pending,
            "active_alerts": active,
            "monitored_locations": locations,
            "pending_users": pending_users,
        }


# Global storage instance
storage = InMemoryStorage()
