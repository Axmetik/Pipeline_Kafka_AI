"""Small preregistered paired comparison. Inference only; no runtime/storage integration."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

from anomaly.combined import combine, selected_rule
from anomaly.features import collect, NAMES
from anomaly.residual import score_batch, StreamDetector
from integration.artifacts import load_manifest, sha256
from processing.energy_rules import EnergyRules, RuleConfig
from producer.appliances_dataset import iter_appliances

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / 'docs/energy-rules/controlled-20261108'
METHODS = ('flatline', 'sustained_high', *NAMES, 'unanimous', 'interval_gap')
STEP = timedelta(seconds=600)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def intervals(times, flags):
    """Build full episodes first: a later evaluation mask must not invent onset."""
    result = []
    for stamp, flag in zip(times, flags):
        if flag is True:
            if result and result[-1]['end'] + STEP == stamp and result[-1]['active']:
                result[-1]['end'] = stamp
                result[-1]['points'] += 1
            else:
                result.append({'start': stamp, 'end': stamp, 'points': 1, 'active': True})
        elif result:
            result[-1]['active'] = False
    return [{k:v for k,v in row.items() if k != 'active'} for row in result]


def onset_match(alarms, start, end, eligible=None):
    eligible = eligible if eligible is not None else {a['start'] for a in alarms}
    return next((a for a in alarms if start <= a['start'] <= end and a['start'] in eligible), None)


def transform(records, scenario):
    changed = deepcopy(records)
    start = datetime.fromisoformat(scenario['start'])
    end = start + STEP*(scenario['intervals']-1)
    index = {r['timestamp']:i for i,r in enumerate(changed)}
    wanted = [(start + STEP*i).isoformat() for i in range(scenario['intervals'])]
    if any(stamp not in index for stamp in wanted) or (end+STEP).isoformat() not in index:
        raise ValueError('Missing planned injection or first-return timestamp; no scenario replacement')
    hold = changed[index[wanted[0]]-1]['energy']['value']
    if scenario['operation'] == 'scheduled_control_profile':
        for row in changed:
            row['energy']['value'] = (scenario['before_08_wh'] if datetime.fromisoformat(row['timestamp']).hour < 8
                                      else scenario['from_08_wh'])
    elif scenario['operation'] == 'remove_records':
        changed = [row for row in changed if row['timestamp'] not in wanted]
    else:
        for stamp in wanted:
            row = changed[index[stamp]]
            if scenario['operation'] == 'hold_previous_energy':
                row['energy']['value'] = hold
            elif scenario['operation'] == 'add_energy_wh':
                row['energy']['value'] += scenario['amplitude_wh']
            elif scenario['operation'] == 'set_energy_wh':
                row['energy']['value'] = scenario['value_wh']
            else:
                raise ValueError('Unregistered operation')
    return changed


def infer(records, artifacts):
    # collect advances causal feature state on this exact stream. rf_x is the
    # preceding interval's feature vector; current/future actual never replaces it.
    frame, x, rf_x = collect(records, artifacts.anomaly.validate_source)
    scored = score_batch(artifacts.anomaly, frame, x, rf_x)
    rules = EnergyRules(RuleConfig())
    registry = {r['role']:r for r in artifacts.registry()}
    rows = []
    for raw, row in zip(records, scored.to_dict('records')):
        assessment = rules.process(raw)
        item = {'timestamp': raw['timestamp'], 'event_id':raw['event_id'],
                'energy_wh':raw['energy']['value'], 'gap_detected':bool(row['gap_detected']),
                'prediction_wh':float(row['prediction_wh']) if pd.notna(row['prediction_wh']) else None,
                'forecast_origin':row['forecast_origin'] if pd.notna(row['forecast_origin']) else None,
                'forecast_target_timestamp':row['forecast_target_timestamp'] if pd.notna(row['forecast_target_timestamp']) else None,
                'rule_evidence_json':json.dumps(assessment['signals'], sort_keys=True, allow_nan=False)}
        for rule in assessment['signals']:
            item[rule['rule']+'_flag'] = rule['flag']
            item[rule['rule']+'_status'] = rule['status']
        inputs = []
        for name in NAMES:
            score = float(row[name]) if pd.notna(row[name]) else None
            threshold = artifacts.anomaly.thresholds['0.99'][name]
            flag = score > threshold if score is not None else None
            status = 'ready' if score is not None else ('gap' if row['gap_detected'] else 'warmup')
            item[name+'_score'], item[name+'_threshold'], item[name+'_flag'] = score, threshold, flag
            inputs.append({'detector':name, 'score':score, 'threshold':threshold,
                           'flag':flag, 'status':status,
                           **{k:registry[name][k] for k in ('model_id','model_version','feature_version','threshold_version')}})
        vote = combine(inputs)  # exact existing frozen default, not a copied AND
        if vote['rule'] != 'unanimous':
            raise ValueError('Frozen rule no longer Unanimous')
        item['unanimous_flag'], item['unanimous_status'] = vote['flag'], vote['status']
        rows.append(item)
    return rows


def save_points(path, rows):
    frame = pd.DataFrame(rows)
    for name in METHODS:
        frame[name+'_flag'] = pd.array(frame[name+'_flag'], dtype='boolean')
    frame.to_parquet(path, index=False)


def describe(scenario, modified, original):
    start = datetime.fromisoformat(scenario['start'])
    end = start + STEP*(scenario['intervals']-1)
    times = [datetime.fromisoformat(r['timestamp']) for r in modified]
    raw_times = [datetime.fromisoformat(r['timestamp']) for r in original]
    original_by_time = dict(zip(raw_times, original))
    family_rule = scenario['family'] if scenario['family'] in ('flatline','sustained_high') else None
    comparison = [family_rule, *NAMES, 'unanimous'] if family_rule else list(METHODS[:-1])
    common = {t for t,r in zip(times,modified) if all(r[n+'_flag'] is not None for n in comparison)}
    target_times = {start+STEP*i for i in range(scenario['intervals'])}
    full_common = target_times <= common
    results = []
    for name in METHODS:
        flags = [r[name+'_flag'] for r in modified]
        raw_flags = [r[name+'_flag'] for r in original]
        alarms, raw_alarms = intervals(times,flags), intervals(raw_times,raw_flags)
        own_match = onset_match(alarms,start,end)
        matched = onset_match(alarms,start,end,common) if full_common else None
        positive = bool(scenario['target'] and family_rule and name in comparison)
        observed = [r for t,r in zip(times,modified) if start <= t <= end]
        overlaps = [a for a in alarms if a['start'] < start <= a['end']]
        new_flag = bool(matched and original_by_time[matched['start']][name+'_flag'] is not True)
        result = {'scenario_id':scenario['scenario_id'], 'family':scenario['family'],
                  'method':name, 'target':positive, 'event_start':start.isoformat(), 'event_end':end.isoformat(),
                  'duration_intervals':scenario['intervals'], 'amplitude_wh':scenario.get('amplitude_wh'),
                  'common_event_coverage':sum(t in common for t in target_times)/len(target_times),
                  'target_coverage':sum(r[name+'_flag'] is not None for r in observed)/len(target_times),
                  'stream_coverage':sum(f is not None for f in flags)/len(flags),
                  'common_stream_coverage':len(common)/len(times),
                  'detected_common': bool(matched) if positive else None,
                  'detected_own':bool(own_match) if positive else None,
                  'new_paired_crossing':new_flag if positive else None,
                  'delay_minutes':(matched['start']-start).total_seconds()/60 if positive and matched else None,
                  'alarm_start':matched['start'].isoformat() if positive and matched else None,
                  'preexisting_overlap':len(overlaps),
                  'modified_episode_onsets':len(alarms), 'paired_episode_onsets':len(raw_alarms),
                  'modified_event_onsets':sum(start<=a['start']<=end for a in alarms),
                  'paired_event_onsets':sum(start<=a['start']<=end for a in raw_alarms),
                  'modified_event_flagged_points':sum(r[name+'_flag'] is True for r in observed),
                  'paired_event_flagged_points':sum(r[name+'_flag'] is True for t,r in zip(raw_times,original) if start<=t<=end),
                  'modified_tail_onsets':sum(a['start']>end for a in alarms),
                  'paired_tail_onsets':sum(a['start']>end for a in raw_alarms),
                  'modified_flagged_points':sum(f is True for f in flags), 'paired_flagged_points':sum(f is True for f in raw_flags)}
        results.append(result)
    return results


def check_gap(scenario, rows):
    start = datetime.fromisoformat(scenario['start'])
    returned = start + STEP*scenario['intervals']
    hits = []
    for row in rows:
        found = next(s for s in json.loads(row['rule_evidence_json']) if s['rule']=='interval_gap')
        if found['flag'] is True:
            hits.append((row['timestamp'],found['evidence']))
    expected = next((e for t,e in hits if t==returned.isoformat()),None)
    return {'scenario_id':scenario['scenario_id'], 'known_missing_intervals':scenario['intervals'],
            'detected_missing_intervals':expected['missing_intervals'] if expected else None,
            'expected_detection_timestamp':returned.isoformat(),
            'actual_detection_timestamp':next((t for t,_ in hits if t==returned.isoformat()),None),
            'gap_signals':len(hits), 'correct':bool(expected and expected['missing_intervals']==scenario['intervals'] and len(hits)==1),
            'delay_from_first_missing_minutes':scenario['intervals']*10 if expected else None,
            'semantics':'returned_gap_not_silence_watchdog'}


def stream_parity(records, expected, artifacts, event_start):
    stream = StreamDetector(artifacts.anomaly)
    checked = 0
    for raw, batch in zip(records,expected):
        actual = stream.process(raw)
        if raw['timestamp'] < event_start:
            continue
        for name in NAMES:
            a,b = actual[name],batch[name+'_score']
            if (a is None)!=(b is None) or (a is not None and not np.isclose(a,b,rtol=1e-6,atol=1e-6)):
                raise ValueError(f'Offline/streaming mismatch: {name} at {raw["timestamp"]}')
            if actual[name+'_flag'] is not batch[name+'_flag']:
                raise ValueError('Offline/streaming flag mismatch')
        for key in ('forecast_origin','forecast_target_timestamp'):
            if actual[key] != batch[key]:
                raise ValueError('Residual origin/target mismatch')
        checked += 1
    return {'scenario_id':'high-04-0750-n6-add300','checked_event_and_tail_records':checked,
            'all_three_scores_and_flags_match':True, 'score_tolerance':{'rtol':1e-6,'atol':1e-6},
            'residual_previous_origin_target_match':True}


def plots(output, all_points, scenarios):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    chosen = ['flatline-04-0750-n3','flatline-04-0750-n6','flatline-04-0750-n12',
              'high-04-0750-n6-add300','control-morning-rise','control-normal-zero',
              'gap-04-n1','gap-05-n3','gap-06-n6']
    directory = output/'plots'; directory.mkdir()
    lookup = {s['scenario_id']:s for s in scenarios}
    for sid in chosen:
        case = lookup[sid]; start = datetime.fromisoformat(case['start']); end = start+STEP*(case['intervals']-1)
        altered, clean = all_points[sid]
        left,right = start-STEP*6,end+STEP*12
        a = [r for r in altered if left<=datetime.fromisoformat(r['timestamp'])<=right]
        b = [r for r in clean if left<=datetime.fromisoformat(r['timestamp'])<=right]
        fig,axes=plt.subplots(3,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1,1]})
        for rows,label,style in ((b,'raw unchanged pair','--'),(a,'modified/control stream','-')):
            axes[0].plot([datetime.fromisoformat(r['timestamp']) for r in rows],[r['energy_wh'] for r in rows],style,label=label)
        reference = [next(e for e in json.loads(r['rule_evidence_json']) if e['rule']=='sustained_high')['evidence'].get('threshold_wh',np.nan) for r in a]
        axes[0].plot([datetime.fromisoformat(r['timestamp']) for r in a],reference,':',label='sustained-high contextual threshold')
        axes[0].set_ylabel('Interval energy, Wh'); axes[0].legend(fontsize=8)
        for ax,names in ((axes[1],('flatline','sustained_high','interval_gap')),(axes[2],(*NAMES,'unanimous'))):
            for lane,name in enumerate(names):
                points=[datetime.fromisoformat(r['timestamp']) for r in a if r[name+'_flag'] is True]
                ax.scatter(points,[lane]*len(points),marker='|',s=100)
            ax.set_yticks(range(len(names)),names,fontsize=8);ax.set_ylim(-.6,len(names)-.4)
        for ax in axes:
            ax.axvspan(start,end+STEP,alpha=.13,color='orange');ax.grid(alpha=.2)
        axes[-1].set_xlabel('Naive dataset time; orange = defined case intervals (last interval included)')
        fig.suptitle(sid+' — controlled historical example, not confirmed faults')
        fig.autofmt_xdate();fig.tight_layout();fig.savefig(directory/(sid+'.png'),dpi=140);plt.close(fig)


def summarize(output, details, gaps, plan, parity):
    df=pd.DataFrame(details);df.to_csv(output/'all-methods-all-cases.csv',index=False)
    pd.DataFrame(gaps).to_csv(output/'returned-gaps.csv',index=False)
    df[df.family=='control'].to_csv(output/'controls.csv',index=False)
    summaries=[]
    for (family,method),group in df[df.target].groupby(['family','method'],sort=True):
        delays=group.delay_minutes.dropna()
        summaries.append({'family':family,'method':method,'target_events':len(group),
                          'detected_events':int(group.detected_common.sum()),
                          'detected_method_only':int(group.detected_own.sum()),
                          'new_paired_crossings':int(group.new_paired_crossing.sum()),
                          'event_coverage_percent':100*float(group.target_coverage.mean()),
                          'common_event_coverage_percent':100*float(group.common_event_coverage.mean()),
                          'stream_coverage_percent':100*float(group.stream_coverage.mean()),
                          'delay_median_minutes':float(delays.median()) if len(delays) else None,
                          'delay_values_minutes':json.dumps(delays.tolist()),
                          'paired_episode_onsets_sum':int(group.paired_episode_onsets.sum()),
                          'paired_event_onsets_sum':int(group.paired_event_onsets.sum()),
                          'modified_event_onsets_sum':int(group.modified_event_onsets.sum()),
                          'preexisting_overlap_cases':int((group.preexisting_overlap>0).sum())})
    pd.DataFrame(summaries).to_csv(output/'summary.csv',index=False)
    lines=['# Controlled comparison on historical Appliances data', '',
           'Exploratory synthetic scenarios, not a new holdout or verification of real faults. All24 planned cases retained. No fitting, calibration or parameter selection. Existing local trusted bundle identity differs from archived Stage4 original binary; old metrics are not substituted.', '',
           '## Target events (common-ready onset matching)', '',
           '| Family | Method | Detected / target | Target coverage | Common coverage | Median detected delay,min | Pair episodes (whole streams / event windows) |',
           '|---|---|---:|---:|---:|---:|---:|']
    for row in summaries:
        delay='—' if row['delay_median_minutes'] is None else f"{row['delay_median_minutes']:g}"
        lines.append(f"| {row['family']} | {row['method']} | {row['detected_events']}/{row['target_events']} | {row['event_coverage_percent']:.1f}% | {row['common_event_coverage_percent']:.1f}% | {delay} | {row['paired_episode_onsets_sum']} / {row['paired_event_onsets_sum']} |")
    lines += ['', 'Pair counts are sums over separately initialized case streams, including repeated historical context; they are neither unique-building alarm counts nor confirmed false positives. Episode onsets and flagged points are separately preserved in the detailed CSV. Missed-event delays are null; short below-duration cases remain in denominators.', '',
              '## Returned gaps (not consumption-event recall)', '',
              '| Case | Missing / reported intervals | First-return detection correct | Event-time delay from first missing,min |',
              '|---|---:|---|---:|']
    for g in gaps:
        lines.append(f"| {g['scenario_id']} | {g['known_missing_intervals']} / {g['detected_missing_intervals']} | {g['correct']} | {g['delay_from_first_missing_minutes']} |")
    lines += ['', '## Controls (event-window flagged points / new episode onsets)', '',
              '| Control | Method | Modified flags / onsets | Raw pair flags / onsets |',
              '|---|---|---:|---:|']
    for row in details:
        if row['family']=='control' and row['method']!='interval_gap':
            lines.append(f"| {row['scenario_id']} | {row['method']} | {row['modified_event_flagged_points']} / {row['modified_event_onsets']} | {row['paired_event_flagged_points']} / {row['paired_event_onsets']} |")
    lines += ['', 'The morning schedule is explicitly modeled over context and observation records, not validated natural normality. The zero window is assumed benign: a flatline flag there may correctly describe repetition but is not a confirmed stuck-meter diagnosis. A one-point peak is not a sustained-high target. No control is relabeled as a successful anomaly detection.', '',
              '## Files and reproducibility', '',
              '`all-methods-all-cases.csv` retains every method/case, own and common coverage, strict matches, pre-existing overlap, paired-crossing diagnostics, tail signals and null delays. `controls.csv` and `returned-gaps.csv` keep tasks separate. `points/*.parquet` contains fresh original and altered scores, exact thresholds, nullable flags, previous-interval residual forecasts and full rule evidence. `provenance.json` records checksums, versions, preservation and parity; no old score files are input.', '',
              'See the preregistered parent `plan.md`, `plan.json`, `scenarios.json`, and runner `diagnostics/rule_comparison.py`. Run in the exact existing inference image with read-only source/artifact/dataset mount, a new writable output directory, no network and single-thread policy. Output directory reuse is refused. No Worker, DB, API, Dashboard or Email process is used.', '',
              f"Offline/streaming parity: {parity['checked_event_and_tail_records']} modified event/tail records, all three scores/flags and previous-origin/target alignment match within the declared tolerance.", '',
              '## Interpretation boundary', '',
              'These counts concern predefined manipulations of one historical house with known but artificial event windows. They do not establish production accuracy, independent generalization, real failures or a universal winner. A short intervention may be intentionally too short for a duration rule. Flatline and high-consumption families have different target meanings and must not be pooled; returned gaps are a third separate task. All failures and pre-existing alarms are retained.']
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    return summaries


def run(plan_dir, output):
    if output.exists():
        raise FileExistsError('Output already exists; never overwrite a registered run')
    plan=json.loads((plan_dir/'plan.json').read_text());manifest=json.loads((plan_dir/'scenarios.json').read_text())
    if sha256(plan_dir/'scenarios.json') != plan['manifest_sha256'] or RuleConfig().__dict__ != plan['rule_config'] or RuleConfig().version != plan['rule_version']:
        raise ValueError('Registered scenario/config differs')
    for path,digest in plan['input_sha256'].items():
        if sha256(ROOT/path) != digest:
            raise ValueError('Registered protected input differs: '+path)
    if selected_rule()!='unanimous': raise ValueError('Frozen Unanimous changed')
    artifacts=load_manifest(ROOT/'artifacts/mvp/docker/manifest.json')
    records=list(iter_appliances(ROOT/'data/energy/raw/energydata_complete.csv'))
    output.mkdir(parents=True,exist_ok=False);(output/'points').mkdir()
    all_details=[];gaps=[];all_points={};parity=None;case_manifest=[]
    for case in manifest['scenarios']:
        start=datetime.fromisoformat(case['start']);end=start+STEP*(case['intervals']-1)
        left=start.replace(hour=0,minute=0,second=0)-timedelta(days=manifest['history_days'])
        right=end+STEP*manifest['post_event_intervals']
        raw=[deepcopy(r) for r in records if left<=datetime.fromisoformat(r['timestamp'])<=right]
        expected_count=int((right-left)/STEP)+1
        if len(raw)!=expected_count: raise ValueError('Incomplete base slice; no silent replacement')
        changed=transform(raw,case)
        print(json.dumps({'case':case['scenario_id'],'raw':len(raw),'modified':len(changed),'phase':'fresh_inference'}),flush=True)
        modified_scores=infer(changed,artifacts);raw_scores=infer(raw,artifacts)
        save_points(output/'points'/(case['scenario_id']+'-modified.parquet'),modified_scores)
        save_points(output/'points'/(case['scenario_id']+'-paired.parquet'),raw_scores)
        all_points[case['scenario_id']]=(modified_scores,raw_scores)
        all_details.extend(describe(case,modified_scores,raw_scores))
        if case['family']=='interval_gap': gaps.append(check_gap(case,modified_scores))
        if case['scenario_id']=='high-04-0750-n6-add300':
            parity=stream_parity(changed,modified_scores,artifacts,case['start'])
        case_manifest.append({**case,'raw_points':len(raw),'modified_points':len(changed),
                              'slice_start':left.isoformat(),'slice_end':right.isoformat(),
                              'modified_energy_records':sum(a['energy']['value']!=b['energy']['value'] for a,b in zip(changed,raw)) if case['family']!='interval_gap' else 0})
    if len(case_manifest)!=plan['scenarios'] or parity is None: raise ValueError('Incomplete registered campaign')
    for path,digest in plan['input_sha256'].items():
        if sha256(ROOT/path)!=digest: raise ValueError('Protected input changed during inference')
    write_json(output/'executed-manifest.json',case_manifest)
    summaries=summarize(output,all_details,gaps,plan,parity)
    plots(output,all_points,manifest['scenarios'])
    try: commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (FileNotFoundError,subprocess.CalledProcessError): commit=None
    provenance={'plan_sha256':sha256(plan_dir/'plan.json'),'manifest_sha256':sha256(plan_dir/'scenarios.json'),
                'runner_sha256':sha256(Path(__file__)),'git_commit':commit,'model_metadata':artifacts.anomaly.metadata,
                'thresholds':artifacts.anomaly.thresholds['0.99'],'rule_metadata':EnergyRules().metadata(),
                'registered_input_sha256':plan['input_sha256'],'all_registered_inputs_preserved':True,
                'docker_image_id':plan['docker_image_id'],'libraries':{n:importlib.metadata.version(n) for n in ('numpy','pandas','scikit-learn','torch','joblib','pyarrow','matplotlib')},
                'parity':parity,'scenarios_planned':24,'scenarios_completed':len(case_manifest),
                'threads':1,'trained':False,'old_scores_used':False,'scheduling':'offline_only_no_network',
                'output_sha256':{str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    write_json(output/'provenance.json',provenance)
    print(json.dumps({'complete':True,'scenarios':len(case_manifest),'gap_checks':all(g['correct'] for g in gaps),'summary':summaries}),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=DEFAULT_PLAN)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    torch.set_num_threads(1)
    with threadpool_limits(1): run(args.plan,args.output)


if __name__=='__main__': main()
