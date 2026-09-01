/**
 * AlertManagement - Advanced alert management page
 * Shows: filter controls | alerts table | bulk actions
 * Integrated with API for fetching and managing alerts
 */

import React, { useState, useEffect } from 'react';
import type { Alert, Admin } from '../../types';
import { getAlerts, approveAlert } from '../../services/alertService';
import TopNav from './TopNav';
import EditModal from './EditModal';
import SuppressModal from './SuppressModal';
import './AlertManagement.css';

interface AlertManagementProps {
  currentAdmin: Admin;
  onNavigate?: (pageId: string) => void;
}

type StatusFilter = 'all' | 'pending' | 'approved' | 'suppressed';
type SeverityFilter = 'all' | 'low' | 'moderate' | 'high' | 'very_high';

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
 * Format timestamp for display
 */
function formatDateTime(isoString: string | null): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

/**
 * AlertManagement component - full page for managing alerts
 */
export const AlertManagement: React.FC<AlertManagementProps> = ({ currentAdmin, onNavigate }) => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Filters
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  
  // Modal state
  const [editingAlert, setEditingAlert] = useState<Alert | null>(null);
  const [suppressingAlert, setSuppressingAlert] = useState<Alert | null>(null);
  
  // Selected alerts for bulk actions
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set());

  /**
   * Load alerts from API
   */
  const loadAlerts = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAlerts();
      setAlerts(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load alerts';
      setError(message);
      console.error('Load alerts error:', err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Load alerts on component mount
   */
  useEffect(() => {
    loadAlerts();
  }, []);

  /**
   * Filter alerts based on current filter selections
   */
  const filteredAlerts = alerts.filter((alert) => {
    if (statusFilter !== 'all' && alert.status !== statusFilter) {
      return false;
    }
    if (severityFilter !== 'all' && alert.severity !== severityFilter) {
      return false;
    }
    return true;
  });

  /**
   * Handle approve action
   */
  const handleApprove = async (alertId: string) => {
    try {
      await approveAlert(alertId, currentAdmin.id);
      await loadAlerts();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to approve alert';
      setError(message);
      console.error('Approve error:', err);
    }
  };

  /**
   * Handle toggle alert selection
   */
  const toggleAlertSelection = (alertId: string) => {
    const newSelected = new Set(selectedAlerts);
    if (newSelected.has(alertId)) {
      newSelected.delete(alertId);
    } else {
      newSelected.add(alertId);
    }
    setSelectedAlerts(newSelected);
  };

  /**
   * Handle select all
   */
  const toggleSelectAll = () => {
    if (selectedAlerts.size === filteredAlerts.length) {
      setSelectedAlerts(new Set());
    } else {
      setSelectedAlerts(new Set(filteredAlerts.map((a) => a.id)));
    }
  };

  /**
   * Handle bulk approve
   */
  const handleBulkApprove = async () => {
    try {
      for (const alertId of selectedAlerts) {
        await approveAlert(alertId, currentAdmin.id);
      }
      setSelectedAlerts(new Set());
      await loadAlerts();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to approve alerts';
      setError(message);
      console.error('Bulk approve error:', err);
    }
  };

  return (
    <div className="alert-management">
      <TopNav currentAdmin={currentAdmin} currentPage="alerts" onNavigate={onNavigate} />
      <div className="alert-management-page">
      {/* Header */}
      <div className="page-header">
        <h1>Alert management</h1>
        <p>Review, approve, suppress, and manage system alerts</p>
      </div>

      {/* Error message */}
      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button className="btn-close" onClick={() => setError(null)}>
            ×
          </button>
        </div>
      )}

      {/* Filter controls */}
      <div className="filter-bar">
        <div className="filter-group">
          <label htmlFor="status-filter">Status:</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="suppressed">Suppressed</option>
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="severity-filter">Severity:</label>
          <select
            id="severity-filter"
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value as SeverityFilter)}
          >
            <option value="all">All</option>
            <option value="low">Low risk</option>
            <option value="moderate">Moderate risk</option>
            <option value="high">High risk</option>
            <option value="very_high">Very high risk</option>
          </select>
        </div>

        <div className="filter-summary">
          Showing {filteredAlerts.length} alert{filteredAlerts.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Bulk actions */}
      {selectedAlerts.size > 0 && (
        <div className="bulk-actions-bar">
          <span>{selectedAlerts.size} alert selected</span>
          <button
            className="btn btn-primary"
            onClick={handleBulkApprove}
          >
            Approve selected
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => setSelectedAlerts(new Set())}
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="loading-message">
          Loading alerts...
        </div>
      )}

      {/* Empty state */}
      {!loading && filteredAlerts.length === 0 && (
        <div className="empty-state">
          <p>No alerts found</p>
          <small>Adjust filters to see more results</small>
        </div>
      )}

      {/* Alerts table */}
      {!loading && filteredAlerts.length > 0 && (
        <div className="alerts-table-wrapper">
          <table className="alerts-table">
            <thead>
              <tr>
                <th className="checkbox-col">
                  <input
                    type="checkbox"
                    checked={
                      filteredAlerts.length > 0 &&
                      selectedAlerts.size === filteredAlerts.length
                    }
                    onChange={toggleSelectAll}
                    title="Select all alerts on this page"
                  />
                </th>
                <th>Location</th>
                <th>Severity</th>
                <th>Confidence</th>
                <th>Status</th>
                <th>Created at</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAlerts.map((alert) => (
                <tr key={alert.id} className={`alert-row status-${alert.status}`}>
                  <td className="checkbox-col">
                    <input
                      type="checkbox"
                      checked={selectedAlerts.has(alert.id)}
                      onChange={() => toggleAlertSelection(alert.id)}
                    />
                  </td>
                  <td className="location-cell">
                    <div className="location-info">
                      <strong>{alert.location_name}</strong>
                      <small>{alert.location_id}</small>
                    </div>
                  </td>
                  <td className="severity-cell">
                    {getSeverityLabel(alert.severity)}
                  </td>
                  <td className="confidence-cell">
                    {Math.round((alert.confidence || 0) * 100)}%
                  </td>
                  <td className="status-cell">
                    <span className={`status-badge status-${alert.status}`}>
                      {alert.status}
                    </span>
                  </td>
                  <td className="timestamp-cell">
                    {formatDateTime(alert.created_at)}
                  </td>
                  <td className="actions-cell">
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => setEditingAlert(alert)}
                      disabled={alert.status !== 'pending'}
                      title={alert.status === 'pending' ? 'Edit alert' : 'Can only edit pending alerts'}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-sm btn-secondary"
                      onClick={() => setSuppressingAlert(alert)}
                      disabled={alert.status === 'suppressed' || alert.status === 'resolved'}
                      title={alert.status === 'pending' ? 'Suppress alert' : 'Alert already suppressed or resolved'}
                    >
                      Suppress
                    </button>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => handleApprove(alert.id)}
                      disabled={alert.status !== 'pending'}
                      title={alert.status === 'pending' ? 'Approve alert' : 'Alert already processed'}
                    >
                      Approve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit Modal */}
      {editingAlert && (
        <EditModal
          alert={editingAlert}
          currentAdmin={currentAdmin}
          onClose={() => setEditingAlert(null)}
          onSuccess={async () => {
            setEditingAlert(null);
            await loadAlerts();
          }}
        />
      )}

      {/* Suppress Modal */}
      {suppressingAlert && (
        <SuppressModal
          alert={suppressingAlert}
          currentAdmin={currentAdmin}
          onClose={() => setSuppressingAlert(null)}
          onSuccess={async () => {
            setSuppressingAlert(null);
            await loadAlerts();
          }}
        />
      )}
      </div>
    </div>
  );
};

export default AlertManagement;
