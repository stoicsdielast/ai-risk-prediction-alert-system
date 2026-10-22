"""Import generated weather into isolated PostgreSQL tables after Alembic upgrade."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from sqlalchemy import select, insert, func
from app.db.session import get_session_factory
from app.models.location import Location
from app.models.synthetic import SyntheticDataset, SyntheticObservation


def import_dataset(db, directory):
    metadata=json.loads((directory/'dataset_metadata.json').read_text())
    if metadata.get('source_type')!='synthetic':raise ValueError('Only synthetic sources accepted')
    registry=pd.read_csv(directory/'locations.csv')
    locations={x.id:x for x in db.scalars(select(Location).where(Location.is_active.is_(True)))}
    if set(registry.location_id)!=set(locations):raise ValueError('Dataset location IDs differ from the active map registry')
    for row in registry.itertuples():
        actual=locations[row.location_id]
        if actual.slug!=row.slug or actual.name!=row.name or actual.division.value!=row.division or abs(actual.latitude-row.latitude)>1e-7 or abs(actual.longitude-row.longitude)>1e-7:
            raise ValueError('Dataset map identity mismatch; regenerate from authoritative locations')
    version=metadata['dataset_version'];digest=hashlib.sha256((directory/'dataset_metadata.json').read_bytes()).hexdigest()
    existing=db.get(SyntheticDataset,version)
    if existing:
        if existing.metadata_json.get('metadata_sha256')!=digest:raise ValueError('Version already exists with different data')
        count=db.scalar(select(func.count()).select_from(SyntheticObservation).where(SyntheticObservation.dataset_version==version))
        if count!=existing.observation_count:raise ValueError('Existing dataset import is incomplete')
        return {'status':'already_imported','version':version,'observations':count}
    observations=pd.read_parquet(directory/'weather_observations.parquet')
    expected=metadata['file_sha256']['weather_observations.parquet']
    with (directory/'weather_observations.parquet').open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=expected:raise ValueError('Observation checksum mismatch')
    db.add(SyntheticDataset(version=version,metadata_json={**metadata,'metadata_sha256':digest},observation_count=len(observations)))
    db.flush()
    columns=[c for c in observations if c not in ['timestamp','location_id','source_type']]
    for start in range(0,len(observations),2000):
        batch=observations.iloc[start:start+2000]
        values=json.loads(batch[columns].to_json(orient='records',double_precision=15))
        records=[{'dataset_version':version,'location_id':int(row.location_id),'observed_at':row.timestamp.to_pydatetime(),'values':value}
                 for row,value in zip(batch.itertuples(),values)]
        db.execute(insert(SyntheticObservation),records)
    db.commit()
    return {'status':'imported','version':version,'observations':len(observations)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--dataset',type=Path,default=Path('../ml/data/synthetic_fiji/v1'))
    with get_session_factory()() as db:print(json.dumps(import_dataset(db,parser.parse_args().dataset),indent=2))
