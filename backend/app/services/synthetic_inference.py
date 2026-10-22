"""Local synthetic replay. No network downloads or fitting during requests."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

NOTICE = "Synthetic Data — Research Demonstration"


def risk_category(probability, threshold):
    if probability < threshold*.5:return 'LOW'
    if probability < threshold:return 'MODERATE'
    if probability < min(1.,threshold*1.5):return 'HIGH'
    return 'VERY_HIGH'


class SyntheticModel:
    def __init__(self,directory):
        self.directory=Path(directory)
        self.metadata=json.loads((self.directory/'model_metadata.json').read_text())
        if self.metadata.get('source_type')!='synthetic':raise ValueError('Not a synthetic model')
        with (self.directory/'selected_model.joblib').open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=self.metadata['model_sha256']:raise ValueError('Synthetic model checksum mismatch')
        self.bundle=joblib.load(self.directory/'selected_model.joblib')
        if self.bundle.get('source_type')!='synthetic' or self.bundle['features']!=self.metadata['features']:raise ValueError('Synthetic model schema mismatch')
        self.features=pd.read_parquet(self.directory/'features.parquet').set_index(['location_id','timestamp']).sort_index()
        self.outcomes=pd.read_parquet(self.directory/'simulation_outcomes.parquet',columns=['location_id','timestamp','flood_occurred']).set_index(['location_id','timestamp']).sort_index()

    def predict(self,location_id,timestamp):
        key=(location_id,pd.Timestamp(timestamp))
        if key not in self.features.index:raise ValueError('Timestamp or location is outside the generated dataset')
        row=self.features.loc[[key]]
        active=bool(self.outcomes.loc[key,'flood_occurred'])
        result={'source_type':'synthetic','notice':NOTICE,'location_id':location_id,'timestamp':timestamp.isoformat(),
            'horizon_hours':24,'model_version':self.metadata['model_version'],'risk_category':None,'probability':None,
            'simulated_flood_active':active,'provisional_risk':True,'decision_threshold':self.bundle['threshold']}
        if active:result['status']='ongoing_simulated_flood';return result
        if not bool(row.history_ready.iloc[0]):result['status']='insufficient_history';return result
        p=float(self.bundle['model'].predict_proba(row[self.bundle['features']])[:,1][0])
        if self.bundle['calibrator'] is not None:
            clipped=np.clip(p,1e-6,1-1e-6)
            p=float(self.bundle['calibrator'].predict_proba([[np.log(clipped/(1-clipped))]])[0,1])
        result.update(status='ok',probability=p,risk_category=risk_category(p,self.bundle['threshold']))
        return result


@lru_cache(maxsize=2)
def load_synthetic_model(directory):
    return SyntheticModel(directory)
