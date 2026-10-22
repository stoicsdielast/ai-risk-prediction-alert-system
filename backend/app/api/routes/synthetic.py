"""Synthetic weather replay and isolated approval demonstration."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
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
from app.services.synthetic_alert_service import create_pending
from app.schemas.alert import AlertClosureRequest, _utc

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
    location_id:int = Field(gt=0)
    timestamp:datetime
    test_alert:bool = Field(default=False, strict=True)

    @field_validator('timestamp')
    @classmethod
    def require_timezone(cls,value):
        if value.tzinfo is None:raise ValueError('Timestamp requires an explicit timezone')
        return value


def alert_json(db,alert,*,admin=False):
    prediction=db.get(SyntheticPrediction,alert.prediction_id);location=db.get(Location,prediction.location_id)
    result = {'id':alert.id,'prediction_id':prediction.id,'status':alert.status,'source_type':'synthetic','notice':NOTICE,'is_test':alert.is_test,
        'location_id':location.id,'slug':location.slug,'location_name':location.name,'risk_category':prediction.risk_category,
        'probability':prediction.probability,'timestamp':_utc(prediction.observed_at).isoformat(),'horizon_hours':24,
        'model_version':prediction.model_version,'message':f'{NOTICE}: {"TEST ALERT — " if alert.is_test else ""}provisional {prediction.risk_category} risk for {location.name}. No emergency warning.',
        'reviewed_at':_utc(alert.reviewed_at).isoformat() if alert.reviewed_at else None}
    if admin:
        result.update(created_by=alert.created_by, created_at=_utc(alert.created_at), reviewed_by=alert.reviewed_by,
            acknowledged_by=alert.acknowledged_by, acknowledged_at=_utc(alert.acknowledged_at),
            closed_by=alert.closed_by, closed_at=_utc(alert.closed_at), closure_reason=alert.closure_reason)
    return result


@router.post('/admin/alerts',status_code=201)
def create_alert(data:AlertRequest,db:Session=Depends(get_db),user:User=Depends(require_met_admin),model=Depends(get_synthetic_model)):
    if not get_settings().synthetic_demo_enabled:raise HTTPException(403,'Synthetic alert demonstration is disabled')
    timestamp=timestamp_utc(data.timestamp)
    # Serialize creation for this location, including first prediction insertion.
    location=db.scalar(select(Location).where(Location.id==data.location_id).with_for_update())
    if location is None or not location.is_active:raise HTTPException(404,'Unknown active map location')
    observation=db.get(SyntheticObservation,(VERSION,location.id,timestamp))
    if observation is None:raise HTTPException(404,'Synthetic weather has not been imported for this timestamp')
    try:result=model.predict(location.id,timestamp)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if (result['status']!='ok' or result.get('risk_category') not in ['LOW','MODERATE','HIGH','VERY_HIGH']
        or result.get('probability') is None or not 0 <= result['probability'] <= 1):
        raise HTTPException(422,'A complete eligible synthetic forecast is required, including for test alerts')
    if result['risk_category'] not in ['HIGH','VERY_HIGH'] and not data.test_alert:
        raise HTTPException(422,'LOW/MODERATE forecasts require an explicitly marked isolated test alert')
    prediction=db.scalar(select(SyntheticPrediction).where(SyntheticPrediction.dataset_version==VERSION,SyntheticPrediction.location_id==location.id,
        SyntheticPrediction.observed_at==timestamp,SyntheticPrediction.model_version==result['model_version']))
    if prediction is None:
        prediction=SyntheticPrediction(dataset_version=VERSION,location_id=location.id,observed_at=timestamp,model_version=result['model_version'],probability=result['probability'],risk_category=result['risk_category'])
        db.add(prediction);db.flush()
    alert=create_pending(db,prediction,user.id,test_alert=data.test_alert)
    db.commit();db.refresh(alert)
    return alert_json(db,alert,admin=True)


@router.get('/alerts')
def approved_alerts(offset:int=Query(default=0,ge=0),limit:int=Query(default=100,ge=1,le=200),db:Session=Depends(get_db)):
    return [alert_json(db,a) for a in db.scalars(select(SyntheticAlert).where(SyntheticAlert.status=='APPROVED').order_by(SyntheticAlert.id.desc()).offset(offset).limit(limit))]


@router.get('/admin/alerts')
def admin_alerts(offset:int=Query(default=0,ge=0),limit:int=Query(default=100,ge=1,le=200),db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    return [alert_json(db,a,admin=True) for a in db.scalars(select(SyntheticAlert).order_by(SyntheticAlert.id.desc()).offset(offset).limit(limit))]


@router.post('/admin/alerts/{alert_id}/approve')
def approve_alert(alert_id:int,db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    if not get_settings().synthetic_demo_enabled:raise HTTPException(403,'Synthetic alert demonstration is disabled')
    alert=db.scalar(select(SyntheticAlert).where(SyntheticAlert.id==alert_id).with_for_update())
    if alert is None:raise HTTPException(404,'Synthetic alert not found')
    if alert.status not in ['PENDING','APPROVED']:raise HTTPException(409,'A closed synthetic alert cannot be approved')
    if alert.status=='PENDING':
        alert.status='APPROVED';alert.reviewed_by=user.id;alert.reviewed_at=datetime.now(timezone.utc);db.commit();db.refresh(alert)
    return alert_json(db,alert,admin=True)


@router.post('/admin/alerts/{alert_id}/acknowledge')
def acknowledge_alert(alert_id:int,db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    alert=db.scalar(select(SyntheticAlert).where(SyntheticAlert.id==alert_id).with_for_update())
    if alert is None:raise HTTPException(404,'Synthetic alert not found')
    if alert.status!='APPROVED':raise HTTPException(409,'Only approved synthetic alerts can be acknowledged')
    if alert.acknowledged_at is None:
        alert.acknowledged_by=user.id;alert.acknowledged_at=datetime.now(timezone.utc);db.commit()
    return alert_json(db,alert,admin=True)


def close_synthetic(db,alert_id,user,data,target):
    alert=db.scalar(select(SyntheticAlert).where(SyntheticAlert.id==alert_id).with_for_update())
    if alert is None:raise HTTPException(404,'Synthetic alert not found')
    allowed=['APPROVED'] if target=='RESOLVED' else ['PENDING','APPROVED']
    if alert.status not in allowed:raise HTTPException(409,f'Cannot {target.lower()} a {alert.status} synthetic alert')
    alert.status=target;alert.closed_by=user.id;alert.closed_at=datetime.now(timezone.utc);alert.closure_reason=data.reason
    db.commit()
    return alert_json(db,alert,admin=True)


@router.post('/admin/alerts/{alert_id}/resolve')
def resolve_alert(alert_id:int,data:AlertClosureRequest,db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    return close_synthetic(db,alert_id,user,data,'RESOLVED')


@router.post('/admin/alerts/{alert_id}/cancel')
def cancel_alert(alert_id:int,data:AlertClosureRequest,db:Session=Depends(get_db),user:User=Depends(require_met_admin)):
    return close_synthetic(db,alert_id,user,data,'CANCELLED')
