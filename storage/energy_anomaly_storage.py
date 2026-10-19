"""Independent anomaly archive; stable types also support all-warmup batches."""
import pyarrow as pa
from storage.parquet_storage import ParquetStorage
from anomaly.features import NAMES

FIELDS = [(name, pa.string()) for name in ['event_id', 'building_id', 'source_id', 'measurement_timestamp',
          'detected_at_utc', 'forecast_origin', 'forecast_target_timestamp', 'forecast_generated_at_utc',
          'model_version', 'feature_version', 'rf_feature_version', 'threshold_version']]
FIELDS += [(name, pa.float64()) for name in ['actual_energy_wh', 'prediction_wh', 'signed_residual_wh', *NAMES]]
FIELDS += [(name, pa.bool_()) for name in ['feature_ready', 'residual_ready', 'gap_detected']]
for detector in NAMES:
    FIELDS.extend([(detector + '_threshold', pa.float64()), (detector + '_flag', pa.bool_()), (detector + '_status', pa.string())])
SCHEMA = pa.schema(FIELDS)


def anomaly_storage(path, batch_size=1000):
    return ParquetStorage(str(path), batch_size, columns=SCHEMA.names, arrow_schema=SCHEMA)
