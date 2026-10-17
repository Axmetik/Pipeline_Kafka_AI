"""Contract for the existing four-feature IoT models (not an energy schema)."""
import json
import math
from datetime import datetime

FEATURES = ("temperature", "humidity", "light", "voltage")
RAW_FIELDS = ("sensor_id", "timestamp", *FEATURES)
PROCESSED_FIELDS = (*RAW_FIELDS,
    "is_temperature_anomaly", "is_humidity_anomaly", "ai_anomaly",
    "iforest_anomaly_score", "autoencoder_anomaly",
    "autoencoder_reconstruction_error", "autoencoder_threshold",
    "autoencoder_training_loss")


class InvalidMessage(ValueError):
    pass


def validate_record(data):
    if not isinstance(data, dict):
        raise InvalidMessage("Message must be a JSON object")
    missing = [field for field in RAW_FIELDS if field not in data]
    if missing:
        raise InvalidMessage(f"Missing fields: {', '.join(missing)}")
    sensor_id = data["sensor_id"]
    if isinstance(sensor_id, bool) or not isinstance(sensor_id, int) or sensor_id < 1:
        raise InvalidMessage("sensor_id must be a positive integer")
    timestamp = data["timestamp"]
    if not isinstance(timestamp, str):
        raise InvalidMessage("timestamp must be an ISO 8601 datetime string")
    try:
        datetime.fromisoformat(timestamp)
        if "T" not in timestamp and " " not in timestamp:
            raise ValueError("Time component required")
    except ValueError as exc:
        raise InvalidMessage("timestamp must contain a valid ISO 8601 date and time") from exc
    # Preserve legacy Intel Lab timestamps: their timezone is not known.
    result = {"sensor_id": sensor_id, "timestamp": timestamp}
    for field in FEATURES:
        value = data[field]
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise InvalidMessage(f"{field} must be a finite number")
        try:
            number = float(value)
        except (ValueError, OverflowError) as exc:
            raise InvalidMessage(f"{field} must be a finite number") from exc
        if not math.isfinite(number):
            raise InvalidMessage(f"{field} must be a finite number")
        result[field] = number
    return result


def decode_record(payload):
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise InvalidMessage(f"Invalid JSON/UTF-8: {exc}") from exc
    return validate_record(data)
