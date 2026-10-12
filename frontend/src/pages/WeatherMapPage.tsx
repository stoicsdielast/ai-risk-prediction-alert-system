import { useEffect, useMemo, useState } from 'react'
import { LocationDetailCard } from '../components/map/LocationDetailCard'
import { WeatherMap } from '../components/map/WeatherMap'
import { RiskPill } from '../components/pills/DataPill'
import { PageHeader } from '../components/layout/PageHeader'
import { usePrototypeData } from '../prototype/usePrototypeData'
import type { RiskLevel } from '../types/prototype'

type RiskFilter = 'ALL' | RiskLevel

const RISK_FILTERS: Array<{ value: RiskFilter; label: string }> = [
  { value: 'ALL', label: 'All risks' },
  { value: 'LOW', label: 'Low' },
  { value: 'MODERATE', label: 'Moderate' },
  { value: 'HIGH', label: 'High' },
  { value: 'VERY_HIGH', label: 'Very high' },
]

export function WeatherMapPage() {
  const { locations } = usePrototypeData()
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('ALL')
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(
    () =>
      locations.find((location) => location.riskLevel === 'VERY_HIGH')?.id ??
      locations[0]?.id ??
      null,
  )

  const filteredLocations = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()

    return locations.filter((location) => {
      const matchesSearch =
        !normalizedQuery ||
        location.name.toLowerCase().includes(normalizedQuery) ||
        location.division.toLowerCase().includes(normalizedQuery)
      const matchesRisk =
        riskFilter === 'ALL' || location.riskLevel === riskFilter

      return matchesSearch && matchesRisk
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
    if (!selectionIsVisible) setSelectedLocationId(filteredLocations[0].id)
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
        description="Explore prototype weather observations and AI flood-risk signals across monitored Fiji locations."
      />

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
              const count =
                filter.value === 'ALL'
                  ? locations.length
                  : locations.filter(
                      (location) => location.riskLevel === filter.value,
                    ).length

              return (
                <button
                  key={filter.value}
                  type="button"
                  className={`risk-filter__button${
                    riskFilter === filter.value ? ' is-active' : ''
                  }`}
                  aria-pressed={riskFilter === filter.value}
                  onClick={() => setRiskFilter(filter.value)}
                >
                  {filter.label}
                  <span>{count}</span>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      <div className="weather-map-layout">
        <section className="weather-map-card" aria-labelledby="map-results-title">
          <header className="weather-map-card__header">
            <div>
              <span>Prototype map view</span>
              <h2 id="map-results-title">
                {filteredLocations.length}{' '}
                {filteredLocations.length === 1 ? 'location' : 'locations'} shown
              </h2>
            </div>
            {filtersAreActive && (
              <button type="button" className="map-clear-button" onClick={clearFilters}>
                Clear filters
              </button>
            )}
          </header>

          <WeatherMap
            locations={filteredLocations}
            selectedLocationId={selectedLocationId}
            onSelectLocation={setSelectedLocationId}
          />

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

        <LocationDetailCard location={selectedLocation} />
      </div>

      <p className="weather-map-disclaimer">
        Prototype weather and prediction data are illustrative. Always follow current
        official Fiji Meteorological Service warnings and emergency instructions.
      </p>
    </div>
  )
}
