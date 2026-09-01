/**
 * PendingApprovalsPanel - displays list of pending alerts for approval
 * Implements SRS 4.4.1 and 4.4.2 (alert management with edit/approve/suppress)
 * REQ-39: display pending alerts with location, risk level, confidence, timestamp
 * REQ-40: approve action
 * REQ-41: edit before approving
 * REQ-44: suppress action
 * REQ-45: suppression requires reason
 */

import React from 'react';
import type { Alert, Admin } from '../../types';
import AlertRow from './AlertRow';

interface PendingApprovalsPanelProps {
  alerts: Alert[];
  currentAdmin: Admin;
  onActionCompleted: () => Promise<void>;
}

/**
 * PendingApprovalsPanel component - list of pending alerts
 * Each row has Edit, Suppress, Approve action buttons
 */
export const PendingApprovalsPanel: React.FC<PendingApprovalsPanelProps> = ({
  alerts,
  currentAdmin,
  onActionCompleted,
}) => {
  return (
    <div className="pending-approvals-panel">
      <div className="panel-header">
        <h2>Pending alert approvals</h2>
        <p className="panel-subtitle">
          4.4.1 Create and approve alert — edit before approving per REQ-41
        </p>
      </div>

      {alerts.length === 0 ? (
        <div className="empty-state">
          <p>No pending alerts</p>
        </div>
      ) : (
        <div className="alerts-list">
          {alerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              currentAdmin={currentAdmin}
              onActionCompleted={onActionCompleted}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default PendingApprovalsPanel;
