"""Saved complementarity flags only; no model imports/inference or detector changes."""
from pathlib import Path
from datetime import datetime,timedelta
import argparse,hashlib,json
import pandas as pd
ROOT=Path.cwd();SRC=ROOT/'docs/energy-rules/complementarity-20261108'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'docs/energy-rules/final-high-comparison-20261108');OUT=p.parse_args().output
if OUT.exists():raise FileExistsError('Never overwrite results')
STEP=timedelta(seconds=600);NAMES=('residual','residual_high_or','ml_high_or')
INPUTS=('residual','sustained_high','isolation_forest','autoencoder')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
hashes={str(SRC/'scenarios.json'):sha(SRC/'scenarios.json'),str(SRC/'plan.json'):sha(SRC/'plan.json')}
manifest=json.loads((SRC/'scenarios.json').read_text());cases=[c for c in manifest['scenarios'] if c['target'] and c['category']=='consumption_pattern'];assert len(cases)==22

def value(v):return None if pd.isna(v) else bool(v)
def union(vals):return True if any(v is True for v in vals) else None if any(v is None for v in vals) else False
def onsets(times,flags):
 out=[];last=None;active=False
 for t,f in zip(times,flags):
  if f is True:
   if not active or t-last!=STEP:out.append(t)
   active=True
  else:active=False
  last=t
 return out

details=[];episodes=[]
for c in cases:
 start=datetime.fromisoformat(c['start']);end=start+STEP*(c['intervals']-1);arms={}
 for arm in ['modified','paired']:
  f=SRC/'results/run1/points'/f"{c['scenario_id']}-{arm}.parquet";hashes[str(f)]=sha(f)
  df=pd.read_parquet(f,columns=['timestamp',*[n+'_flag' for n in INPUTS],'ml_high_or_flag'])
  times=[datetime.fromisoformat(t) for t in df.timestamp]
  source={n:[value(v) for v in df[n+'_flag']] for n in INPUTS}
  flags=dict(residual=source['residual'],residual_high_or=[union(v) for v in zip(source['residual'],source['sustained_high'])],ml_high_or=[union(v) for v in zip(*(source[n] for n in INPUTS))])
  assert flags['ml_high_or']==[value(v) for v in df.ml_high_or_flag]
  event=[i for i,t in enumerate(times) if start<=t<=end]
  assert [times[i] for i in event]==[start+i*STEP for i in range(c['intervals'])]
  result={}
  for name in NAMES:
   starts=onsets(times,flags[name]);hit=next((t for t in starts if start<=t<=end),None)
   result[name]=dict(hit=hit,episode_count=len(starts),event_episode_count=sum(start<=t<=end for t in starts),available=sum(flags[name][i] is not None for i in event),expected=len(event))
   episodes.extend(dict(scenario_id=c['scenario_id'],arm=arm,method=name,onset=t.isoformat(),inside_event=start<=t<=end) for t in starts)
  arms[arm]=result
 for name in NAMES:
  m=arms['modified'][name];r=arms['modified']['residual'];raw=arms['paired'][name]
  details.append(dict(scenario_id=c['scenario_id'],family=c['family'],method=name,event_start=c['start'],event_end=end.isoformat(),detected=m['hit'] is not None,alarm_onset=m['hit'].isoformat() if m['hit'] else None,delay_minutes=(m['hit']-start).total_seconds()/60 if m['hit'] else None,added_vs_residual=m['hit'] is not None and r['hit'] is None,lost_vs_residual=m['hit'] is None and r['hit'] is not None,paired_episode_onsets=raw['episode_count'],paired_event_onsets=raw['event_episode_count'],event_available_points=m['available'],event_expected_points=m['expected']))
D=pd.DataFrame(details);summ=[]
for name in NAMES:
 g=D[D.method==name];delay=g.delay_minutes.dropna()
 summ.append(dict(method=name,detected_events=int(g.detected.sum()),target_events=len(g),added_vs_residual=int(g.added_vs_residual.sum()),lost_vs_residual=int(g.lost_vs_residual.sum()),median_delay_minutes=float(delay.median()) if len(delay) else None,paired_episode_onsets=int(g.paired_episode_onsets.sum()),paired_event_onsets=int(g.paired_event_onsets.sum()),target_coverage_percent=100*float(g.event_available_points.sum()/g.event_expected_points.sum())))
a=set(D[(D.method=='residual_high_or')&D.detected].scenario_id);b=set(D[(D.method=='ml_high_or')&D.detected].scenario_id)
OUT.mkdir();D.to_csv(OUT/'event-matches.csv',index=False);pd.DataFrame(summ).to_csv(OUT/'summary.csv',index=False);pd.DataFrame(episodes).to_csv(OUT/'episode-onsets.csv',index=False)
L=['# Фінальне порівняння residual / high на complementarity-20261108','',
'Лише збережені per-point flags цього експерименту. Всі22 consumption-події, ті самі44 modified/paired потоки. Немає inference, training, Docker, тестів, нових сценаріїв або змін моделей/порогів. Low-кандидати не використовуються, flatline/interval_gap залишаються окремою telemetry-quality задачею та не входять у ці22 події.','',
'| Варіант | Виявлено / всього | Додано / втрачено проти residual | Медіанна затримка | Епізоди на незмінених парах | Coverage цільових інтервалів |','|---|---:|---:|---:|---:|---:|']
labels=dict(residual='residual',residual_high_or='residual OR sustained_high',ml_high_or='ML OR sustained_high')
for r in summ:
 d='—' if r['median_delay_minutes'] is None else f"{r['median_delay_minutes']:g} хв"
 L.append(f"| {labels[r['method']]} | {r['detected_events']}/{r['target_events']} | +{r['added_vs_residual']} / −{r['lost_vs_residual']} | {d} | {r['paired_episode_onsets']} | {r['target_coverage_percent']:.0f}% |")
L+=['',
'**Рекомендація для окремо погодженої інтеграції: residual OR sustained_high як experimental review channel.** Обидва об’єднання виявляють той самий набір11 подій, мають однакову медіанну затримку30хв, але residual|high має121 парний епізод проти231 у ML|high —на110 менше. Проти residual окремо додаються3 події без втрат і без збільшення кількості парних епізодів. У цьому порівнянні немає виграшу від додавання IF/AE до цього об’єднання. Чинний Unanimous не змінюється; реалізацію/інтеграцію не виконано.','',
'OR=true, якщо хоча б один доступний вхід позитивний; false лише за всіх доступних негативних; інакше null. Епізоди **кожного** варіанту перебудовано на повних послідовностях передісторії/події/хвоста, а не складено з компонентів. Null,false і розрив600s розривають епізод. Зараховується лише onset усередині включних першого/останнього label події; раніше початий сигнал не отримує overlap-credit, післяподієвого grace немає. Максимум одне виявлення кожної події. Missed delay=null, не0.',
'Coverage —частка доступних modified-рішень на всіх очікуваних цільових точках; жодну подію не відкинуто. Медіанна затримка —лише виявлені події, хвилини часу датасету, не compute latency. Парні епізоди сумуються за повними22 окремо ініціалізованими raw-потоками з повторюваними контекстами; це не унікальні фізичні події та **не підтверджені хибні тривоги**. Історичний вже переглянутий будинок, не незалежна перевірка покращення.',
'Повні подієві результати: [event-matches.csv](event-matches.csv); усі заново обчислені onsets: [episode-onsets.csv](episode-onsets.csv); [машинна таблиця](summary.csv), [provenance/hashes](provenance.json). analyze.py читає тільки потрібні колонки flags/timestamp; старі збережені ML|high flags також точно звірено з переобчисленим OR.']
assert a==b,'Revise recommendation: detection sets differ'
(OUT/'README.md').write_text('\n'.join(L)+'\n')
for path,h in hashes.items():assert sha(Path(path))==h,path
(OUT/'provenance.json').write_text(json.dumps(dict(source='complementarity-20261108 only',input_sha256={str(Path(p).relative_to(ROOT)):h for p,h in hashes.items()},same_union_detected_event_sets=a==b,detected_event_ids=sorted(a),no_inference=True,no_training=True,no_docker=True,no_tests=True,no_low=True,episodes_recomputed=True,existing_ml_high_flags_exactly_match=True),indent=2)+'\n')
print(pd.DataFrame(summ).to_string(index=False))
