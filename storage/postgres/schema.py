"""SQLAlchemy Core schema. Initial Alembic DDL is frozen independently."""
from sqlalchemy import (MetaData, Table, Column as C, String as S, Integer, BigInteger,
                        Float, Boolean, DateTime, ForeignKey as FK, ForeignKeyConstraint,
                        UniqueConstraint, Index, CheckConstraint, text, func)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

def utc(name):
    return C(name, DateTime(timezone=True), nullable=False, server_default=func.now())

models = Table('mvp_models', metadata,
    C('model_id', S(128), primary_key=True), C('artifact_sha256', S(64), nullable=False),
    C('role', S(40), nullable=False), C('model_version', S(160), nullable=False),
    C('feature_version', S(80), nullable=False), C('threshold_version', S(100)),
    C('maturity', S(20), nullable=False), C('details', JSONB, nullable=False),
    UniqueConstraint('artifact_sha256', 'role'))
runs = Table('mvp_runs', metadata,
    C('run_id', S(100), primary_key=True), C('group_id', S(200), nullable=False, unique=True),
    C('topic', S(249), nullable=False), C('cluster_id', S(200), nullable=False),
    C('manifest_sha256', S(64), nullable=False), C('config', JSONB, nullable=False), utc('created_at'))
sources = Table('mvp_sources', metadata,
    C('building_id', S(160), primary_key=True), C('source_id', S(160), primary_key=True),
    C('binding', JSONB, nullable=False), utc('created_at'))
measurements = Table('mvp_measurements', metadata,
    C('measurement_id', S(64), primary_key=True), C('run_id', FK('mvp_runs.run_id'), nullable=False),
    C('building_id', S(160), nullable=False), C('source_id', S(160), nullable=False),
    C('event_id', S(200), nullable=False), C('kafka_offset', BigInteger, nullable=False),
    C('measurement_timestamp', S(80), nullable=False), C('measurement_time_local', DateTime, nullable=False),
    C('measurement_time_utc', DateTime(timezone=True)), C('time_basis', S(30), nullable=False),
    C('timezone', S(80)), C('timestamp_reference', S(40), nullable=False),
    C('interval_seconds', Integer, nullable=False), C('energy_wh', Float, nullable=False),
    C('environment', JSONB, nullable=False), C('wire_record', JSONB, nullable=False),
    C('normalized_sha256', S(64), nullable=False), C('compatible', Boolean, nullable=False),
    C('feature_status', S(30), nullable=False), C('gap_detected', Boolean, nullable=False), utc('received_at'),
    ForeignKeyConstraint(['building_id','source_id'], ['mvp_sources.building_id','mvp_sources.source_id']),
    UniqueConstraint('run_id','building_id','source_id','event_id'),
    UniqueConstraint('run_id','building_id','source_id','measurement_timestamp'),
    CheckConstraint('energy_wh >= 0 AND interval_seconds > 0'))
Index('ix_mvp_measurement_time', measurements.c.run_id, measurements.c.building_id, measurements.c.source_id, measurements.c.measurement_time_local)
forecasts = Table('mvp_forecasts', metadata,
    C('forecast_id', S(64), primary_key=True), C('run_id', FK('mvp_runs.run_id'), nullable=False),
    C('measurement_id', FK('mvp_measurements.measurement_id'), nullable=False),
    C('model_id', FK('mvp_models.model_id'), nullable=False), C('purpose', S(40), nullable=False),
    C('model_version', S(160), nullable=False), C('feature_version', S(80), nullable=False),
    C('forecast_origin', S(80), nullable=False), C('forecast_target_timestamp', S(80), nullable=False),
    C('target_time_local', DateTime, nullable=False), C('target_time_utc', DateTime(timezone=True)),
    C('generated_at', DateTime(timezone=True), nullable=False), C('predicted_energy_wh', Float),
    C('status', S(30), nullable=False), C('horizon_seconds', Integer, nullable=False),
    UniqueConstraint('measurement_id','model_id','purpose'))
Index('ix_mvp_forecast_target', forecasts.c.run_id, forecasts.c.target_time_local, forecasts.c.model_id)
scores = Table('mvp_scores', metadata,
    C('score_id', S(64), primary_key=True), C('run_id', FK('mvp_runs.run_id'), nullable=False),
    C('measurement_id', FK('mvp_measurements.measurement_id'), nullable=False),
    C('model_id', FK('mvp_models.model_id'), nullable=False), C('detector', S(40), nullable=False),
    C('model_version', S(160), nullable=False), C('feature_version', S(80), nullable=False),
    C('threshold_version', S(100), nullable=False), C('maturity', S(20), nullable=False),
    C('score', Float), C('threshold', Float, nullable=False), C('flag', Boolean), C('status', S(30), nullable=False),
    C('reference_forecast_id', FK('mvp_forecasts.forecast_id')), C('prediction_wh', Float),
    C('signed_residual_wh', Float), C('forecast_origin', S(80)), C('forecast_target_timestamp', S(80)),
    C('reference_generated_at', DateTime(timezone=True)), utc('scored_at'),
    UniqueConstraint('measurement_id','model_id','threshold_version'), CheckConstraint("maturity = 'experimental'"))
Index('ix_mvp_score_detector', scores.c.run_id, scores.c.detector, scores.c.model_version)
episodes = Table('mvp_episodes', metadata,
    C('episode_id', S(64), primary_key=True), C('run_id', FK('mvp_runs.run_id'), nullable=False),
    C('building_id', S(160), nullable=False), C('source_id', S(160), nullable=False),
    C('model_id', FK('mvp_models.model_id'), nullable=False), C('detector', S(40), nullable=False),
    C('model_version', S(160), nullable=False), C('feature_version', S(80), nullable=False),
    C('threshold_version', S(100), nullable=False), C('maturity', S(20), nullable=False),
    C('start_measurement_id', FK('mvp_measurements.measurement_id'), nullable=False),
    C('end_measurement_id', FK('mvp_measurements.measurement_id'), nullable=False),
    C('start_timestamp', S(80), nullable=False), C('end_timestamp', S(80), nullable=False),
    C('flagged_points', Integer, nullable=False), C('status', S(20), nullable=False), C('closed_reason', S(40)),
    utc('created_at'), utc('updated_at'), CheckConstraint("maturity = 'experimental'"),
    CheckConstraint("status IN ('open','closed') AND flagged_points > 0"))
Index('ux_mvp_open_episode', episodes.c.run_id, episodes.c.building_id, episodes.c.source_id,
      episodes.c.model_id, episodes.c.threshold_version, unique=True, postgresql_where=text("status = 'open'"))
checkpoints = Table('mvp_checkpoints', metadata,
    C('group_id', S(200), primary_key=True), C('topic', S(249), primary_key=True), C('partition', Integer, primary_key=True),
    C('run_id', FK('mvp_runs.run_id'), nullable=False), C('next_offset', BigInteger, nullable=False),
    C('last_payload_sha256', S(64)), utc('updated_at'), CheckConstraint('next_offset >= 0'))
receipts = Table('mvp_receipts', metadata,
    C('group_id', S(200), primary_key=True), C('topic', S(249), primary_key=True),
    C('partition', Integer, primary_key=True), C('offset', BigInteger, primary_key=True),
    C('run_id', FK('mvp_runs.run_id'), nullable=False), C('payload_sha256', S(64), nullable=False),
    C('outcome', S(40), nullable=False), C('measurement_id', FK('mvp_measurements.measurement_id')), utc('received_at'))
errors = Table('mvp_errors', metadata,
    C('error_id', S(64), primary_key=True), C('run_id', FK('mvp_runs.run_id'), nullable=False),
    C('topic', S(249), nullable=False), C('partition', Integer, nullable=False), C('offset', BigInteger, nullable=False),
    C('kind', S(40), nullable=False), C('reason', S(1000), nullable=False), C('payload_base64', JSONB, nullable=False), utc('created_at'))
