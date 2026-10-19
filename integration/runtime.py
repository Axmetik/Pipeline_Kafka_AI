"""State adapter only; existing Stage 2/4 inference remains untouched."""
from datetime import datetime,timedelta,timezone
import math
from processing.energy_processor import EnergyProcessor
from processing.energy_schema import validate_energy,parse_timestamp
from processing.message_schema import InvalidMessage
from anomaly.residual import StreamDetector
from anomaly.features import NAMES


def now():
    return datetime.now(timezone.utc)


def clock(value):
    dt=parse_timestamp(value)
    return {'local':dt.replace(tzinfo=None),'utc':dt.astimezone(timezone.utc) if dt.tzinfo else None,
            'basis':'offset_aware' if dt.tzinfo else 'dataset_naive'}


class RecoveryError(RuntimeError):
    pass


class Runtime:
    def __init__(self,artifacts):
        self.artifacts=artifacts
        self.primary=EnergyProcessor()
        self.anomaly=StreamDetector(artifacts.anomaly)
        self.registry={row['role']:row for row in artifacts.registry()}

    def compatible(self,record):
        try:
            self.artifacts.primary.validate_source(record)
            self.artifacts.anomaly.validate_source(record)
            return True
        except InvalidMessage:
            return False

    def compute(self,raw):
        record=validate_energy(raw)
        compatible=self.compatible(record)
        timestamp=parse_timestamp(record['timestamp'])
        forecasts=[];scores=[]
        origin=timestamp.isoformat();target=(timestamp+timedelta(seconds=600)).isoformat()
        primary_value=None;primary_status='incompatible';result=None;anomaly=None
        if compatible:
            result=self.primary.process(record)
            primary_value=self.artifacts.primary.predict(result['features']) if result['features'] is not None else None
            primary_status='ready' if primary_value is not None else 'warmup'
            anomaly=self.anomaly.process(raw)
        key=(record['building_id'],record['source_id'])
        pending=self.anomaly.pending.get(key) if compatible else None
        for purpose,value,status,generated in [
            ('primary_forecast',primary_value,primary_status,now()),
            ('residual_reference',pending['value'] if pending else None,
             'ready' if pending else ('warmup' if compatible else 'incompatible'),
             datetime.fromisoformat(pending['generated_at']) if pending else now())]:
            model=self.registry[purpose]
            forecasts.append({'model_id':model['model_id'],'purpose':purpose,'model_version':model['model_version'],
                              'feature_version':model['feature_version'],'forecast_origin':origin,
                              'forecast_target_timestamp':target,'target_time_local':clock(target)['local'],
                              'target_time_utc':clock(target)['utc'],'generated_at':generated,
                              'predicted_energy_wh':value,'status':status,'horizon_seconds':600})
        for name in NAMES:
            model=self.registry[name]
            status=anomaly[name+'_status'] if compatible else 'incompatible'
            status='ready' if status=='ok' else status
            scores.append({'model_id':model['model_id'],'detector':name,'model_version':model['model_version'],
                           'feature_version':model['feature_version'],'threshold_version':model['threshold_version'],
                           'maturity':'experimental','score':anomaly[name] if compatible else None,
                           'threshold':self.artifacts.anomaly.thresholds['0.99'][name],
                           'flag':anomaly[name+'_flag'] if compatible else None,'status':status,
                           'prediction_wh':anomaly['prediction_wh'] if compatible and name=='residual' else None,
                           'signed_residual_wh':anomaly['signed_residual_wh'] if compatible and name=='residual' else None,
                           'forecast_origin':anomaly['forecast_origin'] if compatible and name=='residual' else None,
                           'forecast_target_timestamp':anomaly['forecast_target_timestamp'] if compatible and name=='residual' else None,
                           'reference_generated_at':datetime.fromisoformat(anomaly['forecast_generated_at_utc'])
                           if compatible and name=='residual' and anomaly['forecast_generated_at_utc'] else None})
        for row in [*forecasts,*scores]:
            value=row.get('score',row.get('predicted_energy_wh'))
            if value is not None and not math.isfinite(value):
                raise RecoveryError('Nonfinite model output; stopping before persistence')
        return {'compatible':compatible,'feature_status':primary_status,
                'gap_detected':bool(result and result['gap_detected']), 'forecasts':forecasts,'scores':scores}

    def restore(self,histories):
        for records,persisted in histories:
            last=None
            for raw in records:
                last=self.compute(raw)
            if last is None:
                continue
            expected={f['purpose']:f for f in persisted}
            if set(expected) != {'primary_forecast','residual_reference'}:
                raise RecoveryError('Missing persisted pending forecasts; recovery cannot continue')
            for forecast in last['forecasts']:
                old=expected[forecast['purpose']]
                a,b=forecast['predicted_energy_wh'],old['predicted_energy_wh']
                if (forecast['status'] != old['status'] or forecast['forecast_origin'] != old['forecast_origin']
                        or forecast['forecast_target_timestamp'] != old['forecast_target_timestamp']
                        or ((a is None)!=(b is None)) or (a is not None and not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12))):
                    raise RecoveryError('Committed history/artifact cannot reproduce persisted forecast')
            key=(records[-1]['building_id'],records[-1]['source_id'])
            pending=self.anomaly.pending.get(key)
            if pending:
                old=expected['residual_reference']
                # Preserve original formation time and value; do not rewrite DB history.
                self.anomaly.pending[key]={'origin':old['forecast_origin'],'target':old['forecast_target_timestamp'],
                                          'value':old['predicted_energy_wh'],'generated_at':old['generated_at'].isoformat()}
