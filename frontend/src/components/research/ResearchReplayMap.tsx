import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { ReplayExample, ResearchResult } from '../../api/predictions'

export function ResearchReplayMap({ example, result }: { example: ReplayExample; result: ResearchResult | null }) {
  const position: [number, number] = [example.station.latitude, example.station.longitude]
  const color = result?.presentation_tier === 'VERY_HIGH' || result?.presentation_tier === 'HIGH' ? '#c24135' : '#217a76'
  return (
    <div aria-label="Bangladesh historical research map" className="research-replay-map">
      <MapContainer key={example.id} center={position} zoom={7} scrollWheelZoom={false} style={{ height: 260, width: '100%' }}>
        <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <CircleMarker center={position} pathOptions={{ color }} radius={12}>
          <Tooltip permanent>{example.station.name}, Bangladesh · {example.feature_date}<br />{result?.presentation_tier ?? 'Replay not run'} · Research only</Tooltip>
        </CircleMarker>
      </MapContainer>
    </div>
  )
}
