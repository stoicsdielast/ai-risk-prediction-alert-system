CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    coordinates GEOGRAPHY(POINT, 4326),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE weather_records (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL,
    rainfall DECIMAL(10,2),
    temperature DECIMAL(5,2),
    humidity DECIMAL(5,2),
    river_level DECIMAL(10,2),
    recorded_at TIMESTAMP NOT NULL,

    CONSTRAINT fk_weather_location
        FOREIGN KEY (location_id)
        REFERENCES locations(id)
        ON DELETE CASCADE,

    CONSTRAINT unique_weather_record
        UNIQUE (location_id, recorded_at)
);
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL,
    risk_score DECIMAL(5,2) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_prediction_location
        FOREIGN KEY (location_id)
        REFERENCES locations(id)
        ON DELETE CASCADE,

    CONSTRAINT check_risk_level
        CHECK (
            risk_level IN (
                'LOW',
                'MODERATE',
                'HIGH',
                'VERY_HIGH'
            )
        ),

    CONSTRAINT unique_prediction_record
        UNIQUE (location_id, generated_at)
);


CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    location_id INTEGER NOT NULL,
    prediction_id INTEGER NOT NULL,
    message TEXT,
    severity VARCHAR(20),
    status VARCHAR(20) DEFAULT 'PENDING',
    suppression_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP,

    CONSTRAINT fk_alert_location
        FOREIGN KEY (location_id)
        REFERENCES locations(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_alert_prediction
        FOREIGN KEY (prediction_id)
        REFERENCES predictions(id)
        ON DELETE CASCADE,

    CONSTRAINT check_alert_status
        CHECK (
            status IN (
                'PENDING',
                'APPROVED',
                'SUPPRESSED',
                'RESOLVED'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_weather_location_time
ON weather_records (location_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_location_time
ON predictions (location_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_locations_coordinates
ON locations USING GIST (coordinates);