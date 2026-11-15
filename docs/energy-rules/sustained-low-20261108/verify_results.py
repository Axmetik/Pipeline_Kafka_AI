from pathlib import Path
from datetime import datetime,timedelta
import hashlib,json,subprocess
import pandas as pd
import numpy as np
r=Path.cwd();base=r/'docs/energy-rules/sustained-low-20261108';out=base/'results/run1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((base/'plan.json').read_text());prov=json.loads((out/'provenance.json').read_text())
assert sha(base/'plan.json')==prov['plan_sha256']
assert sha(base/'scenarios.json')==prov['manifest_sha256']==plan['manifest_sha256']
for p,h in plan['input_sha256'].items():assert sha(r/p)==h,p
for p,h in prov['output_sha256'].items():assert sha(out/p)==h,p
for path,h in [('diagnostics/sustained_low_comparison.py',prov['runner_sha256']),('processing/energy_low_rule.py',prov['low_module_sha256'])]:
 commit=subprocess.check_output(['git','log','-1','--format=%H','--',path],text=True).strip()
 assert hashlib.sha256(subprocess.check_output(['git','show',commit+':'+path])).hexdigest()==h
cases=pd.read_csv(out/'cases.csv');contrib=pd.read_csv(out/'contributions.csv');points=sorted((out/'points').glob('*.parquet'))
assert len(points)==64 and len(cases)==32*7 and len(contrib)==24
assert len(set(cases.scenario_id))==32
assert sum(contrib.cohort=='new')==18 and sum(contrib.cohort=='known_regression')==6
reg=json.loads((out/'v2-regression.json').read_text());assert len(reg)==12 and all(x['all_exact'] for x in reg)
for row in reg:
 source=r/'docs/energy-rules/complementarity-20261108/results/run1/points'/f"{row['scenario_id'].removeprefix('known-')}-{row['arm']}.parquet"
 assert sha(source)==row['old_sha256']
rows_checked=0
for path in points:
 df=pd.read_parquet(path)
 for row in df.to_dict('records'):
  for name,inputs in plan['union_inputs'].items():
   vals={n:None if pd.isna(row[n+'_flag']) else bool(row[n+'_flag']) for n in inputs}
   expected=True if any(v is True for v in vals.values()) else None if any(v is None for v in vals.values()) else False
   actual=None if pd.isna(row[name+'_flag']) else bool(row[name+'_flag'])
   assert expected is actual
   ev=json.loads(row[name+'_provenance_json'])
   assert ev['required']==inputs and ev['positive']==[n for n,v in vals.items() if v is True]
   assert ev['missing']==[n for n,v in vals.items() if v is None]
  if pd.isna(row['sustained_low_flag']):
   assert json.loads(row['sustained_low_evidence_json'])['unavailable_reason']
  if pd.notna(row['prediction_wh']):
   assert row['forecast_target_timestamp']==row['timestamp']
   assert datetime.fromisoformat(row['forecast_origin'])+timedelta(minutes=10)==datetime.fromisoformat(row['timestamp'])
  rows_checked+=1
for c in cases.to_dict('records'):
 for arm in ['modified','paired']:
  df=pd.read_parquet(out/'points'/f"{c['scenario_id']}-{arm}.parquet",columns=['timestamp',c['method']+'_flag'])
  prev=None;active=False;starts=[]
  for stamp,flag in zip(df.timestamp,df[c['method']+'_flag']):
   t=datetime.fromisoformat(stamp);positive=pd.notna(flag) and bool(flag)
   if positive and (not active or t-prev!=timedelta(minutes=10)):starts.append(stamp)
   active=positive;prev=t
  assert len(starts)==c[arm+'_episode_onsets']
  assert sum(c['start']<=s<=c['end'] for s in starts)==c[arm+'_event_onsets']
  if arm=='modified' and c['target']:
   match=next((s for s in starts if c['start']<=s<=c['end']),None)
   assert bool(match)==bool(c['detected'])
   if match:assert c['delay_minutes']==(datetime.fromisoformat(match)-datetime.fromisoformat(c['start'])).total_seconds()/60
   else:assert pd.isna(c['delay_minutes'])
timing=pd.read_csv(out/'timing-records.csv');summ=pd.read_csv(out/'timing-summary.csv')
assert len(timing)==2*5*2*144 and len(summ)==20
for s in summ.to_dict('records'):
 g=timing[(timing.scope==s['scope']) & (timing.repeat==s['repeat']) & (timing.variant==s['variant'])]
 assert len(g)==144
 assert np.isclose(s['record_p50_ms'],np.percentile(g.elapsed_ns,50)/1e6)
 assert np.isclose(s['record_p95_ms'],np.percentile(g.elapsed_ns,95)/1e6)
 assert s['total_ms']>=g.elapsed_ns.sum()/1e6
 if s['variant']=='baseline':assert g.low_compute_ns.isna().all()
 else:assert g.low_compute_ns.notna().all()
context=dict(registration_commit='8cc7334',runner_commit=subprocess.check_output(['git','log','-1','--format=%H','--','diagnostics/sustained_low_comparison.py'],text=True).strip(),
 note='git absent in container: original provenance git_commit=null; exact source hashes verified on host against pre-execution commit.',
 scenarios_completed=32,points_files=64,rows_checked=rows_checked,all_or_decisions_and_sources_verified=True,episode_onsets_independently_reconstructed=True,
 known_v2_exact_pairs=12,known_v2_exact_records=sum(x['rows'] for x in reg),low_exact_offline_streaming_records=prov['low_exact_offline_streaming_records'],
 timing_rows=len(timing),timing_pairs=10,timing_percentiles_independently_verified=True,all_input_output_checksums_preserved=True,targeted_tests=107)
(base/'execution-context.json').write_text(json.dumps(context,indent=2)+'\n')
print(json.dumps(context,indent=2));print(pd.read_csv(out/'summary.csv').query("family=='all_consumption'").to_string(index=False));print(summ.to_string(index=False));print(pd.read_csv(out/'timing-paired-deltas.csv').to_string(index=False))
