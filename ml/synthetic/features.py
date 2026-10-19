"""Causal observed features; simulator outcomes and hidden states stay separate."""
import numpy as np
import pandas as pd
from ml.synthetic.generate import RAW_COLUMNS, GEO_COLUMNS


def build_features(observations, locations, frequency="1h"):
    dt=pd.Timedelta(frequency).total_seconds()/3600
    frame=observations.sort_values(["location_id","timestamp"])[["location_id","timestamp"]+RAW_COLUMNS].copy()
    for c in RAW_COLUMNS:
        frame[c+"_missing"]=frame[c].isna().astype('int8')
    # Short forward-only sensor recovery; never back-fill from future readings.
    frame[RAW_COLUMNS]=frame.groupby('location_id',sort=False)[RAW_COLUMNS].ffill(limit=max(1,int(6/dt)))
    for c in ["rainfall_mm","upstream_rainfall_mm"]:
        for hours in [3,6,24,72,168]:
            window=max(1,int(hours/dt))
            frame[f"{c}_total_{hours}h"]=frame.groupby('location_id')[c].transform(lambda s:s.rolling(window,min_periods=max(1,window//2)).sum())
    for c in ["river_level_m","river_discharge_m3s","soil_moisture_pct"]:
        for hours in [3,6,24]:
            steps=max(1,int(hours/dt))
            frame[f"{c}_change_{hours}h"]=frame.groupby('location_id')[c].diff(steps)
        frame[c+"_mean_24h"]=frame.groupby('location_id')[c].transform(lambda s:s.rolling(max(1,int(24/dt)),min_periods=1).mean())
    frame=frame.merge(locations[["location_id","latitude","longitude"]+GEO_COLUMNS],on='location_id',validate='many_to_one',sort=False)
    frame['month_sin']=np.sin(2*np.pi*frame.timestamp.dt.month/12);frame['month_cos']=np.cos(2*np.pi*frame.timestamp.dt.month/12)
    frame['hour_sin']=np.sin(2*np.pi*frame.timestamp.dt.hour/24);frame['hour_cos']=np.cos(2*np.pi*frame.timestamp.dt.hour/24)
    frame['history_ready']=frame.groupby('location_id').cumcount()>=int(168/dt)
    features=[c for c in frame if c not in ['location_id','timestamp','history_ready']]
    assert not any(any(x in c for x in ['flood','event','scenario','hidden','future','target']) for c in features)
    return frame,features
