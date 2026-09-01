/**
 * Alert Service - typed API integration
 * All state-changing actions (approve, suppress, edit) include admin ID + timestamp
 * REQ-42, REQ-45, REQ-47, REQ-53: audit logging via API
 */

import type {
  Alert,
  AlertSeverity,
  Metrics,
  AuditLogEntry,
  ApproveAlertRequest,
  SuppressAlertRequest,
  EditAlertRequest,
  ApiError,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Helper: format ISO 8601 timestamp for API calls
 */
function getCurrentTimestamp(): string {
  return new Date().toISOString();
}

/**
 * Helper: throw structured ApiError from response
 */
async function handleApiError(response: Response): Promise<never> {
  const data = await response.json().catch(() => ({}));
  throw {
    status: response.status,
    message: data.message || response.statusText,
    details: data,
  } as ApiError;
}

/**
 * Fetch pending alerts (status = 'pending')
 * Used by PendingApprovalsPanel (REQ-39: display with location, risk level, confidence, timestamp)
 */
export async function fetchPendingAlerts(): Promise<Alert[]> {
  const response = await fetch(`${API_BASE_URL}/api/alerts?status=pending`);
  if (!response.ok) {
    await handleApiError(response);
  }
  return response.json();
}

/**
 * Fetch all alerts (or filtered by status)
 * Used by AlertManagement page for comprehensive alert management
 * 
 * @param status - optional status filter
 * @returns array of alerts
 */
export async function getAlerts(status?: string): Promise<Alert[]> {
  let url = `${API_BASE_URL}/api/alerts`;
  if (status) {
    url += `?status=${status}`;
  }
  const response = await fetch(url);
  if (!response.ok) {
    await handleApiError(response);
  }
  return response.json();
}

/**
 * Fetch dashboard metrics (4 cards: pending, active, monitored, pending users)
 * REQ-32: view key metrics
 */
export async function fetchMetrics(): Promise<Metrics> {
  const response = await fetch(`${API_BASE_URL}/api/metrics`);
  if (!response.ok) {
    await handleApiError(response);
  }
  return response.json();
}

/**
 * Approve a pending alert
 * REQ-40: approve action
 * REQ-42: must record admin_id and timestamp in audit log
 *
 * @param alertId - alert to approve
 * @param adminId - admin performing approval
 * @returns updated alert object
 */
export async function approveAlert(
  alertId: string,
  adminId: string
): Promise<Alert> {
  const payload: ApproveAlertRequest = {
    alert_id: alertId,
    admin_id: adminId,
    timestamp: getCurrentTimestamp(),
  };

  const response = await fetch(`${API_BASE_URL}/api/alerts/${alertId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  return response.json();
}

/**
 * Suppress a pending alert with mandatory reason
 * REQ-44: suppress action
 * REQ-45: reason required
 * REQ-47: must record admin_id, timestamp, and reason in audit log
 *
 * @param alertId - alert to suppress
 * @param reason - reason for suppression (non-empty)
 * @param adminId - admin performing suppression
 * @returns updated alert object
 */
export async function suppressAlert(
  alertId: string,
  reason: string,
  adminId: string
): Promise<Alert> {
  if (!reason || !reason.trim()) {
    throw new Error('Suppression reason is required');
  }

  const payload: SuppressAlertRequest = {
    alert_id: alertId,
    reason: reason.trim(),
    admin_id: adminId,
    timestamp: getCurrentTimestamp(),
  };

  const response = await fetch(
    `${API_BASE_URL}/api/alerts/${alertId}/suppress`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );

  if (!response.ok) {
    await handleApiError(response);
  }

  return response.json();
}

/**
 * Edit alert severity and/or message before approval
 * REQ-41: admin can edit message/severity before approving
 * REQ-42 (extension): edit action is also audited
 *
 * @param alertId - alert to edit
 * @param adminId - admin performing edit
 * @param updates - object with severity and/or message to update
 * @returns updated alert object
 */
export async function editAlert(
  alertId: string,
  adminId: string,
  updates: { severity?: AlertSeverity; message?: string }
): Promise<Alert> {
  const payload: EditAlertRequest = {
    alert_id: alertId,
    admin_id: adminId,
    timestamp: getCurrentTimestamp(),
    ...(updates.severity && { severity: updates.severity }),
    ...(updates.message && { message: updates.message }),
  };

  const response = await fetch(`${API_BASE_URL}/api/alerts/${alertId}/edit`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    await handleApiError(response);
  }

  return response.json();
}

/**
 * Fetch recent audit log entries
 * REQ-42, REQ-47, REQ-53: display audit trail of admin actions
 * Used by RecentActivityCard (read-only feed, not paginated/filterable)
 *
 * @param limit - number of recent entries to return (default 10)
 * @returns array of audit log entries, most recent first
 */
export async function fetchRecentActivity(limit: number = 10): Promise<AuditLogEntry[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/audit-log?limit=${limit}&sort=desc`
  );
  if (!response.ok) {
    await handleApiError(response);
  }
  return response.json();
}
