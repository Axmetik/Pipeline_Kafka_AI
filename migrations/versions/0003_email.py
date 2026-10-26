"""Additive email outbox only; no historical backfill."""
from alembic import op
revision="0003_email"
down_revision="0002_combined"
branch_labels=None
depends_on=None
DDL=["\nCREATE TABLE mvp_notification_outbox (\n\tnotification_id VARCHAR(64) NOT NULL, \n\tepisode_id VARCHAR(64) NOT NULL, \n\trun_id VARCHAR(100) NOT NULL, \n\tbuilding_id VARCHAR(160) NOT NULL, \n\tsource_id VARCHAR(160) NOT NULL, \n\tkind VARCHAR(20) NOT NULL, \n\tmethod VARCHAR(160) NOT NULL, \n\trecipient VARCHAR(254) NOT NULL, \n\tconfig_fingerprint VARCHAR(64) NOT NULL, \n\tpayload JSONB NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tattempt_count INTEGER DEFAULT '0' NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tnext_retry_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tclaimed_until TIMESTAMP WITH TIME ZONE, \n\tclaim_token VARCHAR(64), \n\tsent_at TIMESTAMP WITH TIME ZONE, \n\terror_category VARCHAR(60), \n\tsuppression_reason VARCHAR(60), \n\tPRIMARY KEY (notification_id), \n\tUNIQUE (kind, episode_id, recipient), \n\tCHECK (kind IN ('individual','combined')), \n\tCHECK (status IN ('pending','sending','sent','retrying','failed','suppressed') AND attempt_count >= 0), \n\tFOREIGN KEY(run_id) REFERENCES mvp_runs (run_id)\n)\n\n", 'CREATE INDEX ix_mvp_notification_due ON mvp_notification_outbox (status, next_retry_at)', 'CREATE INDEX ix_mvp_notification_scope ON mvp_notification_outbox (run_id, building_id, source_id, kind, method, created_at)']

def upgrade():
    for sql in DDL: op.execute(sql)

def downgrade():
    op.drop_table("mvp_notification_outbox")
