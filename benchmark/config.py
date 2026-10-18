"""Read the pre-registered protocol; the CLI has no tuning overrides."""
import hashlib
import json
from pathlib import Path

PROTOCOL_PATH = Path(__file__).with_name('protocol.json')


def load_protocol():
    raw = PROTOCOL_PATH.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()
