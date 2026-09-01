/**
 * RecentActivityCard - read-only feed of admin actions (audit trail)
 * Displays recent approve/suppress/edit actions from audit log
 * REQ-42, REQ-47, REQ-53: audit trail of admin actions
 * Note: full filterable/paginated audit log lives on a separate Reports/Audit page
 */

import React from 'react';
import type { AuditLogEntry } from '../../types';

interface RecentActivityCardProps {
  activity: AuditLogEntry[];
}

/**
 * Format timestamp for display (e.g., "07:40")
 */
function formatActivityTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/**
 * RecentActivityCard component - shows recent admin actions
 * Read-only feed, not paginated or filterable on this page
 */
export const RecentActivityCard: React.FC<RecentActivityCardProps> = ({
  activity,
}) => (
  <div className="recent-activity-card card">
    <div className="card-header">
      <h3>Recent alert activity</h3>
    </div>

    <div className="card-body">
      {activity.length === 0 ? (
        <p className="empty-message">No recent activity</p>
      ) : (
        <ul className="activity-list">
          {activity.map((entry) => (
            <li key={entry.id} className="activity-item">
              <div className="activity-content">
                <span className="activity-text">
                  <strong>{entry.admin_name}</strong> {entry.details}
                </span>
              </div>
              <div className="activity-time">{formatActivityTime(entry.timestamp)}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  </div>
);

export default RecentActivityCard;
