"""Separate measurement/forecast archives with stable nullable Arrow types."""
import pyarrow as pa
from storage.parquet_storage import ParquetStorage

MEASUREMENT_SCHEMA = pa.schema([
    ("event_id", pa.string()), ("building_id", pa.string()), ("source_id", pa.string()),
    ("source_type", pa.string()), ("measurement_timestamp", pa.string()),
    ("received_at_utc", pa.string()), ("timezone", pa.string()),
    ("timestamp_reference", pa.string()), ("interval_seconds", pa.int64()),
    ("energy_scope", pa.string()), ("actual_energy_wh", pa.float64()),
    ("temperature_c", pa.float64()), ("relative_humidity_pct", pa.float64()),
    ("quality_flags_json", pa.string()), ("additional_parameters_json", pa.string()),
    ("feature_status", pa.string()), ("gap_detected", pa.bool_()),
])
FORECAST_SCHEMA = pa.schema([
    ("event_id", pa.string()), ("building_id", pa.string()), ("source_id", pa.string()),
    ("forecast_origin", pa.string()), ("forecast_generated_at_utc", pa.string()),
    ("forecast_target_timestamp", pa.string()), ("timezone", pa.string()),
    ("timestamp_reference", pa.string()), ("horizon_seconds", pa.int64()),
    ("predicted_energy_wh", pa.float64()), ("baseline_energy_wh", pa.float64()),
    ("status", pa.string()), ("model_version", pa.string()),
])


def energy_storages(settings):
    return (
        ParquetStorage(str(settings.output_dir / "measurements"), settings.parquet_batch_size,
                       columns=MEASUREMENT_SCHEMA.names, arrow_schema=MEASUREMENT_SCHEMA),
        ParquetStorage(str(settings.output_dir / "forecasts"), settings.parquet_batch_size,
                       columns=FORECAST_SCHEMA.names, arrow_schema=FORECAST_SCHEMA),
    )
