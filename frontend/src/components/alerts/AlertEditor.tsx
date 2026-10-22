import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'
import { getLocations } from '../../api/locations'
import { usePollingResource } from '../../alerts/useAlertFeed'
import type { AdminAlert, AlertDraft } from '../../types/alert'
import type { RiskLevel } from '../../types/prototype'
import { Alert } from '../Alert'

interface Props {
  alert?: AdminAlert
  busy: boolean
  onSave: (draft: AlertDraft) => Promise<void>
  onCancel: () => void
}

export function AlertEditor({ alert, busy, onSave, onCancel }: Props) {
  const editing = Boolean(alert)
  const load = useCallback(
    (signal: AbortSignal) => (editing ? Promise.resolve([]) : getLocations(signal)),
    [editing],
  )
  const locations = usePollingResource(load)
  const [locationId, setLocationId] = useState(alert?.location_id.toString() ?? '')
  const [severity, setSeverity] = useState<RiskLevel>(alert?.severity ?? 'HIGH')
  const [message, setMessage] = useState(alert?.message ?? '')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (busy || !message.trim() || !locationId) return
    void onSave({ location_id: Number(locationId), severity, message: message.trim() })
  }

  return (
    <section
      className="prototype-panel alert-editor"
      aria-label={editing ? 'Edit alert' : 'Create alert'}
    >
      <h2>{editing ? `Edit alert #${alert?.id}` : 'Create a MET alert draft'}</h2>
      <p>Drafts become visible to the community after MET approval.</p>
      {locations.error && (
        <Alert tone="error">
          {locations.error}{' '}
          <button type="button" onClick={locations.refresh}>
            Retry locations
          </button>
        </Alert>
      )}
      {!editing && locations.data?.length === 0 && (
        <Alert>No active locations are available. Add locations before creating an alert.</Alert>
      )}
      <form onSubmit={submit}>
        <fieldset disabled={busy}>
          <label className="form-field">
            <span>Location</span>
            {editing ? (
              <input value={alert?.location.name ?? ''} readOnly />
            ) : (
              <select
                required
                value={locationId}
                onChange={(event) => setLocationId(event.target.value)}
              >
                <option value="">
                  {locations.data ? 'Choose a location' : 'Loading locations…'}
                </option>
                {locations.data?.map((location) => (
                  <option value={location.id} key={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
            )}
          </label>
          <label className="form-field">
            <span>Severity</span>
            <select
              value={severity}
              onChange={(event) => setSeverity(event.target.value as RiskLevel)}
            >
              <option value="LOW">Low</option>
              <option value="MODERATE">Moderate</option>
              <option value="HIGH">High</option>
              <option value="VERY_HIGH">Very high</option>
            </select>
          </label>
          <label className="form-field">
            <span>Alert message</span>
            <textarea
              required
              maxLength={4000}
              rows={4}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
            />
          </label>
          <div className="alert-form-actions">
            <button
              className="button button--primary"
              type="submit"
              disabled={
                !message.trim() ||
                !locationId ||
                (!editing &&
                  !locations.data?.some((location) => location.id === Number(locationId)))
              }
            >
              {busy ? 'Saving…' : editing ? 'Save changes' : 'Create draft'}
            </button>
            <button className="button button--secondary" type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}
