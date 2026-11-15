"""Read-only verification of existing Stage2 DB/API exports; no replay/inference."""
import ast
import csv
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT/'plan.json').read_text())
ENV = json.loads((OUT/'environment.json').read_text())


def fetch(path, params):
    with urlopen(ENV['base_url']+path+'?'+urlencode(params), timeout=15) as r:
        assert r.status == 200
        return json.load(r)


def page(endpoint, run):
    params = dict(run_id=run, building_id='appliances-house-1',source_id='uci-appliances',
                  start=PLAN['original_fragment_start'],end='2016-05-02T09:20:00',limit=1000)
    result = []
    while True:
        response = fetch('/api/'+endpoint,params)
        result.extend(response['items'])
        if not response['next_cursor']: return result
        params['cursor'] = response['next_cursor']


def flag(cell):
    return None if cell == '' else {'True':True,'False':False}[cell]


def main():
    assert ENV['status'] == 'completed_retained'
    checks, series = {}, {}
    for name, ids in ENV['scenarios'].items():
        report = json.loads((OUT/(name+'-summary.json')).read_text())
        points = list(csv.DictReader((OUT/(name+'-points.csv')).open()))
        assert len(points) == 300
        assert len(report['changes']) == (12 if name == 'plus-450' else 0)
        measurements = {x['measurement_id']:x for x in page('measurements',ids['run_id'])}
        scores = {(x['measurement_id'],x['detector']):x for x in page('anomaly-scores',ids['run_id'])}
        rules = {(x['measurement_id'],x['rule']):x for x in page('rule-assessments',ids['run_id'])}
        hybrids = {x['measurement_id']:x for x in page('hybrid-decisions',ids['run_id'])}
        primary = {x['forecast_target_timestamp']:x for x in page('forecasts',ids['run_id']) if x['purpose']=='primary_forecast'}
        assert len(measurements) == len(hybrids) == 300 and len(scores) == len(rules) == 900
        for p in points:
            mid, stamp = p['measurement_id'],p['timestamp']
            m = measurements[mid]
            assert m['energy_wh'] == float(p['energy_wh']) and m['measurement_timestamp'] == stamp
            assert m['time_basis'] == 'dataset_naive' and m['timezone'] is None
            assert primary[stamp]['predicted_energy_wh'] == float(p['HGB20_target_forecast_wh'])
            assert primary[stamp]['forecast_origin'] == p['HGB20_origin']
            for detector in ('isolation_forest','autoencoder','residual'):
                s = scores[mid,detector]
                assert s['flag'] is flag(p[detector+'_flag']) and s['status'] == p[detector+'_status']
                for key in ('score','threshold'):
                    assert s[key] == (float(p[detector+'_'+key]) if p[detector+'_'+key] else None)
            residual = scores[mid,'residual']
            assert residual['forecast_origin'] == p['RF21_origin'] and residual['forecast_target_timestamp'] == stamp
            assert residual['prediction_wh'] == float(p['RF21_target_forecast_wh'])
            for rule in ('sustained_high','flatline','interval_gap'):
                r = rules[mid,rule]
                assert r['flag'] is flag(p[rule+'_flag']) and r['status'] == p[rule+'_status']
                assert r['evidence'] == json.loads(p[rule+'_evidence'])
            h = hybrids[mid]
            assert h['flag'] is flag(p['hybrid_flag']) and h['status'] == p['hybrid_status']
            assert h['triggered_inputs'] == json.loads(p['hybrid_triggered_inputs'])
        catalog = fetch('/api/channels',dict(run_id=ids['run_id'],building_id='appliances-house-1',source_id='uci-appliances'))
        assert {x['channel_id'] for x in catalog['items']} == {'appliances','lights',*[f'zone-{i}' for i in range(1,10)]}
        checks[name] = dict(measurement_values_compared=300, ML_rows_compared=900, rule_rows_compared=900,
                            hybrid_rows_compared=300, HGB20_target_aligned_values_compared=300,
                            RF21_causal_target_aligned_values_compared=300, catalog_channels=11,
                            evidence_and_triggered_inputs_match=True, dataset_naive_preserved=True)
        series[name] = points
    control, changed = series['control'],series['plus-450']
    assert [x['timestamp'] for x in control] == [x['timestamp'] for x in changed]
    for a,b in zip(control,changed):
        delta = 450 if PLAN['intervention_start'] <= a['timestamp'] <= PLAN['intervention_end'] else 0
        assert float(b['energy_wh']) - float(a['energy_wh']) == delta
    reactions = {}
    for method in ('residual','isolation_forest','autoencoder','sustained_high','hybrid','unanimous'):
        entry = {}
        for name, points in series.items():
            active = [p for p in points if PLAN['intervention_start'] <= p['timestamp'] <= PLAN['intervention_end'] and flag(p[method+'_flag']) is True]
            entry[name] = dict(positive_points=len(active),first_positive_timestamp=active[0]['timestamp'] if active else None,
                               first_positive_delay_minutes=(datetime.fromisoformat(active[0]['timestamp'])-datetime.fromisoformat(PLAN['intervention_start'])).total_seconds()/60 if active else None)
        reactions[method] = entry
    for script in OUT.glob('*.py'): ast.parse(script.read_text())
    result = dict(scope='Stage2 bounded replay and read-only API verification; no new experiments/screenshots',
                  scenarios=checks,pair_energy_difference_exactly_12x450_wh=True,
                  preliminary_during_intervention_reactions=reactions,
                  scripts_syntax='AST parsed, four scripts',production_code_changed=False,
                  full_suite_CI_training_performance_browser_tests_run=False)
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
