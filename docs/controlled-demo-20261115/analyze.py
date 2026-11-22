"""Derive compact paired tables from existing CSV/DB exports. No inference."""
import argparse,csv,json
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
METHODS=['residual','autoencoder','isolation_forest','unanimous']
def readpoints(report):
 with (HERE/report['points_file']).open() as f:return list(csv.DictReader(f))
def writecsv(name,rows):
 with (HERE/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
def derive():
 control=json.loads((HERE/'control-summary.json').read_text());base=readpoints(control)
 assert len(base)==300
 selected_delta=json.loads((HERE/'context.json').read_text())['selected_delta_wh']
 summary=[];detail=[];changes=[]
 reports=[control]+[json.loads(p.read_text()) for p in sorted(HERE.glob('plus-*-summary.json'))]
 for report in reports:
  rows=readpoints(report);assert len(rows)==len(base)
  assert report['integrity']==control['integrity'] and report['models']==control['models']
  for p,q in zip(rows,base):assert p['timestamp']==q['timestamp']
  for change in report['changes']:changes.append({'delta_wh':report['delta_wh'],**change})
  start,end=report['intervention_start'],report['intervention_end']
  for method in METHODS:
   inside=[p for p in rows if start<=p['timestamp']<=end]
   triggered=[p for p in inside if p[method+'_flag']=='True']
   added=[p for p,q in zip(rows,base) if start<=p['timestamp']<=end and p[method+'_flag']=='True' and q[method+'_flag']!='True']
   lost=[p for p,q in zip(rows,base) if start<=p['timestamp']<=end and p[method+'_flag']!='True' and q[method+'_flag']=='True']
   # Reconstruct actual contiguous episodes, including runs which began before the intervention.
   expected=[];active=[]
   for p in rows:
    if p[method+'_flag']=='True':active.append(p)
    elif active:expected.append((active[0]['timestamp'],active[-1]['timestamp'],len(active),'closed'));active=[]
   if active:expected.append((active[0]['timestamp'],active[-1]['timestamp'],len(active),'open'))
   episodes=report['combined_episodes'] if method=='unanimous' else [e for e in report['episodes'] if e['detector']==method]
   actual=[(e['start_timestamp'],e['end_timestamp'],e['flagged_points'],e['status']) for e in episodes]
   assert sorted(actual)==sorted(expected)
   first=triggered[0]['timestamp'] if triggered else None
   entry=dict(delta_wh=report['delta_wh'],method=method,total_positive_points=sum(p[method+'_flag']=='True' for p in rows),
    target_positive_points=len(triggered),new_positive_points_vs_control=len(added),lost_positive_points_vs_control=len(lost),
    first_positive_during_intervention=first,delay_dataset_minutes=(datetime.fromisoformat(first)-datetime.fromisoformat(start)).total_seconds()/60 if first else None,
    target_available_points=sum(p[method+'_flag']!='' for p in inside),target_points=len(inside),whole_run_available_points=sum(p[method+'_flag']!='' for p in rows),
    total_episodes=len(episodes),onsets_inside_intervention=sum(start<=e['start_timestamp']<=end for e in episodes),
    positive_points_after_intervention=sum(p[method+'_flag']=='True' and p['timestamp']>end for p in rows),
    new_positive_points_after_intervention=sum(p[method+'_flag']=='True' and q[method+'_flag']!='True' and p['timestamp']>end for p,q in zip(rows,base)),
    final_flag=rows[-1][method+'_flag'],final_timestamp=rows[-1]['timestamp'])
   summary.append(entry)
   if report['delta_wh']==selected_delta:
    for episode in episodes:
     if episode['end_timestamp']<start:continue
     next_row=next((p for p in rows if p['timestamp']>episode['end_timestamp']),None)
     assert episode['status']=='open' or next_row and next_row[method+'_flag']!='True'
     signature=(episode['start_timestamp'],episode['end_timestamp'])
     unchanged_pair=any(e['detector']==method and (e['start_timestamp'],e['end_timestamp'])==signature for e in control['episodes'])
     detail.append(dict(method=method,episode_id=episode['episode_id'],start=episode['start_timestamp'],last_positive=episode['end_timestamp'],points=episode['flagged_points'],state=episode['status'],closed_reason=episode['closed_reason'],closure_observed_at=next_row['timestamp'] if next_row and episode['status']=='closed' else None,same_episode_in_control=unchanged_pair,onset_during_intervention=start<=episode['start_timestamp']<=end))
 writecsv('comparison.csv',summary);writecsv('episode-timeline.csv',detail);writecsv('interventions.csv',changes)
 selected=next(r for r in reports if r['delta_wh']==selected_delta);rows=readpoints(selected)
 focus=['2016-05-01T13:10:00','2016-05-01T13:20:00','2016-05-01T13:30:00','2016-05-01T13:40:00','2016-05-01T14:10:00','2016-05-01T15:10:00','2016-05-01T15:20:00','2016-05-01T15:30:00','2016-05-01T15:40:00','2016-05-01T16:50:00',rows[-1]['timestamp']]
 writecsv('key-points.csv',[p for p in rows if p['timestamp'] in focus])
 check=dict(passed=True,saved_exports_only=True,model_registries_identical_across_all_four_runs=True,contexts=len(reports),records_per_context=300,all_episode_boundaries_and_counts_match_per_point_flags=True,original_event_and_other_columns_preserved=True,delay_clock='dataset_naive measurement timestamps, not processing wall clock',total_events_injected=len(reports)-1,independent_quality_evaluation=False)
 (HERE/'analysis-verification.json').write_text(json.dumps(check,indent=2)+'\n')
 print(json.dumps([r for r in summary if r['delta_wh'] in [0,selected_delta]],ensure_ascii=False,indent=2))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,default=HERE);args=parser.parse_args();HERE=args.input.resolve();derive()
