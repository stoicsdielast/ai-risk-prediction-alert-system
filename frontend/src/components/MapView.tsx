import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { latLngBounds } from "leaflet";
import "leaflet/dist/leaflet.css";

export type FloodLocation = {
  name: string;
  country: string;
  position: [number, number];
  risk: "Low" | "Moderate" | "Medium" | "High" | "Severe";
  color: string;
  history: string[];
  alerts: string[];
};

type MapViewProps = {
  locations: FloodLocation[];
  selectedLocation: string;
  onSelectLocation: (name: string) => void;
  includedCountries?: string[];
};

const defaultFijiBounds = latLngBounds([
  [-20.5, 176.0],
  [-14.0, 181.0],
]);

export default function MapView({
  locations,
  selectedLocation,
  onSelectLocation,
  includedCountries = ["Fiji"],
}: MapViewProps) {
  const visibleLocations = locations.filter((location) => includedCountries.includes(location.country));
  const activeLocation = visibleLocations.find((location) => location.name === selectedLocation) ?? visibleLocations[0] ?? locations[0];

  const bounds = visibleLocations.length > 0 ? latLngBounds(visibleLocations.map((location) => location.position)) : defaultFijiBounds;

  if (visibleLocations.length === 0) {
    return (
      <div className="map-shell">
        <div className="flex h-full items-center justify-center bg-slate-100 px-4 text-center text-sm font-medium text-slate-600">
          Map data unavailable. No included countries are currently available for display.
        </div>
      </div>
    );
  }

  return (
    <div className="map-shell">
      <MapContainer
        key={activeLocation.name}
        bounds={bounds}
        scrollWheelZoom={true}
        className="leaflet-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {visibleLocations.map((point) => {
          const isSelected = point.name === selectedLocation;

          return (
            <CircleMarker
              key={point.name}
              center={point.position}
              radius={isSelected ? (point.risk === "Severe" ? 16 : point.risk === "High" ? 14 : 12) : point.risk === "Severe" ? 14 : point.risk === "High" ? 12 : 10}
              eventHandlers={{
                click: () => onSelectLocation(point.name),
              }}
              pathOptions={{
                color: point.color,
                fillColor: point.color,
                fillOpacity: isSelected ? 0.9 : 0.65,
                weight: isSelected ? 3 : 2,
                opacity: isSelected ? 1 : 0.9,
              }}
            >
              <Popup>
                <div className="text-sm font-semibold text-sky-950">{point.name}</div>
                <div className="text-xs text-slate-600">Risk: {point.risk}</div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </div>
  );
}
