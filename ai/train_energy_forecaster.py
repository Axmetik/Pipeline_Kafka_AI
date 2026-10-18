"""Offline chronological training and one-step evaluation on UCI Appliances."""
import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from threadpoolctl import threadpool_limits

from ai.energy_forecaster import EnergyForecaster, source_binding
from processing.energy_schema import validate_energy
from processing.energy_processor import EnergyProcessor, FEATURE_NAMES, FEATURE_VERSION
from processing.message_schema import InvalidMessage
from producer.appliances_dataset import iter_appliances, dataset_sha256, DATASET_URL


def build_samples(records):
    processor = EnergyProcessor()
    pending = {}
    rows = []
    counts = {"received": 0, "valid": 0, "rejected": 0, "insufficient_history": 0, "gaps": 0}
    rejections = []
    for raw in records:
        counts["received"] += 1
        try:
            result = processor.process(validate_energy(raw))
        except InvalidMessage as exc:
            counts["rejected"] += 1
            rejections.append({"event_id": raw.get("event_id"), "reason": str(exc)})
            continue
        counts["valid"] += 1
        counts["gaps"] += int(result["gap_detected"])
        counts["insufficient_history"] += int(result["features"] is None)
        record = result["record"]
        key = (record["building_id"], record["source_id"])
        previous = pending.get(key)
        # A target must be the exact next interval, never the next available row.
        if previous is not None and previous["features"] is not None and previous["forecast_target_timestamp"] == result["forecast_origin"]:
            rows.append({**previous["features"], "forecast_origin": previous["forecast_origin"],
                         "forecast_target_timestamp": result["forecast_origin"],
                         "building_id": key[0], "source_id": key[1],
                         "source_binding": source_binding(record),
                         "actual_energy_wh": record["energy"]["value"]})
        pending[key] = result
    return pd.DataFrame(rows), {**counts, "eligible_samples": len(rows), "rejections": rejections}


def chronological_split(frame, train_fraction=0.8):
    if not 0 < train_fraction < 1 or len(frame) < 20:
        raise ValueError("Need >=20 eligible samples and 0 < train_fraction < 1")
    frame = frame.sort_values("forecast_target_timestamp", kind="stable").reset_index(drop=True)
    boundary = frame.iloc[int(len(frame) * train_fraction)]["forecast_target_timestamp"]
    train = frame[frame.forecast_target_timestamp < boundary].copy()
    test = frame[frame.forecast_target_timestamp >= boundary].copy()
    if len(train) < 10 or len(test) < 2:
        raise ValueError("Insufficient training or test samples")
    return train, test


def metrics(actual, predicted):
    return {"mae_wh": float(mean_absolute_error(actual, predicted)),
            "rmse_wh": float(np.sqrt(mean_squared_error(actual, predicted)))}


def train_experiment(dataset, output, train_fraction=0.8, seed=42, max_iter=100):
    output = Path(output)
    if output.exists():
        raise ValueError("Experiment directory already exists; choose a new run directory")
    frame, quality = build_samples(iter_appliances(dataset))
    train, test = chronological_split(frame, train_fraction)
    # Only sources actually represented in the training partition may be served.
    allowed_sources = [json.loads(value) for value in sorted(
        {json.dumps(binding, sort_keys=True) for binding in train.source_binding})]
    params = {"loss": "squared_error", "max_iter": max_iter, "learning_rate": 0.1,
              "max_leaf_nodes": 31, "min_samples_leaf": 20, "l2_regularization": 0.0,
              "early_stopping": False, "random_state": seed}
    config = {"estimator": "HistGradientBoostingRegressor", "parameters": params,
              "train_fraction": train_fraction, "feature_version": FEATURE_VERSION,
              "feature_names": FEATURE_NAMES, "horizon_seconds": 600,
              "history_records": 7, "prediction_clip_min_wh": 0.0,
              "target": "Appliances", "dataset_sha256": dataset_sha256(dataset),
              "train_target_start": train.forecast_target_timestamp.iloc[0],
              "train_target_end": train.forecast_target_timestamp.iloc[-1],
              "test_target_start": test.forecast_target_timestamp.iloc[0],
              "test_target_end": test.forecast_target_timestamp.iloc[-1],
              "python_version": platform.python_version(), "sklearn_version": sklearn.__version__,
              "numpy_version": np.__version__, "pandas_version": pd.__version__,
              "threads": 1, "allowed_sources": allowed_sources}
    identity = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    metadata = {**config, "model_version": f"hgb-energy-v1-{identity}",
                "trained_at_utc": datetime.now(timezone.utc).isoformat(),
                "dataset_url": DATASET_URL,
                "dataset_citation": "Candanedo (2017), UCI Appliances Energy Prediction, doi:10.24432/C5VC8G",
                "replay_start": (pd.Timestamp(test.forecast_origin.iloc[0]) - pd.Timedelta(minutes=60)).isoformat(),
                "replay_end": test.forecast_target_timestamp.iloc[-1]}
    with threadpool_limits(limits=1):
        model = HistGradientBoostingRegressor(**params)
        model.fit(train[FEATURE_NAMES].to_numpy(dtype=float), train.actual_energy_wh.to_numpy())
        forecaster = EnergyForecaster(model, metadata)
        predicted = forecaster.predict_many(test)
    baseline = test.energy_wh.to_numpy()
    report = {"model_version": metadata["model_version"], "dataset_sha256": config["dataset_sha256"],
              "train_samples": len(train), "test_samples": len(test),
              "ml": metrics(test.actual_energy_wh, predicted),
              "persistence": metrics(test.actual_energy_wh, baseline), "data_quality": quality,
              "evaluation": "chronological one-step; frozen model; observed test history allowed"}
    output.mkdir(parents=True)
    forecaster.save(output / "model.joblib")
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    predictions = test[["building_id", "source_id", "forecast_origin", "forecast_target_timestamp", "actual_energy_wh"]].copy()
    predictions["predicted_energy_wh"] = predicted
    predictions["baseline_energy_wh"] = baseline
    predictions["model_version"] = metadata["model_version"]
    predictions.to_parquet(output / "test_predictions.parquet", index=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--train-fraction", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=100)
    args = parser.parse_args()
    report = train_experiment(args.dataset, args.output, args.train_fraction, args.seed, args.max_iter)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
