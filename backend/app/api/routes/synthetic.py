"""Synthetic weather replay and isolated approval demonstration."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.api.dependencies import require_met_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.location import Location
from app.models.synthetic import SyntheticDataset, SyntheticObservation, SyntheticPrediction, SyntheticAlert
from app.models.user import User
from app.services.synthetic_inference import NOTICE, load_synthetic_model

router=APIRouter(prefix='/api/synthetic',tags=['synthetic research demonstration'])
VERSION='synthetic-fiji-v1'


def get_synthetic_model():
    try:return load_synthetic_model(str(get_settings().synthetic_model_dir.resolve()))
    except (OSError,ValueError,KeyError,ImportError) as exc:
        raise HTTPException(503,'Synthetic model unavailable; generate, train and publish the local bundle') from exc


def timestamp_utc(timestamp):
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:raise HTTPException(422,'Timestamp requires an explicit timezone')
    timestamp=timestamp.astimezone(timezone.utc)
    if timestamp.minute or timestamp.second or timestamp.microsecond:raise HTTPException(422,'Choose an exact hourly timestamp')
    return timestamp


@router.get('/info')
def info(db:Session=Depends(get_db)):
    try:dataset=db.get(SyntheticDataset,VERSION)
    except SQLAlchemyError as exc:raise HTTPException(503,'Initialize synthetic tables using Alembic') from exc
    return {'source_type':'synthetic','notice':NOTICE,'dataset_version':VERSION,'status':'ready' if dataset else 'not_imported',
        'observations':dataset.observation_count if dataset else 0,'config':dataset.metadata_json['config'] if dataset else None,
        'alerts_enabled':get_settings().synthetic_demo_enabled,'risk_categories_provisional':True}


@router.get('/frame')
def frame(timestamp:datetime,db:Session=Depends(get_db),model=Depends(get_synthetic_model)):
    timestamp=timestamp_utc(timestamp)
    observations=db.scalars(select(SyntheticObservation).where(SyntheticObservation.dataset_version==VERSION,SyntheticObservation.observed_at==timestamp)).all()
    if not observations:raise HTTPException(404,'No imported synthetic observations at this timestamp')
    locations={x.id:x for x in db.scalars(select(Location).where(Location.is_active.is_(True)))}
    results=[]
    for obs in observations:
        if obs.location_id not in locations:continue
        location=locations[obs.location_id]
        try:prediction=model.predict(location.id,timestamp)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        results.append({**prediction,'slug':location.slug,'name':location.name,'division':location.division.value,
            'latitude':location.latitude,'longitude':location.longitude,'weather':obs.values})
    return {'source_type':'synthetic','notice':NOTICE,'dataset_version':VERSION,'timestamp':timestamp.isoformat(),'locations':results}


class AlertRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    location_id:int
    timestamp:datetime

    @field_validator('timestamp')
    @classmethod
    def require_timezone(cls,value):
        if value.tzinfo is None:raise ValueError('Timestamp requires an explicit timezone')
        return value


def alert_json(db,alert):
    prediction=db.get(SyntheticPrediction,alert.prediction_id);location=db.get(Location,prediction.location_id)
    return {'id':alert.id,'prediction_id':prediction.id,'status':alert.status,'source_type':'synthetic','notice':NOTICE,
        'location_id':location.id,'slug':location.slug,'location_name':location.name,'risk_category':prediction.risk_category,
        'probability':prediction.probability,'timestamp':prediction.observed_at.isoformat(),'horizon_hours':24,
        'model_version':prediction.model_version,'message':f'{NOTICE}: provisional {prediction.risk_category} risk for {location.name}. No emergency warning.',
        'reviewed_at':alert.reviewed_at.isoformat() if alert.reviewed_at else None}


@router.post('/admin/alerts',status_code=201)
def create_alert(data:AlertRequest,db:Session=Depends(get_db),user:User=Depends(require_met_admin),model=Depends(get_synthetic_model)):
    if not get_settings().synthetic_demo_enabled:raise HTTPException(403,'Synthetic alert demonstration is disabled')
    timestamp=timestamp_utc(data.timestamp);location=db.get(Location,data.location_id)
    if location is None or not location.is_active:raise HTTPException(404,'Unknown active map location')
    observation=db.get(SyntheticObservation,(VERSION,location.id,timestamp))
    if observation is None:raise HTTPException(404,'Synthetic weather has not been imported for this timestamp')
    try:result=model.predict(location.id,timestamp)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if result['status']!='ok' or result['risk_category'] not in ['HIGH','VERY_HIGH']:raise HTTPException(422,'Only eligible HIGH/VERY_HIGH synthetic forecasts can create pending alerts')
    prediction=db.scalar(select(SyntheticPrediction).where(SyntheticPrediction.dataset_version==VERSION,SyntheticPrediction.location_id==location.id,
        SyntheticPrediction.observed_at==timestamp,SyntheticPrediction.model_version==result['model_version']))
    if prediction is None:
        prediction=SyntheticPrediction(dataset_version=VERSION,location_id=location.id,observed_at=timestamp,model_version=result['model_version'],probability=result['probability'],risk_category=result['risk_category'])
        db.add(prediction);db.flush()
    existing=db.scalar(select(SyntheticAlert).where(SyntheticAlert.prediction_id==prediction.id))
    if existing:return alert_json(db,existing)
    alert=SyntheticAlert(prediction_id=prediction.id,status='PENDING',created_by=user.id);db.add(alert);db.commit();db.refresh(alert)
    return alert_json(db,alert)


@router.get('/alerts')
def approved_alerts(db:Session=Depends(get_db)):
    return [alert_json(db,a) for a in db.scalars(select(SyntheticAlert).where(SyntheticAlert.status=='APPROVED').order_by(SyntheticAlert.id.desc()).limit(100))]


@router.get('/admin/alerts')
def admin_alerts(db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    return [alert_json(db,a) for a in db.scalars(select(SyntheticAlert).order_by(SyntheticAlert.id.desc()).limit(100))]


@router.post('/admin/alerts/{alert_id}/approve')
def approve_alert(alert_id:int,db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    if not get_settings().synthetic_demo_enabled:raise HTTPException(403,'Synthetic alert demonstration is disabled')
    alert=db.scalar(select(SyntheticAlert).where(SyntheticAlert.id==alert_id).with_for_update())
    if alert is None:raise HTTPException(404,'Synthetic alert not found')
    if alert.status=='REJECTED':raise HTTPException(409,'A rejected synthetic alert cannot be approved')
    if alert.status=='PENDING':
        alert.status='APPROVED';alert.reviewed_by=user.id;alert.reviewed_at=datetime.now(timezone.utc);db.commit();db.refresh(alert)
    return alert_json(db,alert)
