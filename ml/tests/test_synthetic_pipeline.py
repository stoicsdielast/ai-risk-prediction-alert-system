import numpy as np
import pandas as pd
from ml.synthetic.generate import SimulationConfig, simulate, label_events, REGISTRY
from ml.synthetic.features import build_features
from ml.synthetic.train import partition, HELD_LOCATIONS, event_metrics


def test_simulator_reproducible_and_covers_existing_registry():
    config=SimulationConfig(start='2021-01-01',end='2021-01-20',seed=12)
    first=simulate(config);second=simulate(config)
    for a,b in zip(first,second):pd.testing.assert_frame_equal(a,b)
    registry,obs,events,labels,_=first
    assert set(registry.location_id)==set(pd.read_csv(REGISTRY).location_id)
    assert not obs.duplicated(['location_id','timestamp']).any()
    assert all(g.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all() for _,g in obs.groupby('location_id'))
    assert labels.loc[labels.flood_occurred.eq(1),'forecast_eligible'].eq(False).all()
    assert labels.groupby('location_id').tail(24).flood_within_24h.isna().all()


def test_onset_labels_are_strictly_future_and_current_floods_excluded():
    times=pd.date_range('2024-01-01',periods=100,freq='h',tz='UTC')
    active=np.zeros(100,dtype=bool);active[30:40]=True
    events=pd.DataFrame({'event_start':[times[30]]})
    labels=label_events(times,1,events,active,1)
    assert labels.loc[5,'flood_within_24h']==0
    assert labels.loc[6:29,'flood_within_24h'].eq(1).all()
    assert labels.loc[30:39,'flood_within_24h'].eq(0).all()
    assert not labels.loc[30:39,'forecast_eligible'].any()


def test_features_do_not_change_when_only_future_weather_changes():
    loc,obs,_,_,_=simulate(SimulationConfig(start='2021-01-01',end='2021-01-12',seed=31))
    cutoff=pd.Timestamp('2021-01-08',tz='UTC')
    before,names=build_features(obs,loc)
    changed=obs.copy();changed.loc[changed.timestamp>cutoff,'rainfall_mm']=999
    after,other=build_features(changed,loc)
    pd.testing.assert_frame_equal(before[before.timestamp<=cutoff],after[after.timestamp<=cutoff])
    assert names==other
    assert not any(any(x in c for x in ['flood','event','scenario','hidden','future','target','location_id']) for c in names)


def test_spatial_and_storm_partitions_never_enter_training():
    times=pd.date_range('2021-01-01','2025-12-31',freq='24h',tz='UTC')
    frame=pd.concat([pd.DataFrame({'timestamp':times,'location_id':i,'forecast_eligible':True,'history_ready':True}) for i in [1,3]],ignore_index=True)
    scenarios=pd.DataFrame(columns=['scenario_id','start','end'])
    stages,_=partition(frame,scenarios)
    assert not frame.loc[np.isin(stages,['train','calibration','selection','threshold']),'location_id'].isin(HELD_LOCATIONS).any()
    assert frame.loc[stages=='train','timestamp'].max()<frame.loc[stages=='test','timestamp'].min()-pd.Timedelta(hours=24)


def test_event_recall_counts_events_and_lead_time_not_positive_hours():
    times=pd.date_range('2024-01-01',periods=50,freq='h',tz='UTC')
    d=pd.DataFrame({'location_id':1,'timestamp':times})
    events=pd.DataFrame({'location_id':[1,1],'event_start':[times[24],times[49]]})
    p=np.zeros(50);p[12:16]=.9
    result=event_metrics(d,p,.5,events)
    assert result['eligible_flood_events']==2 and result['events_detected']==1
    assert result['event_recall']==.5 and result['median_warning_lead_hours']==12
