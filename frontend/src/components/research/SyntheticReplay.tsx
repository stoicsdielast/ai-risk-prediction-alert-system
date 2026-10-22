import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { WeatherMap } from '../map/WeatherMap'
import { RiskPill } from '../pills/DataPill'
import { SyntheticAlertCard } from './SyntheticAlertCard'
import type { SyntheticAction } from './SyntheticAlertCard'
import type { MapLocation } from '../../types/location'
import {
  approveSyntheticAlert, createSyntheticAlert, getSyntheticAlerts, getSyntheticFrame,
  getSyntheticInfo, manageSyntheticAlert, notifySyntheticApproval, SYNTHETIC_NOTICE,
  type SyntheticAlert, type SyntheticFrame, type SyntheticInfo,
} from '../../api/synthetic'

const display = (value: number | null | undefined, unit: string) => value == null ? 'Missing observation' : `${value.toFixed(1)} ${unit}`

export function SyntheticReplay() {
  const { user, token } = useAuth()
  const admin = user?.role === 'MET_ADMIN'
  const [info, setInfo] = useState<SyntheticInfo | null>(null)
  const [timestamp, setTimestamp] = useState('2025-01-15T12:00')
  const [frame, setFrame] = useState<SyntheticFrame | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [alerts, setAlerts] = useState<SyntheticAlert[]>([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [alertView, setAlertView] = useState<'CURRENT' | 'HISTORY'>('CURRENT')
  const [busy, setBusy] = useState(false)
  const [notifications, setNotifications] = useState(false)
  const seen = useRef<Set<number> | null>(null)

  useEffect(() => {
    let active = true
    getSyntheticInfo().then(result => {
      if (!active) return
      setInfo(result)
      if (result.example_timestamp) setTimestamp(result.example_timestamp.slice(0, 16))
    }).catch(caught => { if (active) setError(String(caught.message)) })
    return () => { active = false }
  }, [])

  const refreshAlerts = useCallback(async () => {
    const next = await getSyntheticAlerts(admin && token ? token : undefined)
    const approved = next.filter(alert => alert.status === 'APPROVED' && alert.source_type === 'synthetic')
    if (seen.current) {
      for (const alert of approved) {
        if (!seen.current.has(alert.id)) notifySyntheticApproval(alert, notifications)
      }
    }
    seen.current = new Set(approved.map(alert => alert.id))
    setAlerts(next.filter(alert => alert.source_type === 'synthetic'))
  }, [admin, token, notifications])

  useEffect(() => {
    if (info?.status !== 'ready') return
    void refreshAlerts().catch(caught => setError(caught.message))
    const timer = window.setInterval(() => { void refreshAlerts().catch(caught => setError(caught.message)) }, 15000)
    return () => window.clearInterval(timer)
  }, [info?.status, refreshAlerts])

  const loadFrame = async () => {
    setBusy(true); setError(''); setSuccess(''); setFrame(null)
    try {
      const next = await getSyntheticFrame(`${timestamp}:00Z`)
      setFrame(next); setSelectedId(next.locations[0]?.slug ?? null)
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Replay failed') }
    finally { setBusy(false) }
  }

  const maps: MapLocation[] = useMemo(() => frame?.locations.map(location => ({
    id: location.slug, apiId: location.location_id, name: location.name, division: `${location.division} Division`,
    latitude: location.latitude, longitude: location.longitude, riskLevel: location.risk_category,
    prediction: location.risk_category && location.probability != null ? {
      riskLevel: location.risk_category, floodProbabilityPercent: Math.round(location.probability * 100),
      provenance: 'synthetic', modelVersion: location.model_version, predictedAt: location.timestamp,
    } : null,
  })) ?? [], [frame])
  const selected = frame?.locations.find(location => location.slug === selectedId)

  const createAlert = async (locationId: number) => {
    if (!token || !frame) return
    const location = frame.locations.find(row => row.location_id === locationId)
    const test = !['HIGH', 'VERY_HIGH'].includes(location?.risk_category ?? '')
    setBusy(true); setError(''); setSuccess('')
    try {
      const saved = await createSyntheticAlert(locationId, frame.timestamp, token, test)
      setSuccess(`${alerts.some(row => row.id === saved.id) || saved.status !== 'PENDING' ? 'Existing' : saved.is_test ? 'Test' : 'Simulated'} alert #${saved.id} ${saved.status !== 'PENDING' ? `is ${saved.status.toLowerCase()}; history was retained` : 'saved for review'}. No public warning was issued.`)
      setAlertView(saved.status === 'PENDING' || saved.status === 'APPROVED' ? 'CURRENT' : 'HISTORY')
      await refreshAlerts()
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Alert creation failed') }
    finally { setBusy(false) }
  }
  const manageAlert = async (id: number, action: SyntheticAction, reason?: string) => {
    if (!token) return
    if (['resolve', 'cancel'].includes(action) && !reason?.trim()) { setError('Enter an action reason.'); return }
    if (['resolve', 'cancel'].includes(action) && !window.confirm(`${action === 'cancel' ? 'Cancel' : 'Resolve'} simulated alert #${id}? Reason: ${reason?.trim()}. Its audit history will be retained.`)) return
    setBusy(true); setError(''); setSuccess('')
    try {
      if (action === 'approve') await approveSyntheticAlert(id, token)
      else await manageSyntheticAlert(id, token, action, reason)
      setSuccess(`Simulated alert #${id} ${{ approve: 'approved', acknowledge: 'acknowledged', resolve: 'resolved', cancel: 'cancelled' }[action]}. No operational warning was issued.`)
      await refreshAlerts()
    }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Alert update failed') }
    finally { setBusy(false) }
  }
  const enableNotifications = async () => {
    if (!('Notification' in window)) { setError('This browser does not support desktop notifications'); return }
    try {
      const permission = await Notification.requestPermission()
      setNotifications(permission === 'granted')
      if (permission !== 'granted') setError('Browser notification permission was not granted')
    } catch { setError('Browser notifications are unavailable') }
  }

  return <div className="page-stack synthetic-replay" data-source-type="synthetic">
    <section className="synthetic-banner" role="note">
      <span className="source-indicator">Synthetic data</span>
      <h1>Historical analysis</h1>
      <p>Generated weather and simulator-trained predictions. Provisional risk bands; no official Fiji MET readings or emergency warnings.</p>
      <details className="source-details"><summary>Data source & methodology</summary><p>{SYNTHETIC_NOTICE}. Simulated historical records are used for model analysis and isolated alert exercises.</p></details>
    </section>
    {error && <p role="alert">{error}</p>}
    {success && <p className="alert-action-success" role="status">{success}</p>}
    {info?.status === 'not_imported' && <p>Simulation data has not been imported. Follow the synthetic setup guide.</p>}
    <section className="prototype-panel synthetic-controls">
      <label htmlFor="synthetic-time">Historical timestamp (UTC)</label>
      <input id="synthetic-time" type="datetime-local" step="3600" value={timestamp}
        min={info?.config ? `${info.config.start}T00:00` : undefined}
        max={info?.config ? `${info.config.end}T23:00` : undefined}
        onChange={event => setTimestamp(event.target.value)} />
      <button className="button button--primary" disabled={busy || info?.status !== 'ready' || !timestamp} onClick={() => void loadFrame()}>
        {busy ? 'Working…' : 'Load historical analysis'}
      </button>
      <p>{info?.observations.toLocaleString() ?? 'Loading'} generated observations. Forecast horizon: next 24 hours.</p>
    </section>
    {frame && <>
      <p><span className="source-indicator">Synthetic data</span> · {frame.timestamp} · {frame.locations.length} monitored locations</p>
      <WeatherMap locations={maps} selectedLocationId={selectedId} onSelectLocation={setSelectedId} />
      <section className="prototype-panel synthetic-table synthetic-table--predictions" aria-label="Synthetic location forecasts">
        <table><thead><tr><th>Location</th><th>Rainfall</th><th>Soil saturation</th><th>River level</th><th>24h probability</th><th>Provisional risk</th>{admin && <th>Simulation approval</th>}</tr></thead>
          <tbody>{frame.locations.map(location => {
            const existing = alerts.find(alert => alert.location_id === location.location_id && alert.model_version === location.model_version && Date.parse(alert.timestamp) === Date.parse(frame.timestamp))
            const disabledReason = busy ? 'An action is in progress.' : !token ? 'Sign in as an approved MET administrator.'
              : !info?.alerts_enabled ? 'Simulated alert creation is disabled by the operator (SYNTHETIC_DEMO_ENABLED).'
              : location.status !== 'ok' || location.probability == null || !location.risk_category ? 'A complete eligible forecast is required. Load another hour with model output.'
              : existing ? `Alert #${existing.id} already exists (${existing.status.toLowerCase()}). Review it in the simulated alert section; choose another hour for a new test.` : ''
            return <tr key={location.location_id}>
            <td data-label="Location"><button onClick={() => setSelectedId(location.slug)}>{location.name}</button><small> ID {location.location_id}</small></td>
            <td data-label="Rainfall">{display(location.weather.rainfall_mm, 'mm')}</td><td data-label="Soil saturation">{display(location.weather.soil_moisture_pct, '%')}</td><td data-label="River level">{display(location.weather.river_level_m, 'm')}</td>
            <td data-label="24h probability">{location.probability == null ? (location.simulated_flood_active ? 'Flood already active in simulation' : 'Insufficient history') : `${(location.probability * 100).toFixed(1)}%`}</td>
            <td data-label="Provisional risk">{location.risk_category ? <RiskPill risk={location.risk_category} /> : 'Forecast withheld'}</td>
            {admin && <td data-label="Simulated alert" className="synthetic-table__action"><button className="button button--secondary" disabled={Boolean(disabledReason)} aria-describedby={`create-reason-${location.location_id}`}
              onClick={() => void createAlert(location.location_id)}>{['HIGH', 'VERY_HIGH'].includes(location.risk_category ?? '') ? 'Create simulated alert' : 'Create test alert'}</button>
              <small id={`create-reason-${location.location_id}`}>{disabledReason || (['LOW', 'MODERATE'].includes(location.risk_category ?? '') ? 'Isolated test only; forecast risk is unchanged.' : 'Creates a pending simulated alert for review.')}</small></td>}
          </tr>})}</tbody>
        </table>
      </section>
      {selected && <section className="prototype-panel" aria-label="Selected synthetic weather">
        <h2>{selected.name} · Weather analysis</h2>
        <p>Temperature {display(selected.weather.temperature_c, '°C')} · Humidity {display(selected.weather.humidity_pct, '%')} · Pressure {display(selected.weather.pressure_hpa, 'hPa')}</p>
        <p>Wind {display(selected.weather.wind_speed_ms, 'm/s')} at {display(selected.weather.wind_direction_deg, '°')} · Upstream rainfall {display(selected.weather.upstream_rainfall_mm, 'mm')}</p>
        <p>Discharge {display(selected.weather.river_discharge_m3s, 'm³/s')} · Tide {display(selected.weather.coastal_tide_m, 'm')}</p>
        <small>Model {selected.model_version} · Horizon {selected.horizon_hours} hours</small>
      </section>}
    </>}
    <section id="simulated-alerts" className="prototype-panel" aria-label="Isolated synthetic alerts">
      <h2>Simulated alert workflows</h2>
      <p>These records have a separate feed. Only approved synthetic alerts can generate optional browser notifications in this simulation view.</p>
      {!info?.alerts_enabled && <p>Simulated alert creation is currently disabled by the operator.</p>}
      <button className="button button--secondary" onClick={() => notifications ? setNotifications(false) : void enableNotifications()}>{notifications ? 'Disable synthetic browser notifications' : 'Enable synthetic browser notifications'}</button>
      <div className="filter-pills" role="group" aria-label="Simulated alert views">
        <button className="filter-pill" aria-pressed={alertView === 'CURRENT'} onClick={() => setAlertView('CURRENT')}>Current alerts</button>
        <button className="filter-pill" aria-pressed={alertView === 'HISTORY'} onClick={() => setAlertView('HISTORY')}>Alert history</button>
      </div>
      {!admin && <p>Sign in as a MET administrator to create test alerts and manage their history.</p>}
      {alerts.filter(alert => ['PENDING', 'APPROVED'].includes(alert.status) === (alertView === 'CURRENT')).length === 0 && <p>No {alertView === 'CURRENT' ? 'current simulated alerts' : 'simulated alert history'}.</p>}
      {alerts.filter(alert => ['PENDING', 'APPROVED'].includes(alert.status) === (alertView === 'CURRENT')).map(alert => <SyntheticAlertCard key={alert.id} alert={alert} admin={admin} enabled={Boolean(info?.alerts_enabled)} busy={busy} onAction={manageAlert} />)}
    </section>
  </div>
}
