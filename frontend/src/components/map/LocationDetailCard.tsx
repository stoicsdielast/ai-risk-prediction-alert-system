import type { MapLocation, MapPrediction } from '../../types/location'
import { formatDateTime, formatRelativeTime } from '../../utils/date'
import { DataPill, RiskPill } from '../pills/DataPill'

interface LocationDetailCardProps {
  location: MapLocation | null
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

  return (
    <section className="prediction-panel" aria-labelledby="prediction-title">
      <div className="prediction-panel__heading">
        <DataPill value={prediction.isSample ? 'SAMPLE_RISK' : 'AI_PREDICTION'} />
        <span>{prediction.confidencePercent}% confidence</span>
      </div>
      <h3 id="prediction-title">{prediction.label}</h3>
      <p>{prediction.summary}</p>
      <div
        className="confidence-meter"
        role="meter"
        aria-label="Prediction confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={prediction.confidencePercent}
      >
        <span
          className="confidence-meter__fill"
          style={{ width: `${prediction.confidencePercent}%` }}
        />
      </div>
      <small>
        {prediction.isSample
          ? 'Labelled sample for testing · not a real forecast or official warning'
          : 'Decision-support estimate · not an official public warning'}
      </small>
    </section>
  )
}

export function LocationDetailCard({ location }: LocationDetailCardProps) {
  if (!location) {
    return (
      <aside className="location-detail-card location-detail-card--empty">
        <span className="location-detail-card__empty-mark" aria-hidden="true">⌖</span>
        <h2>No location selected</h2>
        <p>Select a visible marker or location card to inspect its latest conditions.</p>
      </aside>
    )
  }

  const { conditions } = location

  return (
    <aside className="location-detail-card" aria-live="polite">
      <header className="location-detail-card__header">
        <div className="location-detail-card__identity">
          <span>{location.division}</span>
          <h2>{location.name}</h2>
        </div>
        <RiskPill risk={location.riskLevel} />
      </header>

      {conditions && (
        <>
          <p className="location-detail-card__timestamp">
            Updated{' '}
            <time
              dateTime={conditions.updatedAt}
              title={formatDateTime(conditions.updatedAt)}
            >
              {formatRelativeTime(conditions.updatedAt)}
            </time>
          </p>

          <section
            className="location-detail-section"
            aria-labelledby="current-weather-title"
          >
            <div className="location-detail-section__heading">
              <span>Latest observation</span>
              <h3 id="current-weather-title">Current weather</h3>
            </div>
            <div className="weather-metric-grid">
              <WeatherMetric label="Conditions" value={conditions.condition} />
              <WeatherMetric label="Temperature" value={`${conditions.temperatureC}°C`} />
              <WeatherMetric
                label="Rainfall"
                value={`${conditions.rainfall24hMm} mm`}
                hint="Past 24 hours"
              />
              <WeatherMetric label="Humidity" value={`${conditions.humidityPercent}%`} />
              <WeatherMetric label="Wind" value={`${conditions.windKph} km/h`} />
            </div>
          </section>
        </>
      )}

      <PredictionPanel prediction={location.prediction} />

      <section
        className={`official-warning-panel${
          conditions?.officialWarning ? '' : ' official-warning-panel--clear'
        }`}
        aria-labelledby="official-warning-title"
      >
        <DataPill
          value="OFFICIAL_WARNING"
          label={conditions?.officialWarning ? undefined : 'No official warning active'}
        />
        <h3 id="official-warning-title">
          {conditions?.officialWarning ? 'Official public warning' : 'Official status'}
        </h3>
        <p>
          {conditions?.officialWarning ??
            'No official Fiji MET warning is included for this location in the current demo data.'}
        </p>
      </section>
    </aside>
  )
}
