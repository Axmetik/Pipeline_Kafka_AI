"""Bounded real Kafka replay; only the existing worker writes analytical results."""
import argparse
import copy
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from alembic import command
from alembic.config import Config
from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from sqlalchemy import create_engine, select
from producer.appliances_dataset import iter_appliances
from processing.energy_schema import validate_energy
from integration.settings import Settings
from integration.energy_worker import run_worker
from integration.processor import payload_digest
from storage.postgres import schema as s
from storage.postgres import rules_schema as r

ROOT = Path('/work')
PLAN = json.loads((ROOT / 'docs/integration/stage2/plan.json').read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=PLAN['scenarios'], required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    assert settings.run_id.startswith('ei-stage2-')
    assert settings.energy_rules_enabled and os.environ['EMAIL_NOTIFICATIONS_ENABLED'] == 'false'
    assert hashlib.sha256(Path('/datasets/appliances.csv').read_bytes()).hexdigest() == PLAN['dataset_sha256']
    original = list(iter_appliances('/datasets/appliances.csv', start=PLAN['start'], end=PLAN['end']))
    records = copy.deepcopy(original)
    changes = []
    for before, after in zip(original, records):
        affected = PLAN['intervention_start'] <= after['timestamp'] <= PLAN['intervention_end']
        if args.scenario == 'plus-450' and affected:
            after['energy']['value'] += PLAN['delta_wh']
            changes.append(dict(timestamp=after['timestamp'], original_wh=before['energy']['value'], modified_wh=after['energy']['value']))
        validate_energy(after)
        restored = copy.deepcopy(after)
        restored['energy']['value'] = before['energy']['value']
        assert restored == before
        assert after == before if not (args.scenario == 'plus-450' and affected) else after['energy']['value'] - before['energy']['value'] == 450
    assert len(changes) == (12 if args.scenario == 'plus-450' else 0)
    n = len(records)
    assert n == PLAN['records_per_run'] and len({x['event_id'] for x in records}) == n
    assert all(datetime.fromisoformat(b['timestamp']) - datetime.fromisoformat(a['timestamp']) == timedelta(seconds=600) for a, b in zip(records, records[1:]))
    prefix = [x for x in records if x['timestamp'] < PLAN['intervention_start']]
    assert len(prefix) == PLAN['before_intervention_points']
    engine = create_engine(settings.database_url)
    for name in ('alembic.ini', 'alembic-rules.ini'):
        config = Config(str(ROOT / name))
        with engine.begin() as c:
            config.attributes['connection'] = c
            command.upgrade(config, 'head')
    admin = KafkaAdminClient(bootstrap_servers=settings.bootstrap_servers)
    assert settings.topic not in admin.list_topics()
    admin.create_topics([NewTopic(settings.topic, 1, 1)])
    admin.close()
    digests = []

    def publish(rows):
        producer = KafkaProducer(bootstrap_servers=settings.bootstrap_servers)
        try:
            for row in rows:
                key = json.dumps([row['building_id'], row['source_id']]).encode()
                value = json.dumps(row, sort_keys=True, allow_nan=False).encode()
                meta = producer.send(settings.topic, key=key, value=value).get(timeout=30)
                assert meta.offset == len(digests)
                digests.append(payload_digest(key, value))
        finally:
            producer.close(timeout=30)

    def rows(table, connection):
        return [dict(x) for x in connection.execute(select(table).where(table.c.run_id == settings.run_id)).mappings()]

    publish(prefix)
    first = run_worker(settings, max_messages=len(prefix), idle_timeout=10)
    assert first['accepted'] == len(prefix) and first['quarantined'] == 0
    with engine.connect() as c:
        anchor = c.execute(select(s.measurements).where(s.measurements.c.run_id == settings.run_id).order_by(s.measurements.c.kafka_offset.desc()).limit(1)).mappings().one()
        high = dict(c.execute(select(r.assessments).where(r.assessments.c.measurement_id == anchor['measurement_id'], r.assessments.c.rule == 'sustained_high')).mappings().one())
        gate_scores = [dict(x) for x in c.execute(select(s.scores).where(s.scores.c.measurement_id == anchor['measurement_id'])).mappings()]
        gate_forecasts = [dict(x) for x in c.execute(select(s.forecasts).where(s.forecasts.c.measurement_id == anchor['measurement_id'])).mappings()]
        snapshot = rows(r.states, c)[0]
        immutable = sorted(rows(s.forecasts, c), key=lambda x: x['forecast_id'])
    assert anchor['measurement_timestamp'] == '2016-05-01T13:10:00'
    assert high['flag'] is not None and high['evidence']['context_points'] >= 18 and high['evidence']['context_days'] >= 3
    assert high['rule_version'] == PLAN['rule_version'] and high['layer_version'] == PLAN['layer_version']
    assert len(gate_scores) == 3 and all(x['status'] == 'ready' for x in gate_scores)
    assert len(gate_forecasts) == 2 and all(x['status'] == 'ready' for x in gate_forecasts)
    context_hours = {}
    source_state = snapshot['state']['source']
    for hour in range(24):
        frozen = source_state['high_references']
        if frozen is not None:
            context = frozen[str(hour)]
        else:
            selected = [(t, v) for t, v, eligible in source_state['history'] if eligible
                        and 1 <= (datetime.fromisoformat(anchor['measurement_timestamp']).date() - datetime.fromisoformat(t).date()).days <= 7
                        and datetime.fromisoformat(t).hour == hour]
            context = dict(context_points=len(selected), context_days=len({t[:10] for t, _ in selected}))
        assert context['context_points'] >= 18 and context['context_days'] >= 3
        context_hours[str(hour)] = context
    gate = dict(all_24_hour_contexts=context_hours, timestamp=anchor['measurement_timestamp'], high=high, scores=gate_scores, forecasts=gate_forecasts,
                snapshot_last_offset=snapshot['last_offset'], snapshot_sha256=snapshot['state_sha256'], checked_before_tail_publication=True)
    print('READINESS_GATE=' + json.dumps(gate, default=str, allow_nan=False), flush=True)
    publish(records[len(prefix):])
    second = run_worker(settings, max_messages=n-len(prefix), idle_timeout=10)
    assert second['accepted'] == n-len(prefix) and second['verified_journal_records'] == len(prefix)
    assert all(x['message_duplicate'] == x['offset_duplicate'] == x['quarantined'] == 0 for x in (first, second))
    with engine.connect() as c:
        measurements = sorted(rows(s.measurements, c), key=lambda x: x['kafka_offset'])
        ledger = sorted(rows(s.receipts, c), key=lambda x: x['offset'])
        checkpoint = rows(s.checkpoints, c)[0]
        forecasts = rows(s.forecasts, c)
        scores = rows(s.scores, c)
        combined = rows(s.combined_decisions, c)
        assessments = rows(r.assessments, c)
        hybrid = rows(r.decisions, c)
        episodes = rows(s.episodes, c)
        combined_events = rows(s.combined_episodes, c)
        hybrid_events = rows(r.episodes, c)
        state = rows(r.states, c)[0]
        notifications = rows(s.notifications, c)
        models = [dict(x) for x in c.execute(select(s.models)).mappings()]
    assert [x['wire_record'] for x in measurements] == records
    assert [x['offset'] for x in ledger] == list(range(n)) and [x['payload_sha256'] for x in ledger] == digests
    assert all(x['outcome'] == 'accepted' for x in ledger)
    assert len({x['event_id'] for x in measurements}) == n
    assert (len(forecasts), len(scores), len(combined), len(assessments), len(hybrid), len(notifications)) == (2*n, 3*n, n, 3*n, n, 0)
    assert checkpoint['next_offset'] == n and state['last_offset'] == n-1
    assert sorted([x for x in forecasts if x['measurement_id'] in {m['measurement_id'] for m in measurements[:len(prefix)]}], key=lambda x: x['forecast_id']) == immutable
    consumer = KafkaConsumer(bootstrap_servers=settings.bootstrap_servers, group_id=settings.group_id, enable_auto_commit=False)
    tp = TopicPartition(settings.topic, 0)
    assert consumer.end_offsets([tp])[tp] == consumer.committed(tp) == n
    consumer.close(autocommit=False)
    by_score = {(x['measurement_id'], x['detector']): x for x in scores}
    by_rule = {(x['measurement_id'], x['rule']): x for x in assessments}
    by_hybrid = {x['measurement_id']: x for x in hybrid}
    by_combined = {x['measurement_id']: x for x in combined}
    primary = {x['forecast_target_timestamp']: x for x in forecasts if x['purpose'] == 'primary_forecast'}
    points = []
    for m in measurements:
        mid, stamp = m['measurement_id'], m['measurement_timestamp']
        point = dict(measurement_id=mid, timestamp=stamp, energy_wh=m['energy_wh'])
        f = primary.get(stamp)
        point.update(HGB20_target_forecast_wh=f['predicted_energy_wh'] if f else None,
                     HGB20_origin=f['forecast_origin'] if f else None,
                     unanimous_flag=by_combined[mid]['flag'], unanimous_status=by_combined[mid]['status'])
        for detector in ('isolation_forest', 'autoencoder', 'residual'):
            score = by_score[mid, detector]
            point.update({detector+'_'+key: score[key] for key in ('score', 'threshold', 'flag', 'status')})
            if detector == 'residual':
                point.update(RF21_target_forecast_wh=score['prediction_wh'], RF21_origin=score['forecast_origin'], RF21_target=score['forecast_target_timestamp'])
                if score['status'] == 'ready':
                    assert score['forecast_target_timestamp'] == stamp and datetime.fromisoformat(score['forecast_origin']) + timedelta(seconds=600) == datetime.fromisoformat(stamp)
        for rule in ('sustained_high', 'flatline', 'interval_gap'):
            signal = by_rule[mid, rule]
            point.update({rule+'_'+key: signal[key] for key in ('flag', 'status', 'evidence')})
        decision = by_hybrid[mid]
        point.update({('hybrid_'+key): decision[key] for key in ('flag', 'status', 'coverage_count', 'available_inputs', 'triggered_inputs')})
        residual, high_flag = point['residual_flag'], point['sustained_high_flag']
        expected = True if residual is True or high_flag is True else False if residual is False and high_flag is False else None
        assert point['hybrid_flag'] is expected
        points.append(point)
    first_ready = next(x for x in points if x['sustained_high_flag'] is not None)
    report = dict(run_id=settings.run_id, topic=settings.topic, group_id=settings.group_id,
        scenario=args.scenario, records=n, start=records[0]['timestamp'], end=records[-1]['timestamp'],
        rules_enabled=True, email_enabled=False, changes=changes, readiness_gate=gate,
        first_high_available=dict(timestamp=first_ready['timestamp'], status=first_ready['sustained_high_status'], evidence=first_ready['sustained_high_evidence']),
        worker_phases=[first, second], models=models,
        rule_versions=sorted({x['rule_version'] for x in assessments}), layer_versions=sorted({x['layer_version'] for x in hybrid}),
        counts=dict(measurements=len(measurements), forecasts=len(forecasts), scores=len(scores), combined_decisions=len(combined), rule_assessments=len(assessments), hybrid_decisions=len(hybrid), episodes=len(episodes), combined_episodes=len(combined_events), hybrid_episodes=len(hybrid_events), notifications=len(notifications)),
        statuses={name:dict(Counter(str(x[key]) for x in items)) for name,items,key in [('ML',scores,'status'),('rules',assessments,'status'),('hybrid',hybrid,'status')]},
        integrity=dict(schema_valid=True, only_energy_changed=True, constant_600s_cadence=True, wire_records_match=True, ledger_hashes_match=True, unique_event_ids=n, db_checkpoint=n, kafka_committed=n, kafka_end=n, previous_forecasts_and_generation_times_preserved=True, ternary_OR_all_points_valid=True),
        episodes=episodes, combined_episodes=combined_events, hybrid_episodes=hybrid_events,
        points=points)
    print('STAGE2_RESULT='+json.dumps(report, default=str, sort_keys=True, allow_nan=False), flush=True)
    engine.dispose()


if __name__ == '__main__':
    main()
