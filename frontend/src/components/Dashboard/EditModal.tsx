/**
 * EditModal - allows admin to edit alert severity and message before approval
 * REQ-41: admin can edit message/severity before approving
 * REQ-42: edit action is audited
 */

import React, { useState } from 'react';
import type { Alert, Admin, AlertSeverity } from '../../types';
import { editAlert } from '../../services/alertService';

interface EditModalProps {
  alert: Alert;
  currentAdmin: Admin;
  onClose: () => void;
  onSuccess: () => Promise<void>;
}

/**
 * EditModal component - inline form to edit severity and message
 * Pre-filled with current values
 */
export const EditModal: React.FC<EditModalProps> = ({
  alert,
  currentAdmin,
  onClose,
  onSuccess,
}) => {
  const [severity, setSeverity] = useState<AlertSeverity>(alert.severity);
  const [message, setMessage] = useState(alert.message);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * Handle save button click
   * Only send changed fields to API
   */
  const handleSave = async () => {
    try {
      setIsSaving(true);
      setError(null);

      const updates: { severity?: AlertSeverity; message?: string } = {};
      if (severity !== alert.severity) {
        updates.severity = severity;
      }
      if (message !== alert.message) {
        updates.message = message;
      }

      // If no changes, just close
      if (Object.keys(updates).length === 0) {
        onClose();
        return;
      }

      await editAlert(alert.id, currentAdmin.id, updates);
      await onSuccess();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to save changes';
      setError(message);
      console.error('Edit error:', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit alert</h2>
          <button className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="error-message">{error}</div>}

          {/* Severity Dropdown */}
          <div className="form-group">
            <label htmlFor="severity">Severity</label>
            <select
              id="severity"
              value={severity}
              onChange={(e) => setSeverity(e.target.value as AlertSeverity)}
              disabled={isSaving}
            >
              <option value="low">Low</option>
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
              <option value="very_high">Very high</option>
            </select>
          </div>

          {/* Message Textarea */}
          <div className="form-group">
            <label htmlFor="message">Message</label>
            <textarea
              id="message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              disabled={isSaving}
              rows={4}
              placeholder="Alert message to be sent"
            />
          </div>
        </div>

        <div className="modal-footer">
          <button
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isSaving}
          >
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? 'Saving...' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default EditModal;
