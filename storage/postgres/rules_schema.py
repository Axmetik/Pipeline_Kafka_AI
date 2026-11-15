"""Opt-in additive schema; base MVP/API metadata and revision remain unchanged."""
from sqlalchemy import MetaData,Table,Column as C,String as S,Integer,BigInteger,Boolean,ForeignKey as FK,UniqueConstraint,Index,CheckConstraint,text
from sqlalchemy.dialects.postgresql import JSONB
from storage.postgres.schema import measurements,runs,sources,utc
metadata=MetaData()
assessments=Table('mvp_rule_assessments',metadata,
 C('assessment_id',S(64),primary_key=True),C('measurement_id',FK(measurements.c.measurement_id),nullable=False),
 C('run_id',FK(runs.c.run_id),nullable=False),C('rule',S(40),nullable=False),C('category',S(40),nullable=False),
 C('rule_version',S(100),nullable=False),C('layer_version',S(100),nullable=False),C('configuration',JSONB,nullable=False),
 C('flag',Boolean),C('status',S(40),nullable=False),C('evidence',JSONB,nullable=False),C('activation',S(40),nullable=False),
 C('maturity',S(20),nullable=False),utc('assessed_at'),UniqueConstraint('measurement_id','rule','layer_version'),
 CheckConstraint("maturity='experimental' AND category IN ('consumption_pattern','telemetry_quality')"))
decisions=Table('mvp_hybrid_decisions',metadata,
 C('decision_id',S(64),primary_key=True),C('measurement_id',FK(measurements.c.measurement_id),nullable=False),C('run_id',FK(runs.c.run_id),nullable=False),
 C('channel',S(50),nullable=False),C('layer_version',S(100),nullable=False),C('configuration',JSONB,nullable=False),C('input_versions',JSONB,nullable=False),
 C('flag',Boolean),C('status',S(40),nullable=False),C('coverage_count',Integer,nullable=False),C('available_inputs',JSONB,nullable=False),
 C('triggered_inputs',JSONB,nullable=False),C('maturity',S(20),nullable=False),utc('decided_at'),UniqueConstraint('measurement_id','layer_version'),
 CheckConstraint("maturity='experimental' AND coverage_count BETWEEN 0 AND 2"),
 CheckConstraint("(flag IS TRUE AND jsonb_array_length(triggered_inputs)>0) OR (flag IS FALSE AND coverage_count=2 AND jsonb_array_length(triggered_inputs)=0) OR (flag IS NULL AND coverage_count<2 AND jsonb_array_length(triggered_inputs)=0)"))
states=Table('mvp_rule_states',metadata,
 C('run_id',FK(runs.c.run_id),primary_key=True),C('building_id',S(160),primary_key=True),C('source_id',S(160),primary_key=True),
 C('layer_version',S(100),nullable=False),C('state',JSONB,nullable=False),C('state_sha256',S(64),nullable=False),
 C('measurement_id',FK(measurements.c.measurement_id),nullable=False),C('last_offset',BigInteger,nullable=False),C('last_timestamp',S(80),nullable=False),utc('updated_at'))
episodes=Table('mvp_hybrid_episodes',metadata,
 C('episode_id',S(64),primary_key=True),C('run_id',FK(runs.c.run_id),nullable=False),C('building_id',S(160),nullable=False),C('source_id',S(160),nullable=False),
 C('layer_version',S(100),nullable=False),C('input_versions',JSONB,nullable=False),C('maturity',S(20),nullable=False),
 C('start_measurement_id',FK(measurements.c.measurement_id),nullable=False),C('end_measurement_id',FK(measurements.c.measurement_id),nullable=False),
 C('start_timestamp',S(80),nullable=False),C('end_timestamp',S(80),nullable=False),C('flagged_points',Integer,nullable=False),
 C('triggered_inputs',JSONB,nullable=False),C('status',S(20),nullable=False),C('closed_reason',S(40)),utc('created_at'),utc('updated_at'),
 CheckConstraint("maturity='experimental' AND status IN ('open','closed') AND flagged_points>0"))
Index('ux_mvp_hybrid_open',episodes.c.run_id,episodes.c.building_id,episodes.c.source_id,unique=True,postgresql_where=text("status='open'"))
