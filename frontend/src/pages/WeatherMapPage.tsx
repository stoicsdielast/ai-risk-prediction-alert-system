import { Fragment, useEffect, useMemo, useState } from 'react'
import { usePublicAlerts } from '../alerts/useAlertFeed'
import { Alert } from '../components/Alert'
import { LocationDetailCard } from '../components/map/LocationDetailCard'
import { WeatherMap } from '../components/map/WeatherMap'
import { RiskPill } from '../components/pills/DataPill'
import { PageHeader } from '../components/layout/PageHeader'
import { useMapLocations } from '../locations/useMapLocations'
import type { DivisionCode, MapLocation } from '../types/location'
import type { RiskLevel } from '../types/prototype'
import { SyntheticReplayPanel } from '../components/research/SyntheticReplayPanel'

type RiskFilter = 'ALL' | RiskLevel | 'NONE'
type DivisionFilter = 'ALL' | DivisionCode

const RISK_FILTERS: Array<{ value: RiskFilter; label: string }> = [
  { value: 'ALL', label: 'All risks' },
  { value: 'LOW', label: 'Low' },
  { value: 'MODERATE', label: 'Moderate' },
  { value: 'HIGH', label: 'High' },
  { value: 'VERY_HIGH', label: 'Very high' },
  { value: 'NONE', label: 'No prediction' },
]

const DIVISION_ORDER: DivisionCode[] = ['CENTRAL', 'WESTERN', 'NORTHERN', 'EASTERN']

function divisionShortLabel(code: DivisionCode): string {
  return code.charAt(0) + code.slice(1).toLowerCase()
}

function divisionFullLabel(code: DivisionCode): string {
  return `${divisionShortLabel(code)} Division`
}

function matchesRiskFilter(location: MapLocation, filter: RiskFilter) {
  if (filter === 'ALL') return true
  if (filter === 'NONE') return location.riskLevel === null
  return location.riskLevel === filter
}

function matchesDivisionFilter(location: MapLocation, filter: DivisionFilter) {
  if (filter === 'ALL') return true
  return location.division === divisionFullLabel(filter)
}

export function WeatherMapPage() {
  const { status, error, locations, retry } = useMapLocations()
  const publicFeed = usePublicAlerts()
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('ALL')
  const [divisionFilter, setDivisionFilter] = useState<DivisionFilter>('ALL')
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)

  const isReady = status === 'ready'
  const hasNoLocations = isReady && locations.length === 0

  const divisionOptions = useMemo(
    () =>
      DIVISION_ORDER.filter((code) =>
        locations.some((location) => matchesDivisionFilter(location, code)),
      ),
    [locations],
  )

  const filteredLocations = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()

    return locations.filter((location) => {
      const matchesSearch =
        !normalizedQuery ||
        location.name.toLowerCase().includes(normalizedQuery) ||
        location.division.toLowerCase().includes(normalizedQuery)

      return (
        matchesSearch &&
        matchesRiskFilter(location, riskFilter) &&
        matchesDivisionFilter(location, divisionFilter)
      )
    })
  }, [locations, riskFilter, divisionFilter, searchQuery])

  const locationGroups = useMemo(() => {
    const byDivision = new Map<string, MapLocation[]>()
    for (const location of filteredLocations) {
      const bucket = byDivision.get(location.division) ?? []
      bucket.push(location)
      byDivision.set(location.division, bucket)
    }

    return DIVISION_ORDER.map(divisionFullLabel)
      .filter((label) => byDivision.has(label))
      .map((label) => ({ label, locations: byDivision.get(label) ?? [] }))
  }, [filteredLocations])

  useEffect(() => {
    if (filteredLocations.length === 0) {
      setSelectedLocationId(null)
      return
    }

    const selectionIsVisible = filteredLocations.some(
      (location) => location.id === selectedLocationId,
    )
    if (!selectionIsVisible) {
      setSelectedLocationId(
        (
          filteredLocations.find((location) => location.riskLevel === 'VERY_HIGH') ??
          filteredLocations[0]
        ).id,
      )
    }
  }, [filteredLocations, selectedLocationId])

  const selectedLocation =
    filteredLocations.find((location) => location.id === selectedLocationId) ?? null
  const filtersAreActive =
    searchQuery.trim() !== '' || riskFilter !== 'ALL' || divisionFilter !== 'ALL'

  const locationAlerts = useMemo(() => {
    if (!selectedLocation || !publicFeed.data) return []
    return publicFeed.data.filter(
      (alert) => alert.location_id === selectedLocation.apiId,
    )
  }, [publicFeed.data, selectedLocation])

  const clearFilters = () => {
    setSearchQuery('')
    setRiskFilter('ALL')
    setDivisionFilter('ALL')
  }

  return (
    <div className="weather-map-page page-stack">
      <PageHeader
        eyebrow="National monitoring view"
        title="Weather monitoring & flood mapping"
        description="Explore monitored Fiji locations, flood risk predictions and stored weather records."
      />

      <SyntheticReplayPanel />

      {publicFeed.error && (
        <Alert tone="error">
          Approved alerts shown here may be out of date. {publicFeed.error}
        </Alert>
      )}

      <section className="map-toolbar" aria-label="Map search and filters">
        <label className="map-search" htmlFor="location-search">
          <span>Find a monitored location</span>
          <div className="map-search__field">
            <span aria-hidden="true">⌕</span>
            <input
              id="location-search"
              type="search"
              value={searchQuery}
              placeholder="Search Suva, Nadi, Western Division…"
              autoComplete="off"
              disabled={!isReady}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </div>
        </label>

        <div className="risk-filter">
          <span id="risk-filter-label">Filter by risk level</span>
          <div
            className="risk-filter__options"
            role="group"
            aria-labelledby="risk-filter-label"
          >
            {RISK_FILTERS.map((filter) => {
              const count = locations.filter((location) =>
                matchesRiskFilter(location, filter.value),
              ).length

              return (
                <button
                  key={filter.value}
                  type="button"
                  className={`risk-filter__button${
                    riskFilter === filter.value ? ' is-active' : ''
                  }`}
                  aria-pressed={riskFilter === filter.value}
                  disabled={!isReady}
                  onClick={() => setRiskFilter(filter.value)}
                >
                  {filter.label}
                  <span>{isReady ? count : '–'}</span>
                </button>
              )
            })}
          </div>
        </div>

        <div className="risk-filter">
          <span id="division-filter-label">Filter by division</span>
          <div
            className="risk-filter__options"
            role="group"
            aria-labelledby="division-filter-label"
          >
            <button
              type="button"
              className={`risk-filter__button${
                divisionFilter === 'ALL' ? ' is-active' : ''
              }`}
              aria-pressed={divisionFilter === 'ALL'}
              disabled={!isReady}
              onClick={() => setDivisionFilter('ALL')}
            >
              All divisions
              <span>{isReady ? locations.length : '–'}</span>
            </button>
            {divisionOptions.map((code) => {
              const count = locations.filter((location) =>
                matchesDivisionFilter(location, code),
              ).length

              return (
                <button
                  key={code}
                  type="button"
                  className={`risk-filter__button${
                    divisionFilter === code ? ' is-active' : ''
                  }`}
                  aria-pressed={divisionFilter === code}
                  disabled={!isReady}
                  onClick={() => setDivisionFilter(code)}
                >
                  {divisionShortLabel(code)}
                  <span>{isReady ? count : '–'}</span>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      <div className="weather-map-layout">
        <section
          className="weather-map-card"
          aria-labelledby="map-results-title"
          aria-busy={status === 'loading'}
        >
          <header className="weather-map-card__header">
            <div>
              <span>Monitored locations</span>
              <h2 id="map-results-title">
                {isReady
                  ? `${filteredLocations.length} ${
                      filteredLocations.length === 1 ? 'location' : 'locations'
                    } shown`
                  : 'Fiji map'}
              </h2>
            </div>
            {isReady && filtersAreActive && (
              <button type="button" className="map-clear-button" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </header>

          {status === 'loading' && (
            <div className="weather-map-empty weather-map-empty--loading" role="status">
              <span className="weather-map-empty__mark" aria-hidden="true">
                ⟳
              </span>
              <h2>Loading monitored locations…</h2>
              <p>Fetching locations and the latest flood-risk predictions.</p>
            </div>
          )}

          {status === 'error' && (
            <div className="weather-map-empty" role="alert">
              <span className="weather-map-empty__mark" aria-hidden="true">!</span>
              <h2>Locations could not be loaded</h2>
              <p>{error}</p>
              <button type="button" className="map-clear-button" onClick={retry}>
                Try again
              </button>
            </div>
          )}

          {hasNoLocations && (
            <div className="weather-map-empty" role="status">
              <span className="weather-map-empty__mark" aria-hidden="true">0</span>
              <h2>No monitored locations yet</h2>
              <p>Locations will appear here once they have been set up.</p>
            </div>
          )}

          {isReady && !hasNoLocations && (
            <WeatherMap
              locations={filteredLocations}
              selectedLocationId={selectedLocationId}
              onSelectLocation={setSelectedLocationId}
            />
          )}

          {filteredLocations.length > 0 && (
            <div className="map-location-list" aria-label="Visible monitored locations">
              {locationGroups.map((group) => (
                <Fragment key={group.label}>
                  <h3 className="map-location-group">{group.label}</h3>
                  {group.locations.map((location) => (
                    <button
                      key={location.id}
                      type="button"
                      className={`map-location-button${
                        location.id === selectedLocationId ? ' is-selected' : ''
                      }`}
                      aria-pressed={location.id === selectedLocationId}
                      onClick={() => setSelectedLocationId(location.id)}
                    >
                      <span className="map-location-button__copy">
                        <strong>{location.name}</strong>
                        <small>{location.division}</small>
                      </span>
                      <RiskPill risk={location.riskLevel} compact />
                    </button>
                  ))}
                </Fragment>
              ))}
            </div>
          )}
        </section>

        {isReady ? (
          <LocationDetailCard
            location={selectedLocation}
            activeAlerts={locationAlerts}
          />
        ) : (
          <aside className="location-detail-card location-detail-card--empty">
            <span className="location-detail-card__empty-mark" aria-hidden="true">⌖</span>
            <h2>Location details</h2>
            <p>
              {status === 'loading'
                ? 'Details will appear once locations have loaded.'
                : 'Details are unavailable until locations can be loaded.'}
            </p>
          </aside>
        )}
      </div>

      <p className="weather-map-disclaimer">
        Sample risks are labelled test data and weather observations may be
        synthetic research data. Always follow current official Fiji
        Meteorological Service warnings and emergency instructions.
      </p>
    </div>
  )
}
