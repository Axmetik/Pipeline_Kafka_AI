import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const require=createRequire(new URL('../../dashboard/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const dir=(process.env.CONTROLLED_DEMO_OUTPUT || fileURLToPath(new URL('.',import.meta.url))).replace(/\/?$/, '/');
const context=JSON.parse(readFileSync(dir+'context.json','utf8'));
const base=process.env.CONTROLLED_DEMO_BASE;
if(!base?.startsWith('http://127.0.0.1:'))throw Error('Use isolated run.py');
for(let i=0;i<40;i++){try{if((await fetch(base+'/health/ready')).ok)break;}catch{}await new Promise(r=>setTimeout(r,500));}
function csv(name){const [header,...lines]=readFileSync(dir+name,'utf8').trim().split(/\r?\n/).map(line=>line.split(','));return lines.map(values=>Object.fromEntries(header.map((key,i)=>[key,values[i]])));}
const bool=value=>value===''?null:value==='True';
const number=value=>value===''?null:Number(value);
const reports=context.reports.map(name=>JSON.parse(readFileSync(dir+name,'utf8')));
const apiChecks=[];
async function get(endpoint,run,limit=1000){const r=await fetch(base+'/api/'+endpoint+'?'+new URLSearchParams({run_id:run,building_id:context.building_id,source_id:context.source_id,limit:String(limit)}));expect(r.status).toBe(200);const body=await r.json();expect(body.next_cursor).toBeNull();return body.items;}
for(const report of reports){
 const points=csv(report.points_file),by=new Map(points.map(p=>[p.measurement_id,p]));
 const measurements=await get('measurements',report.run_id);expect(measurements.length).toBe(300);
 for(const m of measurements){const p=by.get(m.measurement_id);expect(p).toBeTruthy();expect(m.measurement_timestamp).toBe(p.timestamp);expect(m.energy_wh).toBe(Number(p.energy_wh));expect(m.time_basis).toBe('dataset_naive');expect(m.run_id).toBe(report.run_id);}
 const scores=await get('anomaly-scores',report.run_id);expect(scores.length).toBe(900);
 for(const score of scores){const p=by.get(score.measurement_id);expect(score.score).toBe(number(p[score.detector+'_score']));expect(score.flag).toBe(bool(p[score.detector+'_flag']));expect(score.threshold).toBe(Number(p[score.detector+'_threshold']));expect(score.status).toBe(p[score.detector+'_status']);if(score.detector==='residual'&&score.status==='ready'){expect(score.forecast_target_timestamp).toBe(p.timestamp);expect(score.prediction_wh).toBe(number(p.RF21_target_forecast_wh));}}
 const forecasts=await get('forecasts',report.run_id);expect(forecasts.length).toBe(600);
 for(const p of points){const f=forecasts.find(f=>f.purpose==='primary_forecast'&&f.forecast_target_timestamp===p.timestamp);if(f)expect(f.predicted_energy_wh).toBe(number(p.HGB20_target_forecast_wh));}
 const decisions=await get('combined-decisions',report.run_id);expect(decisions.length).toBe(300);
 for(const row of decisions)expect(row.flag).toBe(bool(by.get(row.measurement_id).unanimous_flag));
 const events=await get('events',report.run_id);expect(events.length).toBe(report.episodes.length);
 for(const event of events){const stored=report.episodes.find(e=>e.episode_id===event.episode_id);for(const key of ['start_timestamp','end_timestamp','status','detector','flagged_points'])expect(event[key]).toBe(stored[key]);}
 const notifications=await get('notifications',report.run_id);expect(notifications.length).toBe(0);
 apiChecks.push({run_id:report.run_id,measurements:300,forecasts:600,scores:900,combined_decisions:300,episodes:events.length,notifications:0,all_exported_values_flags_and_timestamps_match:true});
}
const browser=await chromium.launch({channel:'chrome',headless:true});
const shots=[];
try{
 const bctx=await browser.newContext({viewport:{width:1500,height:1200},timezoneId:'Pacific/Honolulu',reducedMotion:'reduce'}),page=await bctx.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 const url=run=>base+'/?'+new URLSearchParams({view:'source',run,building:context.building_id,source:context.source_id,channel:'appliances'});
 async function open(run){await page.goto(url(run));await expect(page.getByTestId('source-energy-chart')).toBeVisible();await expect(page.getByTestId('source-latest-energy')).not.toContainText('—');await page.waitForTimeout(250);expect(await page.locator('.app-shell').count()).toBe(1);await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
 async function shot(name,run,description){await page.screenshot({path:dir+name,fullPage:true});shots.push({file:name,url:page.url().replace(base,'http://127.0.0.1:<isolated-port>'),run_id:run,building_id:context.building_id,source_id:context.source_id,window_measurements:name==='episodes-desktop.png'?null:144,scope:name==='episodes-desktop.png'?'whole selected run, explicitly labeled by UI':'last 144 measurements',description});}
 await open(context.control_run);await shot('control-overview-desktop.png',context.control_run,'Незмінений парний потік, 144 останні вимірювання');
 const selected=reports[1],points=csv(selected.points_file).slice(-144);
 await open(context.selected_run);
 async function hoverAt(stamp){
  await page.evaluate(()=>window.scrollTo(0,0));
  const grid=page.getByTestId('source-energy-chart').locator('.recharts-cartesian-grid');const box=await grid.boundingBox();expect(box).toBeTruthy();
  const index=points.findIndex(p=>p.timestamp===stamp);expect(index).toBeGreaterThanOrEqual(0);
  await page.mouse.move(box.x+box.width*index/144,box.y+box.height/2);await page.waitForTimeout(200);
  await expect(page.getByTestId('source-energy-chart').locator('.recharts-tooltip-wrapper')).toContainText(stamp.replace('T',' '));
 }
 const eventPoint=points.find(p=>p.timestamp===selected.intervention_start);
 await hoverAt(eventPoint.timestamp);await shot('injection-overview-desktop.png',context.selected_run,'Факт + HGB20: до, під час і після ін’єкції; tooltip на початку втручання');
 await page.mouse.move(5,5);await page.getByRole('tab',{name:'Детектори',exact:true}).click();
 for(const method of ['isolation_forest','autoencoder','residual']){await expect(page.getByTestId('detector-'+method)).toContainText('Поріг');}
 await shot('detectors-desktop.png',context.selected_run,'Реальні scores і q99 пороги всіх методів; останні оцінки після втручання');
 await page.getByRole('tab',{name:'Епізоди',exact:true}).click();
 if(selected.episodes.length)await expect(page.locator('tbody tr')).toHaveCount(selected.episodes.length);
 await shot('episodes-desktop.png',context.selected_run,'Фактичний журнал епізодів; статуси не редагувалися');
 await page.getByRole('tab',{name:'Огляд',exact:true}).click();
 await hoverAt(points.at(-1).timestamp);await shot('after-intervention-desktop.png',context.selected_run,'Початковий ряд після втручання, tooltip на останньому вимірюванні');
 expect(errors).toEqual([]);
 const result={passed:true,api_checks:apiChecks,selected_run:context.selected_run,same_plot_window_for_all_modified_graph_screenshots:true,episodes_scope:"Original UI journal shows whole selected run, explicitly labeled; graph window is last 144 points",window_start:points[0].timestamp,window_end:points.at(-1).timestamp,forecast_tail:'one next-interval HGB20 forecast, no fabricated actual',browser_timezone:'Pacific/Honolulu',dataset_labels_unshifted:true,runtime_errors:errors,screenshots:shots};
 writeFileSync(dir+'browser-verification.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({browser_passed:true,api_runs:apiChecks.length,screenshots:shots.length}));
}finally{await browser.close();}
