"""Explicit local artifact provisioning; never trains in the worker."""
import argparse
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

from sklearn.ensemble import HistGradientBoostingRegressor
from ai.energy_forecaster import EnergyForecaster
from anomaly.artifacts import Bundle


class ArtifactError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def versions():
    return {n:importlib.metadata.version(n) for n in ('numpy','scikit-learn','torch','joblib')}


def validate(primary,bundle):
    if not isinstance(primary.model,HistGradientBoostingRegressor) or primary.model.n_features_in_ != 20:
        raise ArtifactError('Primary forecast must be a 20-feature HGB artifact')
    if not bundle.metadata.get('threshold_version'):
        raise ArtifactError('Anomaly artifact needs an explicit threshold_version; provision a calibrated bundle')
    expected='quantiles-v1-'+hashlib.sha256(json.dumps(bundle.thresholds,sort_keys=True).encode()).hexdigest()[:16]
    if bundle.metadata['threshold_version'] != expected:
        raise ArtifactError('Anomaly threshold version does not match thresholds')
    if primary.allowed_sources != bundle.metadata['allowed_sources']:
        raise ArtifactError('HGB and anomaly artifacts must bind the same sources and measurement semantics')


@dataclass
class LoadedArtifacts:
    primary: EnergyForecaster
    anomaly: Bundle
    manifest_sha256: str
    entries: dict

    def registry(self):
        rows=[]
        for role in ('primary_forecast','residual_reference','isolation_forest','autoencoder','residual'):
            primary=role=='primary_forecast'
            metadata=self.primary.metadata if primary else self.anomaly.metadata
            rf=role in ('residual_reference','residual')
            entry=self.entries['hgb' if primary else 'anomaly']
            version=metadata['model_version']
            feature=metadata['feature_version'] if not rf else metadata['rf_feature_version']
            rows.append({'model_id':entry['sha256']+':'+role,'artifact_sha256':entry['sha256'],'role':role,
                         'model_version':version,'feature_version':feature,
                         'threshold_version':None if primary else metadata['threshold_version'],
                         'maturity':'existing' if primary else 'experimental',
                         'details':{'feature_names':metadata['feature_names'] if not rf else metadata['rf_feature_names'],
                                    'allowed_sources':metadata['allowed_sources'],
                                    'thresholds':None if primary else self.anomaly.thresholds,
                                    'horizon_seconds':600}})
        return rows


def load_manifest(path):
    path=Path(path)
    if not path.is_file():
        raise ArtifactError('Artifact manifest missing. Run python -m integration.artifacts prepare or register; see docs/stage5/5a-runbook.md')
    try:
        manifest=json.loads(path.read_text())
        if manifest.get('schema_version') != 1 or manifest.get('libraries') != versions():
            raise ArtifactError('Artifact manifest dependency versions differ; use pinned requirements or provision compatible local artifacts')
        paths={name:(path.parent/entry['path']).resolve() for name,entry in manifest['artifacts'].items()}
        for name in ('hgb','anomaly'):
            if not paths[name].is_file() or sha256(paths[name]) != manifest['artifacts'][name]['sha256']:
                raise ArtifactError(f'{name} artifact missing or checksum mismatch; provision verified local artifacts')
        primary,bundle=EnergyForecaster.load(paths['hgb']),Bundle.load(paths['anomaly'])
        validate(primary,bundle)
        return LoadedArtifacts(primary,bundle,sha256(path),manifest['artifacts'])
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError('Cannot load trusted local artifacts; verify paths, hashes and pinned versions') from exc


def register(hgb,anomaly,output):
    import os
    output=Path(output).resolve()
    if output.exists():
        raise ArtifactError('Manifest already exists; use a new local output path')
    primary,bundle=EnergyForecaster.load(hgb),Bundle.load(anomaly)
    validate(primary,bundle)
    output.parent.mkdir(parents=True,exist_ok=True)
    artifacts={name:{'path':os.path.relpath(Path(path).resolve(),output.parent),'sha256':sha256(path)}
               for name,path in [('hgb',hgb),('anomaly',anomaly)]}
    output.write_text(json.dumps({'schema_version':1,'libraries':versions(),'artifacts':artifacts},indent=2)+'\n')
    load_manifest(output)
    return output


def prepare(dataset,output):
    """Reproduce only frozen training/calibration into new ignored directories."""
    import numpy as np
    from threadpoolctl import threadpool_limits
    from ai.train_energy_forecaster import train_experiment
    from producer.appliances_dataset import dataset_sha256,iter_appliances
    from anomaly.run_experiment import PROTOCOL
    from anomaly.features import collect
    from anomaly.train import fit_models
    from anomaly.residual import score_batch
    from anomaly.calibrate import calibrate
    output=Path(output)
    if output.exists():
        raise ArtifactError('Provisioning directory exists; use a new directory or register existing trusted artifacts')
    config=json.loads(PROTOCOL.read_text())
    if dataset_sha256(dataset) != config['dataset_sha256']:
        raise ArtifactError('Dataset checksum differs from frozen Appliances protocol')
    output.mkdir(parents=True)
    with threadpool_limits(1):
        print('Provisioning HGB using frozen Stage 2 configuration',flush=True)
        train_experiment(dataset,output/'hgb')
        records=list(iter_appliances(dataset))
        frame,x,rx=collect(records)
        train=(frame.measurement_timestamp>=config['train_start'])&(frame.measurement_timestamp<config['calibration_start'])
        calibration=((frame.measurement_timestamp>=config['calibration_start'])&(frame.measurement_timestamp<config['validation_start'])).to_numpy()
        print('Provisioning train-only anomaly models and calibration (no benchmark rerun)',flush=True)
        bundle=fit_models(frame,x,rx,train,records[0],config)
        bundle.thresholds=calibrate(score_batch(bundle,frame[calibration].reset_index(drop=True),x[calibration],rx[calibration]),config['quantiles'])
        bundle.metadata['threshold_version']='quantiles-v1-'+hashlib.sha256(json.dumps(bundle.thresholds,sort_keys=True).encode()).hexdigest()[:16]
        bundle.metadata['dataset_sha256']=config['dataset_sha256']
        bundle.save(output/'bundle.joblib')
    return register(output/'hgb/model.joblib',output/'bundle.joblib',output/'manifest.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    r=sub.add_parser('register');r.add_argument('--hgb',required=True,type=Path);r.add_argument('--anomaly',required=True,type=Path);r.add_argument('--output',required=True,type=Path)
    p=sub.add_parser('prepare');p.add_argument('--dataset',required=True,type=Path);p.add_argument('--output',type=Path,default=Path('artifacts/mvp/local'))
    args=parser.parse_args()
    try:
        result=register(args.hgb,args.anomaly,args.output) if args.command=='register' else prepare(args.dataset,args.output)
        print(f'Verified local artifact manifest: {result}')
    except (ArtifactError,FileNotFoundError) as exc:
        parser.exit(2,str(exc)+'\n')


if __name__=='__main__':
    main()
