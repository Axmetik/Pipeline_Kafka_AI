"""Explicit point/event metrics; no point adjustment or implicit grace period."""
import numpy as np
import pandas as pd


def runs(flags, times):
    groups, start, previous = [], None, None
    for index, (flag, timestamp) in enumerate(zip(flags, pd.to_datetime(times))):
        contiguous = previous is not None and timestamp - previous == pd.Timedelta(minutes=10)
        if start is not None and (not flag or not contiguous):
            groups.append((start, index - 1)); start = None
        if flag and start is None:
            start = index
        previous = timestamp
    if start is not None:
        groups.append((start, len(flags) - 1))
    return groups


def ratio(a, b, default=0.):
    return float(a / b) if b else default


def metrics(flags, labels, times, events, tail_intervals=144):
    flags, labels = np.asarray(flags, dtype=bool), np.asarray(labels, dtype=bool)
    tp, fp = int((flags & labels).sum()), int((flags & ~labels).sum())
    fn, tn = int((~flags & labels).sum()), int((~flags & ~labels).sum())
    precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
    groups = runs(flags, times)
    matched, outcomes = {}, []
    for start, end in groups:
        candidates = [e for e in events if e['event_id'] not in matched and e['start'] <= end and e['end'] >= start]
        if candidates:
            event = min(candidates, key=lambda e: e['start'])
            matched[event['event_id']] = max(start, event['start'])
    for event in events:
        first = matched.get(event['event_id'])
        outcomes.append({k: event[k] for k in ('event_id', 'type', 'severity', 'start', 'end')} | {
            'detected': first is not None, 'delay_minutes': (first - event['start']) * 10 if first is not None else None})
    delays = [e['delay_minutes'] for e in outcomes if e['detected']]
    ep, er = ratio(len(matched), len(groups)), ratio(len(matched), len(events), None)
    tail = np.zeros(len(flags), dtype=bool)
    for event in events:
        tail[event['end'] + 1:min(len(flags), event['end'] + 1 + tail_intervals)] = True
    tail &= ~labels
    result = {'count': len(flags), 'tp': tp, 'fp_synthetic': fp, 'fn': fn, 'tn_synthetic': tn,
              'precision': precision, 'recall': recall, 'f1': ratio(2 * precision * recall, precision + recall),
              'fpr_synthetic': ratio(fp, fp + tn, None), 'alarms': int(flags.sum()),
              'alarms_per_day': ratio(int(flags.sum()), len(flags) / 144),
              'events': len(events), 'alarm_episodes': len(groups), 'matched_events': len(matched),
              'event_precision': ep, 'event_recall': er,
              'event_f1': ratio(2 * ep * er, ep + er) if er is not None else None,
              'missed_events': len(events) - len(matched),
              'missed_fraction': ratio(len(events) - len(matched), len(events), None),
              'delay_median_minutes': float(np.median(delays)) if delays else None,
              'delay_p95_minutes': float(np.percentile(delays, 95)) if delays else None,
              'during_event_alarms': tp, 'post_event_alarms': int((flags & tail).sum()),
              'post_event_points': int(tail.sum()), 'other_background_alarms': int((flags & ~labels & ~tail).sum())}
    return result, outcomes


def choose_detector(validation, clean, names, limit):
    candidates, summary = [], {}
    for name in names:
        rows = validation[(validation.detector == name) & validation.scenario.str.startswith('mixed-') & (validation['quantile'] == .99)]
        control = clean[(clean.detector == name) & (clean['quantile'] == .99)].iloc[0]
        rate = control['background_alarm_rate']
        f1 = float(rows.event_f1.mean())
        delay = rows.delay_median_minutes.mean()
        delay = float(delay) if pd.notna(delay) else None
        summary[name] = {'validation_event_f1': f1, 'background_alarm_rate': float(rate),
                         'matched_event_median_delay_mean_minutes': delay, 'eligible': bool(rate <= limit)}
        if rate <= limit:
            candidates.append(( -f1, delay if delay is not None else float('inf'), rate, names.index(name), name))
    return {'recommended': min(candidates)[-1] if candidates else None, 'candidates': summary,
            'uses_test': False, 'selection': 'validation mixed-event F1 with clean background alarm budget'}
