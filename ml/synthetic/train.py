"""Classical benchmark and validation-only selection for the synthetic simulator."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, precision_recall_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.refinement import reliability, score, threshold_table, recall_budget_threshold, sha256
from ml.train import write_json
from ml.training03 import fit_sigmoid, apply_sigmoid
from ml.synthetic.features import build_features
from ml.synthetic.generate import NOTICE

BUDGET=75/42
HELD_LOCATIONS=[3,10,12]
EVALUATIONS=['test','held_location','storm_holdout','held_location_storm']


def partition(frame, scenarios):
    dates=frame.timestamp;stages=np.full(len(frame),'excluded',dtype=object)
    for name,a,b in [('train','2021-01-01','2023-01-01'),('calibration','2023-01-01','2023-07-01'),
                     ('selection','2023-07-01','2024-01-01'),('threshold','2024-01-01','2024-07-01'),('test','2024-07-01','2026-01-01')]:
        mask=dates.ge(pd.Timestamp(a,tz='UTC')+pd.Timedelta(hours=24))&dates.lt(pd.Timestamp(b,tz='UTC')-pd.Timedelta(hours=24))
        stages[mask]=name
    held=frame.location_id.isin(HELD_LOCATIONS).to_numpy(); future=stages=='test'
    stages[held]='excluded_held_history';stages[held&future]='held_location'
    reserved=np.zeros(len(frame),dtype=bool);crossing=np.zeros(len(frame),dtype=bool)
    boundaries=pd.to_datetime(['2023-01-01','2023-07-01','2024-01-01','2024-07-01'],utc=True)
    selected=[]
    for storm in scenarios.itertuples():
        a=storm.start-pd.Timedelta(hours=24);b=storm.end+pd.Timedelta(hours=168)
        mask=dates.between(a,b).to_numpy()
        if int(hashlib.sha256(storm.scenario_id.encode()).hexdigest()[:8],16)%5==0:
            reserved|=mask;selected.append(storm.scenario_id)
        if any(a<=boundary<=b for boundary in boundaries):crossing|=mask
    stages[reserved]='excluded_storm_history'
    stages[reserved&future&~held]='storm_holdout';stages[reserved&future&held]='held_location_storm'
    stages[crossing]='embargo_storm_boundary'
    stages[~frame.forecast_eligible.to_numpy()|~frame.history_ready.to_numpy()]='ineligible'
    return stages,selected


def policy(y,p):
    try:return float(recall_budget_threshold(threshold_table(y,p),BUDGET)['threshold']),True
    except ValueError:return float(np.nextafter(1.,2.)),False


def metrics(y,p,threshold):
    result=score(y,p,threshold)
    if len(y):result.update(accuracy=float(accuracy_score(y,np.asarray(p)>=threshold)),balanced_accuracy=float(balanced_accuracy_score(y,np.asarray(p)>=threshold)) if len(np.unique(y))==2 else None)
    return result


def event_metrics(data, probabilities, threshold, events):
    detected=0;lead=[];eligible_events=0
    lookup={}
    for location_id,g in data.assign(_warning=np.asarray(probabilities)>=threshold).groupby('location_id'):
        g=g.sort_values('timestamp')
        lookup[location_id]=(g.timestamp.to_numpy(dtype='datetime64[ns]').astype('int64'),g._warning.to_numpy())
    for event in events.itertuples():
        if event.location_id not in lookup:continue
        times,warning=lookup[event.location_id];onset=event.event_start.value
        a=np.searchsorted(times,onset-24*3600*10**9);b=np.searchsorted(times,onset)
        if a==b:continue
        eligible_events+=1
        warned=np.flatnonzero(warning[a:b])
        if len(warned):detected+=1;lead.append((onset-times[a+warned[0]])/(3600*10**9))
    return {'eligible_flood_events':eligible_events,'events_detected':detected,'event_recall':detected/eligible_events if eligible_events else None,
            'median_warning_lead_hours':float(np.median(lead)) if lead else None,'insufficient_events':eligible_events<10}


def estimators():
    from catboost import CatBoostClassifier
    from lightgbm import LGBMClassifier
    return {
        'logistic':LogisticRegression(C=1.,class_weight='balanced',max_iter=1500,random_state=314),
        'random_forest':RandomForestClassifier(n_estimators=160,max_depth=14,min_samples_leaf=10,class_weight='balanced_subsample',n_jobs=2,random_state=314),
        'lightgbm':LGBMClassifier(n_estimators=350,num_leaves=15,max_depth=6,min_child_samples=40,class_weight='balanced',learning_rate=.04,n_jobs=2,random_state=314,verbosity=-1,deterministic=True,force_col_wise=True),
        'catboost':CatBoostClassifier(iterations=350,depth=6,learning_rate=.04,l2_leaf_reg=8,auto_class_weights='Balanced',thread_count=2,random_seed=314,verbose=False,allow_writing_files=False)}


def train(dataset,out):
    if out.exists():raise ValueError('Run exists; use a fresh output directory')
    meta=json.loads((dataset/'dataset_metadata.json').read_text());loc=pd.read_csv(dataset/'locations.csv')
    obs=pd.read_parquet(dataset/'weather_observations.parquet');labels=pd.read_parquet(dataset/'training_labels.parquet')
    scenarios=pd.read_csv(dataset/'simulation_scenarios.csv',parse_dates=['start','end'])
    events=pd.read_csv(dataset/'flood_events.csv',parse_dates=['event_start','event_end'])
    features,names=build_features(obs,loc,meta['config']['frequency'])
    frame=features.merge(labels,on=['location_id','timestamp'],validate='one_to_one')
    frame['stage'],reserved=partition(frame,scenarios)
    out.mkdir(parents=True)
    features.to_parquet(out/'features.parquet',index=False)
    frame[['location_id','timestamp','stage','flood_within_24h','flood_occurred','forecast_eligible']].to_parquet(out/'splits.parquet',index=False)
    summary=frame.groupby('stage').agg(rows=('stage','size'),positives=('flood_within_24h','sum'));summary.to_csv(out/'partition_summary.csv')
    write_json(out/'protocol.json',{'source_type':'synthetic','notice':NOTICE,'dataset':str(dataset.resolve()),'dataset_metadata_sha256':sha256(dataset/'dataset_metadata.json'),
        'features':names,'held_location_ids':HELD_LOCATIONS,'reserved_storms':reserved,'false_alerts_per_detection_budget':BUDGET,
        'selection':'Maximum pooled selection recall under FP/TP budget, then AP, F1, lower Brier. Calibration 2023 H1, selection 2023 H2, threshold 2024 H1.',
        'embargo':'24h on both sides of each temporal boundary; entire storm start-24h through end+168h excluded if crossing a boundary',
        'future_leakage':'Only present/past raw observations and declared geography are inputs. Label, scenario ID, active-flood state and hidden states excluded.',
        'model_specs':{k:str(v) for k,v in estimators().items()},'seed':314})
    parts={s:frame[frame.stage.eq(s)].copy() for s in ['train','calibration','selection','threshold']+EVALUATIONS}
    for s in ['train','calibration','selection','threshold']:
        if parts[s].flood_within_24h.nunique()!=2:raise ValueError(f'Insufficient classes in {s}')
    rows=[];models={};predictions={};timings={}
    for name,estimator in estimators().items():
        started=time.monotonic();print('Fitting',name,flush=True)
        model=Pipeline([('imputer',SimpleImputer(strategy='median',add_indicator=True)),('scale',StandardScaler()),('classifier',estimator)])
        model.fit(parts['train'][names],parts['train'].flood_within_24h.astype(int))
        joblib.dump(model,out/(name+'.joblib'))
        raw={s:model.predict_proba(d[names])[:,1] for s,d in parts.items()}
        calibrator=fit_sigmoid(raw['calibration'],parts['calibration'].flood_within_24h)
        joblib.dump(calibrator,out/(name+'__sigmoid.joblib'))
        for method in ['none','sigmoid']:
            candidate=name+'__'+method;p={s:(apply_sigmoid(calibrator,v) if method=='sigmoid' else v) for s,v in raw.items()}
            threshold,feasible=policy(parts['selection'].flood_within_24h,p['selection'])
            rows.append({'candidate':candidate,'feasible':feasible,**metrics(parts['selection'].flood_within_24h,p['selection'],threshold)})
            models[candidate]={'model':name,'calibration':method};predictions[candidate]=p
        timings[name]=time.monotonic()-started
    selection=pd.DataFrame(rows);selection.to_csv(out/'selection_metrics.csv',index=False)
    eligible=selection[selection.feasible].sort_values(['recall','pr_auc_average_precision','f1','brier','candidate'],ascending=[False,False,False,True,True])
    if eligible.empty:raise ValueError('No model meets validation false-alert budget')
    winner=eligible.iloc[0].candidate
    write_json(out/'selection_lock.json',{'selected':winner,'selected_before_threshold_scoring':True,'dataset_sha256':sha256(dataset/'dataset_metadata.json')})
    # All eight predeclared variants get their own H2 threshold for comparison;
    # none of the later test outcomes changes the already frozen winner.
    thresholds={k:dict(zip(['threshold','feasible'],policy(parts['threshold'].flood_within_24h,p['threshold']))) for k,p in predictions.items()}
    write_json(out/'thresholds.json',thresholds)
    # Baselines are fixed from training data / simple visible observation rules.
    prevalence=float(parts['train'].flood_within_24h.mean())
    predictions['majority']={s:np.full(len(d),prevalence) for s,d in parts.items()};thresholds['majority']={'threshold':.5,'feasible':False}
    predictions['rainfall_soil_rule']={s:np.where((d.rainfall_mm_total_24h.fillna(0)>80)&(d.soil_moisture_pct.fillna(0)>75),.75,.01) for s,d in parts.items()}
    thresholds['rainfall_soil_rule']={'threshold':.5,'feasible':None}
    all_metrics=[];per_location=[];saved=[]
    for candidate,prob in predictions.items():
        threshold=thresholds[candidate]['threshold']
        for s,d in parts.items():
            all_metrics.append({'candidate':candidate,'stage':s,**metrics(d.flood_within_24h,prob[s],threshold),**event_metrics(d,prob[s],threshold,events)})
            if s in EVALUATIONS:
                for location_id,g in d.groupby('location_id'):
                    mask=d.location_id.eq(location_id).to_numpy()
                    per_location.append({'candidate':candidate,'stage':s,'location_id':location_id,**metrics(g.flood_within_24h,prob[s][mask],threshold),**event_metrics(g,prob[s][mask],threshold,events)})
            saved.append(d[['location_id','timestamp','flood_within_24h']].assign(candidate=candidate,stage=s,probability=prob[s],threshold=threshold))
    pd.DataFrame(all_metrics).to_csv(out/'metrics.csv',index=False);pd.DataFrame(per_location).to_csv(out/'per_location_metrics.csv',index=False)
    pd.concat(saved,ignore_index=True).to_parquet(out/'predictions.parquet',index=False)
    selected=models[winner];bundle={'model':joblib.load(out/(selected['model']+'.joblib')),
        'calibrator':joblib.load(out/(selected['model']+'__sigmoid.joblib')) if selected['calibration']=='sigmoid' else None,
        'features':names,'threshold':thresholds[winner]['threshold'],'model_version':'synthetic-fiji-v1-'+winner,'source_type':'synthetic'}
    joblib.dump(bundle,out/'selected_model.joblib')
    write_json(out/'model_metadata.json',{'model_version':bundle['model_version'],'selected_candidate':winner,'threshold':bundle['threshold'],
        'threshold_feasible':thresholds[winner]['feasible'],'source_type':'synthetic','notice':NOTICE,'dataset':str(dataset.resolve()),
        'features':names,'feature_schema_sha256':hashlib.sha256(json.dumps(names).encode()).hexdigest(),'model_sha256':sha256(out/'selected_model.joblib'),
        'training_seconds':timings,'selected_at':datetime.now(timezone.utc).isoformat(),'risk_tiers':'Provisional research bands relative to validation threshold: LOW <0.5t, MODERATE <t, HIGH <min(1,1.5t), VERY_HIGH otherwise'})
    clustering=Pipeline([('impute',SimpleImputer()),('scale',StandardScaler()),('cluster',MiniBatchKMeans(n_clusters=5,random_state=314,n_init=5,batch_size=2048))])
    cluster_features=['rainfall_mm_total_24h','rainfall_mm_total_72h','river_level_m','river_discharge_m3s','soil_moisture_pct','pressure_hpa']
    clustering.fit(parts['train'][cluster_features]);joblib.dump(clustering,out/'clustering.joblib')
    cluster_rows=[]
    for stage,d in parts.items():
        clusters=clustering.predict(d[cluster_features])
        for k in range(5):
            labels=d.loc[clusters==k,'flood_within_24h'];cluster_rows.append({'stage':stage,'cluster':k,'rows':len(labels),'flood_incidence':float(labels.mean()) if len(labels) else None})
    pd.DataFrame(cluster_rows).to_csv(out/'cluster_incidence.csv',index=False)
    clf=bundle['model'].named_steps['classifier']
    importance=getattr(clf,'feature_importances_',None)
    if importance is None and hasattr(clf,'coef_'):importance=np.abs(clf.coef_[0])
    if importance is not None:
        expanded=bundle['model'].named_steps['imputer'].get_feature_names_out(names)
        pd.DataFrame({'feature':expanded,'importance':importance}).sort_values('importance',ascending=False).to_csv(out/'feature_importance.csv',index=False)
    plot_results(out,parts,predictions,thresholds,winner)
    print(pd.DataFrame(all_metrics).query('stage == "test"')[['candidate','precision','recall','f1','pr_auc_average_precision','brier']].to_string(index=False))
    print('Selected on validation:',winner)


def plot_results(out,parts,predictions,thresholds,winner):
    bins=[]
    for stage in ['selection','threshold']+EVALUATIONS:
        d=parts[stage];fig,axes=plt.subplots(1,2,figsize=(13,5))
        for candidate,p in predictions.items():
            if d.flood_within_24h.sum():
                precision,recall,_=precision_recall_curve(d.flood_within_24h,p[stage]);axes[0].plot(recall,precision,label=candidate)
            rel=reliability(d.flood_within_24h,p[stage]);axes[1].plot([r['mean_probability'] for r in rel],[r['positive_fraction'] for r in rel],marker='.')
            bins.extend({'candidate':candidate,'stage':stage,**r} for r in rel)
        axes[0].set(xlabel='Recall',ylabel='Precision',title=stage+' — simulator outcomes');axes[0].legend(fontsize=6)
        if not d.flood_within_24h.sum():axes[0].text(.1,.5,'No positive events: PR curve undefined')
        axes[1].plot([0,1],[0,1],'k--');axes[1].set(xlabel='Predicted probability',ylabel='Simulated incidence',title='Calibration')
        fig.tight_layout();fig.savefig(out/(stage+'_pr_calibration.png'),dpi=160);plt.close(fig)
    pd.DataFrame(bins).to_csv(out/'calibration_bins.csv',index=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,default=Path('ml/data/synthetic_fiji/v1'));p.add_argument('--out',type=Path,default=Path('ml/runs/synthetic-v1'))
    a=p.parse_args();train(a.dataset,a.out)
