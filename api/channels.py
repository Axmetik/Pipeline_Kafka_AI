"""Logical UCI measurement channels, read directly from archived wire records.

No synthetic sources, model calls, writes, or fallback to Appliances energy.
Zone descriptions: https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, union_all, literal, case, Float, func, and_, or_
from .query import page
from storage.postgres import schema as s

ZONE_NAMES = ['Кухня', 'Вітальня', 'Пральня', 'Кабінет', 'Ванна кімната',
              'Зовні будівлі · північна сторона', 'Кімната для прасування',
              'Кімната підлітка №2', 'Спальня батьків']
# Stable IDs describe channels, not individually identified physical devices.
DEFINITIONS = [dict(channel_id='appliances', category='appliances', name='Побутові прилади',
                    columns=['Appliances'], units=['Wh'], capabilities=['statistics','forecast','detectors','events','notifications']),
               dict(channel_id='lights', category='lighting', name='Освітлення',
                    columns=['lights'], units=['Wh'], capabilities=['statistics'])] + [
    dict(channel_id=f'zone-{i}', category='zones', name=name, columns=[f'T{i}',f'RH_{i}'],
         units=['°C','%'], capabilities=['statistics']) for i,name in enumerate(ZONE_NAMES,1)]
BY_ID = {d['channel_id']:d for d in DEFINITIONS}

class ChannelFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1,max_length=100)
    building_id: str | None = Field(None,max_length=160)
    source_id: str | None = Field(None,max_length=160)
    category: Literal['appliances','lighting','zones'] | None = None
    search: str | None = Field(None,max_length=160)
    limit: int = Field(24,ge=1,le=1000)
    cursor: str | None = Field(None,max_length=4096)

from .query import Filters
class ChannelSeriesFilters(Filters):
    run_id: str = Field(min_length=1,max_length=100)
    building_id: str = Field(min_length=1,max_length=160)
    source_id: str = Field(min_length=1,max_length=160)
    channel_id: Literal['appliances','lights','zone-1','zone-2','zone-3','zone-4','zone-5','zone-6','zone-7','zone-8','zone-9']


def numeric(value):
    # JSON null, absent keys, strings and booleans stay unavailable, never zero.
    return case((func.jsonb_typeof(value)=='number',value.astext.cast(Float)),else_=None)


def rows(f):
    m=s.measurements; src=s.sources
    base=select(m,src.c.binding).select_from(m.join(src,and_(m.c.building_id==src.c.building_id,
        m.c.source_id==src.c.source_id))).where(m.c.run_id==f.run_id)
    for key in ('building_id','source_id'):
        if getattr(f,key):base=base.where(m.c[key]==getattr(f,key))
    b=base.cte('channel_measurements')
    wire=b.c.wire_record; extra=wire['additional_parameters']; env=wire['environment']
    # Recognize the UCI adapter's column bundle, not an arbitrary temperature sensor.
    uci=and_(wire['source_type'].astext=='dataset',wire['energy']['scope'].astext=='appliances',
             extra.has_key('lights'),extra.has_key('T2'),extra.has_key('RH_2'))
    statements=[]
    for d in DEFINITIONS:
        cid=d['channel_id']
        if getattr(f,'category',None) and f.category!=d['category']:continue
        if getattr(f,'channel_id',None) and f.channel_id!=cid:continue
        if cid=='appliances':
            first=b.c.energy_wh; second=literal(None,Float).cast(Float); present=literal(True)
        elif cid=='lights':
            first=numeric(extra['lights']); second=literal(None,Float).cast(Float); present=and_(uci,extra.has_key('lights'))
        else:
            i=int(cid.split('-')[1])
            if i==1:
                first=numeric(env['temperature_c']);second=numeric(env['relative_humidity_pct'])
                present=and_(uci,or_(env.has_key('temperature_c'),env.has_key('relative_humidity_pct')))
            else:
                first=numeric(extra[f'T{i}']);second=numeric(extra[f'RH_{i}'])
                present=and_(uci,or_(extra.has_key(f'T{i}'),extra.has_key(f'RH_{i}')))
        stmt=select(*[b.c[k] for k in ['measurement_id','run_id','building_id','source_id','measurement_timestamp',
                     'measurement_time_local','measurement_time_utc','time_basis','interval_seconds','received_at','binding']],
                     literal(cid).label('channel_id'),literal(d['category']).label('category'),literal(d['name']).label('name'),
                     first.label('value'),second.label('secondary_value')).where(present)
        if getattr(f,'search',None):
            stmt=stmt.where(or_(b.c.source_id.icontains(f.search,autoescape=True),b.c.building_id.icontains(f.search,autoescape=True),
                           literal(cid).icontains(f.search,autoescape=True),literal(d['name']).icontains(f.search,autoescape=True),
                           literal(' '.join(d['columns'])).icontains(f.search,autoescape=True)))
        statements.append(stmt)
    return union_all(*statements).subquery()


def catalog(c,f):
    b=rows(f)
    ranked=select(b,func.row_number().over(partition_by=[b.c.building_id,b.c.source_id,b.c.channel_id],
        order_by=[b.c.measurement_time_utc.desc().nullslast(),b.c.measurement_time_local.desc(),b.c.measurement_id.desc()]).label('position')).subquery()
    result=page(c,select(ranked).where(ranked.c.position==1),
        [ranked.c.building_id,ranked.c.source_id,ranked.c.channel_id],'channels',f)
    for item in result['items']:enrich(item)
    m=s.measurements
    buildings=c.execute(select(m.c.building_id).where(m.c.run_id==f.run_id).distinct().order_by(m.c.building_id).limit(1001)).scalars().all()
    return dict(**result,building_ids=buildings[:1000],buildings_truncated=len(buildings)>1000)


def enrich(item):
    binding=item.pop('binding',{})
    item.update({k:binding.get(k) for k in ['source_type','energy_scope','timestamp_reference','timezone','timestamp_has_offset']})
    item.update({k:v for k,v in BY_ID[item['channel_id']].items() if k not in ('channel_id','category','name')})
    item['activity_status']='unknown'
    item['provenance']='stored_measurement' if item['channel_id']=='appliances' else 'archived_uci_wire_columns'
    return item


def series(c,f):
    b=rows(f); stamp=b.c.measurement_time_local if f.time_basis=='dataset_naive' else b.c.measurement_time_utc
    stmt=select(b,stamp.label('_sort_time')).where(b.c.time_basis==f.time_basis)
    if f.start:stmt=stmt.where(stamp>=f.start)
    if f.end:stmt=stmt.where(stamp<f.end)
    result=page(c,stmt,[stamp.label('_sort_time'),b.c.measurement_id],'channel-series',f,['time','str'],descending=True)
    for item in result['items']:enrich(item)
    # Descriptive statistics describe exactly the returned bounded window, not an unseen full dataset.
    statistics=[]
    for field in ['value','secondary_value'][:len(BY_ID[f.channel_id]['columns'])]:
        values=[p[field] for p in result['items'] if p[field] is not None]
        statistics.append(dict(count=len(values),minimum=min(values) if values else None,
            maximum=max(values) if values else None,mean=sum(values)/len(values) if values else None))
    return dict(**result,definition=BY_ID[f.channel_id],statistics=statistics,statistics_scope='returned_window')
