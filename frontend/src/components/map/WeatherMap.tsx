import { useEffect, useMemo, useRef, useState } from 'react'
import { divIcon, latLngBounds } from 'leaflet'
import {
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  useMap,
} from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { MapLocation } from '../../types/location'
import type { RiskLevel } from '../../types/prototype'
import { RiskPill } from '../pills/DataPill'

const FIJI_CENTRE: [number, number] = [-17.76, 178.35]

const RISK_LABELS: Record<RiskLevel, string> = {
  LOW: 'Low',
  MODERATE: 'Moderate',
  HIGH: 'High',
  VERY_HIGH: 'Very high',
}

interface WeatherMapProps {
  locations: MapLocation[]
  selectedLocationId: string | null
  onSelectLocation: (locationId: string) => void
}

interface MapViewportProps {
  locations: MapLocation[]
  selectedLocation: MapLocation | null
}

function riskDescription({ prediction }: MapLocation) {
  if (!prediction) return 'No prediction available'
  const description = `${RISK_LABELS[prediction.riskLevel]} flood risk`
  if (prediction.provenance === 'sample') return `${description} (sample)`
  if (prediction.provenance === 'synthetic') return `${description} (synthetic research)`
  return description
}

function markerIcon(riskLevel: RiskLevel | null, isSelected: boolean) {
  const riskClass = riskLevel?.toLowerCase().replace('_', '-') ?? 'none'

  return divIcon({
    className: 'weather-map-marker-shell',
    html: `<span class="weather-map-marker weather-map-marker--${riskClass}${
      isSelected ? ' is-selected' : ''
    }"><span class="weather-map-marker__pulse"></span><span class="weather-map-marker__core"></span></span>`,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
    tooltipAnchor: [0, -18],
  })
}

function MapViewport({ locations, selectedLocation }: MapViewportProps) {
  const map = useMap()
  const previousSelection = useRef(selectedLocation?.id)

  useEffect(() => {
    const selectionChanged =
      selectedLocation && previousSelection.current !== selectedLocation.id

    if (selectionChanged) {
      map.flyTo(
        [selectedLocation.latitude, selectedLocation.longitude],
        Math.max(map.getZoom(), 9),
        { duration: 0.65 },
      )
    } else if (!selectedLocation && locations.length > 0) {
      const bounds = latLngBounds(
        locations.map((location) => [location.latitude, location.longitude]),
      )
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 8 })
    }

    previousSelection.current = selectedLocation?.id
  }, [locations, map, selectedLocation])

  return null
}

export function WeatherMap({
  locations,
  selectedLocationId,
  onSelectLocation,
}: WeatherMapProps) {
  const selectedLocation =
    locations.find((location) => location.id === selectedLocationId) ?? null
  // Offline/blocked tiles produce repeated tileerrors with no successful
  // loads; a single transient error while the map still loads is not shown.
  const [tileErrors, setTileErrors] = useState(0)
  const [tilesLoaded, setTilesLoaded] = useState(0)
  const tilesUnavailable = tileErrors >= 3 && tilesLoaded === 0

  const markerIcons = useMemo(
    () =>
      new Map(
        locations.map((location) => [
          location.id,
          markerIcon(location.riskLevel, location.id === selectedLocationId),
        ]),
      ),
    [locations, selectedLocationId],
  )

  if (locations.length === 0) {
    return (
      <div className="weather-map-empty" role="status">
        <span className="weather-map-empty__mark" aria-hidden="true">0</span>
        <h2>No monitored locations match</h2>
        <p>Try a different location name or broaden the risk and division filters.</p>
      </div>
    )
  }

  return (
    <div
      className="weather-map-region"
      role="region"
      aria-label="Fiji monitored weather and flood-risk locations"
    >
      {tilesUnavailable && (
        <div className="weather-map-tile-notice" role="status">
          <strong>Map background unavailable.</strong> Map tiles failed to
          load, so the base map may appear blank. Location markers and the
          data below remain available.
        </div>
      )}

      <MapContainer
        center={FIJI_CENTRE}
        zoom={7}
        minZoom={6}
        maxZoom={13}
        scrollWheelZoom={false}
        className="weather-map-canvas"
        style={{ height: 'clamp(28rem, 64vh, 42rem)' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          eventHandlers={{
            tileerror: () => setTileErrors((count) => count + 1),
            tileload: () => setTilesLoaded((count) => count + 1),
          }}
        />

        {locations.map((location) => (
          <Marker
            key={location.id}
            position={[location.latitude, location.longitude]}
            icon={markerIcons.get(location.id)}
            title={`${location.name} — ${riskDescription(location)}`}
            riseOnHover
            eventHandlers={{
              click: () => onSelectLocation(location.id),
            }}
          >
            <Tooltip direction="top" opacity={1}>
              <span className="weather-map-tooltip">
                <strong>{location.name}</strong>
                <small>{riskDescription(location)}</small>
              </span>
            </Tooltip>
          </Marker>
        ))}

        <MapViewport
          locations={locations}
          selectedLocation={selectedLocation}
        />
      </MapContainer>

      <div className="weather-map-legend" aria-label="Flood-risk legend">
        <span className="weather-map-legend__label">Risk level</span>
        <div>
          <RiskPill risk="LOW" compact />
          <RiskPill risk="MODERATE" compact />
          <RiskPill risk="HIGH" compact />
          <RiskPill risk="VERY_HIGH" compact />
          <RiskPill risk={null} compact />
        </div>
      </div>
    </div>
  )
}
