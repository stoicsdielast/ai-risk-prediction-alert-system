import type { WeatherLocation } from '../../types/prototype'
import { formatDateTime, formatRelativeTime } from '../../utils/date'
import { DataPill, RiskPill } from '../pills/DataPill'

interface LocationDetailCardProps {
  location: WeatherLocation | null
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

  return (
    <aside className="location-detail-card" aria-live="polite">
      <header className="location-detail-card__header">
        <div className="location-detail-card__identity">
          <span>{location.division}</span>
          <h2>{location.name}</h2>
        </div>
        <RiskPill risk={location.riskLevel} />
      </header>

      <p className="location-detail-card__timestamp">
        Updated{' '}
        <time dateTime={location.updatedAt} title={formatDateTime(location.updatedAt)}>
          {formatRelativeTime(location.updatedAt)}
        </time>
      </p>

      <section className="location-detail-section" aria-labelledby="current-weather-title">
        <div className="location-detail-section__heading">
          <span>Latest observation</span>
          <h3 id="current-weather-title">Current weather</h3>
        </div>
        <div className="weather-metric-grid">
          <WeatherMetric label="Conditions" value={location.condition} />
          <WeatherMetric label="Temperature" value={`${location.temperatureC}°C`} />
          <WeatherMetric
            label="Rainfall"
            value={`${location.rainfall24hMm} mm`}
            hint="Past 24 hours"
          />
          <WeatherMetric label="Humidity" value={`${location.humidityPercent}%`} />
          <WeatherMetric label="Wind" value={`${location.windKph} km/h`} />
        </div>
      </section>

      <section className="prediction-panel" aria-labelledby="prediction-title">
        <div className="prediction-panel__heading">
          <DataPill value="AI_PREDICTION" />
          <span>{location.prediction.confidencePercent}% confidence</span>
        </div>
        <h3 id="prediction-title">{location.prediction.label}</h3>
        <p>{location.prediction.summary}</p>
        <div
          className="confidence-meter"
          role="meter"
          aria-label="Prediction confidence"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={location.prediction.confidencePercent}
        >
          <span
            className="confidence-meter__fill"
            style={{ width: `${location.prediction.confidencePercent}%` }}
          />
        </div>
        <small>Decision-support estimate · not an official public warning</small>
      </section>

      <section
        className={`official-warning-panel${
          location.officialWarning ? '' : ' official-warning-panel--clear'
        }`}
        aria-labelledby="official-warning-title"
      >
        <DataPill
          value="OFFICIAL_WARNING"
          label={location.officialWarning ? undefined : 'No official warning active'}
        />
        <h3 id="official-warning-title">
          {location.officialWarning ? 'Official public warning' : 'Official status'}
        </h3>
        <p>
          {location.officialWarning ??
            'No official Fiji MET warning is included for this location in the current demo data.'}
        </p>
      </section>
    </aside>
  )
}
