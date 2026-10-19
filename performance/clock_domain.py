"""Identity of the Linux kernel monotonic domain; no distributed-clock assumption."""
import json
import os
from pathlib import Path
import time


def domain():
    clock=time.get_clock_info('perf_counter')
    linux=Path('/proc/sys/kernel/random/boot_id').exists()
    return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip() if linux else None,
            'time_namespace':os.readlink('/proc/self/ns/time') if linux else None,
            'implementation':clock.implementation,'monotonic':clock.monotonic,'adjustable':clock.adjustable,
            'resolution_seconds':clock.resolution}


def compatible(domains):
    if not domains:return False
    first=domains[0]
    return all(item==first and item['boot_id'] and item['time_namespace'] and item['monotonic'] and not item['adjustable']
               and item['implementation']=='clock_gettime(CLOCK_MONOTONIC)' for item in domains)


if __name__=='__main__':print(json.dumps(domain()))
