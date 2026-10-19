# Stage 6: registered system-performance protocol, version 1

Registered before instrumentation and observations. Base: `v0.1.0-mvp` (`6c63d8d`). No training, model selection, threshold adjustment or checkpoint changes are permitted. This evaluates historical UCI dataset replay on one Docker host, not physical smart meters. Historical naive timestamps are model inputs only, never system clocks.

## Frozen design

Three sequential, acknowledged-producer modes: slow `sleep=1 s`, demonstration `sleep=0.15 s`, maximum `sleep=0 s`. Sleep is after acknowledgement; actual arrival rate also includes producer overhead. Each independent primary run has 300 warm-up records, a drain barrier, and 3,600 measured records from the same consecutive dataset prefix. Five independent repetitions per mode. Seed 42. Block order: [slow,demo,max], [demo,max,slow], [max,slow,demo], [slow,max,demo], [demo,slow,max]. No post-hoc removal of slow or failed runs. Drain timeout 900 s; startup timeout 240 s. Pilot: 150 warm-up + 60 measured per mode, excluded from main results. Overhead: three paired maximum-rate trials, 150+100 records; pair orders on/off, off/on, on/off. Compare medians of throughput and worker duration. A measured overhead above 5% is reported and investigated before the full series; no silent subtraction.

Each run uses a unique run/topic/group and a new Compose project with fresh PostgreSQL/Kafka volumes. Preserve user demo volumes. Same source binding, dataset SHA256, trusted read-only artifacts, CPU inference thread policy (one thread), library versions and images throughout. Record host CPU/RAM/OS, Docker VM CPUs/RAM, image IDs/digests, container CPU/memory limits and concurrent background services. No resource-limit changes between runs. OS disk cache is not claimed cold. Do not retrain artifacts.

## Clocks and latency boundaries

All backend producer, worker and DB observer processes run in the same Docker VM. Each span uses `perf_counter_ns()` within one process. Epoch `time_ns()` is used only for correlation across processes. Record both clocks at start/end; detect clock steps against monotonic elapsed time. Browser uses `performance.timeOrigin + performance.now()`, and 10 request/response clock exchanges at start, every 60 s and end. Estimate offset using midpoint and bound uncertainty by half RTT plus server span; keep raw exchanges. Cross-process latency is invalid if clock uncertainty exceeds 10 ms or clock steps exceed 10 ms; retain observations and report invalid counts, never clamp negatives. Browser results are explicitly bounded by this synchronization error.

| Metric | Beginning → end | Clock/source |
|---|---|---|
| Publication acknowledgement | immediately before producer.send → successful future.get | producer monotonic; include serialization, enqueue, broker roundtrip; record epoch bounds and returned topic/partition/offset |
| Worker processing | Processor.process entry → return after DB transaction commits | worker monotonic, excluding subsequent Kafka commit |
| Poll-to-DB acknowledgement | delivery from Kafka poll → Processor.process return | worker monotonic |
| ML inference | each HGB/RF/IF/AE prediction call entry → return | worker monotonic; separate calls, sum disjoint prediction spans; feature processing reported separately |
| Transaction scope | Engine.begin entry → exit | worker monotonic; includes model execution inside the existing transaction, so it is not pure SQL latency |
| SQL execution | before_cursor_execute → after_cursor_execute | worker monotonic; sum per message, includes network roundtrip |
| DB commit acknowledgement | dialect.do_commit entry → return | worker monotonic; actual DBAPI commit call including acknowledgement, not transaction-start timestamps |
| Kafka commit acknowledgement | consumer.commit entry → return | worker monotonic; remains strictly after successful DB transaction |
| End-to-end acknowledgement | producer send epoch → worker DB acknowledgement epoch | synchronized epoch, including publication/queue/worker; producer acknowledgement may occur after consumer delivery |
| API response | request initiation → complete HTTP response body | load-client monotonic; status/timeouts separately |
| Fetch→DOM | dashboard refresh response completion → committed DOM observation | browser performance clock |
| DB availability→DOM | independent committed-read availability interval → first DOM observation of that measurement ID | VM/browser epochs with synchronization bounds |
| Recovery | controller restart request → restored history AND first subsequent successful record commit | controller monotonic; report startup/history ready and resumed commit separately |

`received_at` defaults to PostgreSQL transaction-start time, not commit time. An independent read-only observer queries newly committed measurement IDs every 50 ms; availability is interval-censored between the previous query start and first successful query end. Preserve those bounds; publish DOM-latency lower/upper bounds and midpoint estimates, with clock uncertainty. Never substitute DB commit acknowledgement for exact availability. Observer cost belongs to measured instrumentation overhead. No DB triggers, schema changes, synchronous per-message large logging or additional transactional writes. Buffered telemetry uses a bounded queue with a dedicated writer; missing/dropped records invalidate telemetry completeness, while business integrity is checked independently.

## Pilot and overhead gates

Before main runs, validate event_id ↔ Kafka offset ↔ DB measurement_id correlation; 1 receipt/measurement, 2 forecast rows and 3 score rows per accepted event including nullable warm-up rows. Check unique IDs, contiguous offsets, DB/broker next offset, no quarantines/duplicates and identical model outputs instrumented/uninstrumented (excluding generated wall times and random run IDs). Verify every required span, SQL/commit counts, clock exchanges, DOM/DB visibility coverage and resource samples. Pilot must include restart after warm-up. Document failures and fixes with protocol amendments before a repeat; retain failed raw runs. No main series until measurement correctness and overhead are understood.

## Separate API, browser and recovery series

Primary worker runs have one normal dashboard observer, DB observer and 1 Hz resource sampling; no synthetic API load. API load series are separate, labeled idle/replay scenarios: five repetitions, 1 and 5 concurrent clients, 50 warm-up + 1,000 measured requests per client, balanced round-robin measurements/forecasts/scores/events/status endpoints, bounded queries. In replay scenarios use a distinct demonstration-rate 300+3,600 replay context, release HTTP clients after warm-up, and report the exact overlap interval/count. No API load observations are pooled into primary throughput results. Fixed request timeout 10 s; record all errors/timeouts and actual offered rate.

Dashboard uses normal two-second polling with the default 144-point window; report actual poll intervals, first DOM appearances, latest-point freshness and fraction of committed IDs ever observed. Fast replay may skip intermediate states: missing DOM observations are censored, never zero-latency samples. Browser itself must actually render new Kafka-delivered data. Resource samples include browser and observers separately.

Recovery: five independent demonstration-rate trials after 300 warm-up records, restart worker while retaining DB and Kafka; send 100 further records and wait for resumed commits. Record all five recovery durations, median/min/max. Capture pre-restart forecasts (including generated_at), checkpoint and episodes; assert old rows unchanged, successful runtime history restoration, resumed inference, zero unexpected duplicates and contiguous receipts. Existing before/after DB commit failure integration tests remain mandatory. Recovery results are not mixed into steady-state latency.

## Analysis and retained artifacts

Per run: counts, duration, arrival/commit throughput, p50/p95/p99 via linear quantiles for every latency, CPU mean/p95/peak and RAM peak, clock error/coverage, completeness and integrity. Across five independent runs report individual quantiles plus median/min/max of run summaries; pooled message quantiles may be supplementary only. Do not treat dependent messages as independent experimental replicates. Preserve incomplete runs and reasons; no test-driven tuning of models or thresholds.

Store protocol/config, environment manifest, per-run CSV/JSONL (optionally gzip), errors/integrity, model checksums, tables, plots and final report under `docs/stage6/`. Never include credentials, database connection URLs, raw quarantine payloads or trusted model binaries. Write resumable run manifests before launch; an interrupted run is retained as incomplete. The full slow series takes at least five hours; never shorten it while retaining its label.
