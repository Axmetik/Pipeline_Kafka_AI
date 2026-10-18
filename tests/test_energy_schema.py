import copy
import json
import unittest

from processing.energy_schema import validate_energy, decode_energy
from processing.message_schema import InvalidMessage
from energy_helpers import energy_records


class EnergySchemaTests(unittest.TestCase):
    def test_units_and_timezone_preservation(self):
        record = next(energy_records())
        record['energy'].update(value=0.12, unit='kWh')
        result = validate_energy(record)
        self.assertEqual(result['energy']['value'], 120)
        self.assertIsNone(result['timezone'])
        self.assertEqual(result['timestamp'], record['timestamp'])
        self.assertEqual(record['energy']['unit'], 'kWh')

    def test_reject_energy_units_values_and_times(self):
        base = next(energy_records())
        cases = []
        for field, value in [('value', None), ('value', -1), ('value', float('nan')),
                             ('value', float('inf')), ('value', True), ('unit', 'W'),
                             ('measurement_type', 'cumulative')]:
            record = copy.deepcopy(base)
            record['energy'][field] = value
            cases.append(record)
        cases += [{**base, 'timestamp': '2016-01-01'}, {**base, 'timezone': 'Europe/Brussels'},
                  {**base, 'schema_version': '2.0'}]
        for record in cases:
            with self.subTest(record=record), self.assertRaises(InvalidMessage):
                validate_energy(record)
        for payload in [b'{invalid', b'\xff', b'null', None]:
            with self.assertRaises(InvalidMessage):
                decode_energy(payload)

    def test_missing_auxiliary_values_have_quality_flags(self):
        record = next(energy_records())
        record['environment'] = {'temperature_c': float('nan'), 'relative_humidity_pct': 101}
        result = validate_energy(record)
        self.assertIsNone(result['environment']['temperature_c'])
        self.assertIsNone(result['environment']['relative_humidity_pct'])
        self.assertEqual(len(result['quality_flags']), 2)
        record['environment'] = {}
        self.assertEqual(len(decode_energy(json.dumps(record).encode())['quality_flags']), 2)

    def test_explicit_timezone_must_match_offset(self):
        record = next(energy_records())
        record['timestamp'] += '+00:00'
        record['timezone'] = 'UTC'
        self.assertEqual(validate_energy(record)['timezone'], 'UTC')
        record['timezone'] = 'Europe/Brussels'
        with self.assertRaises(InvalidMessage):
            validate_energy(record)
