/**
 * SuppressModal - modal to suppress alert with mandatory reason
 * REQ-44: suppress action
 * REQ-45: reason required; suppress cannot be confirmed without one
 * REQ-47: record admin_id and timestamp
 */

import React, { useState } from 'react';
import type { Alert, Admin } from '../../types';
import { suppressAlert } from '../../services/alertService';

interface SuppressModalProps {
  alert: Alert;
  currentAdmin: Admin;
  onClose: () => void;
  onSuccess: () => Promise<void>;
}

/**
 * SuppressModal component - requires reason before allowing suppression
 * Suppress button disabled until reason is entered and non-empty
 */
export const SuppressModal: React.FC<SuppressModalProps> = ({
  alert,
  currentAdmin,
  onClose,
  onSuccess,
}) => {
  const [reason, setReason] = useState('');
  const [isSuppressing, setIsSuppressing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isReasonValid = reason.trim().length > 0;

  /**
   * Handle suppress button click
   * Calls API with reason, then refreshes dashboard
   */
  const handleSuppress = async () => {
    if (!isReasonValid) {
      setError('Please enter a suppression reason');
      return;
    }

    try {
      setIsSuppressing(true);
      setError(null);
      await suppressAlert(alert.id, reason, currentAdmin.id);
      await onSuccess();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to suppress alert';
      setError(message);
      console.error('Suppress error:', err);
    } finally {
      setIsSuppressing(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Suppress alert</h2>
          <button className="modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {error && <div className="error-message">{error}</div>}

          <p className="suppress-prompt">
            Please provide a reason for suppressing this alert from{' '}
            <strong>{alert.location_name}</strong>:
          </p>

          {/* Reason Textarea - required */}
          <div className="form-group">
            <label htmlFor="reason">
              Suppression reason <span className="required">*</span>
            </label>
            <textarea
              id="reason"
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                // Clear error when user starts typing
                if (error && e.target.value.trim()) {
                  setError(null);
                }
              }}
              disabled={isSuppressing}
              rows={4}
              placeholder="e.g., False positive detected, alert already issued for this event, etc."
            />
            <div className="form-help">
              {reason.length === 0
                ? 'Reason is required'
                : `${reason.length} character${reason.length !== 1 ? 's' : ''}`}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isSuppressing}
          >
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSuppress}
            disabled={!isReasonValid || isSuppressing}
            title={!isReasonValid ? 'Enter a suppression reason' : ''}
          >
            {isSuppressing ? 'Suppressing...' : 'Suppress'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SuppressModal;
