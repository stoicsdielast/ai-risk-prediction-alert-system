"""Evaluate the frozen selected model on independent simulator seeds/settings."""
import argparse
import json
from pathlib import Path
import joblib
import pandas as pd
from ml.synthetic.generate import SimulationConfig, save_dataset
from ml.synthetic.features import build_features
from ml.synthetic.train import metrics,event_metrics,HELD_LOCATIONS
from ml.training03 import apply_sigmoid


def run(out):
    bundle=joblib.load(out/'selected_model.joblib')
    rows=[]
    for name,seed,storm,drainage in [('independent_seed',8314,1.,1.),('wetter_reduced_drainage',9314,1.2,.8)]:
        path=Path('ml/data/synthetic_fiji')/name
        if not path.exists():save_dataset(path,SimulationConfig('2024-01-01','2025-12-31',seed,'1h',storm,drainage))
        obs=pd.read_parquet(path/'weather_observations.parquet');loc=pd.read_csv(path/'locations.csv')
        features,names=build_features(obs,loc);assert names==bundle['features']
        labels=pd.read_parquet(path/'training_labels.parquet');d=features.merge(labels,on=['location_id','timestamp'],validate='one_to_one')
        d=d[d.history_ready&d.forecast_eligible]
        raw=bundle['model'].predict_proba(d[names])[:,1]
        probability=apply_sigmoid(bundle['calibrator'],raw) if bundle['calibrator'] is not None else raw
        events=pd.read_csv(path/'flood_events.csv',parse_dates=['event_start','event_end'])
        for subset,mask in [('all',pd.Series(True,index=d.index)),('unseen_locations',d.location_id.isin(HELD_LOCATIONS))]:
            g=d[mask];p=probability[mask.to_numpy()]
            rows.append({'stress':name,'seed':seed,'storm_scale':storm,'drainage_scale':drainage,'subset':subset,
                         **metrics(g.flood_within_24h,p,bundle['threshold']),**event_metrics(g,p,bundle['threshold'],events)})
        d[['location_id','timestamp','flood_within_24h']].assign(probability=probability).to_parquet(out/(name+'_predictions.parquet'),index=False)
    pd.DataFrame(rows).to_csv(out/'stress_metrics.csv',index=False)
    print(pd.DataFrame(rows)[['stress','subset','precision','recall','f1','pr_auc_average_precision','brier','event_recall']].to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('ml/runs/synthetic-v1'));run(parser.parse_args().out)
