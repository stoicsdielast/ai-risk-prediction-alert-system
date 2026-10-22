import { lazy, Suspense, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { AuthContext } from '../../auth/AuthContext'
import { getReplayExamples, getResearchInfo, runReplay } from '../../api/predictions'
import type { ReplayExample, ResearchInfo, ResearchResult } from '../../api/predictions'

const ResearchReplayMap = lazy(() => import('./ResearchReplayMap').then((module) => ({ default: module.ResearchReplayMap })))

export function ResearchReplayPanel() {
  const session = useContext(AuthContext)
  const [open, setOpen] = useState(false)
  const [info, setInfo] = useState<ResearchInfo | null>(null)
  const [examples, setExamples] = useState<ReplayExample[]>([])
  const [selected, setSelected] = useState('normal')
  const [result, setResult] = useState<ResearchResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [consent, setConsent] = useState(false)
  const [permission, setPermission] = useState('')
  const requestVersion = useRef(0)
  const invalidateRequest = useCallback(() => { requestVersion.current++ }, [])
  const example = examples.find((item) => item.id === selected)

  useEffect(() => {
    if (!open) return
    let current = true
    setBusy(false)
    setResult(null)
    setNotice('')
    setLoading(true)
    setError('')
    Promise.all([getResearchInfo(), getReplayExamples()]).then(([model, replay]) => {
      if (current) { setInfo(model); setExamples(replay.examples) }
    }).catch((caught: unknown) => {
      if (current) setError(caught instanceof Error ? caught.message : 'Research data unavailable')
    }).finally(() => { if (current) setLoading(false) })
    return () => { current = false; invalidateRequest() }
  }, [open, invalidateRequest])

  useEffect(() => {
    // An expired/signed-out session cannot retain a runnable prediction result.
    requestVersion.current++
    setResult(null)
    setBusy(false)
    setNotice('')
  }, [session?.token])

  async function predict() {
    if (!example || !session?.token || busy) return
    const version = ++requestVersion.current
    setBusy(true); setResult(null); setError(''); setNotice('')
    try {
      const response = await runReplay(example, session.token)
      if (version === requestVersion.current) setResult(response)
    } catch (caught: unknown) {
      if (version === requestVersion.current) setError(caught instanceof Error ? caught.message : 'Prediction unavailable')
    } finally {
      if (version === requestVersion.current) setBusy(false)
    }
  }

  async function allowBrowserDemo() {
    if (!('Notification' in window)) { setPermission('Browser notifications are unavailable.'); return }
    try {
      const granted = await Notification.requestPermission()
      setPermission(granted === 'granted' ? 'Browser demo notifications enabled for this panel.' : 'Browser permission was not granted.')
      setConsent(granted === 'granted')
    } catch { setPermission('Browser notifications are unavailable.'); setConsent(false) }
  }

  function demonstrateAlert() {
    if (!result || result.status !== 'ok' || !example) return
    const message = `DEMO ONLY — ${example.station.name}, Bangladesh, ${example.feature_date}: ${result.presentation_tier} provisional tier. Historical research replay; no public warning.`
    setNotice(message)
    if (consent && 'Notification' in window && Notification.permission === 'granted') {
      try { new Notification('DEMO ONLY — Bangladesh research replay', { body: message, tag: 'bangladesh-research-demo' }) }
      catch { setPermission('Browser notification failed; the internal demo message is shown below.') }
    }
  }

  return (
    <section className="prototype-panel research-replay-panel" aria-label="Bangladesh research proof of concept">
      <span className="eyebrow">Research Proof of Concept</span>
      <h2>Bangladesh historical flood replay</h2>
      <p>Historical Bangladesh data. This model has not been validated for Fiji or operational public warnings.</p>
      <button type="button" className="button button--secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Close research replay' : 'Open Bangladesh research replay'}
      </button>
      {open && <div className="research-replay-content">
        {loading && <p>Loading research artifacts…</p>}
        {error && <p role="alert">{error}</p>}
        {info?.status === 'data_unavailable' && <p>{info.reason ?? 'Research model data unavailable. Train the pinned research pipeline first.'}</p>}
        {info?.status === 'ok' && <>
          <p>Model: {info.selected_model} · {info.model_version}. Source-qualified proxy labels; probabilities are uncalibrated. Four presentation tiers use provisional thresholds.</p>
          <p><a href="https://github.com/Srabon-bot/Bangladesh-flood-data-set" target="_blank" rel="noreferrer">Bangladesh dataset and provenance</a></p>
          {examples.length === 0 ? <p>Held-out replay examples are unavailable.</p> : <>
            <label>Held-out historical example{' '}
              <select value={selected} disabled={busy} onChange={(event) => { requestVersion.current++; setSelected(event.target.value); setResult(null); setNotice('') }}>
                {examples.map((item) => <option value={item.id} key={item.id}>{item.id === 'normal' ? 'Lower model score' : 'Higher model score'} — {item.station.name}, {item.feature_date}</option>)}
              </select>
            </label>
            <p>These are the lowest and highest model scores from held-out test rows, selected after evaluation for demonstration. They do not represent typical performance.</p>
            {example && <p>{example.station.name}, Bangladesh · Feature date: {example.feature_date} · Replay timestamp: {example.as_of} (UTC convention)</p>}
            {!session?.token && <p>Sign in with an approved account to run the historical replay.</p>}
            <button type="button" className="button button--primary" disabled={!session?.token || !example || busy} onClick={predict}>{busy ? 'Running historical replay…' : 'Run historical replay'}</button>
            {result?.status === 'data_unavailable' && <p role="alert">Data unavailable: {result.reason}. {result.missing_features.join(', ')}</p>}
            {result?.status === 'ok' && <div className="research-replay-result">
              <strong>{result.probability !== null ? (result.probability * 100).toFixed(2) : 'Unavailable'}% model score · {result.presentation_tier} provisional tier</strong>
              <p>Next {result.prediction_horizon_hours} hours after the historical feature day · {result.model_version}. {result.disclaimer}</p>
              <button type="button" className="button button--secondary" onClick={demonstrateAlert}>Show internal demo alert</button>{' '}
              <button type="button" className="button button--secondary" onClick={allowBrowserDemo}>Allow browser demo alerts</button>
              {permission && <p>{permission}</p>}
              {consent && <button type="button" onClick={() => { setConsent(false); setPermission('Browser demo alerts disabled for this panel.') }}>Disable browser demo alerts</button>}
              {notice && <p role="status">{notice}</p>}
            </div>}
            {example && <Suspense fallback={<p>Loading Bangladesh research map…</p>}><ResearchReplayMap example={example} result={result} /></Suspense>}
          </>}
        </>}
      </div>}
    </section>
  )
}
