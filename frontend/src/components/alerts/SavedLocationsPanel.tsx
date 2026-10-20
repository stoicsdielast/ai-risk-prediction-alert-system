import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { apiRequest } from '../../api/client'
import { getNotifications, getSavedLocations, saveLocation } from '../../api/notifications'
import type { NotificationRecord, SavedLocation } from '../../api/notifications'

export function SavedLocationsPanel() {
  const { token } = useAuth()
  const [locations, setLocations] = useState<SavedLocation[]>([])
  const [saved, setSaved] = useState<SavedLocation[]>([])
  const [history, setHistory] = useState<NotificationRecord[]>([])
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const load = useCallback(async (signal?: AbortSignal) => {
    if (!token) return
    const [registry, subscriptions, notifications] = await Promise.all([
      apiRequest<SavedLocation[]>('/api/locations', { signal }), getSavedLocations(token, signal), getNotifications(token, false, signal, offset),
    ])
    if (signal?.aborted) return
    setLocations(registry); setSaved(subscriptions); setHistory(notifications); setError(null)
  }, [token, offset])
  useEffect(() => {
    const controller = new AbortController()
    setBusy(true)
    void load(controller.signal).catch(e => { if (!controller.signal.aborted) setError(e.message) })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [load])
  async function toggle(id: number, checked: boolean) {
    if (!token) return
    setBusy(true)
    try { await saveLocation(token, id, checked); await load() }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update saved locations') }
    finally { setBusy(false) }
  }
  const available = [...locations, ...saved.filter(row => !locations.some(loc => loc.id === row.id))]
  return <section id="saved-locations" className="prototype-panel" aria-label="Saved locations and notification history">
    <h2>My saved locations</h2>
    <p>Follow multiple monitored Fiji locations. Use the notification controls above to opt in or out.</p>
    {error && <p role="alert">{error}</p>}
    <button className="button button--secondary" disabled={busy} onClick={() => {
      setBusy(true); void load().catch(e => setError(e.message)).finally(() => setBusy(false))
    }}>Refresh saved locations and history</button>
    <fieldset disabled={busy}>
      <legend>Monitored locations</legend>
      {available.map(loc => <label key={loc.id} style={{ display: 'block', padding: '.5rem' }}>
        <input type="checkbox" checked={saved.some(row => row.id === loc.id)}
          onChange={e => void toggle(loc.id, e.target.checked)} /> {loc.name}{!loc.is_active && ' (inactive — unsubscribe available)'}
      </label>)}
    </fieldset>
    <h3>My notification history</h3>
    <p>Delivered means the browser reported displaying the notification, not that you read it.</p>
    {!history.length && <p>No notifications recorded.</p>}
    <ul>{history.map(row => <li key={row.id}>
      <Link to={`/alerts#alert-${row.alert_id}`}>{row.is_demo ? 'DEMO ONLY — ' : ''}{row.location}</Link>
      {' — '}{row.status} · {row.message} · Attempts: {row.attempts}
      {row.delivered_at && <span> · Delivered {new Date(row.delivered_at).toLocaleString()}</span>}
      {row.last_error && <span> · Last error: {row.last_error}</span>}
    </li>)}</ul>
    <button disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous notifications</button>
    <button disabled={busy || history.length < 50} onClick={() => setOffset(offset + 50)}>Older notifications</button>
  </section>
}
