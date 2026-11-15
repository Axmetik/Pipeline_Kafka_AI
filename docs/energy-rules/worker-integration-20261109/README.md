# Experimental rules — Worker/PostgreSQL/recovery, first integration

Date:2026-11-09. Branch:feature/energy-rule-detectors. Adds only the opt-in frozen rules-v2 layer and **residual OR sustained_high** consumption review channel. No low, API, Dashboard or Email integration; existing ML, thresholds, Unanimous, experiments and Kafka commit code unchanged.

## Explicit default-off switch

`MVP_ENERGY_RULES_ENABLED=false` is the default in `Settings`. Only true/false/1/0 are accepted; typos fail explicitly. When off, no rule-table access, assessments, state updates, hybrid decisions or hybrid episodes occur. Existing base DB revision0003_email works without the optional migration. The existing run/artifact identity and old model recovery are unchanged.

When enabled, worker startup requires the optional schema and fails with the migration command if absent. Base API deliberately checks revision0003_email, so this feature uses a **separate additive Alembic revision ledger**, preserving that base revision and leaving API code untouched. There is no automatic migration on worker startup.

Reviewed future setup on an explicitly selected local database (commands documented, **not executed on the demo**):

```sh
# Existing base schema and trusted artifacts must already be provisioned.
# Set MVP_DATABASE_URL privately for the intended DB; do not paste credentials into Git.
.venv/bin/alembic -c alembic-rules.ini upgrade head
export MVP_ENERGY_RULES_ENABLED=true
# Start the existing worker with its usual run/group/topic/artifact settings.
.venv/bin/python -m integration.energy_worker
```

No build, replay, training or backfill is involved. For disabling, use `MVP_ENERGY_RULES_ENABLED=false` on the next deliberate worker start. This implementation does not automatically restart anything.

## Four separate tables, no rewriting historical results

| Table | Content |
|---|---|
| mvp_rule_assessments | Three rows per new accepted measurement: flatline/interval_gap in telemetry_quality, sustained_high in consumption_pattern; nullable flag,status,evidence,rule_version,layer_version,exact configuration,activation reason,experimental maturity |
| mvp_hybrid_decisions | One residual-or-high decision per new measurement/version; true/false/null,status,coverage_count,available_inputs,triggered_inputs,input model/feature/threshold versions and rule config |
| mvp_rule_states | Latest committed per-run/building/source JSON state, version/checksum and exact measurement/offset/timestamp anchor |
| mvp_hybrid_episodes | Experimental consumption episodes only; version,input versions,start/end measurements/timestamps,point count,trigger-source union,status/close reason |

The migration is `migrations/rules/versions/0001_rules.py`, tracked by `alembic_rule_layer_version`. Base `alembic_version`, original tables and original SQLAlchemy metadata are unchanged. Upgrade creates empty tables: **no backfill**. Downgrade drops only optional tables and is destructive to these new results; it was tested only in a private temporary schema, not run against the demo.

ML scores remain in mvp_scores; original Unanimous remains in mvp_combined_decisions/episodes. New tables are not read by API/Dashboard/Email, and no new notification is enqueued. Current Email behavior for original channels is untouched.

## Tri-state decisions and episodes

The hybrid input is the **current committed-transaction residual score flag**, already based on the prior interval's persisted RF21 forecast, plus current sustained_high. No extra RF/HGB/IF/AE inference is added by the rule layer.

- true if either available input is true, even when the other is null;
- false only if both inputs are available and false;
- otherwise null.

Decision stores available/positive input names and their versions. `partial_positive` is explicitly available true with one input; a missing input is never treated as false. An incompatible ML source can still have an interpretable rule signal, without applying an incompatible ML model.

Hybrid episodes are built from consecutive true decisions at600-second source timestamp cadence. False, null, a timestamp gap, configuration change or activation-gap resets close the old episode. A current true can start a new episode after the closure, but never bridge across the interruption. Configuration version hashes algorithm/config/rules-v2/residual model+feature+threshold identities. Flatline and returned interval_gap are assessments only here, not consumption episodes. Gap evidence is produced **after the next received measurement**, not a silence watchdog.

## Transaction, idempotency and failure handling

`Processor.process` checks the existing locked DB checkpoint and ledger first. Same-coordinate redelivery and same-event redelivery at a new offset bypass both ML and rules computations. No new derived rows or history change occurs on duplicates.

For a new accepted measurement, the existing ML persistence and original Unanimous run as before. Rule assessments, hybrid decision/episode changes and source snapshot are then written **in that same transaction**, before ledger/checkpoint finish and DB commit. Existing worker Kafka commit remains after successful `Processor.process`; `integration/energy_worker.py` is unchanged.

Any exception or ambiguous post-commit failure poisons the Processor, including its advanced in-memory rule state. Reuse is rejected; a new Processor must restore committed DB state. Nothing attempts to continue with rolled-back memory.

## Recovery — why144 measurements are insufficient

An explicit JSON snapshot is the minimal sufficient state, not a pickle and not an unbounded history scan. It preserves the complete frozen `EnergyRules` state:

- bounded previous7-calendar-day/current-day history and cadence eligibility;
- flatline sliding window and last timestamp;
- candidate count/start and **all24 hourly profiles frozen before candidate onset**, including cutoff and unavailable contexts;
- source binding, last-event fingerprint and cached last assessment for idempotent last-message retry.

`energy-rules-state-v1` is separate from the unchanged rules algorithm/version. The source snapshot is committed atomically with each accepted enabled record. On startup, checksum, schema/config version, source/measurement/offset/timestamp anchor and normalized last-record fingerprint are verified. Missing snapshots for an already assessed source, corrupted snapshots, or snapshots not anchored to the latest assessment fail closed. The DB checkpoint is rechecked after model+rule recovery to fence concurrent advancement. Open hybrid episodes remain in DB and are continued/closed by the next transactional decision.

**First activation:** existing historical measurements are not retroactively processed. A new layer begins explicit v2 warm-up on newly accepted records; default sustained_high needs18 same-hour historical points across3 previous dates. This is intentionally not a historical backfill. A changed configuration also starts warm-up; the next source transaction closes any old-version episode. If the layer was disabled while that source advanced, reactivation records `activation_gap`, discards the obsolete snapshot and starts warm-up; it cannot silently treat the disabled period as a continuous monitored stream. Idle disable/re-enable without source advancement can restore the existing valid state.

Unsupported non600-second measurements receive null/incompatible rule assessments and do not feed v2 history. No fabricated timezone is assigned. Snapshot state is in-memory algorithm state only, not a diagnosis of failure or a change to the existing ML ledger/recovery contract.

## Verification actually performed

**58 targeted checks passed**, no skipped tests:

-5 new unit tests: all9 OR states+provenance, strict/default-off switch, JSON7-day/candidate/retry parity, corruption/anchor/config/reactivation, unsupported interval/no-low/category separation;
-4 new real PostgreSQL integration tests: opt-in migration with no backfill/base revision unchanged and old/on-off output parity; seven-day candidate recovery across rollback and restart; offset/event redelivery and after-commit crash; old-row immutability; config closure; true/false/null/gap lifecycle; no hybrid notifications; corrupted/missing state and activation-gap handling;
-41 frozen rules-v2 regressions and8 existing MVP unit checks.

Integration used deterministic **model doubles**, not retraining or experiment artifacts. Forecast/score/Unanimous values and formation timestamps were compared exactly under a fixed clock across off/on runs; existing committed rows were also checked unchanged after recovery. The seven-day test processed more than1000 synthetic accepted measurements through the actual SQL transaction path and resumed count5 with all24 frozen references intact. The first test attempt had a fixture query selecting both a legitimately closed residual episode and the active hybrid episode; query corrected to select the open episode, final run passed.

Tests ran in an owned, isolated PostgreSQL18 container/schema on a private internal Docker network, no published ports, tmpfs data, and an existing backend image. No image rebuild/pull, Kafka replay, new model experiment, or demo restart/migration occurred. Cleanup removed only those owned temporary containers/network. Existing volumes/datasets/ML artifacts/Stage6 checkout were untouched.

New PostgreSQL tests are included in the existing API/PostgreSQL CI suite (they require only PostgreSQL); unit selection excludes them. Full Kafka/browser/E2E/performance campaigns and manual full CI reruns were not performed for this stage. Push may trigger the repository's normal automatic CI; success is not claimed without a checked run.

[Targeted test log](targeted-tests.log). Source changes: integration/rule_layer.py, integration/processor.py, integration/settings.py, storage/postgres/rules.py, storage/postgres/rules_schema.py, optional migration/config and targeted tests. Low candidates and old research evidence remain separate and unchanged.
