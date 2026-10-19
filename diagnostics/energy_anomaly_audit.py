"""Post-hoc paired diagnostics; never fits models or changes Stage 4 results."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from anomaly.evaluate import runs, metrics
from anomaly.features import NAMES

ROOT = Path(__file__).resolve().parents[1]


def event_matches(flags, times, events):
    """Expose the original overlap rule, including pre-existing alarm episodes."""
    matches = {}
    for start, end in runs(flags, times):
        candidates = [e for e in events if e['event_id'] not in matches and e['start'] <= end and e['end'] >= start]
        if candidates:
            event = min(candidates, key=lambda e: e['start'])
            matches[event['event_id']] = {'episode_start': start, 'episode_end': end,
                                          'first_overlap': max(start, event['start'])}
    return matches


def paired_summary(frame):
    clean, modified = frame.clean_score.to_numpy(), frame.modified_score.to_numpy()
    delta = modified - clean
    threshold = float(frame.threshold.iloc[0])
    cf, mf = clean > threshold, modified > threshold
    return {'points': len(frame), 'clean_p50': float(np.median(clean)), 'clean_p95': float(np.quantile(clean,.95)),
            'modified_p50': float(np.median(modified)), 'modified_p95': float(np.quantile(modified,.95)),
            'modified_p99': float(np.quantile(modified,.99)), 'delta_p05': float(np.quantile(delta,.05)),
            'delta_p50': float(np.median(delta)), 'delta_p95': float(np.quantile(delta,.95)),
            'mean_abs_delta': float(np.abs(delta).mean()), 'increased_fraction': float((delta > 1e-12).mean()),
            'clean_crossings': int(cf.sum()), 'modified_crossings': int(mf.sum()),
            'new_crossings': int((mf & ~cf).sum()), 'lost_crossings': int((cf & ~mf).sum()),
            'threshold': threshold, 'modified_crossing_rate': float(mf.mean()),
            'new_crossing_rate': float((mf & ~cf).mean())}


def analyze(results, output):
    if output.exists():
        raise ValueError('Use a new diagnostics output path')
    output.mkdir(parents=True)
    frozen = json.loads((results / 'checksums.json').read_text())
    for name, checksum in frozen.items():
        if hashlib.sha256((results / name).read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Frozen output checksum mismatch: {name}')
    thresholds = json.loads((results / 'thresholds.json').read_text())
    clean = {split: pd.read_parquet(results / f'scores/{split}-clean.parquet') for split in ('validation','test')}
    points, events, adaptation, tails, distributions, detailed_matches = [], [], [], [], [], []
    # Unique unchanged streams and calibration are not multiplied by scenario count.
    for split in ('calibration','validation','test'):
        original = pd.read_parquet(results / 'scores/calibration.parquet') if split == 'calibration' else clean[split]
        for name in NAMES:
            values = original[name].to_numpy()
            distributions.append({'split': split, 'detector': name, 'count': len(values),
                **{f'p{int(q*1000):03d}':float(np.quantile(values,q)) for q in (.5,.9,.95,.98,.99,.995,1.)},
                'primary_threshold':thresholds['0.99'][name],
                'primary_crossings':int((values>thresholds['0.99'][name]).sum())})
    for path in sorted((results / 'manifests').glob('*.json')):
        manifest = json.loads(path.read_text())
        split, scenario = manifest['split'], manifest['scenario']
        modified = pd.read_parquet(results / f'scores/{split}-{scenario}.parquet')
        original = clean[split]
        keys = ['building_id','source_id','measurement_timestamp','event_id']
        pd.testing.assert_frame_equal(original[keys], modified[keys])
        labels = modified.synthetic_label.to_numpy(bool)
        tail = np.zeros(len(modified),bool)
        identity = {'split':split,'scenario':scenario,'scenario_type':manifest['type'],'seed':manifest['seed']}
        for event in manifest['events']:
            start,end = event['start'],event['end']
            tail[end+1:min(len(tail),end+145)] = True
            ei = identity | {'event_id':event['event_id'],'type':event['type'],'severity':event['severity'],
                             'start':start,'end':end,'duration':event['duration']}
            energy_delta = modified.actual_energy_wh.iloc[start:end+1].to_numpy()-original.actual_energy_wh.iloc[start:end+1].to_numpy()
            forecast_delta = modified.prediction_wh.iloc[start:end+1].to_numpy()-original.prediction_wh.iloc[start:end+1].to_numpy()
            signed_delta = modified.signed_residual_wh.iloc[start:end+1].to_numpy()-original.signed_residual_wh.iloc[start:end+1].to_numpy()
            np.testing.assert_allclose(signed_delta,energy_delta-forecast_delta,rtol=1e-10,atol=1e-10)
            adaptation.append(ei | {'energy_delta_first':float(energy_delta[0]),'energy_delta_last':float(energy_delta[-1]),
                'forecast_delta_first':float(forecast_delta[0]),'forecast_delta_last':float(forecast_delta[-1]),
                'signed_residual_delta_first':float(signed_delta[0]),'signed_residual_delta_last':float(signed_delta[-1]),
                'constant_energy_delta':bool(np.allclose(energy_delta,energy_delta[0])),
                'residual_clean_first':float(original.residual.iloc[start]),'residual_modified_first':float(modified.residual.iloc[start]),
                'residual_clean_last':float(original.residual.iloc[end]),'residual_modified_last':float(modified.residual.iloc[end]),
                'cancellation_last':float(forecast_delta[-1]/energy_delta[-1]) if abs(energy_delta[-1])>1e-12 else None})
            for name in NAMES:
                threshold = thresholds['0.99'][name]
                c,m = original[name].iloc[start:end+1].to_numpy(),modified[name].iloc[start:end+1].to_numpy()
                point = pd.DataFrame({'index':np.arange(start,end+1),'clean_score':c,'modified_score':m,'threshold':threshold})
                point['delta_score']=m-c
                for key,value in (ei | {'detector':name}).items():
                    point[key]=value
                points.append(point)
                events.append(ei | {'detector':name,**paired_summary(point)})
        tail &= ~labels
        for name in NAMES:
            threshold = thresholds['0.99'][name]
            c,m=original.loc[tail,name].to_numpy(),modified.loc[tail,name].to_numpy()
            tails.append(identity | {'detector':name,'tail_points':len(c),
                'clean_alarms':int((c>threshold).sum()),'modified_alarms':int((m>threshold).sum()),
                'new_alarms':int(((m>threshold)&(c<=threshold)).sum()),
                'lost_alarms':int(((m<=threshold)&(c>threshold)).sum()),
                'changed_scores':int((np.abs(m-c)>1e-10).sum())})
            for q,values in thresholds.items():
                flags = modified[name].to_numpy()>values[name]
                cf = original[name].to_numpy()>values[name]
                matched = event_matches(flags,modified.measurement_timestamp,manifest['events'])
                _,outcomes = metrics(flags,labels,modified.measurement_timestamp,manifest['events'])
                assert {e['event_id'] for e in outcomes if e['detected']} == set(matched)
                for event in manifest['events']:
                    start,end=event['start'],event['end'];match=matched.get(event['event_id'])
                    detailed_matches.append(identity | {'type':event['type'],'severity':event['severity'],
                        'detector':name,'quantile':float(q),'event_id':event['event_id'],'start':start,'end':end,
                        'original_detected':match is not None,
                        'episode_started_before_event':bool(match and match['episode_start']<start),
                        'episode_start':match['episode_start'] if match else None,
                        'clean_flag_at_original_detection':bool(cf[match['first_overlap']]) if match else None,
                        'new_flag_somewhere_during_event':bool((flags[start:end+1]&~cf[start:end+1]).any()),
                        'clean_alarms_during_event':int(cf[start:end+1].sum()),
                        'modified_alarms_during_event':int(flags[start:end+1].sum())})
    point_frame=pd.concat(points,ignore_index=True)
    point_frame.to_parquet(output / 'paired_event_scores.parquet',index=False)
    pd.DataFrame(events).to_csv(output / 'paired_event_summary.csv',index=False)
    grouped=[]
    for keys,frame in point_frame.groupby(['split','type','severity','detector']):
        grouped.append(dict(zip(['split','type','severity','detector'],keys)) | paired_summary(frame))
    pd.DataFrame(grouped).to_csv(output / 'paired_by_type_strength.csv',index=False)
    pd.DataFrame(distributions).to_csv(output / 'unchanged_distributions.csv',index=False)
    pd.DataFrame(adaptation).to_csv(output / 'history_response.csv',index=False)
    pd.DataFrame(tails).to_csv(output / 'paired_recovery.csv',index=False)
    pd.DataFrame(detailed_matches).to_csv(output / 'event_overlap_diagnostics.csv',index=False)
    overall=[]
    for (split,name),frame in point_frame.groupby(['split','detector']):
        overall.append({'split':split,'detector':name,**paired_summary(frame)})
    pd.DataFrame(overall).to_csv(output / 'paired_overall.csv',index=False)
    figures(output,point_frame,thresholds)
    unchanged_figure(results,output,thresholds)
    # A specific original finding, shown with its unchanged counterpart.
    matches=pd.DataFrame(detailed_matches)
    hits=matches[(matches.split=='test') & matches.scenario.str.startswith('mixed-') &
                 (matches.detector=='residual') & (matches['quantile']==.99) & matches.original_detected]
    assert len(hits)==1
    hit=hits.iloc[0]
    modified=pd.read_parquet(results / f'scores/test-{hit.scenario}.parquet')
    first,last=int(hit.start),int(hit.end)
    window=modified.loc[first-2:last+2,['measurement_timestamp','actual_energy_wh','prediction_wh','residual']].copy()
    window=window.rename(columns={c:'modified_'+c for c in window.columns if c!='measurement_timestamp'})
    for col in ['actual_energy_wh','prediction_wh','residual']:
        window['clean_'+col]=clean['test'].loc[first-2:last+2,col]
    window['threshold']=thresholds['0.99']['residual']
    window.to_csv(output / 'sole_residual_hit.csv',index=False)
    provenance={'kind':'post-hoc diagnostic; original experiment not modified','original_results_commit':'9d9baab885e563d6912154f3a586cf63712269b2',
        'original_file_hashes_verified':len(frozen),'original_checksummed_files_unchanged':True,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'thresholds_unchanged':thresholds,'paired_rows':len(point_frame),
        'note':'Pooled summaries weight each scenario-point; repeated clean timestamps are not independent observations.'}
    for name,checksum in frozen.items():
        assert hashlib.sha256((results/name).read_bytes()).hexdigest()==checksum
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(provenance,indent=2))


def figures(output,points,thresholds):
    (output/'plots').mkdir()
    for detector in NAMES:
        frame=points[(points.split=='test') & (points.detector==detector)]
        fig,axes=plt.subplots(2,3,figsize=(15,8))
        for ax,(kind,data) in zip(axes.flat,frame.groupby('type',sort=True)):
            for column,label,color in [('clean_score','Clean paired','black')]:
                values=np.sort(data[column].to_numpy())
                ax.plot(values,np.arange(1,len(values)+1)/len(values),label=label,color=color,lw=1)
            for severity,group in data.groupby('severity'):
                values=np.sort(group.modified_score.to_numpy())
                ax.plot(values,np.arange(1,len(values)+1)/len(values),label=f'Modified strength {severity}')
            for q,style in [('0.98',':'),('0.99','--'),('0.995','-.')]:
                ax.axvline(thresholds[q][detector],color='red',ls=style,alpha=.7,label=f'q={q}')
            ax.set_title(kind);ax.set_ylabel('ECDF');ax.set_xlabel('Anomaly score');ax.legend(fontsize=7)
        fig.suptitle(f'{detector}: paired event-point scores, test (post-hoc diagnostic)')
        fig.tight_layout()
        for ext in ('png','svg'):
            fig.savefig(output/f'plots/{detector}_distributions.{ext}',dpi=150)
        plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    for ax,name in zip(axes,NAMES):
        frame=points[(points.split=='test')&(points.detector==name)]
        kinds=sorted(frame.type.unique())
        values=[frame.loc[frame.type==kind,'delta_score']/thresholds['0.99'][name] for kind in kinds]
        ax.boxplot(values,tick_labels=kinds,showfliers=False);ax.axhline(0,color='black',lw=.7)
        ax.tick_params(axis='x',rotation=45);ax.set_title(name);ax.set_ylabel('(Modified − clean score) / threshold')
    fig.tight_layout()
    for ext in ('png','svg'):
        fig.savefig(output/f'plots/paired_score_changes.{ext}',dpi=150)
    plt.close(fig)


def unchanged_figure(results,output,thresholds):
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    for ax,name in zip(axes,NAMES):
        for split in ('calibration','validation','test'):
            filename='calibration.parquet' if split=='calibration' else f'{split}-clean.parquet'
            values=np.sort(pd.read_parquet(results/'scores'/filename,columns=[name])[name].to_numpy())
            ax.plot(values,np.arange(1,len(values)+1)/len(values),label=split)
        ax.axvline(thresholds['0.99'][name],color='red',ls='--',label='Frozen q=.99 threshold')
        ax.set_title(name);ax.set_xlabel('Unchanged anomaly score');ax.set_ylabel('ECDF');ax.legend(fontsize=8)
    fig.tight_layout()
    for ext in ('png','svg'):
        fig.savefig(output/f'plots/unchanged_calibration_shift.{ext}',dpi=150)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=ROOT/'docs/energy-anomaly/results')
    p.add_argument('--output',type=Path,default=ROOT/'docs/energy-anomaly/diagnostics')
    a=p.parse_args();analyze(a.results,a.output)


if __name__=='__main__':
    main()
