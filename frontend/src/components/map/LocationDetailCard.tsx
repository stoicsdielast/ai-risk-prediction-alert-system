import { isSimulatedAlert } from '../../alerts/provenance'
import { useLocationWeather } from '../../locations/useLocationWeather'
import type { PublicAlert } from '../../types/alert'
import type { MapLocation, MapPrediction } from '../../types/location'
import type { ApiWeatherObservation } from '../../types/weather'
import type { RiskLevel } from '../../types/prototype'
import {
  formatDateTime,
  formatRelativeTime,
  isStaleTimestamp,
  PREDICTION_STALE_AFTER_HOURS,
} from '../../utils/date'
import { DataPill, RiskPill } from '../pills/DataPill'
import type { PillValue } from '../pills/DataPill'

const RISK_HEADINGS: Record<RiskLevel, string> = {
  LOW: 'Low flood risk',
  MODERATE: 'Moderate flood risk',
  HIGH: 'High flood risk',
  VERY_HIGH: 'Very high flood risk',
}

interface LocationDetailCardProps {
  location: MapLocation | null
  /** Approved community alerts for this location, from the live public feed. */
  activeAlerts?: PublicAlert[]
}

interface WeatherMetricProps {
  label: string
  value: string
  hint?: string
}

function WeatherMetric({ label, value, hint }: WeatherMetricProps) {
  return (
    <div className="weather-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

const weatherNumber = new Intl.NumberFormat('en-FJ', { maximumFractionDigits: 1 })

function observationMetrics(
  observation: ApiWeatherObservation,
): WeatherMetricProps[] {
  const metrics: WeatherMetricProps[] = []

  if (observation.temperature_c !== null) {
    metrics.push({ label: 'Temperature', value: `${weatherNumber.format(observation.temperature_c)}°C` })
  }
  if (observation.rainfall_mm !== null) {
    metrics.push({
      label: 'Rainfall',
      value: `${weatherNumber.format(observation.rainfall_mm)} mm`,
      hint: observation.rainfall_period_minutes
        ? `Per ${observation.rainfall_period_minutes}-minute interval`
        : undefined,
    })
  }
  if (observation.humidity_pct !== null) {
    metrics.push({ label: 'Humidity', value: `${weatherNumber.format(observation.humidity_pct)}%` })
  }
  if (observation.wind_speed_mps !== null) {
    metrics.push({ label: 'Wind', value: `${weatherNumber.format(observation.wind_speed_mps)} m/s` })
  }
  if (observation.pressure_hpa !== null) {
    metrics.push({ label: 'Pressure', value: `${weatherNumber.format(observation.pressure_hpa)} hPa` })
  }
  if (observation.river_level_m !== null) {
    metrics.push({
      label: 'River level',
      value: `${weatherNumber.format(observation.river_level_m)} m`,
      hint: observation.gauge_datum ?? undefined,
    })
  }

  return metrics
}

const PROVENANCE_PILLS: Record<MapPrediction['provenance'], PillValue> = {
  model: 'AI_PREDICTION',
  sample: 'SAMPLE_RISK',
  synthetic: 'SYNTHETIC_PREDICTION',
}

function provenanceNote(prediction: MapPrediction): string {
  switch (prediction.provenance) {
    case 'model':
      return `Model ${prediction.modelVersion} · decision-support estimate · not an official public warning`
    case 'sample':
      return 'Labelled sample for testing · not a real forecast or official warning'
    case 'synthetic':
      return 'Synthetic research simulation · not Fiji MET data or a real forecast'
  }
}

function PredictionPanel({ prediction }: { prediction: MapPrediction | null }) {
  if (!prediction) {
    return (
      <section className="prediction-panel" aria-labelledby="prediction-title">
        <div className="prediction-panel__heading">
          <DataPill value="NO_PREDICTION" />
        </div>
        <h3 id="prediction-title">No prediction available</h3>
        <p>There is no flood-risk prediction for this location yet.</p>
      </section>
    )
  }

  const stale = isStaleTimestamp(prediction.predictedAt)

  return (
    <section className="prediction-panel" aria-labelledby="prediction-title">
      <div className="prediction-panel__heading">
        <DataPill value={PROVENANCE_PILLS[prediction.provenance]} />
        <span>{prediction.floodProbabilityPercent}% flood probability</span>
      </div>
      <h3 id="prediction-title">{RISK_HEADINGS[prediction.riskLevel]}</h3>
      <p>
        Predicted{' '}
        <time
          dateTime={prediction.predictedAt}
          title={formatDateTime(prediction.predictedAt)}
        >
          {formatRelativeTime(prediction.predictedAt)}
        </time>
        {stale && (
          <>
            {' '}
            <DataPill value="STALE" compact />
          </>
        )}
        .
      </p>
      <div
        className="confidence-meter"
        role="meter"
        aria-label="Flood probability"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={prediction.floodProbabilityPercent}
      >
        <span
          className="confidence-meter__fill"
          style={{ width: `${prediction.floodProbabilityPercent}%` }}
        />
      </div>
      <small>{provenanceNote(prediction)}</small>
      {stale && (
        <small>
          This prediction is more than {PREDICTION_STALE_AFTER_HOURS} hours old
          — treat it as out of date.
        </small>
      )}
    </section>
  )
}

function WeatherSection({
  status,
  error,
  latest,
  retry,
}: {
  status: ReturnType<typeof useLocationWeather>['status']
  error: string | null
  latest: ReturnType<typeof useLocationWeather>['latest']
  retry: () => void
}) {
  const observation = latest?.observation ?? null
  const metrics = observation ? observationMetrics(observation) : []

  return (
    <section
      className="location-detail-section"
      aria-labelledby="current-weather-title"
    >
      <div className="location-detail-section__heading">
        <span>
          Latest observation
          {observation?.source_type === 'synthetic' && (
            <>
              {' '}
              <DataPill value="SYNTHETIC_DATA" compact />
            </>
          )}
        </span>
        <h3 id="current-weather-title">Stored weather</h3>
      </div>

      {status === 'idle' || status === 'loading' ? (
        <div className="prototype-empty-state" role="status">
          Loading latest stored observation…
        </div>
      ) : status === 'error' ? (
        <div className="prototype-empty-state" role="alert">
          <p>Weather observations are unavailable. {error}</p>
          <button type="button" className="map-clear-button" onClick={retry}>
            Try again
          </button>
        </div>
      ) : !observation ? (
        <div className="prototype-empty-state">
          <p>
            No observation has been stored for this location yet. Generated historical
            weather appears here once it has been ingested.
          </p>
        </div>
      ) : (
        <>
          <p className="location-detail-card__timestamp">
            {observation.source_type === 'synthetic' ? 'Simulated timestamp' : 'Observed'}{' '}
            <time
              dateTime={observation.observed_at}
              title={formatDateTime(observation.observed_at)}
            >
              {formatRelativeTime(observation.observed_at)}
            </time>
            {observation.stale && (
              <>
                {' '}
                <DataPill value="STALE" compact />
              </>
            )}
          </p>

          {metrics.length === 0 ? (
            <div className="prototype-empty-state">
              This observation was stored without measurement values.
            </div>
          ) : (
            <div className="weather-metric-grid">
              {metrics.map((metric) => (
                <WeatherMetric key={metric.label} {...metric} />
              ))}
            </div>
          )}

          {observation.notice && <small>{observation.notice}</small>}
        </>
      )}
    </section>
  )
}

function alertSourceLabel(source: PublicAlert['source']): string {
  return source === 'MET_OFFICIAL' ? 'MET official' : 'AI recommendation'
}

function PublicAlertsPanel({ alerts }: { alerts: PublicAlert[] }) {
  return (
    <section
      className={`official-warning-panel${
        alerts.length === 0 ? ' official-warning-panel--clear' : ''
      }`}
      aria-labelledby="public-alerts-title"
    >
      <DataPill
        value={alerts.length === 0 ? 'NO_ALERTS' : 'APPROVED'}
        label={alerts.length === 0 ? undefined : 'Approved alert'}
      />
      <h3 id="public-alerts-title">Approved public alerts</h3>

      {alerts.length === 0 ? (
        <p>No approved community alert is active for this location.</p>
      ) : (
        alerts.map((alert) => (
          <div className="activity-item" key={alert.id}>
            <div className="activity-item__content">
              <div className="activity-item__heading">
                <RiskPill risk={alert.severity} compact />
                <small>{isSimulatedAlert(alert) ? 'Simulated alert · Not an emergency warning' : alertSourceLabel(alert.source)}</small>
              </div>
              <p>{alert.message}</p>
              <small>{formatRelativeTime(alert.created_at)}</small>
            </div>
          </div>
        ))
      )}

      <small>
        Approved alerts from this system only. Official Fiji Meteorological
        Service warnings are issued separately and always take precedence.
      </small>
    </section>
  )
}

export function LocationDetailCard({
  location,
  activeAlerts = [],
}: LocationDetailCardProps) {
  const weather = useLocationWeather(location?.apiId ?? null)

  if (!location) {
    return (
      <aside className="location-detail-card location-detail-card--empty">
        <span className="location-detail-card__empty-mark" aria-hidden="true">⌖</span>
        <h2>No location selected</h2>
        <p>Select a visible marker or location card to inspect its latest conditions.</p>
      </aside>
    )
  }

  return (
    <aside className="location-detail-card" aria-live="polite">
      <header className="location-detail-card__header">
        <div className="location-detail-card__identity">
          <span>{location.division}</span>
          <h2>{location.name}</h2>
        </div>
        <RiskPill risk={location.riskLevel} />
      </header>

      <WeatherSection
        status={weather.status}
        error={weather.error}
        latest={weather.latest}
        retry={weather.retry}
      />

      <PredictionPanel prediction={location.prediction} />

      <PublicAlertsPanel alerts={activeAlerts} />
    </aside>
  )
}
