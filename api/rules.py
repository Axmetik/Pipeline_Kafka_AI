"""Read persisted optional results only; never load rule state or run detectors."""
from sqlalchemy import select, func
from storage.postgres import schema as s, rules_schema as r
from .query import page, TIMED_FIELDS


def optional_series(c, kind, f):
    # Inspect without issuing a failing SELECT that would abort the read transaction.
    names = ('mvp_rule_assessments', 'mvp_hybrid_decisions', 'mvp_hybrid_episodes')
    ready = all(c.execute(select(func.to_regclass(name))).scalar_one() is not None for name in names)
    empty = dict(items=[], next_cursor=None, order='descending')
    if not ready:
        return dict(**empty, channel_status='not_connected', status_reason='Optional rule tables are not connected; channel disabled or not installed')
    table, ident = {'rule-assessments': (r.assessments, r.assessments.c.assessment_id),
                    'hybrid-decisions': (r.decisions, r.decisions.c.decision_id),
                    'hybrid-events': (r.episodes, r.episodes.c.episode_id)}[kind]
    m = s.measurements
    anchor = table.c.start_measurement_id if kind == 'hybrid-events' else table.c.measurement_id
    stamp = m.c.measurement_time_local if f.time_basis == 'dataset_naive' else m.c.measurement_time_utc
    cols = list(table.c) + [m.c[k] for k in TIMED_FIELDS if k not in table.c]
    if kind != 'hybrid-events': cols.append(m.c.measurement_timestamp)
    q = select(*cols, stamp.label('_sort_time')).select_from(table.join(m, anchor == m.c.measurement_id)).where(m.c.time_basis == f.time_basis)
    for key in ('run_id', 'building_id', 'source_id'):
        if getattr(f, key) is not None: q = q.where(m.c[key] == getattr(f, key))
    # Availability is about persisted records in this source/run, not current worker liveness.
    populated = c.execute(select(q.exists())).scalar_one()
    if f.start: q = q.where(stamp >= f.start)
    if f.end: q = q.where(stamp < f.end)
    if f.status: q = q.where(table.c.status == f.status)
    result = page(c, q, [stamp.label('_sort_time'), ident], kind, f, ['time', 'str'], descending=True)
    return dict(**result, channel_status='available' if populated else 'no_data',
                status_reason='Persisted results only; current worker enablement is unknown' if populated else
                'No persisted records for this selection; channel may be disabled or awaiting data')
