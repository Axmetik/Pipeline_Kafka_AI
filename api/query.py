"""Bounded, parameterized, keyset queries. No model loading, Kafka, or writes."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, func, and_, or_, literal, cast, Interval, Numeric
from storage.postgres import schema as s


class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: str | None = Field(None, max_length=100)
    building_id: str | None = Field(None, max_length=160)
    source_id: str | None = Field(None, max_length=160)
    rule_version: str | None = Field(None, max_length=100)
    model_id: str | None = Field(None, max_length=128)
    model_version: str | None = Field(None, max_length=160)
    detector: Literal['isolation_forest', 'autoencoder', 'residual'] | None = None
    status: str | None = Field(None, max_length=40)
    purpose: Literal['primary_forecast', 'residual_reference'] | None = None
    time_basis: Literal['dataset_naive', 'offset_aware'] = 'dataset_naive'
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(100, ge=1, le=1000)
    cursor: str | None = Field(None, max_length=4096)

    @model_validator(mode='after')
    def times(self):
        for value in (self.start, self.end):
            if value is not None and (value.utcoffset() is not None) != (self.time_basis == 'offset_aware'):
                raise ValueError('start/end must match time_basis; dataset labels are timezone-naive')
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError('start must be before end (exclusive)')
        return self


class AggregateFilters(Filters):
    bucket_minutes: Literal['60', '1440'] = '60'


def fingerprint(endpoint, f):
    data = f.model_dump(mode='json', exclude={'cursor','limit'})
    return hashlib.sha256(json.dumps([endpoint,data],sort_keys=True).encode()).hexdigest()


def decode_cursor(value, endpoint, f, types):
    try:
        raw = json.loads(base64.b64decode(value + '=' * (-len(value)%4), altchars=b'-_', validate=True))
        if not isinstance(raw,dict) or not isinstance(raw.get('k'),list):
            raise ValueError()
        if raw['v'] != 1 or raw['q'] != fingerprint(endpoint,f) or len(raw['k']) != len(types):
            raise ValueError()
        values=[]
        for item, kind in zip(raw['k'],types):
            if not isinstance(item,str) or len(item)>512:
                raise ValueError()
            value=datetime.fromisoformat(item) if kind=='time' else item
            if kind=='time':
                aware=value.utcoffset() is not None
                expected=(endpoint in ('runs','notifications') or f.time_basis=='offset_aware')
                if aware!=expected: raise ValueError()
            values.append(value)
        return values
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        raise HTTPException(422,'Invalid cursor or cursor filters changed') from None


def page(c, stmt, keys, endpoint, f, types=None, descending=False):
    types = types or ['str'] * len(keys)
    if f.cursor:
        values = decode_cursor(f.cursor,endpoint,f,types)
        terms = [and_(*(keys[j] == values[j] for j in range(i)), (keys[i] < values[i] if descending else keys[i] > values[i])) for i in range(len(keys))]
        stmt = stmt.where(or_(*terms))
    rows=[dict(r) for r in c.execute(stmt.order_by(*(key.desc() if descending else key.asc() for key in keys)).limit(f.limit+1)).mappings()]
    more = len(rows)>f.limit
    rows=rows[:f.limit]
    cursor=None
    if more:
        values = [rows[-1][key.key] for key in keys]
        payload={'v':1,'q':fingerprint(endpoint,f),'k':[v.isoformat() if isinstance(v,datetime) else str(v) for v in values]}
        cursor=base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')
    return {'items':rows,'next_cursor':cursor,'order':'descending' if descending else 'ascending'}


TIMED_FIELDS=['building_id','source_id','time_basis','timezone','timestamp_reference']


def series_query(kind, f):
    m=s.measurements
    if kind=='measurements':
        table=m; joined=m; timestamp=m.c.measurement_time_local if f.time_basis=='dataset_naive' else m.c.measurement_time_utc
        columns=[m.c[x] for x in ['measurement_id','run_id','event_id','measurement_timestamp','interval_seconds','energy_wh','compatible','feature_status','gap_detected','received_at']+TIMED_FIELDS]
        columns += [m.c.environment['temperature_c'].as_float().label('temperature_c'),m.c.environment['relative_humidity_pct'].as_float().label('relative_humidity_pct')]
        ident=m.c.measurement_id; status=m.c.feature_status
    else:
        table={'forecasts':s.forecasts,'anomaly-scores':s.scores,'events':s.episodes,'combined-decisions':s.combined_decisions,'combined-events':s.combined_episodes}[kind]
        joinid=table.c.start_measurement_id if kind in ('events','combined-events') else table.c.measurement_id
        joined=table.join(m,joinid==m.c.measurement_id)
        columns=list(table.c)+[m.c[x] for x in TIMED_FIELDS if x not in table.c]
        if kind=='forecasts':
            timestamp=table.c.target_time_local if f.time_basis=='dataset_naive' else table.c.target_time_utc
            ident=table.c.forecast_id
        else:
            timestamp=m.c.measurement_time_local if f.time_basis=='dataset_naive' else m.c.measurement_time_utc
            ident=table.c.decision_id if kind=='combined-decisions' else table.c.score_id if kind=='anomaly-scores' else table.c.episode_id
            if kind in ('anomaly-scores','combined-decisions'): columns.append(m.c.measurement_timestamp)
        status=table.c.status
    stmt=select(*columns,timestamp.label('_sort_time')).select_from(joined).where(m.c.time_basis==f.time_basis)
    for field in ['run_id','building_id','source_id']:
        if getattr(f,field) is not None: stmt=stmt.where(m.c[field]==getattr(f,field))
    if f.status:
        allowed={'measurements':{'ready','warmup','incompatible'},'forecasts':{'ready','warmup','incompatible'},
                 'anomaly-scores':{'ready','warmup','gap','incompatible'},'events':{'open','closed'},'combined-decisions':{'ready','warmup','gap','incompatible','partial'},'combined-events':{'open','closed'}}[kind]
        if f.status not in allowed: raise HTTPException(422,'Unsupported status for this resource')
        stmt=stmt.where(status==f.status)
    for field in ['model_id','model_version','detector','purpose','rule_version']:
        if getattr(f,field) is not None:
            if field not in table.c: raise HTTPException(422,f'{field} is not applicable to {kind}')
            stmt=stmt.where(table.c[field]==getattr(f,field))
    if f.start: stmt=stmt.where(timestamp>=f.start)
    if f.end: stmt=stmt.where(timestamp<f.end)
    # No implicit wall-clock filter: all available historical labels are queryable.
    return stmt, [timestamp.label('_sort_time'),ident]


def series(c,kind,f):
    stmt, keys=series_query(kind,f)
    return page(c,stmt,keys,kind,f,['time','str'],descending=True)


def aggregation(c,f,bucket_minutes):
    stmt,_=series_query('measurements',f)
    # Unsupported cadences are never silently included in a 600-second sum.
    base=stmt.subquery()
    if c.execute(select(func.count()).select_from(base).where(base.c.interval_seconds!=600)).scalar_one():
        raise HTTPException(422,'Aggregation requires 600-second measurement intervals')
    interval=literal(f'{bucket_minutes} minutes').cast(Interval)
    stamp=base.c._sort_time
    origin=datetime(2000,1,1,tzinfo=timezone.utc if f.time_basis=='offset_aware' else None)
    bucket=func.date_bin(interval,stamp,origin).label('bucket')
    grouped=select(*[base.c[x] for x in ['run_id']+TIMED_FIELDS],bucket,
                   func.count().label('observed_intervals'),func.count(func.distinct(stamp)).label('distinct_intervals'),func.sum(base.c.energy_wh).label('sum_wh'),
                   func.min(stamp).label('first'),func.max(stamp).label('last'),
                   func.bool_and(func.mod(cast(func.extract('epoch',stamp-origin),Numeric),600)==0).label('on_grid'))
    groupcols=[base.c[x] for x in ['run_id']+TIMED_FIELDS]
    g=grouped.group_by(*groupcols,bucket).subquery()
    q=select(g)
    result=page(c,q,[g.c.bucket,g.c.run_id,g.c.building_id,g.c.source_id],f'aggregate-{bucket_minutes}',f,['time','str','str','str'],descending=True)
    for row in result['items']:
        expected=bucket_minutes//10
        complete=(row['observed_intervals']==expected and row['distinct_intervals']==expected and row['on_grid'] and row['first']==row['bucket'] and row['last']==row['bucket']+timedelta(minutes=bucket_minutes-10))
        row.update(bucket_start=row['bucket'].isoformat(),bucket_end=(row['bucket']+timedelta(minutes=bucket_minutes)).isoformat(),
                   bucket_minutes=bucket_minutes,expected_intervals=expected,complete=complete,energy_wh=row['sum_wh'] if complete else None)
    return result

