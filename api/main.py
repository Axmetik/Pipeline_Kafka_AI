"""Read-only PostgreSQL API. No training, inference, migrations, or Kafka access."""
from contextlib import asynccontextmanager, contextmanager
from typing import Annotated, Literal
from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.exc import SQLAlchemyError
from integration.settings import Settings
from storage.postgres import schema as s
from . import schemas as out
from .query import Filters, AggregateFilters, page, series, aggregation


@contextmanager
def read_connection(engine):
    with engine.connect() as c, c.begin():
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout = '5s'"))
        c.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        yield c


def create_app(engine=None):
    owned = engine is None
    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine if engine is not None else create_engine(
            Settings.from_env().database_url, pool_pre_ping=True,
            connect_args={'connect_timeout':3}, hide_parameters=True)
        yield
        if owned: app.state.engine.dispose()

    app=FastAPI(title='Energy Monitoring read-only API',version='5B.1',lifespan=lifespan)
    app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],
                       allow_credentials=False,allow_methods=['GET'],allow_headers=['Accept'])

    @app.middleware('http')
    async def local_only(request,call_next):
        # Also protect alternative uvicorn invocations: no unauthenticated remote clients.
        if request.client and request.client.host not in ('127.0.0.1','::1','localhost','testclient'):
            return JSONResponse(status_code=403,content={'detail':'Local access only'})
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request,exc):
        return JSONResponse(status_code=503,content={'detail':'PostgreSQL unavailable or schema not ready'})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Do not echo arbitrary input, credentials, or Pydantic ctx exceptions.
        errors=[{'loc':list(e['loc']),'type':e['type'],'msg':e['msg']} for e in exc.errors()]
        return JSONResponse(status_code=422,content={'detail':errors})

    def reject_filters(f,allowed):
        for field in ('run_id','building_id','source_id','model_id','model_version','detector','status','purpose','start','end'):
            if field not in allowed and getattr(f,field) is not None:
                raise HTTPException(422,f'{field} is not applicable to this resource')

    def connection(request:Request):
        with read_connection(request.app.state.engine) as c: yield c
    DB=Annotated[object,Depends(connection)]
    F=Annotated[Filters,Query()]
    AF=Annotated[AggregateFilters,Query()]

    @app.get('/health/live',response_model=out.Health)
    def live(): return {'status':'live'}

    @app.get('/health/ready',response_model=out.Health)
    def ready(c:DB):
        revision=c.execute(text('SELECT version_num FROM alembic_version')).scalar_one_or_none()
        if revision!='0001_mvp': raise HTTPException(503,'PostgreSQL schema not ready')
        c.execute(select(s.runs.c.run_id).limit(1))
        return {'status':'ready'}

    @app.get('/api/runs',response_model=out.Page[out.Run])
    def runs(c:DB,f:F):
        reject_filters(f,{'run_id'})
        q=select(s.runs.c.run_id,s.runs.c.group_id,s.runs.c.topic,s.runs.c.created_at)
        if f.run_id: q=q.where(s.runs.c.run_id==f.run_id)
        return page(c,q,[s.runs.c.created_at,s.runs.c.run_id],'runs',f,['time','str'])

    @app.get('/api/sources',response_model=out.Page[out.Source])
    def sources(c:DB,f:F):
        reject_filters(f,{'run_id','building_id','source_id'})
        q=select(s.sources)
        for field in ('building_id','source_id'):
            if getattr(f,field): q=q.where(s.sources.c[field]==getattr(f,field))
        if f.run_id:
            q=q.where(select(s.measurements.c.measurement_id).where(s.measurements.c.run_id==f.run_id,
                s.measurements.c.building_id==s.sources.c.building_id,s.measurements.c.source_id==s.sources.c.source_id).exists())
        result=page(c,q,[s.sources.c.building_id,s.sources.c.source_id],'sources',f)
        for row in result['items']:
            binding=row.pop('binding')
            for field in ('source_type','energy_scope','interval_seconds','timestamp_reference','timezone','timestamp_has_offset'):
                row[field]=binding.get(field)
        return result

    @app.get('/api/measurements/aggregate',response_model=out.Page[out.Aggregate])
    def aggregate(c:DB,f:AF):
        return aggregation(c,f,int(f.bucket_minutes))

    # Explicit handlers keep OpenAPI response types and per-resource contracts stable.
    @app.get('/api/measurements',response_model=out.Page[out.Measurement])
    def measurements(c:DB,f:F): return series(c,'measurements',f)

    @app.get('/api/forecasts',response_model=out.Page[out.Forecast])
    def forecasts(c:DB,f:F): return series(c,'forecasts',f)

    @app.get('/api/anomaly-scores',response_model=out.Page[out.Score])
    def scores(c:DB,f:F): return series(c,'anomaly-scores',f)

    @app.get('/api/events',response_model=out.Page[out.Event])
    def events(c:DB,f:F): return series(c,'events',f)

    @app.get('/api/models',response_model=out.Page[out.Model])
    def models(c:DB,f:F):
        reject_filters(f,{'run_id','model_id','model_version'})
        q=select(s.models)
        for field in ('model_id','model_version'):
            if getattr(f,field): q=q.where(s.models.c[field]==getattr(f,field))
        if f.run_id:
            q=q.where(s.models.c.model_id.in_(select(s.forecasts.c.model_id).where(s.forecasts.c.run_id==f.run_id).union(
                select(s.scores.c.model_id).where(s.scores.c.run_id==f.run_id))))
        result=page(c,q,[s.models.c.model_id],'models',f)
        for row in result['items']:
            details=row.pop('details')
            row['feature_names']=details.get('feature_names',[])
            row['horizon_seconds']=details.get('horizon_seconds')
        return result

    @app.get('/api/pipeline-status',response_model=out.PipelineStatus)
    def pipeline(c:DB,run_id:Annotated[str|None,Query(max_length=100)]=None):
        def scope(q,t): return q.where(t.c.run_id==run_id) if run_id else q
        checkpoints=[dict(r) for r in c.execute(scope(select(s.checkpoints),s.checkpoints).order_by(
            s.checkpoints.c.updated_at.desc(),s.checkpoints.c.run_id).limit(100)).mappings()]
        last=c.execute(scope(select(func.max(s.checkpoints.c.updated_at)),s.checkpoints)).scalar_one()
        count=lambda t,condition=None: c.execute(scope(select(func.count()).select_from(t).where(condition if condition is not None else text('true')),t)).scalar_one()
        errors=[dict(r) for r in c.execute(scope(select(s.errors.c.error_id,s.errors.c.run_id,s.errors.c.topic,
            s.errors.c.partition,s.errors.c.offset,s.errors.c.kind,s.errors.c.created_at),s.errors).order_by(
                s.errors.c.created_at.desc(),s.errors.c.error_id).limit(10)).mappings()]
        for row in checkpoints: row['last_processed_at']=row.pop('updated_at')
        return {'last_processed_at':last,'scope_run_id':run_id,
            'unique_measurements':count(s.measurements),
            'forecasts':count(s.forecasts),'anomaly_scores':count(s.scores),
            'duplicate_deliveries':count(s.receipts,s.receipts.c.outcome=='message_duplicate'),
            'rejected_messages':count(s.receipts,s.receipts.c.outcome.not_in(['accepted','message_duplicate'])),
            'checkpoints':checkpoints,'recent_errors':errors,
            'checkpoint_count':count(s.checkpoints),'checkpoints_truncated':count(s.checkpoints)>len(checkpoints)}
    return app
