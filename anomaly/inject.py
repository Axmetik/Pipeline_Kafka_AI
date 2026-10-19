"""Deterministic interventions independent of scores; original records unchanged."""
import copy
import numpy as np
import pandas as pd


def train_statistics(frame):
    energy = frame.actual_energy_wh
    hours = pd.to_datetime(frame.measurement_timestamp).dt.hour
    medians = energy.groupby(hours).median()
    low = sorted(medians.index, key=lambda h: (medians[h], h))[:6]
    return {'iqr_wh': max(1., float(energy.quantile(.75) - energy.quantile(.25))),
            'low_hours': [int(h) for h in low], 'p90_wh': float(energy.quantile(.9))}


def scenarios(config, split):
    for kind in config['types']:
        for severity in config['severity_levels']:
            for seed in config[split + '_seeds']:
                yield f'{kind}-s{severity}-seed{seed}', kind, severity, seed
    for seed in config[split + '_seeds']:
        yield f'mixed-seed{seed}', 'mixed', None, seed


def inject(records, prefix, config, stats, kind, severity, seed):
    if prefix < 1 or prefix >= len(records):
        raise ValueError('Injection requires past context and a nonempty partition')
    output = copy.deepcopy(records)
    n = len(records) - prefix
    rng = np.random.default_rng(seed)
    budget = int(config['fraction'] * n)
    occupied = np.zeros(n, dtype=bool)
    labels = np.zeros(n, dtype=bool)
    events = []
    order = list(rng.permutation(list(config['types']))) if kind == 'mixed' else [kind]
    used = 0
    while used < budget:
        event_kind = order[len(events) % len(order)]
        level = int(rng.integers(3)) if kind == 'mixed' else severity
        settings = config['types'][event_kind]
        minimum, maximum = settings['duration']
        duration = min(int(rng.integers(minimum, maximum + 1)), budget - used)
        if duration < minimum:
            break
        start = None
        for _ in range(config['max_attempts']):
            candidate = int(rng.integers(0, n - duration + 1))
            lo = max(0, candidate - config['minimum_gap'])
            hi = min(n, candidate + duration + config['minimum_gap'])
            if occupied[lo:hi].any():
                continue
            if event_kind == 'context_load' and pd.Timestamp(records[prefix + candidate]['timestamp']).hour not in stats['low_hours']:
                continue
            start = candidate
            break
        if start is None:
            break
        end = start + duration - 1
        strength = settings['strength'][level]
        before = output[prefix + start - 1]['energy']['value']
        changes = []
        for offset, index in enumerate(range(start, end + 1)):
            raw = records[prefix + index]['energy']['value']
            if event_kind == 'drop':
                value = raw * strength
            elif event_kind == 'stuck':
                value = before
            else:
                factor = (offset + 1) / duration if event_kind == 'drift' else 1.
                value = raw + factor * strength * stats['iqr_wh']
            output[prefix + index]['energy']['value'] = float(value)
            changes.append({'index': index, 'timestamp': records[prefix + index]['timestamp'],
                            'original_wh': raw, 'modified_wh': float(value)})
        labels[start:end + 1] = True
        occupied[start:end + 1] = True
        events.append({'event_id': len(events), 'type': event_kind, 'severity': level,
                       'strength': strength, 'start': start, 'end': end, 'duration': duration,
                       'start_timestamp': changes[0]['timestamp'], 'end_timestamp': changes[-1]['timestamp'],
                       'changes': changes})
        used += duration
    return output, labels, events, {'requested_points': budget, 'labeled_points': int(labels.sum()),
                                    'numerically_changed_points': sum(c['original_wh'] != c['modified_wh'] for e in events for c in e['changes']),
                                    'achieved_fraction': float(labels.mean())}
