import { useEffect, useMemo, useState } from 'react'
import { LocationDetailCard } from '../components/map/LocationDetailCard'
import { WeatherMap } from '../components/map/WeatherMap'
import { RiskPill } from '../components/pills/DataPill'
import { PageHeader } from '../components/layout/PageHeader'
import { useMapLocations } from '../locations/useMapLocations'
import type { MapLocation } from '../types/location'
import type { RiskLevel } from '../types/prototype'
import { SyntheticReplayPanel } from '../components/research/SyntheticReplayPanel'

type RiskFilter = 'ALL' | RiskLevel | 'NONE'

const RISK_FILTERS: Array<{ value: RiskFilter; label: string }> = [
  { value: 'ALL', label: 'All risks' },
  { value: 'LOW', label: 'Low' },
  { value: 'MODERATE', label: 'Moderate' },
  { value: 'HIGH', label: 'High' },
  { value: 'VERY_HIGH', label: 'Very high' },
  { value: 'NONE', label: 'No prediction' },
]

function matchesRiskFilter(location: MapLocation, filter: RiskFilter) {
  if (filter === 'ALL') return true
  if (filter === 'NONE') return location.riskLevel === null
  return location.riskLevel === filter
}

export function WeatherMapPage() {
  const { status, error, locations, retry } = useMapLocations()
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('ALL')
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null)

  const isReady = status === 'ready'
  const hasNoLocations = isReady && locations.length === 0

  const filteredLocations = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()

    return locations.filter((location) => {
      const matchesSearch =
        !normalizedQuery ||
        location.name.toLowerCase().includes(normalizedQuery) ||
        location.division.toLowerCase().includes(normalizedQuery)

      return matchesSearch && matchesRiskFilter(location, riskFilter)
    })
  }, [locations, riskFilter, searchQuery])

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
  const filtersAreActive = searchQuery.trim() !== '' || riskFilter !== 'ALL'

  const clearFilters = () => {
    setSearchQuery('')
    setRiskFilter('ALL')
  }

  return (
    <div className="weather-map-page page-stack">
      <PageHeader
        eyebrow="National monitoring view"
        title="Weather & flood-risk map"
        description="Explore monitored Fiji locations with labelled sample flood risks and prototype weather observations."
      />

      <SyntheticReplayPanel />

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
              {filteredLocations.map((location) => (
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
            </div>
          )}
        </section>

        {isReady ? (
          <LocationDetailCard location={selectedLocation} />
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
        Sample risks are labelled test data and weather observations are illustrative.
        Always follow current official Fiji Meteorological Service warnings and
        emergency instructions.
      </p>
    </div>
  )
}
