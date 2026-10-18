"""UCI Appliances CSV adapter. Timestamp labels remain timezone-naive."""
import hashlib
import math
from pathlib import Path

import pandas as pd

DATASET_URL = "https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip"


def dataset_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def optional_number(value):
    if pd.isna(value):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def iter_appliances(path, building_id="appliances-house-1", source_id="uci-appliances",
                    start=None, end=None, limit=None):
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")
    frame = pd.read_csv(path)
    required = {"date", "Appliances", "T1", "RH_1"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Missing CSV columns: {sorted(required - set(frame.columns))}")
    dates = pd.to_datetime(frame["date"], errors="raise")
    if dates.dt.tz is not None:
        raise ValueError("Appliances adapter expects original timezone-naive labels")
    if not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError("Dataset must have strictly increasing timestamps")
    frame = frame.assign(date=dates)
    if start is not None:
        frame = frame[frame.date >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame.date <= pd.Timestamp(end)]
    if limit is not None:
        frame = frame.head(limit)
    for row in frame.to_dict("records"):
        timestamp = row["date"].isoformat()
        extra = {}
        for key, value in row.items():
            if key not in {"date", "Appliances", "T1", "RH_1", "rv1", "rv2"}:
                extra[key] = optional_number(value)
        yield {
            "schema_version": "1.0",
            "event_id": f"{building_id}:{source_id}:{timestamp}",
            "building_id": building_id, "source_id": source_id, "source_type": "dataset",
            "timestamp": timestamp, "timezone": None, "timestamp_reference": "dataset_label",
            "interval_seconds": 600,
            "energy": {"value": optional_number(row["Appliances"]), "unit": "Wh",
                       "measurement_type": "interval_energy", "scope": "appliances"},
            "environment": {"temperature_c": optional_number(row["T1"]),
                            "relative_humidity_pct": optional_number(row["RH_1"])},
            "additional_parameters": extra,
        }
