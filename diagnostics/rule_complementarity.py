"""Preregistered standalone complementarity diagnostic; inference only."""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import torch
from threadpoolctl import threadpool_limits

from anomaly.combined import selected_rule
from anomaly.features import NAMES
from diagnostics.rule_comparison import ROOT, STEP, infer, intervals, onset_match, check_gap, transform as old_transform, write_json
from integration.artifacts import load_manifest, sha256
from processing.energy_rules import RuleConfig, EnergyRules
from producer.appliances_dataset import iter_appliances

PLAN = ROOT / 'docs/energy-rules/complementarity-20261108'
CONSUMPTION = (*NAMES, 'ml_or', 'sustained_high', 'ml_high_or', 'unanimous')
TELEMETRY = ('flatline', *NAMES, 'ml_or', 'unanimous')
METHODS = (*CONSUMPTION, 'flatline', 'interval_gap')
UNIONS = {'ml_or': NAMES, 'ml_high_or': (*NAMES, 'sustained_high')}


def tri_or(inputs):
    """A known positive is sufficient; negatives require complete availability."""
    if not inputs or any(value is not None and type(value) is not bool for value in inputs.values()):
        raise ValueError('Nonempty mapping of strict bool or None required')
    available = [name for name, value in inputs.items() if value is not None]
    positive = [name for name, value in inputs.items() if value is True]
    missing = [name for name, value in inputs.items() if value is None]
    flag = True if positive else (None if missing else False)
    return dict(flag=flag, required=list(inputs), available=available, positive=positive, missing=missing)


def augment(rows):
    result = deepcopy(rows)
    for row in result:
        for name, required in UNIONS.items():
            vote = tri_or({n: row[n+'_flag'] for n in required})
            row[name+'_flag'] = vote['flag']
            row[name+'_provenance_json'] = json.dumps(vote, sort_keys=True, allow_nan=False)
    return result


def transform(records, case):
    if case['operation'] not in ('scale_energy', 'ramp_add_energy', 'identity'):
        return old_transform(records, case)
    # Reuse original exact-time validation without changing any raw input.
    checked = old_transform(records, {**case, 'operation': 'set_energy_wh', 'value_wh': 0})
    changed = deepcopy(records)
    start = datetime.fromisoformat(case['start'])
    lookup = {row['timestamp']: row for row in changed}
    for i in range(case['intervals']):
        row = lookup[(start+STEP*i).isoformat()]
        if case['operation'] == 'scale_energy':
            row['energy']['value'] *= case['factor']
        elif case['operation'] == 'ramp_add_energy':
            row['energy']['value'] += case['final_addition_wh']*(i+1)/case['intervals']
    assert len(changed) == len(checked)
    return changed


def measure(case, altered, raw):
    start = datetime.fromisoformat(case['start']); end = start+STEP*(case['intervals']-1)
    times = [datetime.fromisoformat(r['timestamp']) for r in altered]
    raw_times = [datetime.fromisoformat(r['timestamp']) for r in raw]
    raw_lookup = dict(zip(raw_times, raw))
    expected = {start+STEP*i for i in range(case['intervals'])}
    comparison = TELEMETRY if case['family']=='flatline' else CONSUMPTION
    common = {t for t, r in zip(times, altered) if all(r[n+'_flag'] is not None for n in comparison)}
    observed = [(t, r) for t, r in zip(times, altered) if t in expected]
    details=[]; episodes=[]
    for name in METHODS:
        alarms = intervals(times, [r[name+'_flag'] for r in altered])
        paired = intervals(raw_times, [r[name+'_flag'] for r in raw])
        match = onset_match(alarms, start, end)
        common_match = onset_match(alarms, start, end, common)
        target = bool(case['target'] and ((case['category']=='consumption_pattern' and name in CONSUMPTION) or (case['family']=='flatline' and name in TELEMETRY)))
        pair_flag = raw_lookup[match['start']][name+'_flag'] if match else None
        result = dict(scenario_id=case['scenario_id'], family=case['family'], category=case['category'], method=name,
                      target=target, start=start.isoformat(), end=end.isoformat(), intervals=case['intervals'],
                      detected=bool(match) if target else None, detected_common_onset=bool(common_match) if target else None,
                      alarm_start=match['start'].isoformat() if target and match else None,
                      delay_minutes=(match['start']-start).total_seconds()/60 if target and match else None,
                      paired_flag_at_match=pair_flag if target and match else None,
                      new_paired_crossing=bool(pair_flag is False) if target and match else None,
                      paired_unknown_at_match=bool(pair_flag is None) if target and match else None,
                      event_coverage=sum(r[name+'_flag'] is not None for _,r in observed)/len(expected),
                      unavailable_event_points=len(expected)-sum(r[name+'_flag'] is not None for _,r in observed),
                      stream_coverage=sum(r[name+'_flag'] is not None for r in altered)/len(altered),
                      unavailable_stream_points=sum(r[name+'_flag'] is None for r in altered),
                      common_event_coverage=len(expected & common)/len(expected),
                      common_stream_coverage=len(common)/len(altered),
                      stream_points=len(altered),
                      modified_episode_onsets=len(alarms), paired_episode_onsets=len(paired),
                      modified_event_onsets=sum(start<=a['start']<=end for a in alarms),
                      paired_event_onsets=sum(start<=a['start']<=end for a in paired),
                      modified_tail_onsets=sum(a['start']>end for a in alarms),
                      paired_tail_onsets=sum(a['start']>end for a in paired),
                      modified_event_flagged_points=sum(r[name+'_flag'] is True for _,r in observed),
                      paired_event_flagged_points=sum(r[name+'_flag'] is True for t,r in zip(raw_times, raw) if t in expected),
                      preexisting_overlap=sum(a['start']<start<=a['end'] for a in alarms))
        details.append(result)
        for arm, al in [('modified', alarms), ('paired', paired)]:
            for a in al:
                episodes.append(dict(scenario_id=case['scenario_id'], method=name, arm=arm,
                                     start=a['start'].isoformat(), end=a['end'].isoformat(), points=a['points'],
                                     onset_inside_event=start<=a['start']<=end))
    return details, episodes


def contributions(details):
    result=[]
    df=pd.DataFrame(details)
    for sid,g in df[(df.category=='consumption_pattern') & df.target].groupby('scenario_id', sort=True):
        lookup=g.set_index('method').to_dict('index')
        ml=bool(lookup['ml_or']['detected']); rule=bool(lookup['sustained_high']['detected'])
        combined=bool(lookup['ml_high_or']['detected'])
        result.append(dict(scenario_id=sid, family=lookup['ml_or']['family'], ml_detected=ml,
                           rule_detected=rule, combined_detected=combined,
                           component_group='both' if ml and rule else 'ml_only' if ml else 'rule_only' if rule else 'neither',
                           combined_added_vs_ml=combined and not ml, combined_lost_vs_ml=ml and not combined,
                           combined_added_vs_rule=combined and not rule, combined_lost_vs_rule=rule and not combined,
                           component_set_union=ml or rule,
                           union_episode_differs_from_component_set=combined != (ml or rule),
                           ml_delay=lookup['ml_or']['delay_minutes'], rule_delay=lookup['sustained_high']['delay_minutes'],
                           combined_delay=lookup['ml_high_or']['delay_minutes']))
    return result


def summary_rows(details):
    df=pd.DataFrame(details);rows=[]
    targets=df[df.target]
    for level in ('category','family'):
        for (family,name),g in targets.groupby([level,'method'],sort=True):
            delays=g.delay_minutes.dropna()
            rows.append(dict(level=level,group=family,method=name,target_events=len(g),
                             detected_events=int(g.detected.sum()),missed_events=int((~g.detected.astype(bool)).sum()),
                             common_onset_detected_events=int(g.detected_common_onset.sum()),
                             event_coverage_percent=100*float(g.event_coverage.mean()),
                             common_event_coverage_percent=100*float(g.common_event_coverage.mean()),
                             stream_coverage_percent=100*float(g.stream_coverage.mean()),
                             unavailable_event_points=int(g.unavailable_event_points.sum()),
                             unavailable_stream_points=int(g.unavailable_stream_points.sum()),
                             delay_median_minutes=float(delays.median()) if len(delays) else None,
                             delay_values_minutes=json.dumps(delays.tolist()),
                             new_paired_crossings=int(g.new_paired_crossing.fillna(False).sum()),
                             paired_unknown_matches=int(g.paired_unknown_at_match.fillna(False).sum()),
                             paired_episode_onsets=int(g.paired_episode_onsets.sum()),
                             modified_episode_onsets=int(g.modified_episode_onsets.sum()),
                             paired_event_onsets=int(g.paired_event_onsets.sum()),
                             paired_tail_onsets=int(g.paired_tail_onsets.sum()),
                             modified_tail_onsets=int(g.modified_tail_onsets.sum()),
                             paired_episodes_per_observed_day=float(g.paired_episode_onsets.sum()/(g.stream_points.sum()/144))))
    return rows


def plot_cases(output, points, manifest, plan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    (output/'plots').mkdir()
    lookup={c['scenario_id']:c for c in manifest['scenarios']}
    for sid in plan['preselected_plots']:
        c=lookup[sid]; start=datetime.fromisoformat(c['start']); end=start+STEP*(c['intervals']-1)
        mod,raw=points[sid]; left=start-STEP*6; right=end+STEP*12
        fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True,gridspec_kw={'height_ratios':[1,2]})
        for data,label,style in [(raw,'Untouched pair','--'),(mod,'Modified/control','-')]:
            window=[r for r in data if left<=datetime.fromisoformat(r['timestamp'])<=right]
            axes[0].plot([datetime.fromisoformat(r['timestamp']) for r in window],[r['energy_wh'] for r in window],style,label=label)
        axes[0].set_ylabel('Interval energy, Wh');axes[0].legend()
        for lane,name in enumerate(METHODS):
            times=[datetime.fromisoformat(r['timestamp']) for r in mod if left<=datetime.fromisoformat(r['timestamp'])<=right and r[name+'_flag'] is True]
            missing=[datetime.fromisoformat(r['timestamp']) for r in mod if left<=datetime.fromisoformat(r['timestamp'])<=right and r[name+'_flag'] is None]
            axes[1].scatter(times,[lane]*len(times),s=45,marker='|',color='tab:blue')
            axes[1].scatter(missing,[lane]*len(missing),s=15,marker='x',color='gray')
        axes[1].set_yticks(range(len(METHODS)),METHODS,fontsize=9)
        axes[1].set_ylim(-.7,len(METHODS)-.3)
        for ax in axes:
            ax.axvspan(start,end+STEP,alpha=.12,color='orange');ax.grid(alpha=.2)
        axes[1].set_xlabel('Dataset time, timezone undefined; blue=true, gray x=unavailable, blank=false')
        fig.suptitle(sid+' — controlled historical scenario, not confirmed fault')
        fig.autofmt_xdate();fig.tight_layout();fig.savefig(output/'plots'/f'{sid}.png',dpi=140);plt.close(fig)


def report(output, summaries, contribution, gaps):
    primary=[r for r in summaries if r['level']=='category' and r['group']=='consumption_pattern']
    counts={name:sum(c['component_group']==name for c in contribution) for name in ['ml_only','rule_only','both','neither']}
    added=sum(c['combined_added_vs_ml'] for c in contribution);lost=sum(c['combined_lost_vs_ml'] for c in contribution)
    lines=['# ML–rules complementarity: controlled historical comparison','',
           'All33 preregistered cases retained. Fresh paired inference, existing compatible artifacts only; no training or threshold/config changes. Same previously studied UCI house/period, not a new independent holdout. Synthetic labels do not prove physical faults.','',
           '## Consumption events only (22)','',
           '| Method | Detected / target | Missed | Coverage: event / stream | Median delay,min | Raw pair episodes: all / event | New paired crossings |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for r in primary:
        delay='—' if r['delay_median_minutes'] is None else f"{r['delay_median_minutes']:g}"
        lines.append(f"| {r['method']} | {r['detected_events']}/{r['target_events']} | {r['missed_events']} | {r['event_coverage_percent']:.1f}% / {r['stream_coverage_percent']:.1f}% | {delay} | {r['paired_episode_onsets']} / {r['paired_event_onsets']} | {r['new_paired_crossings']} |")
    lines+=['','## Contribution (component event matches, not sum of union metrics)','',
            f"ML_OR only: **{counts['ml_only']}**; sustained_high only: **{counts['rule_only']}**; both: **{counts['both']}**; neither: **{counts['neither']}**.",
            f'Actual recomputed ML+high OR adds **{added}** and loses **{lost}** event matches relative to ML_OR. Net change: **{added-lost:+d}**.',
            f"Union-episode match differs from component-event set union in **{sum(c['union_episode_differs_from_component_set'] for c in contribution)}** cases.", '',
            '## Per-family detected counts','',
            '| Family | Method | Detected / target | Median delay,min |','|---|---|---:|---:|']
    for r in summaries:
        if r['level']!='family':continue
        delay='—' if r['delay_median_minutes'] is None else f"{r['delay_median_minutes']:g}"
        lines.append(f"| {r['group']} | {r['method']} | {r['detected_events']}/{r['target_events']} | {delay} |")
    lines+=['','## Controls: new episode onsets / flagged points in control window','',
            '| Control | Method | Modified | Untouched pair |','|---|---|---:|---:|']
    controls=pd.read_csv(output/'controls.csv')
    for r in controls.to_dict('records'):
        lines.append(f"| {r['scenario_id']} | {r['method']} | {r['modified_event_onsets']} / {r['modified_event_flagged_points']} | {r['paired_event_onsets']} / {r['paired_event_flagged_points']} |")
    lines+=['','## Returned gaps — separate telemetry check','',
            '| Case | Missing / reported | First return | Correct |','|---|---:|---|---|']
    for g in gaps:
        lines.append(f"| {g['scenario_id']} | {g['known_missing_intervals']} / {g['detected_missing_intervals']} | {g['actual_detection_timestamp']} | {g['correct']} |")
    lines+=['','## Interpretation and reproduction','',
            'Flatline targets and returned gaps are excluded from every consumption total above. Repeated benign zero and normal plateaus may produce a correct repetition signal without a fault. Raw UCI paired episodes are not verified false positives. Counts include duplicated historical context across independently initialized case streams, not unique physical days/buildings.',
            'All episodes are reconstructed separately for each OR on full nullable streams. A pre-existing episode does not receive overlap credit. Delay is dataset-time minutes for detected events only; misses have null delay. New paired crossing means raw-pair flag is explicitly false at the matched modified onset; unavailable raw flag is separately unknown.',
            'Coverage is decision availability, not availability of every union input: a known positive makes OR true even with missing inputs. points/* stores required/available/missing/positive contributors for both unions at every timestamp. Summary includes common-ready onset diagnostic, unavailable counts and signal rates; cases.csv retains every method/case and missed event. No cases are filtered out for incomplete coverage.',
            'Plots show true markers and unavailable crosses. Orange shading extends through the energy duration of the final interval; event matching ends at its label, with no extra grace.',
            'The local trusted bundle differs from archived original Stage4 binary; its version, exact thresholds and hashes are recorded. No archived scores are loaded. Historical24-case outputs remain unchanged and are not pooled.',
            'Reproduction: use the frozen plan/manifest in the parent directory, exact image ID, read-only repo/artifacts/dataset mount, no network and single-thread policy. Run python -m diagnostics.rule_complementarity --output NEW_EMPTY_DIRECTORY. Never reuse run1. See the parent README for exact Docker command and interpretation.', '',
            ('No additional detections from combination: any additional background episodes are burden without demonstrated event benefit on these cases.' if added==0 else 'Combination finds additional event matches in this fixed set; this is a limited complementarity result, not proof of operational precision or universal superiority.')]
    (output/'report.md').write_text('\n'.join(lines)+'\n')


def run(plan_dir,output):
    if output.exists(): raise FileExistsError('Refuse to overwrite any output directory')
    plan=json.loads((plan_dir/'plan.json').read_text());manifest=json.loads((plan_dir/'scenarios.json').read_text())
    if sha256(plan_dir/'scenarios.json')!=plan['manifest_sha256'] or RuleConfig().__dict__!=plan['rule_config'] or RuleConfig().version!=plan['rule_version']:
        raise ValueError('Registered manifest/rules differ')
    if plan['union_inputs']!={k:list(v) for k,v in UNIONS.items()} or selected_rule()!='unanimous':
        raise ValueError('Registered union/Unanimous differs')
    for path,h in plan['input_sha256'].items():
        if sha256(ROOT/path)!=h:raise ValueError('Protected input differs: '+path)
    artifacts=load_manifest(ROOT/'artifacts/mvp/docker/manifest.json')
    records=list(iter_appliances(ROOT/'data/energy/raw/energydata_complete.csv'))
    output.mkdir(parents=True,exist_ok=False);(output/'points').mkdir()
    details=[];episodes=[];gaps=[];executed=[];points={}
    for case in manifest['scenarios']:
        start=datetime.fromisoformat(case['start']);end=start+STEP*(case['intervals']-1)
        left=start.replace(hour=0,minute=0,second=0)-timedelta(days=manifest['history_days']);right=end+STEP*manifest['post_event_intervals']
        raw=[deepcopy(r) for r in records if left<=datetime.fromisoformat(r['timestamp'])<=right]
        expected=[(left+STEP*i).isoformat() for i in range(int((right-left)/STEP)+1)]
        if [r['timestamp'] for r in raw]!=expected:raise ValueError('Base timestamps incomplete; no replacement')
        changed=transform(raw,case)
        print(json.dumps(dict(case=case['scenario_id'],phase='fresh_paired_inference',raw_points=len(raw),modified_points=len(changed))),flush=True)
        altered=augment(infer(changed,artifacts));original=augment(infer(raw,artifacts))
        for arm,rows in [('modified',altered),('paired',original)]:
            df=pd.DataFrame(rows)
            for n in METHODS:df[n+'_flag']=pd.array(df[n+'_flag'],dtype='boolean')
            df.to_parquet(output/'points'/f"{case['scenario_id']}-{arm}.parquet",index=False)
        d,e=measure(case,altered,original);details.extend(d);episodes.extend(e)
        points[case['scenario_id']]=(altered,original)
        if case['family']=='interval_gap':gaps.append(check_gap(case,altered))
        executed.append({**case,'raw_points':len(raw),'modified_points':len(changed),'slice_start':left.isoformat(),'slice_end':right.isoformat()})
    if len(executed)!=plan['scenarios']:raise ValueError('Incomplete campaign')
    df=pd.DataFrame(details);df.to_csv(output/'cases.csv',index=False)
    df[df.family=='control'].to_csv(output/'controls.csv',index=False)
    pd.DataFrame(episodes).to_csv(output/'episodes.csv',index=False)
    pd.DataFrame(gaps).to_csv(output/'gaps.csv',index=False)
    contrib=contributions(details);pd.DataFrame(contrib).to_csv(output/'contributions.csv',index=False)
    summaries=summary_rows(details);pd.DataFrame(summaries).to_csv(output/'summary.csv',index=False)
    report(output,summaries,contrib,gaps);plot_cases(output,points,manifest,plan)
    write_json(output/'executed-manifest.json',executed)
    for path,h in plan['input_sha256'].items():
        if sha256(ROOT/path)!=h:raise ValueError('Protected input changed during inference: '+path)
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    except (FileNotFoundError,subprocess.CalledProcessError):commit=None
    provenance=dict(plan_sha256=sha256(plan_dir/'plan.json'),manifest_sha256=plan['manifest_sha256'],
                    runner_sha256=sha256(Path(__file__)),git_commit=commit,
                    docker_image_id=plan['docker_image_id'],rule_metadata=EnergyRules().metadata(),
                    model_metadata=artifacts.anomaly.metadata,registry=artifacts.registry(),thresholds=artifacts.anomaly.thresholds['0.99'],
                    protected_inputs_preserved=True,input_sha256=plan['input_sha256'],
                    libraries={n:importlib.metadata.version(n) for n in ['numpy','pandas','scikit-learn','torch','joblib','pyarrow','matplotlib']},
                    scenarios_completed=len(executed),scenarios_planned=plan['scenarios'],
                    trained=False,old_scores_used=False,threads=1,
                    output_sha256={str(p.relative_to(output)):sha256(p) for p in sorted(output.rglob('*')) if p.is_file()})
    write_json(output/'provenance.json',provenance)
    print(json.dumps(dict(complete=True,scenarios=len(executed),contribution_groups={g:sum(r['component_group']==g for r in contrib) for g in ['ml_only','rule_only','both','neither']},combined_added_vs_ml=sum(r['combined_added_vs_ml'] for r in contrib),combined_lost_vs_ml=sum(r['combined_lost_vs_ml'] for r in contrib))),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,default=PLAN);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();torch.set_num_threads(1)
    with threadpool_limits(1):run(args.plan,args.output)

if __name__=='__main__':main()
