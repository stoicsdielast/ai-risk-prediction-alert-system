/**
 * Admin Dashboard Types
 * Matches API contract and SRS requirements (REQ-32, REQ-39, REQ-40, REQ-41, REQ-42, REQ-44, REQ-45, REQ-47)
 */

export type AlertSeverity = 'low' | 'moderate' | 'high' | 'very_high';
export type AlertStatus = 'pending' | 'approved' | 'suppressed' | 'resolved';
export type AlertSource = 'model' | 'manual';

/**
 * Alert object - core domain model
 * Fields denormalized for dashboard performance (e.g., location_name cached)
 */
export interface Alert {
  id: string; // UUID
  location_id: string; // FK reference only — do not embed full Location object
  location_name: string; // denormalized for display
  severity: AlertSeverity;
  status: AlertStatus;
  message: string; // editable per REQ-41
  confidence: number; // 0.0–1.0, from ML prediction (null if manually created)
  source: AlertSource; // REQ-38: distinguish manual from model-triggered
  predicted_at: string | null; // ISO 8601, null if source = "manual"
  created_at: string; // ISO 8601
  created_by: string | null; // admin user ID if manual, null if system-generated
  approved_by: string | null; // REQ-42
  approved_at: string | null; // ISO 8601, null until approved
  suppressed_by: string | null; // REQ-47
  suppressed_at: string | null; // ISO 8601
  suppression_reason: string | null; // REQ-45: required if status = "suppressed"
  updated_at: string; // last modification timestamp
}

/**
 * Admin user object - current authenticated admin
 * Stored in Postgres, passed to Dashboard after auth
 */
export interface Admin {
  id: string; // UUID
  name: string; // full name
  email: string;
  initials: string; // e.g., "AS" for Aryan S.
  role: 'admin' | 'super_admin'; // may extend later
}

/**
 * Dashboard metrics snapshot
 * Returned by /api/metrics endpoint (REQ-32)
 */
export interface Metrics {
  pending_alerts: number;
  active_alerts: number;
  monitored_locations: number;
  pending_users: number;
}

/**
 * Audit log entry - tracks all state-changing actions
 * REQ-42 (approve), REQ-47 (suppress), REQ-53 (edit)
 */
export interface AuditLogEntry {
  id: string; // UUID
  action: 'approve' | 'suppress' | 'edit' | 'create'; // state-changing action
  admin_id: string; // which admin performed it
  admin_name: string; // denormalized for display (e.g., "Aryan S.")
  alert_id: string | null; // null if action is not alert-related
  timestamp: string; // ISO 8601, server-side
  details: string; // human-readable summary (e.g., "approved Ba River alert")
}

/**
 * Request payload for approve action
 * REQ-42: must record which admin, when, and what alert
 */
export interface ApproveAlertRequest {
  alert_id: string;
  admin_id: string;
  timestamp: string; // ISO 8601
}

/**
 * Request payload for suppress action
 * REQ-45: must include reason; REQ-47: must record admin + timestamp
 */
export interface SuppressAlertRequest {
  alert_id: string;
  reason: string; // required, non-empty
  admin_id: string;
  timestamp: string; // ISO 8601
}

/**
 * Request payload for edit + approve flow
 * REQ-41: admin can edit severity and message before approving
 * REQ-42: audit log records the edit
 */
export interface EditAlertRequest {
  alert_id: string;
  severity?: AlertSeverity; // optional; if provided, updates alert
  message?: string; // optional; if provided, updates alert
  admin_id: string;
  timestamp: string; // ISO 8601
}

/**
 * Generic API error response
 */
export interface ApiError {
  status: number;
  message: string;
  details?: Record<string, unknown>;
}
