from pathlib import Path
from datetime import datetime,timedelta
import hashlib,json,subprocess
import pandas as pd
root=Path.cwd();base=root/'docs/energy-rules/complementarity-20261108';out=base/'results/run1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((base/'plan.json').read_text());manifest=json.loads((base/'scenarios.json').read_text());prov=json.loads((out/'provenance.json').read_text())
assert sha(base/'plan.json')==prov['plan_sha256']
assert sha(base/'scenarios.json')==plan['manifest_sha256']
for path,h in plan['input_sha256'].items():assert sha(root/path)==h,path
for path,h in prov['output_sha256'].items():assert sha(out/path)==h,path
assert len(list((out/'points').glob('*.parquet')))==66
assert len(list((out/'plots').glob('*.png')))==8
cases=pd.read_csv(out/'cases.csv');contrib=pd.read_csv(out/'contributions.csv');summ=pd.read_csv(out/'summary.csv');gaps=pd.read_csv(out/'gaps.csv')
assert len(cases)==33*9
assert len(contrib)==22
assert set(cases.scenario_id)=={s['scenario_id'] for s in manifest['scenarios']}
assert gaps.correct.all()
union_defs=plan['union_inputs'];checked=0;predictions=0
for path in sorted((out/'points').glob('*.parquet')):
 df=pd.read_parquet(path)
 for row in df.to_dict('records'):
  for name,inputs in union_defs.items():
   vals={n:None if pd.isna(row[n+'_flag']) else bool(row[n+'_flag']) for n in inputs}
   expected=True if any(v is True for v in vals.values()) else None if any(v is None for v in vals.values()) else False
   actual=None if pd.isna(row[name+'_flag']) else bool(row[name+'_flag'])
   assert actual is expected,(path,name,row['timestamp'])
   provenance=json.loads(row[name+'_provenance_json'])
   assert provenance['positive']==[n for n,v in vals.items() if v is True]
   assert provenance['missing']==[n for n,v in vals.items() if v is None]
   assert provenance['available']==[n for n,v in vals.items() if v is not None]
   assert provenance['required']==inputs
  if pd.notna(row['prediction_wh']):
   assert row['forecast_target_timestamp']==row['timestamp']
   assert datetime.fromisoformat(row['forecast_origin'])+timedelta(minutes=10)==datetime.fromisoformat(row['timestamp'])
   predictions+=1
  checked+=1
# Independent episode onset extraction from persisted data, with tri-state and cadence breaks.
for detail in cases.to_dict('records'):
 sid=detail['scenario_id'];name=detail['method'];start=detail['start'];end=detail['end']
 counts={}
 for arm in ('modified','paired'):
  frame=pd.read_parquet(out/'points'/f'{sid}-{arm}.parquet',columns=['timestamp',name+'_flag'])
  prev_time=None;prev_true=False;onsets=[]
  for t,flag in zip(frame.timestamp,frame[name+'_flag']):
   true=pd.notna(flag) and bool(flag)
   stamp=datetime.fromisoformat(t)
   if true and (not prev_true or stamp-prev_time!=timedelta(minutes=10)):onsets.append(t)
   prev_time=stamp;prev_true=true
  counts[arm]=onsets
  assert len(onsets)==detail[arm+'_episode_onsets']
  assert sum(start<=s<=end for s in onsets)==detail[arm+'_event_onsets']
 if detail['target']:
  match=next((s for s in counts['modified'] if start<=s<=end),None)
  assert bool(match)==bool(detail['detected'])
  if match:assert detail['delay_minutes']==(datetime.fromisoformat(match)-datetime.fromisoformat(start)).total_seconds()/60
  else:assert pd.isna(detail['delay_minutes'])
runner_commit=subprocess.check_output(['git','log','-1','--format=%H','--','diagnostics/rule_complementarity.py'],text=True).strip()
committed=subprocess.check_output(['git','show',runner_commit+':diagnostics/rule_complementarity.py'])
assert hashlib.sha256(committed).hexdigest()==prov['runner_sha256']
context=dict(registration_commit='950d6b7',runner_commit=runner_commit,runner_matches_provenance_sha256=True,
 note='git is absent inside inference image; provenance git_commit is null. Exact runner hash verified against host pre-execution Git commit.',
 all_output_hashes_verified=True,protected_inputs_preserved=True,scenarios_completed=33,point_files=66,plots=8,
 cases_method_rows=len(cases),consumption_events=22,all_point_union_and_provenance_checks=checked,causal_residual_prediction_alignments=predictions,
 independent_saved_point_episode_and_match_reconstruction=True,targeted_tests=79,
 limits=dict(cpu=1,memory='2g',threads=1,network='none',source_artifacts_dataset='read-only',write='new result directory'))
(base/'execution-context.json').write_text(json.dumps(context,indent=2)+'\n')
print(json.dumps(context,indent=2));print(summ[(summ.level=='category') & (summ.group=='consumption_pattern')].to_string(index=False));print(contrib.to_string(index=False))
