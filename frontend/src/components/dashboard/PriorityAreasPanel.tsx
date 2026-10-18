import { Link } from 'react-router-dom'
import { usePriorityLocations } from '../../locations/usePriorityLocations'
import { Alert } from '../Alert'
import { DataPill, RiskPill } from '../pills/DataPill'

/** The signed-in user's saved priority areas with their latest risk. */
export function PriorityAreasPanel() {
  const { status, error, actionError, locations, pendingSlugs, toggle, retry } =
    usePriorityLocations()

  return (
    <section aria-labelledby="priority-areas-title">
      <div className="section-heading">
        <div>
          <span className="eyebrow">Saved on your account</span>
          <h2 id="priority-areas-title">My priority areas</h2>
        </div>
        <Link className="roadmap-label" to="/weather-map">
          Manage on the weather map
        </Link>
      </div>

      {actionError && <Alert tone="error">{actionError}</Alert>}

      {status === 'loading' && (
        <p className="priority-areas-empty" role="status">
          Loading your priority areas…
        </p>
      )}

      {status === 'error' && (
        <div className="priority-status" role="alert">
          <span>{error}</span>
          <button type="button" className="map-clear-button" onClick={retry}>
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && locations.length === 0 && (
        <p className="priority-areas-empty">
          You have not saved any priority areas yet. Open the weather map, select a
          location and choose “Save as priority area”.
        </p>
      )}

      {status === 'ready' && locations.length > 0 && (
        <ul className="priority-areas-grid">
          {locations.map((location) => (
            <li className="priority-area-card" key={location.slug}>
              <div className="priority-area-card__identity">
                <span>{location.division_label}</span>
                <strong>{location.name}</strong>
              </div>
              <div className="priority-area-card__risk">
                <RiskPill risk={location.prediction?.risk_level ?? null} compact />
                {location.prediction?.is_sample && <DataPill value="SAMPLE_RISK" compact />}
              </div>
              <button
                type="button"
                className="map-clear-button"
                disabled={pendingSlugs.has(location.slug)}
                aria-label={`Remove ${location.name} from priority areas`}
                onClick={() => void toggle(location.slug)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
