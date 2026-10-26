export type Basis = "dataset_naive" | "offset_aware";
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  order: "ascending" | "descending";
}
export interface Run {
  run_id: string;
  created_at: string;
  topic: string;
}
export interface Source {
  building_id: string;
  source_id: string;
  source_type: string;
  interval_seconds: number;
  timestamp_has_offset: boolean;
  timezone: string | null;
}
export interface Measurement {
  measurement_id: string;
  measurement_timestamp: string;
  run_id: string;
  building_id: string;
  source_id: string;
  time_basis: Basis;
  energy_wh: number;
  interval_seconds: number;
  feature_status: string;
  received_at: string;
  temperature_c: number | null;
  relative_humidity_pct: number | null;
}
export interface Forecast {
  forecast_id: string;
  measurement_id: string;
  purpose: "primary_forecast" | "residual_reference";
  forecast_origin: string;
  forecast_target_timestamp: string;
  generated_at: string;
  predicted_energy_wh: number | null;
  status: string;
  model_version: string;
  feature_version: string;
}
export type Detector = "isolation_forest" | "autoencoder" | "residual";
export interface Score {
  score_id: string;
  measurement_id: string;
  measurement_timestamp: string;
  detector: Detector;
  score: number | null;
  threshold: number;
  flag: boolean | null;
  status: string;
  maturity: "experimental";
  model_version: string;
  threshold_version: string;
  feature_version: string;
}
export interface Episode {
  episode_id: string;
  detector: Detector;
  start_timestamp: string;
  end_timestamp: string;
  status: "open" | "closed";
  flagged_points: number;
  maturity: "experimental";
  model_version: string;
  threshold_version: string;
}
export interface Model {
  model_id: string;
  role: string;
  model_version: string;
  feature_version: string;
  threshold_version: string | null;
  maturity: string;
  feature_names: string[];
}
export interface Status {
  worker_status: "unknown";
  last_processed_at: string | null;
  unique_measurements: number;
  forecasts: number;
  anomaly_scores: number;
  duplicate_deliveries: number;
  rejected_messages: number;
  checkpoints: { next_offset: number; topic: string }[];
  recent_errors: { kind: string; created_at: string }[];
}
export interface Selection {
  run: string;
  building: string;
  source: string;
}
export interface Snapshot {
  combined?: CombinedDecision[];
  combinedEvents?: CombinedEpisode[];
  moreCombinedEvents?: boolean;
  runs: Run[];
  sources: Source[];
  selection: Selection;
  measurements: Measurement[];
  forecasts: Forecast[];
  scores: Score[];
  events: Episode[];
  moreEvents: boolean;
  models: Model[];
  status: Status;
  basis: Basis;
}
export interface CombinedDecision {
  decision_id: string;
  measurement_id: string;
  measurement_timestamp: string;
  rule: "or" | "majority" | "unanimous";
  rule_version: string;
  coverage_count: number;
  available_trigger_count: number;
  trigger_count: number | null;
  triggered_methods: Detector[];
  flag: boolean | null;
  status: "ready" | "warmup" | "gap" | "incompatible" | "partial";
  maturity: "experimental";
}
export interface CombinedEpisode {
  episode_id: string;
  start_timestamp: string;
  end_timestamp: string;
  max_trigger_count: number;
  last_trigger_count: number;
  triggered_methods: Detector[];
  flagged_points: number;
  status: "open" | "closed";
  rule_version: string;
  closed_reason: string | null;
}
