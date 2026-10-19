"""Stage 5A initial schema, frozen SQL independent of future runtime metadata."""
from alembic import op
revision = '0001_mvp'
down_revision = None
branch_labels = None
depends_on = None

DDL = [
    """
CREATE TABLE mvp_models (
	model_id VARCHAR(128) NOT NULL, 
	artifact_sha256 VARCHAR(64) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	model_version VARCHAR(160) NOT NULL, 
	feature_version VARCHAR(80) NOT NULL, 
	threshold_version VARCHAR(100), 
	maturity VARCHAR(20) NOT NULL, 
	details JSONB NOT NULL, 
	PRIMARY KEY (model_id), 
	UNIQUE (artifact_sha256, role)
)

""",
    """
CREATE TABLE mvp_runs (
	run_id VARCHAR(100) NOT NULL, 
	group_id VARCHAR(200) NOT NULL, 
	topic VARCHAR(249) NOT NULL, 
	cluster_id VARCHAR(200) NOT NULL, 
	manifest_sha256 VARCHAR(64) NOT NULL, 
	config JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (run_id), 
	UNIQUE (group_id)
)

""",
    """
CREATE TABLE mvp_sources (
	building_id VARCHAR(160) NOT NULL, 
	source_id VARCHAR(160) NOT NULL, 
	binding JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (building_id, source_id)
)

""",
    """
CREATE TABLE mvp_checkpoints (
	group_id VARCHAR(200) NOT NULL, 
	topic VARCHAR(249) NOT NULL, 
	partition INTEGER NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	next_offset BIGINT NOT NULL, 
	last_payload_sha256 VARCHAR(64), 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (group_id, topic, partition), 
	CHECK (next_offset >= 0), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id)
)

""",
    """
CREATE TABLE mvp_errors (
	error_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	topic VARCHAR(249) NOT NULL, 
	partition INTEGER NOT NULL, 
	"offset" BIGINT NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	reason VARCHAR(1000) NOT NULL, 
	payload_base64 JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (error_id), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id)
)

""",
    """
CREATE TABLE mvp_measurements (
	measurement_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	building_id VARCHAR(160) NOT NULL, 
	source_id VARCHAR(160) NOT NULL, 
	event_id VARCHAR(200) NOT NULL, 
	kafka_offset BIGINT NOT NULL, 
	measurement_timestamp VARCHAR(80) NOT NULL, 
	measurement_time_local TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	measurement_time_utc TIMESTAMP WITH TIME ZONE, 
	time_basis VARCHAR(30) NOT NULL, 
	timezone VARCHAR(80), 
	timestamp_reference VARCHAR(40) NOT NULL, 
	interval_seconds INTEGER NOT NULL, 
	energy_wh FLOAT NOT NULL, 
	environment JSONB NOT NULL, 
	wire_record JSONB NOT NULL, 
	normalized_sha256 VARCHAR(64) NOT NULL, 
	compatible BOOLEAN NOT NULL, 
	feature_status VARCHAR(30) NOT NULL, 
	gap_detected BOOLEAN NOT NULL, 
	received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (measurement_id), 
	FOREIGN KEY(building_id, source_id) REFERENCES mvp_sources (building_id, source_id), 
	UNIQUE (run_id, building_id, source_id, event_id), 
	UNIQUE (run_id, building_id, source_id, measurement_timestamp), 
	CHECK (energy_wh >= 0 AND interval_seconds > 0), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id)
)

""",
    """CREATE INDEX ix_mvp_measurement_time ON mvp_measurements (run_id, building_id, source_id, measurement_time_local)""",
    """
CREATE TABLE mvp_episodes (
	episode_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	building_id VARCHAR(160) NOT NULL, 
	source_id VARCHAR(160) NOT NULL, 
	model_id VARCHAR(128) NOT NULL, 
	detector VARCHAR(40) NOT NULL, 
	model_version VARCHAR(160) NOT NULL, 
	feature_version VARCHAR(80) NOT NULL, 
	threshold_version VARCHAR(100) NOT NULL, 
	maturity VARCHAR(20) NOT NULL, 
	start_measurement_id VARCHAR(64) NOT NULL, 
	end_measurement_id VARCHAR(64) NOT NULL, 
	start_timestamp VARCHAR(80) NOT NULL, 
	end_timestamp VARCHAR(80) NOT NULL, 
	flagged_points INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	closed_reason VARCHAR(40), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (episode_id), 
	CHECK (maturity = 'experimental'), 
	CHECK (status IN ('open','closed') AND flagged_points > 0), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id), 
	FOREIGN KEY(model_id) REFERENCES mvp_models (model_id), 
	FOREIGN KEY(start_measurement_id) REFERENCES mvp_measurements (measurement_id), 
	FOREIGN KEY(end_measurement_id) REFERENCES mvp_measurements (measurement_id)
)

""",
    """CREATE UNIQUE INDEX ux_mvp_open_episode ON mvp_episodes (run_id, building_id, source_id, model_id, threshold_version) WHERE status = 'open'""",
    """
CREATE TABLE mvp_forecasts (
	forecast_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	measurement_id VARCHAR(64) NOT NULL, 
	model_id VARCHAR(128) NOT NULL, 
	purpose VARCHAR(40) NOT NULL, 
	model_version VARCHAR(160) NOT NULL, 
	feature_version VARCHAR(80) NOT NULL, 
	forecast_origin VARCHAR(80) NOT NULL, 
	forecast_target_timestamp VARCHAR(80) NOT NULL, 
	target_time_local TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	target_time_utc TIMESTAMP WITH TIME ZONE, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	predicted_energy_wh FLOAT, 
	status VARCHAR(30) NOT NULL, 
	horizon_seconds INTEGER NOT NULL, 
	PRIMARY KEY (forecast_id), 
	UNIQUE (measurement_id, model_id, purpose), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id), 
	FOREIGN KEY(measurement_id) REFERENCES mvp_measurements (measurement_id), 
	FOREIGN KEY(model_id) REFERENCES mvp_models (model_id)
)

""",
    """CREATE INDEX ix_mvp_forecast_target ON mvp_forecasts (run_id, target_time_local, model_id)""",
    """
CREATE TABLE mvp_receipts (
	group_id VARCHAR(200) NOT NULL, 
	topic VARCHAR(249) NOT NULL, 
	partition INTEGER NOT NULL, 
	"offset" BIGINT NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	payload_sha256 VARCHAR(64) NOT NULL, 
	outcome VARCHAR(40) NOT NULL, 
	measurement_id VARCHAR(64), 
	received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (group_id, topic, partition, "offset"), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id), 
	FOREIGN KEY(measurement_id) REFERENCES mvp_measurements (measurement_id)
)

""",
    """
CREATE TABLE mvp_scores (
	score_id VARCHAR(64) NOT NULL, 
	run_id VARCHAR(100) NOT NULL, 
	measurement_id VARCHAR(64) NOT NULL, 
	model_id VARCHAR(128) NOT NULL, 
	detector VARCHAR(40) NOT NULL, 
	model_version VARCHAR(160) NOT NULL, 
	feature_version VARCHAR(80) NOT NULL, 
	threshold_version VARCHAR(100) NOT NULL, 
	maturity VARCHAR(20) NOT NULL, 
	score FLOAT, 
	threshold FLOAT NOT NULL, 
	flag BOOLEAN, 
	status VARCHAR(30) NOT NULL, 
	reference_forecast_id VARCHAR(64), 
	prediction_wh FLOAT, 
	signed_residual_wh FLOAT, 
	forecast_origin VARCHAR(80), 
	forecast_target_timestamp VARCHAR(80), 
	reference_generated_at TIMESTAMP WITH TIME ZONE, 
	scored_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (score_id), 
	UNIQUE (measurement_id, model_id, threshold_version), 
	CHECK (maturity = 'experimental'), 
	FOREIGN KEY(run_id) REFERENCES mvp_runs (run_id), 
	FOREIGN KEY(measurement_id) REFERENCES mvp_measurements (measurement_id), 
	FOREIGN KEY(model_id) REFERENCES mvp_models (model_id), 
	FOREIGN KEY(reference_forecast_id) REFERENCES mvp_forecasts (forecast_id)
)

""",
    """CREATE INDEX ix_mvp_score_detector ON mvp_scores (run_id, detector, model_version)""",
]

def upgrade():
    for statement in DDL:
        op.execute(statement)

def downgrade():
    op.drop_table('mvp_scores')
    op.drop_table('mvp_receipts')
    op.drop_table('mvp_forecasts')
    op.drop_table('mvp_episodes')
    op.drop_table('mvp_measurements')
    op.drop_table('mvp_errors')
    op.drop_table('mvp_checkpoints')
    op.drop_table('mvp_sources')
    op.drop_table('mvp_runs')
    op.drop_table('mvp_models')
