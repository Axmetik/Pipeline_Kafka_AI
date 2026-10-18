"""Select unit or broker integration checks explicitly, without silent Kafka skips."""
import argparse
import os
from pathlib import Path
import sys
import unittest


def individual_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from individual_tests(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['unit', 'kafka', 'all'], required=True)
    args = parser.parse_args()
    os.environ['RUN_KAFKA_SMOKE'] = '0' if args.suite == 'unit' else '1'
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    discovered = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py')
    selected = unittest.TestSuite()
    for test in individual_tests(discovered):
        broker_test = test.id().split('.')[0].endswith('kafka_smoke')
        if args.suite == 'all' or broker_test == (args.suite == 'kafka'):
            selected.addTest(test)
    if not selected.countTestCases():
        raise SystemExit('No tests selected')
    result = unittest.TextTestRunner(verbosity=2).run(selected)
    raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)


if __name__ == '__main__':
    main()
