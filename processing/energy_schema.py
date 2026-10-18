"""Energy contract validation and normalization; no inferred timezones."""
import copy
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jsonschema import Draft202012Validator
from processing.message_schema import InvalidMessage

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/energy-message-v1.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text()))


def parse_timestamp(value):
    try:
        if not isinstance(value, str) or ("T" not in value and " " not in value):
            raise ValueError("date and time required")
        return datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise InvalidMessage("Invalid measurement timestamp") from exc


def validate_energy(data):
    error = next(VALIDATOR.iter_errors(data), None)
    if error:
        raise InvalidMessage(f"Schema: {error.message}")
    result = copy.deepcopy(data)
    timestamp = parse_timestamp(result["timestamp"])
    # Named zones on naive times require an explicit adapter, not silent localization.
    if timestamp.tzinfo is None and result["timezone"] is not None:
        raise InvalidMessage("A timezone label requires an explicit timestamp offset")
    if result["timezone"] is not None:
        try:
            zone = ZoneInfo(result["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise InvalidMessage("Unknown timezone label") from exc
        if timestamp.astimezone(zone).utcoffset() != timestamp.utcoffset():
            raise InvalidMessage("Timezone label conflicts with timestamp offset")
    try:
        energy = float(result["energy"]["value"])
        energy *= 1000 if result["energy"]["unit"] == "kWh" else 1
    except (ValueError, OverflowError) as exc:
        raise InvalidMessage("Energy must be finite") from exc
    if not math.isfinite(energy):
        raise InvalidMessage("Energy must be finite")
    result["energy"]["value"] = energy
    result["energy"]["unit"] = "Wh"
    flags = []
    for field in ("temperature_c", "relative_humidity_pct"):
        value = result["environment"].get(field)
        try:
            value = float(value) if value is not None else None
        except OverflowError:
            value = None
        if value is not None and (not math.isfinite(value) or
                (field == "relative_humidity_pct" and not 0 <= value <= 100)):
            value = None
        result["environment"][field] = value
        if value is None:
            flags.append(f"missing_or_invalid_{field}")
    for key, value in result["additional_parameters"].items():
        try:
            finite = value is None or math.isfinite(float(value))
        except OverflowError:
            finite = False
        if not finite:
            raise InvalidMessage(f"Non-finite additional parameter: {key}")
    result["quality_flags"] = flags
    return result


def decode_energy(payload):
    try:
        value = json.loads(payload)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise InvalidMessage(f"Invalid JSON/UTF-8: {exc}") from exc
    return validate_energy(value)
