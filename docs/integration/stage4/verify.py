"""Only GET existing API/static assets and inspect local evidence. No inference/replay."""
import csv,gzip,hashlib,json,re,subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PREV=OUT.parent/'stage2'
THIRD=OUT.parent/'stage3'
ENV=json.loads((PREV/'environment.json').read_text())
BASE=ENV['base_url']

def sha(data):return hashlib.sha256(data).hexdigest()
def get(path,params=None):
 with urlopen(BASE+path+('?' + urlencode(params) if params else ''),timeout=15) as r:return r.read()
def api(kind,run):
 params=dict(run_id=run,building_id='appliances-house-1',source_id='uci-appliances',limit=1000,
             start='2016-05-01T09:20:00',end='2016-05-02T09:20:00')
 result=[]
 while True:
  page=json.loads(get('/api/'+kind,params));result+=page['items']
  if not page['next_cursor']:return result
  params['cursor']=page['next_cursor']

def curve_points(d):
 result=[]
 for command,part in re.findall(r'([MLC])([^MLC]+)',d):
  nums=[float(x) for x in re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',part)]
  step=6 if command=='C' else 2
  assert len(nums)%step==0
  result.extend((nums[i+step-2],nums[i+step-1]) for i in range(0,len(nums),step))
 return result

def main():
 saved=json.loads(gzip.decompress((THIRD/'source-api.json.gz').read_bytes()))
 verification={'base_url':BASE,'application_code_sha':'a6c1287ea8532aacb2d04c346d96d5d2595b9ad1',
               'evidence_start_sha':'30912158e2be2031b498ebca85d45dd29fe44103','scenarios':{}}
 axes=json.loads((OUT/'chart-axis-audit.json').read_text())['ticks']
 ticks={float(x['text']):float(x['y']) for x in axes}
 assert sorted(ticks)==[0,150,300,450,600]
 for label,ids in ENV['scenarios'].items():
  measurements=api('measurements',ids['run_id']);scores=api('anomaly-scores',ids['run_id'])
  rules=api('rule-assessments',ids['run_id']);hybrid=api('hybrid-decisions',ids['run_id'])
  combined=api('combined-decisions',ids['run_id'])
  assert (len(measurements),len(scores),len(rules),len(hybrid),len(combined))==(144,432,432,144,144)
  for endpoint,rows in [('measurements',measurements),('anomaly-scores',scores),('rule-assessments',rules),('hybrid-decisions',hybrid),('combined-decisions',combined)]:
   key='measurement_id' if endpoint=='measurements' else 'score_id' if endpoint=='anomaly-scores' else 'assessment_id' if endpoint=='rule-assessments' else 'decision_id'
   old={x[key]:x for x in saved['scenarios'][label][endpoint]}
   assert all(x==old[x[key]] for x in rows),('changed persisted API row',label,endpoint)
  flags={}
  for row in scores+rules:
   method=row.get('detector',row.get('rule'));flags[row['measurement_timestamp'],method]=row['flag']
  for row in hybrid:flags[row['measurement_timestamp'],'hybrid']=row['flag']
  for row in combined:flags[row['measurement_timestamp'],'unanimous']=row['flag']
  checks={stamp:{m:flags['2016-05-01T'+stamp,m] for m in ('residual','sustained_high','hybrid','isolation_forest','autoencoder','unanimous')}
          for stamp in ('13:20:00','13:30:00','13:40:00','13:50:00','14:00:00','14:10:00','15:10:00','15:20:00','15:30:00','15:40:00','16:50:00')}
  if label=='plus-450':
   assert checks['13:20:00']['residual'] is checks['13:20:00']['hybrid'] is True
   assert all(checks[t]['hybrid'] is False for t in ('13:30:00','13:40:00','13:50:00','14:00:00'))
   assert checks['14:10:00']['sustained_high'] is checks['14:10:00']['hybrid'] is True
   assert checks['15:10:00']['sustained_high'] is checks['15:10:00']['hybrid'] is True
   assert checks['13:30:00']['hybrid'] is checks['15:30:00']['hybrid'] is False
   assert checks['15:20:00']['sustained_high'] is False and checks['15:20:00']['residual'] is checks['15:20:00']['hybrid'] is True
  assert all(x is False for x in checks['15:40:00'].values())
  assert checks['16:50:00']['residual'] is checks['16:50:00']['hybrid'] is True
  chart=json.loads((OUT/('control-chart-dom.json' if label=='control' else 'modified-chart-dom.json')).read_text())
  assert '144 точок у вікні' in chart['text']
  assert all(str(int(t)) in chart['text'].splitlines() for t in ticks)
  actual=next(x for x in chart['paths'] if 'area' in x['class'])
  rendered=curve_points(actual['d'])
  chronological=sorted(measurements,key=lambda x:x['measurement_timestamp'])
  assert len(rendered)==len(chronological)==144
  expected_y=[ticks[0]+x['energy_wh']*(ticks[600]-ticks[0])/600 for x in chronological]
  max_error=max(abs(y-want) for (x,y),want in zip(rendered,expected_y))
  assert max_error<=0.0011
  forecasts=json.loads(get('/api/forecasts',dict(run_id=ids['run_id'],building_id='appliances-house-1',source_id='uci-appliances',purpose='primary_forecast',limit=145)))['items']
  fbytime={x['forecast_target_timestamp']:x['predicted_energy_wh'] for x in forecasts}
  forecast=next(x for x in chart['paths'] if 'line' in x['class'])
  fpoints=curve_points(forecast['d'])
  stamps=[x['measurement_timestamp'] for x in chronological]+['2016-05-02T09:20:00']
  assert len(fpoints)==145
  x0,x1=fpoints[0][0],fpoints[-1][0]
  assert all(abs(x-(x0+i*(x1-x0)/144))<=0.0011 for i,(x,y) in enumerate(fpoints))
  assert all(abs(x-(x0+i*(x1-x0)/144))<=0.0011 for i,(x,y) in enumerate(rendered))
  forecast_error=max(abs(y-(ticks[0]+fbytime[t]*(ticks[600]-ticks[0])/600)) for (x,y),t in zip(fpoints,stamps))
  assert forecast_error<=0.0011
  # Row text is rendered UI, not synthesized labels. Compare every hybrid row to API source.
  rows=json.loads((OUT/('control-hybrid-event-rows.json' if label=='control' else 'hybrid-event-rows.json')).read_text())
  old=saved['scenarios'][label]['hybrid-events']
  assert len(rows)-1==len(old)
  for e in old:
   a,b=e['start_timestamp'].replace('T',' '),e['end_timestamp'].replace('T',' ')
   matched=[r for r in rows[1:] if a in r and b in r]
   assert len(matched)==1 and e['status'] in matched[0] and e['closed_reason'] in matched[0]
  counts={m:sum(x['flag'] is True for x in scores if x['detector']==m) for m in ('isolation_forest','autoencoder','residual')}
  verification['scenarios'][label]=dict(unchanged_API_rows_verified=144+432+432+144+144,required_point_checks=checks,
     actual_chart_points_verified=144,HGB20_target_aligned_chart_points_verified=145,
     maximum_actual_chart_error_pixels=max_error,maximum_forecast_chart_error_pixels=forecast_error,
     visible_window_positive_ML_counts=counts,UI_hybrid_episode_rows_verified=len(old))
 advanced=(OUT/'advanced-dom.txt').read_text()
 assert all(f'Перевищень у вибраному вікні: {n}' in advanced for n in (9,10,3))
 assert '2016-05-02 09:10:00' in advanced and 'Відхилення немає за обома доступними входами' in advanced
 catalog=(OUT/'catalog-dom.txt').read_text()
 assert all(s in catalog for s in ('11 на цій сторінці','Освітлення','Кухня','Зовні будівлі'))
 # Prove actual served frontend assets are those of the frozen Stage2 build.
 launch=json.loads((PREV/'launch-config.json').read_text())
 assets={}
 for path,expected in launch['dashboard_assets_sha256'].items():
  rel=path.removeprefix('dashboard/dist/')
  assert sha((ROOT/path).read_bytes())==sha(get('/'+rel))==expected
  assets[rel]=expected
 state=json.loads(subprocess.check_output(['docker','inspect',ENV['api']],text=True))[0]
 assert state['Config']['Cmd']==['python','docs/integration/stage2/serve.py']
 assert state['Image']==launch['images']['energy-monitoring-backend:local']
 mounts={x['Destination']:x for x in state['Mounts']}
 assert mounts['/work']['Source']==str(ROOT) and all(not x['RW'] for x in mounts.values())
 runtime_env=dict(x.split('=',1) for x in state['Config']['Env'])
 assert runtime_env['EMAIL_NOTIFICATIONS_ENABLED']=='false' and runtime_env['MVP_ENERGY_RULES_ENABLED']=='true'
 verification.update(served_frontend_assets_sha256=assets,backend_image_id=state['Image'],read_only_worktree_mount=str(ROOT),
       email_enabled=False,rules_enabled=True,public_binding=state['NetworkSettings']['Ports'],
       actual_time_window={'measurements':'2016-05-01T09:20:00..2016-05-02T09:10:00','forecast_last_target':'2016-05-02T09:20:00','points':144},
       same_control_modified_y_axis_Wh=[0,600],arbitrary_time_filter_available=False,rule_decision_history_available_in_UI=False,
       closing_measurement_timestamp_displayed_in_UI=False,derived_high_episode_not_claimed_as_persisted=True,
       screenshots_via='cua_repl only; native JPEG originals preserved; PNG conversion/cropping only',
       new_replay_inference_training_full_tests=False,application_changes=False)
 (OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
 print('Read-only UI/API verification passed; all 288 actual and 290 HGB20 rendered points match persisted values.')

if __name__=='__main__':main()
