"""Write measured simulator evaluation and a portable serving bundle."""
import argparse
import ast
import importlib.metadata
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve
from ml.refinement import sha256,reliability
from ml.train import write_json


def markdown(d):
    def value(v):
        if isinstance(v,float):return 'N/A' if np.isnan(v) else f'{v:.6f}'
        return str(v)
    return '| '+' | '.join(d.columns)+' |\n|'+'|'.join(['---']*len(d.columns))+'|\n'+'\n'.join('| '+' | '.join(value(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))


def report(out,publish):
    meta=json.loads((out/'model_metadata.json').read_text());dataset=Path(meta['dataset']);data_meta=json.loads((dataset/'dataset_metadata.json').read_text())
    metrics=pd.read_csv(out/'metrics.csv');selected=metrics[metrics.candidate.eq(meta['selected_candidate'])].copy()
    # Single-class subsets have no estimable detection recall or balanced accuracy.
    for file in ['metrics.csv','per_location_metrics.csv']:
        d=pd.read_csv(out/file);mask=(d.positives==0)|(d.positives==d.rows)
        d.loc[mask,'balanced_accuracy']=np.nan
        d.loc[d.positives==0,['recall','f1','f2']]=np.nan
        d.to_csv(out/file,index=False)
    metrics=pd.read_csv(out/'metrics.csv');selected=metrics[metrics.candidate.eq(meta['selected_candidate'])]
    confusion=[]
    for row in metrics.itertuples():
        tn,fp,fn,tp=ast.literal_eval(row.confusion_matrix_tn_fp_fn_tp)
        confusion.append({'candidate':row.candidate,'stage':row.stage,'TN':tn,'FP':fp,'FN':fn,'TP':tp})
    pd.DataFrame(confusion).to_csv(out/'confusion_matrices.csv',index=False)
    selected_confusion=pd.DataFrame(confusion)
    fig,axes=plt.subplots(1,4,figsize=(14,4))
    for ax,stage in zip(axes,['test','held_location','storm_holdout','held_location_storm']):
        r=selected_confusion[(selected_confusion.candidate==meta['selected_candidate'])&(selected_confusion.stage==stage)].iloc[0]
        matrix=np.array([[r.TN,r.FP],[r.FN,r.TP]]);ax.imshow(matrix,cmap='Blues')
        for i in range(2):
            for j in range(2):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',color='red')
        ax.set(xticks=[0,1],yticks=[0,1],xlabel='Predicted',ylabel='Simulated outcome',title=stage)
    fig.tight_layout();fig.savefig(out/'selected_confusion_matrices.png',dpi=160);plt.close(fig)
    # Explicitly replace the undefined joint PR chart, retaining calibration.
    pred=pd.read_parquet(out/'predictions.parquet')
    joint=pred[pred.stage.eq('held_location_storm')]
    fig,axes=plt.subplots(1,2,figsize=(12,4));axes[0].text(.05,.5,'No positive flood events: PR curve and recall undefined')
    for candidate,g in joint.groupby('candidate'):
        rel=reliability(g.flood_within_24h,g.probability)
        axes[1].plot([r['mean_probability'] for r in rel],[r['positive_fraction'] for r in rel],label=candidate)
    axes[1].plot([0,1],[0,1],'k--');axes[1].set(xlabel='Predicted probability',ylabel='Observed simulated incidence');axes[1].legend(fontsize=6)
    fig.tight_layout();fig.savefig(out/'held_location_storm_pr_calibration.png',dpi=160);plt.close(fig)
    versions={k:importlib.metadata.version(k) for k in ['numpy','pandas','scikit-learn','catboost','lightgbm','pyarrow']}
    write_json(out/'reproducibility.json',{'versions':versions,'source_sha256':{str(p):sha256(p) for p in sorted(Path('ml/synthetic').glob('*.py'))},
        'dataset_metadata_sha256':sha256(dataset/'dataset_metadata.json'),'model_sha256':sha256(out/'selected_model.joblib')})
    text='# Synthetic Fiji v1 measured evaluation\n\nSynthetic Data — Research Demonstration. All outcomes and skill measures below refer to the simulator, not observed Fiji flood forecasting performance.\n\n'
    text+='## Dataset\n\n```json\n'+json.dumps(data_meta['distribution'],indent=2)+'\n```\n\n'
    text+='## Chronological test comparison\n\n'+markdown(metrics[metrics.stage.eq('test')][['candidate','accuracy','balanced_accuracy','precision','recall','f1','pr_auc_average_precision','roc_auc','brier','confusion_matrix_tn_fp_fn_tp']])
    text+='\n\n## Selected model and geographical/event transfer\n\nSelected using validation only: **'+meta['selected_candidate']+'**, threshold '+str(meta['threshold'])+'.\n\n'
    text+=markdown(selected[['stage','rows','positives','recall','precision','pr_auc_average_precision','brier','eligible_flood_events','event_recall','median_warning_lead_hours','false_alerts_per_1000']])
    text+='\n\n## Independent simulator stress tests\n\n'+markdown(pd.read_csv(out/'stress_metrics.csv')[['stress','subset','precision','recall','f1','pr_auc_average_precision','brier','eligible_flood_events','event_recall']])
    text+='\n\n## Calibration and limitations\n\nSigmoid preserves ranking and budget-optimized decisions for these fits. It improved test Brier, but worsened the selection-period Brier; raw CatBoost was selected before test evaluation. Calibration fitted only 2023 H1, model choice used 2023 H2, and thresholds used 2024 H1. Reported calibration-block scores are in-sample for the calibrator.\n\n'
    text+='The approved empirical FP/TP budget is 75/42 = 1.785714. It is enforced on threshold validation, not guaranteed on new regimes. The selected test FP/TP is '+str(float(selected[selected.stage.eq('test')].iloc[0].false_alerts_per_detection))+'. Independent-seed precision deteriorated, demonstrating sensitivity to simulator regimes. Majority-class accuracy is high despite zero detections; accuracy alone is unsuitable. Event recall measures whether any eligible warning occurs in the preceding 24 hours, not recall of every positive hour. Lead time is conditional on detected events.\n\n'
    text+='The joint unseen-location/unseen-storm subset contains zero flood events: no detection claim is supported there. Unseen-location assessment has only 11 events, and temporal records within storms are correlated. K-Means incidence summaries are descriptive weather patterns, not validated risk categories. Static hydrological characteristics, hidden capacities and vulnerability are assumed. No real-world calibration, alert-cost validation or Fiji MET endorsement is implied.\n\n'
    text+='## Optional foundation models\n\n```json\n'+(out/'optional_foundation/status.json').read_text()+'\n```\n\nTabICLv2 smoke testing produced finite predictions but no full performance scores within the configured optional budget. Its conservative runtime extrapolation includes startup and is not a measured full-run duration. TabFM/TabICL environments and public checkpoints remain available for future resource-expanded experiments.\n'
    (out/'evaluation_report.md').write_text(text)
    if publish:
        destination=Path('ml/artifacts/synthetic/v1')
        if destination.exists():raise ValueError('Serving bundle exists; no silent model replacement')
        destination.mkdir(parents=True)
        for filename in ['selected_model.joblib','model_metadata.json','features.parquet']:
            shutil.copy2(out/filename,destination/filename)
        shutil.copy2(dataset/'training_labels.parquet',destination/'simulation_outcomes.parquet')
        write_json(destination/'bundle_manifest.json',{p.name:sha256(p) for p in destination.iterdir()})
        print('Published local synthetic-only serving bundle:',destination)
    print('Report:',out/'evaluation_report.md')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('ml/runs/synthetic-v1'));p.add_argument('--publish-local-bundle',action='store_true')
    a=p.parse_args();report(a.out,a.publish_local_bundle)
