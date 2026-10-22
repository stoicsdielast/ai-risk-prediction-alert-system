import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MapLocation } from '../../types/location'
import { WeatherMap } from './WeatherMap'

// Leaflet needs real layout, which jsdom does not provide; react-leaflet is
// replaced with stubs whose TileLayer replays scripted tile events.
const tileBehaviour = vi.hoisted(() => ({ errors: 0, loads: 0 }))

vi.mock('react-leaflet', async () => {
  const { useEffect, useRef } = await import('react')
  return {
    MapContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    TileLayer: ({
      eventHandlers,
    }: {
      eventHandlers?: Record<string, () => void>
    }) => {
      // Replay scripted tile events once on mount. Handlers are read through
      // a ref so the recreated object does not re-trigger the effect.
      const handlersRef = useRef(eventHandlers)
      handlersRef.current = eventHandlers
      useEffect(() => {
        for (let index = 0; index < tileBehaviour.errors; index += 1) {
          handlersRef.current?.tileerror?.()
        }
        for (let index = 0; index < tileBehaviour.loads; index += 1) {
          handlersRef.current?.tileload?.()
        }
      }, [])
      return null
    },
    Marker: ({ title }: { title?: string }) => (
      <span aria-label={title ?? 'marker'} />
    ),
    Tooltip: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    useMap: () => ({
      flyTo: vi.fn(),
      fitBounds: vi.fn(),
      getZoom: () => 7,
    }),
  }
})

const LOCATIONS: MapLocation[] = [
  {
    id: 'nadi',
    apiId: 1,
    name: 'Nadi',
    division: 'Western Division',
    latitude: -17.7765,
    longitude: 177.4356,
    riskLevel: 'HIGH',
    prediction: {
      riskLevel: 'HIGH',
      floodProbabilityPercent: 72,
      provenance: 'model',
      modelVersion: 'synthetic-fiji-v1-catboost__none',
      predictedAt: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    },
  },
]

function renderMap() {
  return render(
    <WeatherMap
      locations={LOCATIONS}
      selectedLocationId="nadi"
      onSelectLocation={() => {}}
    />,
  )
}

describe('WeatherMap', () => {
  beforeEach(() => {
    tileBehaviour.errors = 0
    tileBehaviour.loads = 0
  })

  it('renders the map region and legend without a tile notice when tiles load', () => {
    tileBehaviour.loads = 1

    renderMap()

    expect(
      screen.getByRole('region', {
        name: 'Fiji monitored weather and flood-risk locations',
      }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Flood-risk legend')).toBeInTheDocument()
    expect(screen.queryByText(/Map background unavailable/)).not.toBeInTheDocument()
  })

  it('shows a notice when repeated tile errors occur with no successful loads', async () => {
    tileBehaviour.errors = 3

    renderMap()

    expect(await screen.findByText(/Map background unavailable/)).toBeInTheDocument()
    expect(
      screen.getByText(/Location markers and the data below remain available/),
    ).toBeInTheDocument()
  })

  it('stays quiet when some tiles still load despite errors', () => {
    tileBehaviour.errors = 3
    tileBehaviour.loads = 1

    renderMap()

    expect(screen.queryByText(/Map background unavailable/)).not.toBeInTheDocument()
  })

  it('explains that no locations match and mentions both filters', () => {
    render(
      <WeatherMap
        locations={[]}
        selectedLocationId={null}
        onSelectLocation={() => {}}
      />,
    )

    expect(screen.getByText('No monitored locations match')).toBeInTheDocument()
    expect(
      screen.getByText(/broaden the risk and division filters/),
    ).toBeInTheDocument()
  })

  it('labels a model prediction without a sample or research suffix', () => {
    renderMap()

    expect(screen.getByLabelText('Nadi — High flood risk')).toBeInTheDocument()
  })

  it('suffixes sample and synthetic research predictions in marker titles', () => {
    const sample: MapLocation = {
      ...LOCATIONS[0],
      id: 'navua',
      name: 'Navua',
      prediction: {
        riskLevel: 'HIGH',
        floodProbabilityPercent: 70,
        provenance: 'sample',
        modelVersion: 'sample-demo-not-a-model-result',
        predictedAt: new Date().toISOString(),
      },
    }
    const synthetic: MapLocation = {
      ...LOCATIONS[0],
      id: 'suva',
      name: 'Suva',
      prediction: {
        riskLevel: 'HIGH',
        floodProbabilityPercent: 70,
        provenance: 'synthetic',
        modelVersion: 'synthetic-fiji-v1-catboost__none',
        predictedAt: new Date().toISOString(),
      },
    }

    render(
      <WeatherMap
        locations={[sample, synthetic]}
        selectedLocationId={null}
        onSelectLocation={() => {}}
      />,
    )

    expect(
      screen.getByLabelText('Navua — High flood risk (sample)'),
    ).toBeInTheDocument()
    expect(
      screen.getByLabelText('Suva — High flood risk (synthetic research)'),
    ).toBeInTheDocument()
  })
})
