from datetime import datetime, timedelta
import pandas as pd


def energy_records(count=40):
    start = datetime(2016, 1, 1)
    for index in range(count):
        yield {
            "schema_version": "1.0", "event_id": f"event-{index}",
            "building_id": "house", "source_id": "meter", "source_type": "dataset",
            "timestamp": (start + timedelta(minutes=10 * index)).isoformat(),
            "timezone": None, "timestamp_reference": "dataset_label", "interval_seconds": 600,
            "energy": {"value": float(index + 1), "unit": "Wh", "scope": "appliances", "measurement_type": "interval_energy"},
            "environment": {"temperature_c": 20.0, "relative_humidity_pct": 50.0},
            "additional_parameters": {},
        }


def write_csv(path, count=100):
    rows = [{"date": r["timestamp"], "Appliances": r["energy"]["value"],
             "T1": 20.0, "RH_1": 50.0, "lights": 0.0} for r in energy_records(count)]
    pd.DataFrame(rows).to_csv(path, index=False)
