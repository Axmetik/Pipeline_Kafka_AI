import copy
import hashlib
import json
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
from ai.energy_forecaster import EnergyForecaster
from processing.energy_processor import FEATURE_NAMES,FEATURE_VERSION
from anomaly_helpers import fixture
from integration.artifacts import register,load_manifest


def artifact_fixture(root,always_flag=False):
    records,frame,x,rx,bundle,config=fixture()
    model=HistGradientBoostingRegressor(max_iter=3,min_samples_leaf=5,random_state=42,early_stopping=False)
    model.fit(x[144:240],frame.actual_energy_wh.iloc[144:240])
    primary=EnergyForecaster(model,{'feature_version':FEATURE_VERSION,'feature_names':FEATURE_NAMES,
          'horizon_seconds':600,'model_version':'test-hgb-20-v1','allowed_sources':copy.deepcopy(bundle.metadata['allowed_sources'])})
    if always_flag:
        bundle.thresholds['0.99']={k:0. for k in bundle.thresholds['0.99']}
    bundle.metadata['threshold_version']='quantiles-v1-'+hashlib.sha256(json.dumps(bundle.thresholds,sort_keys=True).encode()).hexdigest()[:16]
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    primary.save(root/'hgb.joblib');bundle.save(root/'anomaly.joblib')
    manifest=register(root/'hgb.joblib',root/'anomaly.joblib',root/'manifest.json')
    return records,manifest,load_manifest(manifest)
