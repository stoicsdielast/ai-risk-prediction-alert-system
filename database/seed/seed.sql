INSERT INTO locations (name, latitude, longitude, coordinates)
VALUES
('Nadi', -17.800000, 177.416667, ST_SetSRID(ST_MakePoint(177.416667, -17.800000), 4326)::geography),
('Lautoka', -17.624167, 177.452778, ST_SetSRID(ST_MakePoint(177.452778, -17.624167), 4326)::geography),
('Ba', -17.533333, 177.683333, ST_SetSRID(ST_MakePoint(177.683333, -17.533333), 4326)::geography),
('Rakiraki', -17.423500, 178.023200, ST_SetSRID(ST_MakePoint(178.023200, -17.423500), 4326)::geography),
('Nausori', -18.024444, 178.545556, ST_SetSRID(ST_MakePoint(178.545556, -18.024444), 4326)::geography),
('Suva', -18.133333, 178.433333, ST_SetSRID(ST_MakePoint(178.433333, -18.133333), 4326)::geography),
('Navua', -18.220000, 178.180000, ST_SetSRID(ST_MakePoint(178.180000, -18.220000), 4326)::geography),
('Sigatoka', -18.141667, 177.508333, ST_SetSRID(ST_MakePoint(177.508333, -18.141667), 4326)::geography),
('Labasa', -16.433333, 179.366667, ST_SetSRID(ST_MakePoint(179.366667, -16.433333), 4326)::geography),
('Savusavu', -16.746667, 179.358333, ST_SetSRID(ST_MakePoint(179.358333, -16.746667), 4326)::geography)
ON CONFLICT (name) DO NOTHING;

-- Prototype weather data for demonstration/testing only
INSERT INTO weather_records
(location_id, rainfall, temperature, humidity, river_level, recorded_at)
VALUES
(1, 12.50, 29.00, 72.00, 1.20, '2026-08-31 12:00:00'),
(2, 35.00, 28.50, 80.00, 1.80, '2026-08-31 12:00:00'),
(3, 85.00, 27.50, 88.00, 3.10, '2026-08-31 12:00:00'),
(4, 120.00, 27.00, 92.00, 4.20, '2026-08-31 12:00:00'),
(5, 65.00, 28.00, 86.00, 2.70, '2026-08-31 12:00:00'),
(6, 45.00, 28.50, 82.00, 2.00, '2026-08-31 12:00:00'),
(7, 95.00, 27.00, 90.00, 3.60, '2026-08-31 12:00:00'),
(8, 20.00, 29.00, 75.00, 1.40, '2026-08-31 12:00:00'),
(9, 55.00, 28.00, 84.00, 2.30, '2026-08-31 12:00:00'),
(10, 30.00, 28.50, 78.00, 1.60, '2026-08-31 12:00:00')
ON CONFLICT (location_id, recorded_at) DO NOTHING;

-- Prototype prediction data for demonstration/testing only
INSERT INTO predictions
(location_id, risk_score, risk_level, generated_at)
VALUES
(1, 20.00, 'LOW', '2026-08-31 12:05:00'),
(2, 42.00, 'MODERATE', '2026-08-31 12:05:00'),
(3, 72.00, 'HIGH', '2026-08-31 12:05:00'),
(4, 91.00, 'VERY_HIGH', '2026-08-31 12:05:00'),
(5, 65.00, 'HIGH', '2026-08-31 12:05:00'),
(6, 48.00, 'MODERATE', '2026-08-31 12:05:00'),
(7, 88.00, 'VERY_HIGH', '2026-08-31 12:05:00'),
(8, 25.00, 'LOW', '2026-08-31 12:05:00'),
(9, 55.00, 'MODERATE', '2026-08-31 12:05:00'),
(10, 35.00, 'LOW', '2026-08-31 12:05:00')
ON CONFLICT (location_id, generated_at) DO NOTHING;