"""Public contracts. Stored dataset labels remain strings without a fabricated UTC suffix."""
from datetime import datetime
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, ConfigDict


class Public(BaseModel):
    model_config = ConfigDict(extra='ignore')


T = TypeVar('T')
class Page(Public, Generic[T]):
    items: list[T]
    next_cursor: str | None
    order: Literal['ascending','descending'] = 'ascending'


class Health(Public):
    status: Literal['live', 'ready']


class Run(Public):
    run_id: str
    group_id: str
    topic: str
    created_at: datetime


class Source(Public):
    building_id: str
    source_id: str
    source_type: str
    energy_scope: str
    interval_seconds: int
    timestamp_reference: str
    timezone: str | None
    timestamp_has_offset: bool


class Timed(Public):
    run_id: str
    building_id: str
    source_id: str
    time_basis: Literal['dataset_naive', 'offset_aware']
    timezone: str | None
    timestamp_reference: str


class Measurement(Timed):
    measurement_id: str
    event_id: str
    measurement_timestamp: str
    interval_seconds: int
    energy_wh: float
    energy_unit: Literal['Wh'] = 'Wh'
    temperature_c: float | None
    relative_humidity_pct: float | None
    compatible: bool
    feature_status: Literal['ready','warmup','incompatible']
    gap_detected: bool
    received_at: datetime


class Forecast(Timed):
    forecast_id: str
    measurement_id: str
    model_id: str
    model_version: str
    feature_version: str
    purpose: str
    forecast_origin: str
    forecast_target_timestamp: str
    generated_at: datetime
    predicted_energy_wh: float | None
    energy_unit: Literal['Wh'] = 'Wh'
    horizon_seconds: int
    status: Literal['ready','warmup','incompatible']


class Score(Timed):
    score_id: str
    measurement_id: str
    measurement_timestamp: str
    model_id: str
    detector: str
    model_version: str
    feature_version: str
    threshold_version: str
    maturity: Literal['experimental']
    score: float | None
    threshold: float
    flag: bool | None
    status: Literal['ready','warmup','gap','incompatible']
    reference_forecast_id: str | None
    prediction_wh: float | None
    signed_residual_wh: float | None
    forecast_origin: str | None
    forecast_target_timestamp: str | None
    reference_generated_at: datetime | None
    scored_at: datetime
    score_semantics: Literal['detector_score_not_probability'] = 'detector_score_not_probability'


class Event(Timed):
    episode_id: str
    model_id: str
    detector: str
    model_version: str
    feature_version: str
    threshold_version: str
    maturity: Literal['experimental']
    start_timestamp: str
    end_timestamp: str
    flagged_points: int
    status: Literal['open', 'closed']
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime
    event_type: Literal['experimental_threshold_exceedance'] = 'experimental_threshold_exceedance'


class Model(Public):
    model_id: str
    role: str
    model_version: str
    feature_version: str
    threshold_version: str | None
    maturity: str
    feature_names: list[str]
    horizon_seconds: int | None


class Checkpoint(Public):
    run_id: str
    topic: str
    partition: int
    next_offset: int
    last_processed_at: datetime


class IngestionError(Public):
    error_id: str
    run_id: str
    topic: str
    partition: int
    offset: int
    kind: str
    created_at: datetime
    summary: Literal['Message rejected; inspect private worker diagnostics'] = 'Message rejected; inspect private worker diagnostics'


class PipelineStatus(Public):
    worker_status: Literal['unknown'] = 'unknown'
    status_reason: Literal['No heartbeat is recorded; checkpoints do not prove liveness'] = 'No heartbeat is recorded; checkpoints do not prove liveness'
    last_processed_at: datetime | None
    unique_measurements: int
    forecasts: int
    anomaly_scores: int
    duplicate_deliveries: int
    rejected_messages: int
    checkpoint_count: int
    checkpoints_truncated: bool
    checkpoints: list[Checkpoint]
    recent_errors: list[IngestionError]
    scope_run_id: str | None


class Aggregate(Timed):
    bucket_start: str
    bucket_end: str
    bucket_reference: Literal['measurement_label'] = 'measurement_label'
    interval_seconds: Literal[600] = 600
    bucket_minutes: int
    observed_intervals: int
    expected_intervals: int
    complete: bool
    energy_wh: float | None
    energy_unit: Literal['Wh'] = 'Wh'


class CombinedDecision(Timed):
    decision_id: str
    measurement_id: str
    measurement_timestamp: str
    rule: Literal['or','majority','unanimous']
    rule_version: str
    maturity: Literal['experimental']
    coverage_count: int
    available_detectors: list[str]
    triggered_methods: list[str]
    available_trigger_count: int
    trigger_count: int | None
    flag: bool | None
    agreement: Literal['none','one','two','three'] | None
    status: Literal['ready','warmup','gap','incompatible','partial']
    input_versions: dict[str,dict[str,str | None]]
    decided_at: datetime
    semantics: Literal['experimental_detector_agreement_not_probability_or_fault_severity'] = 'experimental_detector_agreement_not_probability_or_fault_severity'


class CombinedEpisode(Timed):
    episode_id: str
    rule_version: str
    maturity: Literal['experimental']
    start_timestamp: str
    end_timestamp: str
    flagged_points: int
    max_trigger_count: int
    last_trigger_count: int
    triggered_methods: list[str]
    status: Literal['open','closed']
    closed_reason: str | None
    input_versions: dict[str,dict[str,str | None]]
    created_at: datetime
    updated_at: datetime
