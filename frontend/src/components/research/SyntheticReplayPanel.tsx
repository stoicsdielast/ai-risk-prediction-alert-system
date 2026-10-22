import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { WeatherMap } from '../map/WeatherMap'
import { RiskPill } from '../pills/DataPill'
import type { MapLocation } from '../../types/location'
import {
  approveSyntheticAlert, createSyntheticAlert, getSyntheticAlerts, getSyntheticFrame,
  getSyntheticInfo, notifySyntheticApproval, SYNTHETIC_NOTICE,
  type SyntheticAlert, type SyntheticFrame, type SyntheticInfo,
} from '../../api/synthetic'

export function SyntheticReplayPanel() {
  return <section className="prototype-panel synthetic-callout" aria-label={SYNTHETIC_NOTICE}>
    <strong>{SYNTHETIC_NOTICE}</strong>
    <p>Replay generated Fiji weather, compare model forecasts and demonstrate isolated alert approval for all monitored locations.</p>
    <Link className="button button--primary" to="/simulation">Open historical simulation</Link>
  </section>
}

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
    setBusy(true); setError(''); setFrame(null)
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
    setBusy(true); setError('')
    try { await createSyntheticAlert(locationId, frame.timestamp, token); await refreshAlerts() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Demo alert failed') }
    finally { setBusy(false) }
  }
  const approve = async (id: number) => {
    if (!token) return
    setBusy(true); setError('')
    try { await approveSyntheticAlert(id, token); await refreshAlerts() }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Demo approval failed') }
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

  return <div className="page-stack synthetic-replay">
    <section className="synthetic-banner" role="note">
      <h1>{SYNTHETIC_NOTICE}</h1>
      <p>Generated weather and simulator-trained predictions. Provisional risk bands; no official Fiji MET readings or emergency warnings.</p>
    </section>
    {error && <p role="alert">{error}</p>}
    {info?.status === 'not_imported' && <p>Simulation data has not been imported. Follow the synthetic setup guide.</p>}
    <section className="prototype-panel synthetic-controls">
      <label htmlFor="synthetic-time">Historical timestamp (UTC)</label>
      <input id="synthetic-time" type="datetime-local" step="3600" value={timestamp}
        min={info?.config ? `${info.config.start}T00:00` : undefined}
        max={info?.config ? `${info.config.end}T23:00` : undefined}
        onChange={event => setTimestamp(event.target.value)} />
      <button className="button button--primary" disabled={busy || info?.status !== 'ready' || !timestamp} onClick={() => void loadFrame()}>
        {busy ? 'Working…' : 'Load synthetic replay'}
      </button>
      <p>{info?.observations.toLocaleString() ?? 'Loading'} generated observations. Forecast horizon: next 24 hours.</p>
    </section>
    {frame && <>
      <p><strong>{SYNTHETIC_NOTICE}</strong> · {frame.timestamp} · {frame.locations.length} existing map locations</p>
      <WeatherMap locations={maps} selectedLocationId={selectedId} onSelectLocation={setSelectedId} />
      <section className="prototype-panel synthetic-table" aria-label="Synthetic location forecasts">
        <table><thead><tr><th>Location</th><th>Rainfall</th><th>Soil saturation</th><th>River level</th><th>24h probability</th><th>Provisional risk</th>{admin && <th>Simulation approval</th>}</tr></thead>
          <tbody>{frame.locations.map(location => <tr key={location.location_id}>
            <td><button onClick={() => setSelectedId(location.slug)}>{location.name}</button><small> ID {location.location_id}</small></td>
            <td>{display(location.weather.rainfall_mm, 'mm')}</td><td>{display(location.weather.soil_moisture_pct, '%')}</td><td>{display(location.weather.river_level_m, 'm')}</td>
            <td>{location.probability == null ? (location.simulated_flood_active ? 'Flood already active in simulation' : 'Insufficient history') : `${(location.probability * 100).toFixed(1)}%`}</td>
            <td>{location.risk_category ? <RiskPill risk={location.risk_category} /> : 'Forecast withheld'}</td>
            {admin && <td><button disabled={busy || !info?.alerts_enabled || !['HIGH', 'VERY_HIGH'].includes(location.risk_category ?? '')}
              onClick={() => void createAlert(location.location_id)}>Create pending demo alert</button></td>}
          </tr>)}</tbody>
        </table>
      </section>
      {selected && <section className="prototype-panel" aria-label="Selected synthetic weather">
        <h2>{selected.name} · {SYNTHETIC_NOTICE}</h2>
        <p>Temperature {display(selected.weather.temperature_c, '°C')} · Humidity {display(selected.weather.humidity_pct, '%')} · Pressure {display(selected.weather.pressure_hpa, 'hPa')}</p>
        <p>Wind {display(selected.weather.wind_speed_ms, 'm/s')} at {display(selected.weather.wind_direction_deg, '°')} · Upstream rainfall {display(selected.weather.upstream_rainfall_mm, 'mm')}</p>
        <p>Discharge {display(selected.weather.river_discharge_m3s, 'm³/s')} · Tide {display(selected.weather.coastal_tide_m, 'm')}</p>
        <small>Model {selected.model_version} · Horizon {selected.horizon_hours} hours</small>
      </section>}
    </>}
    <section className="prototype-panel" aria-label="Isolated synthetic alerts">
      <h2>{SYNTHETIC_NOTICE} — approval and browser notifications</h2>
      <p>These records have a separate feed. Only approved synthetic alerts can generate optional browser notifications in this simulation view.</p>
      {!info?.alerts_enabled && <p>Alert creation is disabled. Start the local backend with SYNTHETIC_DEMO_ENABLED=true to enable this isolated exercise.</p>}
      <button onClick={() => notifications ? setNotifications(false) : void enableNotifications()}>{notifications ? 'Disable synthetic browser notifications' : 'Enable synthetic browser notifications'}</button>
      {alerts.length === 0 && <p>No synthetic alerts yet.</p>}
      {alerts.map(alert => <article key={alert.id} className="synthetic-alert">
        <strong>{SYNTHETIC_NOTICE} · {alert.status}</strong><p>{alert.message}</p><small>{alert.timestamp} · {(alert.probability * 100).toFixed(1)}%</small>
        {admin && alert.status === 'PENDING' && <button disabled={busy || !info?.alerts_enabled} onClick={() => void approve(alert.id)}>Approve synthetic alert</button>}
      </article>)}
    </section>
  </div>
}
