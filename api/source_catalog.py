"""Bounded source catalog: one latest-row query, never one query per source."""
from sqlalchemy import select, func, and_, or_
from pydantic import Field
from .query import Filters, page
from storage.postgres import schema as s


class CatalogFilters(Filters):
    run_id: str = Field(..., min_length=1, max_length=100)
    search: str | None = Field(None, max_length=160)


def catalog(c, f):
    m = s.measurements
    fields = ['measurement_id','building_id','source_id','measurement_timestamp',
              'energy_wh','received_at','feature_status','time_basis']
    q = select(*(m.c[k] for k in fields), func.row_number().over(
        partition_by=[m.c.building_id,m.c.source_id],
        order_by=[m.c.measurement_time_utc.desc().nullslast(),
                  m.c.measurement_time_local.desc(),m.c.measurement_id.desc()]).label('position')).where(m.c.run_id == f.run_id)
    for key in ('building_id','source_id'):
        if getattr(f,key) is not None: q = q.where(m.c[key] == getattr(f,key))
    if f.search:
        q = q.where(or_(m.c.source_id.icontains(f.search,autoescape=True),
                        m.c.building_id.icontains(f.search,autoescape=True)))
    latest = q.subquery()
    sources = s.sources
    joined = sources.join(latest,and_(sources.c.building_id == latest.c.building_id,
                                      sources.c.source_id == latest.c.source_id))
    stmt = select(sources.c.building_id,sources.c.source_id,sources.c.binding,
                  latest.c.measurement_id,latest.c.measurement_timestamp,
                  latest.c.energy_wh.label('latest_energy_wh'),latest.c.received_at,
                  latest.c.feature_status,latest.c.time_basis).select_from(joined).where(latest.c.position == 1)
    result = page(c,stmt,[sources.c.building_id,sources.c.source_id],'source-summaries',f)
    for row in result['items']:
        binding = row.pop('binding')
        row.update({k:binding.get(k) for k in ('source_type','energy_scope','interval_seconds',
                     'timestamp_reference','timezone','timestamp_has_offset')})
        row['run_id'] = f.run_id
    # Building choices deliberately ignore search/building filters, but retain run scope.
    buildings = c.execute(select(m.c.building_id).where(m.c.run_id == f.run_id)
                          .distinct().order_by(m.c.building_id).limit(1001)).scalars().all()
    return dict(**result,building_ids=buildings[:1000],buildings_truncated=len(buildings)>1000)
