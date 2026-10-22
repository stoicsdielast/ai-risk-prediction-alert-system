import { useCallback, useEffect, useMemo, useState } from 'react'
import { RiskPill } from '../components/pills/DataPill'
import {
  getResearchFrame, getResearchInfo, getResearchSeries, getResearchStorms, SYNTHETIC_NOTICE,
  type ResearchFrame, type ResearchInfo, type ResearchScenarioName, type ResearchSeries,
  type ResearchStorm,
} from '../api/syntheticResearch'

const SCENARIOS: ResearchScenarioName[] = ['controlled', 'realistic', 'stress']

const display = (value: number | null | undefined, unit: string) =>
  value == null ? '—' : `${value.toFixed(1)} ${unit}`

const inputStamp = (iso: string) => new Date(iso.replace(' ', 'T')).toISOString().slice(0, 16)

const isoZ = (value: string) => new Date(value.replace(' ', 'T')).toISOString()

const hourShift = (iso: string, hours: number) =>
  new Date(new Date(iso.replace(' ', 'T')).getTime() + hours * 3600_000).toISOString()

function truthCell(label: string, value: boolean | undefined) {
  if (value == null) return <td title={`Ground truth ${label}: unavailable`}>—</td>
  return <td title={`Ground truth ${label} (display only)`}>{value ? 'Yes' : 'No'}</td>
}

export function SyntheticResearchPage() {
  const [info, setInfo] = useState<ResearchInfo | null>(null)
  const [scenario, setScenario] = useState<ResearchScenarioName>('realistic')
  const [timestamp, setTimestamp] = useState('')
  const [frame, setFrame] = useState<ResearchFrame | null>(null)
  const [storms, setStorms] = useState<ResearchStorm[]>([])
  const [series, setSeries] = useState<ResearchSeries | null>(null)
  const [locationId, setLocationId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    getResearchInfo().then(result => { if (active) setInfo(result) })
      .catch(caught => { if (active) setError(String(caught.message)) })
    return () => { active = false }
  }, [])

  const activeScenario = info?.scenarios.find(entry => entry.scenario === scenario)

  const loadStorms = useCallback(async (name: ResearchScenarioName) => {
    setBusy(true); setError(''); setFrame(null); setSeries(null); setLocationId(null)
    try {
      const result = await getResearchStorms(name)
      setStorms(result.storms)
      const range = info?.scenarios.find(entry => entry.scenario === name)?.time_range
      if (range) setTimestamp(inputStamp(range.start))
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Storms failed to load') }
    finally { setBusy(false) }
  }, [info])

  useEffect(() => { void loadStorms(scenario) }, [scenario, loadStorms])

  const loadFrame = async () => {
    setBusy(true); setError('')
    try { setFrame(await getResearchFrame(scenario, `${timestamp}:00Z`)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Frame failed to load') }
    finally { setBusy(false) }
  }

  const loadSeries = async (id: number, start: string, end: string) => {
    setLocationId(id); setBusy(true); setError('')
    try { setSeries(await getResearchSeries(scenario, id, start, end)) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Series failed to load') }
    finally { setBusy(false) }
  }

  const replayStorm = (storm: ResearchStorm) => {
    setTimestamp(inputStamp(storm.start))
    void loadFrameFor(storm.start)
    void loadSeries(storm.location_id, hourShift(storm.start, -6), hourShift(storm.end, 12))
  }

  const loadFrameFor = async (iso: string) => {
    setBusy(true); setError('')
    try { setFrame(await getResearchFrame(scenario, isoZ(iso))) }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'Frame failed to load') }
    finally { setBusy(false) }
  }

  const seriesLocation = useMemo(
    () => series?.series.find(entry => entry.location_id === locationId) ?? null,
    [series, locationId],
  )

  return <div className="page-stack synthetic-replay" data-source-type="synthetic">
    <section className="synthetic-banner" role="note">
      <span className="source-indicator">Synthetic data · Research only</span>
      <h1>Scenario analysis</h1>
      <p>Compare controlled, realistic and stress scenarios using generated historical weather. Results are not Fiji MET observations or emergency warnings.</p>
      <details className="source-details"><summary>Data source & methodology</summary>
        <p>{SYNTHETIC_NOTICE}. Simulator outcomes do not establish real forecast skill. The deployed V1 model and its configuration are unchanged; this view cannot create alerts.</p>
      </details>
    </section>
    {error && <p role="alert">{error}</p>}
    <section className="prototype-panel synthetic-controls" aria-label="Scenario selector">
      <label htmlFor="research-scenario">Synthetic scenario</label>
      <select id="research-scenario" value={scenario} disabled={busy}
        onChange={event => setScenario(event.target.value as ResearchScenarioName)}>
        {SCENARIOS.map(name => {
          const entry = info?.scenarios.find(candidate => candidate.scenario === name)
          const label = entry?.status === 'ready' ? name : `${name} (not published)`
          return <option key={name} value={name} disabled={entry?.status !== 'ready'}>{label}</option>
        })}
      </select>
      <label htmlFor="research-time">Historical timestamp (UTC)</label>
      <input id="research-time" type="datetime-local" step="3600" value={timestamp} disabled={busy}
        min={activeScenario?.time_range ? inputStamp(activeScenario.time_range.start) : undefined}
        max={activeScenario?.time_range ? inputStamp(activeScenario.time_range.end) : undefined}
        onChange={event => setTimestamp(event.target.value)} />
      <button className="button button--primary" disabled={busy || !timestamp}
        onClick={() => void loadFrame()}>Load scenario frame</button>
      {activeScenario?.status === 'ready' && <p>
        Model {activeScenario.model_version} · candidate {activeScenario.selected_candidate} ({activeScenario.calibration}) ·
        threshold {activeScenario.threshold?.toFixed(4)} · {activeScenario.observations?.toLocaleString()} observations ·
        {' '}{activeScenario.events?.total} simulated flood events · held locations {(activeScenario.held_location_ids ?? []).join(', ')}
      </p>}
      {info && !info.v1_serving_unchanged && <p role="alert">Unexpected serving configuration</p>}
    </section>
    <section className="prototype-panel synthetic-table" aria-label="Simulated storm replay">
      <h2>Storm replay — {scenario}</h2>
      <p>Select a simulated flood event to jump the frame to its onset and load the affected location timeline.</p>
      <table>
        <thead><tr><th>Event</th><th>Location</th><th>Start (UTC)</th><th>End (UTC)</th><th>Severity</th>
          <th>Duration</th><th>Peak river level</th><th>Replay</th></tr></thead>
        <tbody>{storms.slice(0, 60).map(storm => <tr key={storm.event_id}>
          <td><code>{storm.event_id}</code></td>
          <td>{storm.name}</td><td>{storm.start}</td><td>{storm.end}</td><td>{storm.severity}</td>
          <td>{storm.duration_hours.toFixed(0)} h</td><td>{display(storm.max_river_level_m, 'm')}</td>
          <td><button disabled={busy} onClick={() => replayStorm(storm)}>Replay storm</button></td>
        </tr>)}</tbody>
      </table>
      {storms.length > 60 && <p>Showing the first 60 of {storms.length} simulated events.</p>}
    </section>
    {frame && <section className="prototype-panel synthetic-table" aria-label="Scenario frame">
      <h2>Frame at {frame.timestamp}</h2>
      <p><strong>{SYNTHETIC_NOTICE}</strong> · threshold {frame.threshold.toFixed(4)} ·
        {' '}ground truth columns are evaluation labels served separately from the model input.</p>
      <table>
        <thead><tr><th>Location</th><th>Rainfall</th><th>Soil saturation</th><th>River level</th>
          <th>24h probability</th><th>Provisional risk</th><th>Flood active (truth)</th>
          <th>Flood within 24h (truth)</th><th>Event</th><th>Partition</th></tr></thead>
        <tbody>{frame.locations.map(location => <tr key={location.location_id}>
          <td><button disabled={busy}
            onClick={() => void loadSeries(location.location_id, hourShift(frame.timestamp, -12), hourShift(frame.timestamp, 12))}>
            {location.name}</button><small> ID {location.location_id}</small></td>
          <td>{display(location.weather.rainfall_mm, 'mm')}</td>
          <td>{display(location.weather.soil_moisture_pct, '%')}</td>
          <td>{display(location.weather.river_level_m, 'm')}</td>
          <td>{location.probability == null ? 'Insufficient history' : `${(location.probability * 100).toFixed(1)}%`}</td>
          <td>{location.risk_category ? <RiskPill risk={location.risk_category} /> : 'Forecast withheld'}</td>
          {truthCell('flood active', location.ground_truth.flood_occurred)}
          {truthCell('flood within 24h', location.ground_truth.flood_within_24h)}
          <td>{location.ground_truth.event_id ?? '—'}</td>
          <td>{location.ground_truth.partition ?? '—'}</td>
        </tr>)}</tbody>
      </table>
    </section>}
    {series && seriesLocation && <section className="prototype-panel" aria-label="Location timeline">
      <h2>{seriesLocation.name} · timeline {series.start} → {series.end}</h2>
      <p>Hourly simulated weather, provisional probability and evaluation labels for this scenario.</p>
      <table>
        <thead><tr><th>Time (UTC)</th><th>Rainfall</th><th>River level</th><th>Probability</th>
          <th>Risk</th><th>Flood active (truth)</th><th>Event</th></tr></thead>
        <tbody>{series.series.map(entry => <tr key={entry.timestamp}>
          <td>{entry.timestamp}</td>
          <td>{display(entry.weather.rainfall_mm, 'mm')}</td>
          <td>{display(entry.weather.river_level_m, 'm')}</td>
          <td>{entry.probability == null ? '—' : `${(entry.probability * 100).toFixed(1)}%`}</td>
          <td>{entry.risk_category ? <RiskPill risk={entry.risk_category} /> : '—'}</td>
          {truthCell('flood active', entry.ground_truth.flood_occurred)}
          <td>{entry.ground_truth.event_id ?? '—'}</td>
        </tr>)}</tbody>
      </table>
    </section>}
  </div>
}
