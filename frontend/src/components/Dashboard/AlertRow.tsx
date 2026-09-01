/**
 * AlertRow - single pending alert row in the approval panel
 * Shows: status dot | location info | confidence + timestamp | Edit | Suppress | Approve buttons
 * REQ-39: display pending alerts with location, risk level, confidence, timestamp
 */

import React, { useState } from 'react';
import type { Alert, Admin } from '../../types';
import { approveAlert } from '../../services/alertService';
import EditModal from './EditModal';
import SuppressModal from './SuppressModal';

interface AlertRowProps {
  alert: Alert;
  currentAdmin: Admin;
  onActionCompleted: () => Promise<void>;
}

/**
 * Get muted color for severity status dot
 * Colors paired with text labels (not used alone for conveying info)
 */
function getSeverityColor(severity: Alert['severity']): string {
  const colors: Record<Alert['severity'], string> = {
    low: '#999999', // gray
    moderate: '#C59D3B', // muted yellow-ochre
    high: '#D89B4A', // muted orange
    very_high: '#C85A54', // muted red
  };
  return colors[severity];
}

/**
 * Get display text for severity
 */
function getSeverityLabel(severity: Alert['severity']): string {
  const labels: Record<Alert['severity'], string> = {
    low: 'Low risk',
    moderate: 'Moderate risk',
    high: 'High risk',
    very_high: 'Very high risk',
  };
  return labels[severity];
}

/**
 * Format timestamp for display (e.g., "08:12")
 */
function formatTime(isoString: string | null): string {
  if (!isoString) return '';
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * AlertRow component - displays a single pending alert with action buttons
 */
export const AlertRow: React.FC<AlertRowProps> = ({
  alert,
  currentAdmin,
  onActionCompleted,
}) => {
  const [showEditModal, setShowEditModal] = useState(false);
  const [showSuppressModal, setShowSuppressModal] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handle approve button click
   * Calls API, then refreshes dashboard data
   */
  const handleApprove = async () => {
    try {
      setIsApproving(true);
      setError(null);
      await approveAlert(alert.id, currentAdmin.id);
      await onActionCompleted();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to approve alert';
      setError(message);
      console.error('Approve error:', err);
    } finally {
      setIsApproving(false);
    }
  };

  const severityColor = getSeverityColor(alert.severity);
  const severityLabel = getSeverityLabel(alert.severity);
  const predictionTime = formatTime(alert.predicted_at);
  const confidencePercent = Math.round((alert.confidence || 0) * 100);

  return (
    <>
      <div className={`alert-row ${error ? 'has-error' : ''}`}>
        {/* Status dot + severity label */}
        <div className="alert-status">
          <span
            className="status-dot"
            style={{ backgroundColor: severityColor }}
            title={severityLabel}
            aria-label={`Severity: ${severityLabel}`}
          />
          <span className="severity-text">{severityLabel}</span>
        </div>

        {/* Location and risk level */}
        <div className="alert-location">
          <div className="location-name">{alert.location_name}</div>
        </div>

        {/* Secondary info: confidence + timestamp */}
        <div className="alert-meta">
          <span>
            Confidence {confidencePercent}% · predicted {predictionTime}
          </span>
        </div>

        {/* Action buttons: Edit | Suppress | Approve */}
        <div className="alert-actions">
          <button
            className="action-btn action-edit"
            onClick={() => setShowEditModal(true)}
            title="Edit alert before approving"
            disabled={isApproving}
          >
             Edit
          </button>

          <button
            className="action-btn action-suppress"
            onClick={() => setShowSuppressModal(true)}
            title="Suppress this alert"
            disabled={isApproving}
          >
            Suppress
          </button>

          <button
            className="action-btn action-approve"
            onClick={handleApprove}
            disabled={isApproving}
            title="Approve and send alert"
          >
            {isApproving ? 'Approving...' : 'Approve'}
          </button>
        </div>

        {/* Error message inline */}
        {error && <div className="alert-error">{error}</div>}
      </div>

      {/* Edit Modal */}
      {showEditModal && (
        <EditModal
          alert={alert}
          currentAdmin={currentAdmin}
          onClose={() => setShowEditModal(false)}
          onSuccess={async () => {
            setShowEditModal(false);
            await onActionCompleted();
          }}
        />
      )}

      {/* Suppress Modal */}
      {showSuppressModal && (
        <SuppressModal
          alert={alert}
          currentAdmin={currentAdmin}
          onClose={() => setShowSuppressModal(false)}
          onSuccess={async () => {
            setShowSuppressModal(false);
            await onActionCompleted();
          }}
        />
      )}
    </>
  );
};

export default AlertRow;
