"""Reproducible spatial weather and hidden-state hydrology simulator."""
import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ml.train import write_json

NOTICE = "Synthetic Data — Research Demonstration. Generated simulation, not official Fiji MET readings or validated flood forecasts."
REGISTRY = Path(__file__).with_name("locations.csv")
RAW_COLUMNS = ["rainfall_mm", "temperature_c", "humidity_pct", "pressure_hpa", "wind_speed_ms", "wind_direction_deg",
               "soil_moisture_pct", "river_level_m", "river_discharge_m3s", "upstream_rainfall_mm", "coastal_tide_m"]
GEO_COLUMNS = ["elevation_m", "catchment_area_km2", "slope_pct", "drainage_capacity_mm_h", "river_proximity_km", "coastal_influence"]


@dataclass(frozen=True)
class SimulationConfig:
    start: str = "2021-01-01"
    end: str = "2025-12-31"
    seed: int = 314
    frequency: str = "1h"
    storm_scale: float = 1.
    drainage_scale: float = 1.
    missing_rate: float = .006
    scenario: str = "realistic"
    dataset_version: str = "synthetic-fiji-v1"


@dataclass(frozen=True)
class ScenarioSettings:
    """Scenario knobs for the v3 study.

    Defaults are numerically identical to the original v1 simulator, so
    `scenario="realistic"` reproduces v1 behaviour bit-for-bit. Every field is
    a documented simulator assumption; none of them is derived from labels.
    """
    name: str = "realistic"
    purpose: str = "v1-style challenging conditions: rainfall variability, imperfect sensors, drainage and saturation differences"
    jitter_seed: int = 0
    rain_threshold_noise: float = .3
    rain_gamma_shape: float = 1.2
    rain_gamma_scale: float = .55
    met_noise: float = 1.
    storm_duration_scale: float = 1.
    storm_amplitude_scale: float = 1.
    storm_gap_scale: float = 1.
    footprint_scale: float = 1.
    extreme_prob_wet: float = .2
    extreme_prob_dry: float = .06
    ood_profile_prob: float = 0.
    sensor_noise: float = 1.
    rain_obs_noise: float = 0.
    sensor_drift: float = 0.
    sensor_spike_prob: float = 0.
    missing_scale: float = 1.
    burst_missing_prob: float = 0.
    drainage_scale: float = 1.
    drainage_heterogeneity: float = 0.
    blockage_noise: float = 1.
    capacity_tide_coef: float = .18
    drainage_tide_coef: float = .15
    catchment_jitter: float = 0.


SCENARIOS = {
    "controlled": ScenarioSettings(
        name="controlled",
        purpose="coherent rainfall-runoff signal: low sensor noise, low missingness, stable catchment blockage, weak coastal interference",
        rain_threshold_noise=.12, met_noise=.5,
        extreme_prob_wet=.16, extreme_prob_dry=.05, storm_amplitude_scale=1.25,
        sensor_noise=.35, missing_scale=.17,
        blockage_noise=.2, capacity_tide_coef=.12, drainage_tide_coef=.09),
    "realistic": ScenarioSettings(),
    "stress": ScenarioSettings(
        name="stress",
        purpose="out-of-distribution storms, noisy and bursty sensors, unusual rainfall distributions, altered catchments and stronger coastal backwater",
        jitter_seed=90210,
        rain_threshold_noise=.5, rain_gamma_shape=.75, rain_gamma_scale=.8, met_noise=1.6,
        storm_duration_scale=1.2, storm_amplitude_scale=1., storm_gap_scale=.7, footprint_scale=1.4,
        extreme_prob_wet=.3, extreme_prob_dry=.12, ood_profile_prob=.45,
        sensor_noise=2., rain_obs_noise=.8, sensor_drift=.01, sensor_spike_prob=.01,
        missing_scale=8., burst_missing_prob=.03,
        drainage_scale=1., drainage_heterogeneity=.35, blockage_noise=3.,
        capacity_tide_coef=.32, drainage_tide_coef=.29, catchment_jitter=.25),
}


def scenario_settings(name):
    if name not in SCENARIOS:
        raise ValueError(f"Unknown scenario {name!r}; expected one of {sorted(SCENARIOS)}")
    return SCENARIOS[name]


def characteristics(registry, settings=None):
    """Fixed assumed geography, independent of weather seed and labels."""
    settings = SCENARIOS["realistic"] if settings is None else settings
    rng = np.random.default_rng(1314)
    loc = registry.copy()
    n = len(loc)
    loc["elevation_m"] = rng.uniform(4, 70, n).round(2)
    loc["catchment_area_km2"] = rng.uniform(80, 650, n).round(2)
    loc["slope_pct"] = rng.uniform(1, 12, n).round(2)
    loc["drainage_capacity_mm_h"] = rng.uniform(3, 7, n).round(2)
    loc["river_proximity_km"] = rng.uniform(.1, 2.5, n).round(2)
    loc["coastal_influence"] = np.where(loc.slug.isin(["nausori", "ba", "labasa", "navua"]), .2, .8)
    if settings.catchment_jitter:
        # Dedicated RNG derived from the scenario seed: never touches the weather
        # stream and never reads labels, so jitter cannot encode targets.
        jr = np.random.default_rng(settings.jitter_seed)
        loc["catchment_area_km2"] = (loc.catchment_area_km2 *
                                     (1 + jr.normal(0, settings.catchment_jitter, n))).round(2)
        loc["drainage_capacity_mm_h"] = (loc.drainage_capacity_mm_h *
                                         (1 + jr.normal(0, settings.catchment_jitter, n))).clip(1.5, None).round(2)
        loc["slope_pct"] = (loc.slope_pct * (1 + jr.normal(0, settings.catchment_jitter, n))).clip(.5, None).round(2)
    return loc


def storm_profile(length, style, settings):
    """Rainfall time profile for one storm; style -1 is the original sinusoid."""
    if style < 0:
        return np.sin(np.linspace(0, np.pi, length))**1.6
    u = np.linspace(0., 1., length)
    if style == 0:      # flat-top plateau: long sustained burst
        return np.clip(np.minimum(u, 1 - u) / .18, 0, 1)**1.1
    if style == 1:      # multi-peak system: unusual rainfall distribution
        base = np.sin(np.pi * u)**1.2
        return np.clip(base * (.55 + .45 * np.cos(2 * np.pi * u * 1.5 + np.pi)), 0., None)
    return np.clip(np.minimum(u, 1 - u) * 10, 0, 1)   # abrupt onset and decay


def label_events(times, location_id, events, active, dt):
    n = len(times)
    frame = pd.DataFrame({"timestamp": times, "location_id": location_id, "flood_occurred": active.astype("int8")})
    starts = pd.DatetimeIndex(events.event_start) if len(events) else pd.DatetimeIndex([], tz="UTC")
    for horizon in [24, 48, 72]:
        target = np.zeros(n, dtype=np.int8)
        # Strictly future onset; an event at t is already active, not a forecast.
        for onset in starts:
            target[(times < onset) & (times >= onset-pd.Timedelta(hours=horizon)) & ~active] = 1
        values = pd.array(target, dtype="Int8")
        values[times > times[-1]-pd.Timedelta(hours=horizon)] = pd.NA
        frame[f"flood_within_{horizon}h"] = values
    frame["forecast_eligible"] = ~active & frame.flood_within_24h.notna().to_numpy()
    return frame


def simulate(config, registry=None):
    registry = pd.read_csv(REGISTRY) if registry is None else registry.copy()
    assert registry.location_id.is_unique and registry.slug.is_unique
    settings = scenario_settings(config.scenario)
    dt = pd.Timedelta(config.frequency).total_seconds()/3600
    if dt not in [1, 2, 3, 6]: raise ValueError("Frequency must be 1h, 2h, 3h or 6h")
    times = pd.date_range(config.start, pd.Timestamp(config.end)+pd.Timedelta(days=1), freq=config.frequency, inclusive="left", tz="UTC")
    if len(times) < 80/dt: raise ValueError("At least 80 hours are required")
    rng = np.random.default_rng(config.seed); loc = characteristics(registry, settings)
    n, m = len(times), len(loc)
    wet = np.isin(times.month, [11, 12, 1, 2, 3, 4])
    xy = np.column_stack([loc.longitude.to_numpy()*np.cos(np.deg2rad(-18))*111, loc.latitude.to_numpy()*111])
    distances = np.sqrt(((xy[:, None]-xy[None, :])**2).sum(axis=2))
    spatial = np.linalg.cholesky(np.exp(-distances/180)+np.eye(m)*.08)
    noise = rng.normal(size=(n, m)) @ spatial.T
    cloud = np.zeros((n, m))
    for t in range(1, n): cloud[t] = .92**dt*cloud[t-1] + np.sqrt(1-.92**(2*dt))*noise[t]
    rainfall = rng.gamma(settings.rain_gamma_shape, settings.rain_gamma_scale, (n, m))*((cloud+rng.normal(size=(n, m))*settings.rain_threshold_noise) > np.where(wet[:, None], .65, 1.2))*dt
    storm = np.zeros((n, m)); scenario = np.full(n, "background", dtype=object); scenarios = []
    cursor = int(72/dt)
    while cursor < n-72/dt:
        duration = int(rng.integers(30, int(round(97*settings.storm_duration_scale)))/dt)
        end = min(cursor+duration, n)
        center = xy[rng.integers(m)] + rng.normal(0, 40, 2)
        width = rng.uniform(100, 300)*settings.footprint_scale
        footprint = np.exp(-((xy-center)**2).sum(axis=1)/(2*width**2))
        extreme = bool(rng.random() < (settings.extreme_prob_wet if wet[cursor] else settings.extreme_prob_dry))
        amplitude = rng.uniform(7, 15) if extreme else rng.uniform(1.5, 4.5)
        style = -1
        if settings.ood_profile_prob and rng.random() < settings.ood_profile_prob:
            style = int(rng.integers(3))
        profile = storm_profile(end-cursor, style, settings)
        storm[cursor:end] += profile[:, None]*footprint*amplitude*config.storm_scale*settings.storm_amplitude_scale
        sid = f"seed{config.seed}-storm{len(scenarios)+1:04d}"
        scenario[cursor:min(n, end+int(96/dt))] = sid
        scenarios.append(dict(scenario_id=sid, start=times[cursor], end=times[end-1], cyclone_like=extreme,
                              peak_rain_rate_mm_h=amplitude*config.storm_scale*settings.storm_amplitude_scale,
                              profile_style=style))
        cursor = end + int(rng.uniform(180, 300)*settings.storm_gap_scale/dt if wet[cursor] else rng.uniform(260, 460)*settings.storm_gap_scale/dt)
    rainfall += storm*dt*(.9+.2*rng.random((n, m)))
    upstream = np.maximum(0, rainfall*(.85+.3*rng.random((n, m))) + .15*storm*dt)
    seasonal = np.cos(2*np.pi*(times.dayofyear.to_numpy()-35)/365.25)
    temperature = 25.5 + 2*seasonal[:, None]+2*np.sin(2*np.pi*(times.hour.to_numpy()-8)/24)[:, None]-.07*storm+noise*.45*settings.met_noise
    humidity = np.clip(72+10*cloud+storm*1.3, 35, 100)
    pressure = np.clip(1013-1.4*storm-2.5*cloud+rng.normal(0,.4,(n,m)), 965, 1030)
    wind = np.clip(3+.8*storm+np.abs(noise)*1.3, 0, 55)
    direction = (110+cloud*30+np.arange(n)[:,None]*dt*.2+rng.normal(0,10,(n,m)))%360
    tide = (np.sin(np.arange(n)[:,None]*dt*2*np.pi/12.42)*.65 + .25*np.sin(np.arange(n)[:,None]*dt*2*np.pi/(24*14)))*loc.coastal_influence.to_numpy()
    soil = np.full(m,.45); fast = np.zeros(m); slow = np.zeros(m); storage = np.zeros(m); blockage = np.zeros(m)
    # Hidden channel geometry/vulnerability is never exported as a model feature.
    bank = loc.catchment_area_km2.to_numpy()*rng.uniform(.65,1.05,m)+30
    flood_depth_capacity = rng.uniform(2.5,5,m)*(1+loc.elevation_m.to_numpy()/120)
    drainage_factor = np.ones(m)
    if settings.drainage_heterogeneity:
        drainage_factor = 1+rng.uniform(-settings.drainage_heterogeneity, settings.drainage_heterogeneity, m)
    effective_drainage = config.drainage_scale*settings.drainage_scale
    active = np.zeros((n,m),dtype=bool); moist = np.zeros((n,m)); discharge = np.zeros((n,m)); level = np.zeros((n,m)); depths=np.zeros((n,m))
    was_active = np.zeros(m,dtype=bool)
    delay = np.maximum(1, (loc.river_proximity_km.to_numpy()*2+3)/dt).astype(int)
    for t in range(n):
        soil = np.clip(soil + rainfall[t]/140 - dt*(.0018+.00008*np.maximum(temperature[t]-22,0)) - dt*.004*np.maximum(soil-.7,0), .08, 1)
        routed = upstream[np.maximum(0,t-delay),np.arange(m)]/dt
        inflow = .278*loc.catchment_area_km2.to_numpy()*routed*(.08+.72*soil**2)
        fast += (1-np.exp(-dt/8))*(inflow-fast)
        slow += (1-np.exp(-dt/48))*(inflow-slow)
        q = 8+.02*loc.catchment_area_km2.to_numpy()+.75*fast+.25*slow
        blockage = .995**dt*blockage + rng.normal(0,.003*settings.blockage_noise*np.sqrt(dt),m)
        capacity = bank*(1-np.clip(blockage,-.15,.2))*(1-settings.capacity_tide_coef*np.maximum(tide[t],0))
        river_excess = np.maximum(q-capacity,0)/(.278*loc.catchment_area_km2.to_numpy())
        drainage = loc.drainage_capacity_mm_h.to_numpy()*drainage_factor*effective_drainage*(1-.65*soil)*(1-settings.drainage_tide_coef*np.maximum(tide[t],0))
        pluvial_excess = np.maximum(rainfall[t]/dt-drainage,0)*.22
        storage = storage*np.exp(-dt/12) + dt*(river_excess*.8+pluvial_excess)
        was_active = np.where(was_active, storage > flood_depth_capacity*.45, storage > flood_depth_capacity)
        active[t] = was_active; moist[t] = soil*100; discharge[t] = q
        level[t] = .4+(q/(loc.catchment_area_km2.to_numpy()+20))**.6*2.5+.12*tide[t]
        depths[t] = storage/flood_depth_capacity
    observations, labels, events = [], [], []
    effective_missing = config.missing_rate*settings.missing_scale
    for j, item in loc.iterrows():
        starts = np.flatnonzero(active[:,j] & ~np.r_[False,active[:-1,j]])
        ends = np.flatnonzero(active[:,j] & ~np.r_[active[1:,j],False])
        local_events=[]
        for k,(a,b) in enumerate(zip(starts,ends)):
            severity = "extreme" if depths[a:b+1,j].max()>3 else "severe" if depths[a:b+1,j].max()>1.8 else "moderate"
            event=dict(event_id=f"seed{config.seed}-loc{item.location_id}-event{k+1:04d}", location_id=int(item.location_id),
                event_start=times[a], event_end=times[b]+pd.Timedelta(hours=dt), severity=severity, duration_hours=(b-a+1)*dt,
                max_river_discharge_m3s=float(discharge[a:b+1,j].max()), max_river_level_m=float(level[a:b+1,j].max()),
                max_soil_moisture_pct=float(moist[a:b+1,j].max()), scenario_id=scenario[a], source_type="synthetic")
            events.append(event);local_events.append(event)
        d=pd.DataFrame({"timestamp":times,"location_id":int(item.location_id),"rainfall_mm":rainfall[:,j],"temperature_c":temperature[:,j],
            "humidity_pct":humidity[:,j],"pressure_hpa":pressure[:,j],"wind_speed_ms":wind[:,j],"wind_direction_deg":direction[:,j],
            "soil_moisture_pct":moist[:,j]+rng.normal(0,1.2*settings.sensor_noise,n),"river_level_m":level[:,j]+rng.normal(0,.04*settings.sensor_noise,n),
            "river_discharge_m3s":discharge[:,j]*np.exp(rng.normal(0,.04*settings.sensor_noise,n)),"upstream_rainfall_mm":upstream[:,j],"coastal_tide_m":tide[:,j]+rng.normal(0,.03*settings.sensor_noise,n)})
        if settings.rain_obs_noise:
            # Sensor error only: the hidden forcing used by the soil bucket is untouched.
            d["rainfall_mm"] = (d.rainfall_mm + rng.normal(0, settings.rain_obs_noise, n)).clip(lower=0)
        if settings.sensor_drift or settings.sensor_spike_prob:
            if settings.sensor_drift:
                d["river_level_m"] = d.river_level_m + np.cumsum(rng.normal(0, settings.sensor_drift, n))
                d["soil_moisture_pct"] = d.soil_moisture_pct + np.cumsum(rng.normal(0, settings.sensor_drift*4, n))
            if settings.sensor_spike_prob:
                spike = rng.random(n) < settings.sensor_spike_prob
                if spike.any():
                    d.loc[spike, "river_level_m"] += rng.normal(0, .35, int(spike.sum()))
                    d.loc[spike, "rainfall_mm"] += np.abs(rng.normal(0, 6, int(spike.sum())))
        d.soil_moisture_pct=d.soil_moisture_pct.clip(0,100);d.river_level_m=d.river_level_m.clip(lower=0)
        for column in RAW_COLUMNS:
            missing=rng.random(n)<effective_missing
            d.loc[missing,column]=np.nan
        if settings.burst_missing_prob:
            # Contiguous sensor outages: several-hour gaps a 6 h fill cannot hide.
            for column in RAW_COLUMNS:
                for start_hour in np.flatnonzero(rng.random(int(n)) < settings.burst_missing_prob*dt/24):
                    length = int(rng.integers(6, 37)/dt)
                    d.iloc[start_hour:min(n, start_hour+length), d.columns.get_loc(column)] = np.nan
        d["source_type"]="synthetic";observations.append(d)
        labels.append(label_events(times,int(item.location_id),pd.DataFrame(local_events),active[:,j],dt))
    return loc,pd.concat(observations,ignore_index=True),pd.DataFrame(events),pd.concat(labels,ignore_index=True),pd.DataFrame(scenarios)


def save_dataset(out, config, dataset_version=None):
    if out.exists(): raise ValueError("Dataset directory exists; choose a new version/output")
    settings = scenario_settings(config.scenario)
    version = dataset_version or config.dataset_version
    loc,obs,events,labels,scenarios=simulate(config)
    out.mkdir(parents=True)
    loc.to_csv(out/"locations.csv",index=False);obs.to_parquet(out/"weather_observations.parquet",index=False)
    obs.groupby("location_id",sort=True).head(24).to_csv(out/"weather_observations_sample.csv",index=False)
    events.to_csv(out/"flood_events.csv",index=False);labels.to_parquet(out/"training_labels.parquet",index=False)
    scenarios.to_csv(out/"simulation_scenarios.csv",index=False)
    eligible=labels[labels.forecast_eligible]
    distribution={"observations":len(obs),"locations":len(loc),"flood_events":len(events),"currently_flooded_observations":int(labels.flood_occurred.sum()),
        "eligible_observations":len(eligible),"positive_labels":int(eligible.flood_within_24h.sum()),
        "negative_labels":int(eligible.flood_within_24h.eq(0).sum()),"prevalence":float(eligible.flood_within_24h.mean()),
        "unknown_24h_horizon":int(labels.flood_within_24h.isna().sum())}
    quality={"duplicate_keys":int(obs.duplicated(["location_id","timestamp"]).sum()),"unknown_location_ids":sorted(set(obs.location_id)-set(loc.location_id)),
        "missingness":obs[RAW_COLUMNS].isna().mean().to_dict(),"ranges":{c:[float(obs[c].min()),float(obs[c].max())] for c in RAW_COLUMNS},
        "continuous_timestamps":all(g.timestamp.diff().dropna().eq(pd.Timedelta(config.frequency)).all() for _,g in obs.groupby("location_id")),
        "location_ids_match_registry":sorted(obs.location_id.unique().tolist())==sorted(pd.read_csv(REGISTRY).location_id.tolist())}
    assert not quality["duplicate_keys"] and not quality["unknown_location_ids"] and quality["continuous_timestamps"] and quality["location_ids_match_registry"]
    hashes={}
    for p in sorted(out.iterdir()):
        with p.open('rb') as f: hashes[p.name]=hashlib.file_digest(f,"sha256").hexdigest()
    write_json(out/"dataset_metadata.json",{"dataset_version":version,"source_type":"synthetic","notice":NOTICE,"config":asdict(config),
        "scenario":config.scenario,"scenario_settings":asdict(settings),
        "timezone":"UTC","registry_sha256":hashlib.sha256(REGISTRY.read_bytes()).hexdigest(),"distribution":distribution,"quality":quality,
        "authentic_application_metadata":["location_id","slug","name","division","latitude","longitude"],"assumed_characteristics":GEO_COLUMNS,
        "units":{"rainfall_mm":"mm per observation interval","upstream_rainfall_mm":"mm per observation interval","temperature_c":"degrees Celsius",
                 "humidity_pct":"percent","pressure_hpa":"hPa","wind_speed_ms":"m/s","wind_direction_deg":"degrees clockwise from north",
                 "soil_moisture_pct":"percent relative saturation","river_level_m":"m above simulated datum","river_discharge_m3s":"m3/s",
                 "coastal_tide_m":"m relative to simulated mean sea level","elevation_m":"m","catchment_area_km2":"km2","slope_pct":"percent",
                 "drainage_capacity_mm_h":"mm/h","river_proximity_km":"km","coastal_influence":"unitless 0–1"},"file_sha256":hashes,
        "climate_reference":"https://www.met.gov.fj/media/climate_product_files/Fiji_Climate_Outlook_September_2025.pdf",
        "label_policy":"New onset strictly after t and <=t+24h; current floods excluded via forecast_eligible; incomplete future horizon nullable; event_end exclusive",
        "causal_chain":"rainfall -> soil moisture/infiltration -> fast and slow runoff -> river discharge/level -> channel storage -> flood onset",
        "ground_truth_separation":"weather_observations.parquet holds sensor channels only; training_labels.parquet and flood_events.csv hold simulated ground truth; hidden states (storage, capacity, blockage, vulnerability) are never exported",
        "scenario_separation":"Scenario datasets are generated and evaluated independently; they are never pooled into one headline score",
        "hidden_states":"Storage, channel capacity, blockage and vulnerability determine events and are never model inputs"})
    manifest={"dataset_version":version,"scenario":config.scenario,"notice":NOTICE,"files":{}}
    for p in sorted(out.iterdir()):
        with p.open('rb') as handle:
            entry={"sha256":hashlib.file_digest(handle,"sha256").hexdigest(),"bytes":p.stat().st_size}
        if p.suffix==".csv": entry["data_rows"]=max(0,sum(1 for _ in p.open())-1)
        if p.suffix==".parquet": entry["data_rows"]=int(len(pd.read_parquet(p)))
        manifest["files"][p.name]=entry
    write_json(out/"dataset_manifest.json",manifest)
    by_loc=events.groupby("location_id").size().rename("events").reset_index();by_loc.to_csv(out/"events_per_location.csv",index=False)
    seasonal=events.assign(season=np.where(pd.to_datetime(events.event_start).dt.month.isin([11,12,1,2,3,4]),"wet","dry")).groupby(["location_id","season"]).size().rename("events").reset_index()
    seasonal.to_csv(out/"events_per_location_season.csv",index=False)
    (out/"data_quality_report.md").write_text(f"# Synthetic Fiji data quality — {version} ({config.scenario} scenario)\n\n"+NOTICE+"\n\nScenario purpose: {settings.purpose}\n\n```json\n"+json.dumps({**distribution,**quality},indent=2)+"\n```\n\nGeographical names/IDs/coordinates are the existing application registry. All hydrological characteristics, weather and flood outcomes are simulated. No individual positive labels were forced.\n")
    fig,axes=plt.subplots(2,2,figsize=(13,8))
    obs.groupby(obs.timestamp.dt.month).rainfall_mm.mean().plot(ax=axes[0,0],title="Mean rainfall by month (mm per observation)")
    by_loc.set_index("location_id").events.plot.bar(ax=axes[0,1],title="Simulated flood events per location")
    if len(events):
        first=events.iloc[0]; episode=obs[(obs.location_id==first.location_id)&obs.timestamp.between(first.event_start-pd.Timedelta(days=3),first.event_end+pd.Timedelta(days=2))]
        axes[1,0].plot(episode.timestamp,episode.rainfall_mm,label="Rainfall mm");axes[1,0].plot(episode.timestamp,episode.soil_moisture_pct,label="Soil %");axes[1,0].legend();axes[1,0].tick_params(axis='x',rotation=30)
        axes[1,1].plot(episode.timestamp,episode.river_level_m,label="River level m");axes[1,1].axvspan(first.event_start,first.event_end,alpha=.2,color='red',label='Flood active');axes[1,1].legend();axes[1,1].tick_params(axis='x',rotation=30)
    fig.tight_layout();fig.savefig(out/"simulation_overview.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,6));mapped=loc.merge(by_loc,on="location_id",how="left").fillna({"events":0})
    dots=ax.scatter(mapped.longitude,mapped.latitude,c=mapped.events,s=70,cmap='viridis')
    for row in mapped.itertuples():ax.annotate(row.slug,(row.longitude,row.latitude),fontsize=7)
    fig.colorbar(dots,ax=ax,label='Simulated events');ax.set(xlabel='Longitude',ylabel='Latitude',title=NOTICE);fig.tight_layout();fig.savefig(out/"spatial_events.png",dpi=160);plt.close(fig)
    print(json.dumps(distribution,indent=2))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,default=Path("ml/data/synthetic_fiji/v1"));p.add_argument("--start",default="2021-01-01");p.add_argument("--end",default="2025-12-31")
    p.add_argument("--seed",type=int,default=314);p.add_argument("--frequency",default="1h");p.add_argument("--storm-scale",type=float,default=1.);p.add_argument("--drainage-scale",type=float,default=1.)
    p.add_argument("--scenario",choices=sorted(SCENARIOS),default=None,
                   help="v3 scenario layer; omit to reproduce the original v1 configuration exactly")
    p.add_argument("--dataset-version",default=None,
                   help="defaults to synthetic-fiji-v1 without --scenario, else synthetic-fiji-v3-<scenario>")
    args=p.parse_args()
    scenario=args.scenario or "realistic"
    version=args.dataset_version or ("synthetic-fiji-v1" if args.scenario is None else f"synthetic-fiji-v3-{scenario}")
    save_dataset(args.out,SimulationConfig(start=args.start,end=args.end,seed=args.seed,frequency=args.frequency,
                                           storm_scale=args.storm_scale,drainage_scale=args.drainage_scale,
                                           scenario=scenario,dataset_version=version),dataset_version=version)
