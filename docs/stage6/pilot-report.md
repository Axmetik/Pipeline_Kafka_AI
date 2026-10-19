# Stage 6 — final pilot report

Final commissioning campaign: **v7**. This is a pilot validation report, not the registered five-repeat primary evaluation. The full series has not yet been executed.

## Measurement validation

All three final replay pilots passed the publication/event-ID/Kafka-offset/PostgreSQL correlation and telemetry-loss checks. Each used 150 warm-up records and 60 measured records, separate run/topic/group and fresh database/broker volumes. Pilot data are excluded from the primary statistics.

| Mode | Measured publications / DB commits | Send→DB acknowledgement p50 / p95 / p99 (ms) | Measured IDs observed in DOM | Clock valid |
|---|---:|---|---:|---|
| slow | 60 / 60 | 61.041 / 101.134 / 131.735 | 60 / 60 | True |
| demo | 60 / 60 | 57.409 / 160.176 / 172.094 | 60 / 60 | True |
| max | 60 / 60 | 1481.779 / 2954.583 / 3140.701 | 60 / 60 | True |

These short-run latency estimates validate collection and queue behavior; they are not substitutes for the full 3600-record runs. The maximum-rate replay accumulates queue delay. No historical dataset timestamps are used as latency clocks. Worker/API/producer/observer share a verified Linux VM monotonic domain; the browser uses bounded clock exchanges. Availability→DOM remains bounded by 200 ms DB observation and synchronization uncertainty. Per-pilot bounds, polling cadence, fetch→DOM timing and censoring counts are retained in each summary.

## Instrumentation overhead

All three preregistered v7 pairs used 300 warm-up and 600 measured records per arm. Signed throughput differences (positive means slower instrumented completion): 1.2498%, -19.4914%, 8.3255%.
Median: **1.2498%**. The 5% investigation flag is **False**. Exact forecast/score parity passed for every pair. Wide pair-to-pair variation limits causal interpretation; no correction is subtracted from primary timings. See [all pairs and investigation](overhead-investigation.md).

V7 uses read-only PostgreSQL checkpoint completion probes, with no synthetic HTTP completion load. Ordinary Dashboard polling and the documented DB visibility probe remain part of the instrumented condition. Earlier campaigns, clock adjustments, failed/preflight attempts and methodological amendments remain retained separately; they are not pooled into this estimate.

## Functional recovery pilot

Run: `s6-pilot-recovery-v7-demo-20261019t175618-a15932`. Restored journal/history: 150 records. History restoration took **1.991 s**; worker startup/ready took **6.330 s**; restart invocation to the first subsequently committed record observed by the controller took **8.015 s**. The latter includes restart, replay start and observation delay and is the functional recovery metric.
Saved forecast hashes including generation timestamps and saved scores remained unchanged. Checkpoint/offset reconciliation and episode continuity passed. There were **0 open** and **1 closed** episodes before restart. Consequently this natural-stream pilot does not demonstrate recovery of an open episode; the existing crash/recovery integration fixture explicitly exercises that case.

## Environment, tests and limitations

Apple M1 MacBook Pro, 16 GB host RAM; Docker VM 5 CPUs and 6,212,689,920 bytes RAM. Frozen image IDs, library versions, model manifest, dataset checksum and power/thermal observations are in [environment.json](environment.json). Background MVP containers remain present and are documented. This is a shared-laptop evaluation, without exclusive CPU scheduling.

Before final pilots, the complete local Python suite passed: **103 tests in 62.632 s** (unit, Kafka, PostgreSQL, recovery and API). Frontend regression previously passed 9 tests, TypeScript, build and Docker browser contracts. GitHub Actions is tracked separately; no unfinished CI is represented as successful.

Docker resource sampling has an actual cadence around 2 seconds, despite a nominal 1-second request cadence. Ephemeral container sampling errors/counts remain explicit in summaries; resource series are sampled observations, not complete CPU traces. Cross-process monotonic compatibility is Docker-VM-specific and must not be generalized to separate physical devices.

The pilot release gate passed with zero integrity/telemetry/clock issues. It binds configuration, instrumentation, trusted manifest and frozen environment checksums. Proceed with the preregistered 15 primary runs, five recovery trials and 20 separate HTTP scenarios without changing models, thresholds or business transaction semantics.

All six GitHub Actions jobs passed for implementation commit `8c56e5a`: [CI run](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/39297827898).
