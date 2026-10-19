"""Bounded optional TabICLv2 comparison; no change to the classical selection."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import joblib
import numpy as np
import pandas as pd
from ml.synthetic.train import metrics,policy,event_metrics,EVALUATIONS
from ml.training03 import fit_sigmoid,apply_sigmoid
from ml.train import write_json


def worker(job,context,query,features,asset,timeout):
    job.mkdir(parents=True,exist_ok=False)
    context[features].assign(label=context.flood_within_24h.astype(int).to_numpy()).to_parquet(job/'context.parquet',index=False)
    query[features+['row_id']].to_parquet(job/'query.parquet',index=False)
    request={'model':'tabicl','asset':{**asset,'kv_cache':True},'features':features,'device':'cuda','memory_gb':16,'timeout_seconds':timeout,
        'query_batch_rows':64,'context':str((job/'context.parquet').resolve()),'query':str((job/'query.parquet').resolve()),'output':str((job/'probabilities.parquet').resolve())}
    write_json(job/'request.json',request)
    env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2'}
    started=time.monotonic()
    with (job/'worker.log').open('w') as log:
        subprocess.run([asset['python'],'-m','ml.foundation_worker',str(job/'request.json')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,check=True)
    seconds=time.monotonic()-started
    return pd.read_parquet(job/'probabilities.parquet').probability.to_numpy(),seconds


def run(out):
    folder=out/'optional_foundation';folder.mkdir(exist_ok=False)
    status={'tabfm':'Skipped: float32 checkpoint 6.56 GB; GPU smoke failed on 4 GB laptop. Full CPU benchmark outside bounded optional budget.',
            'tabpfn':'Skipped: authenticated TabPFN-2.5 checkpoint access unavailable.'}
    try:
        assets=json.loads(Path('ml/foundation/assets.json').read_text());asset=assets['tabicl']
        protocol=json.loads((out/'protocol.json').read_text());features=protocol['features']
        data=pd.read_parquet(out/'features.parquet').merge(pd.read_parquet(out/'splits.parquet'),on=['location_id','timestamp'],validate='one_to_one')
        data['row_id']=np.arange(len(data))
        training=data[data.stage.eq('train')].copy()
        training['hash']=pd.util.hash_pandas_object(training[['location_id','timestamp']],index=False).to_numpy()
        context=training.sort_values('hash').head(1024)
        query=data[data.stage.isin(['calibration','selection','threshold']+EVALUATIONS)]
        write_json(folder/'protocol.json',{'context_rows':1024,'context_selection':'Lowest deterministic hash, labels not used','context_positives':int(context.flood_within_24h.sum()),
            'features':features,'full_query_rows':len(query),'seconds_budget':600,'calibration':'2023 H1','selection':'2023 H2','threshold':'2024 H1',
            'comparison':'Same evaluation records as classical models; fewer context rows; supplementary benchmark does not alter frozen classical serving choice'})
        smoke,seconds=worker(folder/'smoke',context,query.head(512),features,asset,120)
        # Runtime screening uses no labels or performance scores.
        estimate=seconds*len(query)/512
        write_json(folder/'smoke.json',{'passed':True,'rows':len(smoke),'seconds':seconds,'conservative_full_seconds_estimate_including_repeated_startup':estimate,'performance_scores':None})
        if estimate>1800:raise TimeoutError('Smoke timing indicates full inference exceeds optional laptop budget')
        p,elapsed=worker(folder/'full',context,query,features,asset,600)
        cal=query.stage.eq('calibration').to_numpy();selection=query.stage.eq('selection').to_numpy();threshold=query.stage.eq('threshold').to_numpy()
        sigmoid=fit_sigmoid(p[cal],query.loc[cal,'flood_within_24h']);joblib.dump(sigmoid,folder/'sigmoid.joblib')
        calibrated=apply_sigmoid(sigmoid,p);candidates={};selection_rows=[]
        for name,prob in [('none',p),('sigmoid',calibrated)]:
            t,feasible=policy(query.loc[selection,'flood_within_24h'],prob[selection])
            selection_rows.append({'method':name,'feasible':feasible,**metrics(query.loc[selection,'flood_within_24h'],prob[selection],t)});candidates[name]=prob
        ranked=pd.DataFrame(selection_rows).sort_values(['feasible','recall','pr_auc_average_precision','brier'],ascending=[False,False,False,True])
        name=ranked.iloc[0].method;prob=candidates[name];t,feasible=policy(query.loc[threshold,'flood_within_24h'],prob[threshold])
        write_json(folder/'selection_lock.json',{'method':name,'threshold':t,'threshold_feasible':feasible,'chosen_without_test_metrics':True})
        events=pd.read_csv(Path(protocol['dataset'])/'flood_events.csv',parse_dates=['event_start','event_end'])
        rows=[]
        for stage in ['selection','threshold']+EVALUATIONS:
            mask=query.stage.eq(stage).to_numpy();d=query.loc[mask]
            rows.append({'candidate':'tabicl_1024__'+name,'stage':stage,**metrics(d.flood_within_24h,prob[mask],t),**event_metrics(d,prob[mask],t,events)})
        pd.DataFrame(rows).to_csv(folder/'metrics.csv',index=False);ranked.to_csv(folder/'selection_metrics.csv',index=False)
        query[['location_id','timestamp','stage','flood_within_24h']].assign(probability=prob).to_parquet(folder/'predictions.parquet',index=False)
        status['tabicl']={'status':'benchmarked','seconds':elapsed,'method':name,'threshold':t}
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as error:
        status['tabicl']={'status':'unavailable_or_resource_limited','reason':str(error)}
    write_json(folder/'status.json',status);print(json.dumps(status,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('ml/runs/synthetic-v1'));run(p.parse_args().out)
