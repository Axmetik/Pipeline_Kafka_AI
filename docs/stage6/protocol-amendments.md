# Protocol amendments and preflight observations

## A1 — before the primary series

The first preflight failed before any containers started: uppercase `T` in the generated Compose project ID was rejected. The failed run manifest/log is retained; IDs now use lowercase `t`. No measurements from that attempt exist.

Overhead off-trials use the original worker entry point, no independent DB observer and no DOM telemetry callback; the ordinary browser dashboard and external resource sampler remain in both arms. Both arms retain the small producer correlation ledger. Therefore this estimates incremental worker/DB-observer/DOM instrumentation overhead, not the absolute overhead of every external measurement tool. Baseline worker durations cannot be obtained without instrumenting that baseline: compare completion throughput instead and report instrumented worker duration separately. No synthetic reduction of measured times.

Completion overhead is measured from the first measured producer send to the controller observing the final committed count (100 ms observation cadence). It includes the drain-observation uncertainty; per-message commit throughput is available only in instrumented trials. Freeze model output parity and report the three individual pairs, median and range. These short trials characterize overhead imprecisely; a large or unstable effect requires investigation, not an unqualified zero-overhead claim.

Resource sampling records actual timestamps. Docker CLI stats may deliver samples less frequently than the nominal 1 Hz target; report realized cadence, rather than asserting a precise 1 Hz rate. Browser callback marks React DOM layout commitment, not the end of Recharts animation or display scanout.

The first overhead preflight completed business processing and integrity validation, but its summary parser rejected Docker's compact RAM string (for example `100MiB`). The parser was corrected and cleanup made unconditional; raw data remain available. This unpaired preflight is retained separately from the registered three complete overhead pairs.

## A2 — pilot diagnosis, before the primary series

The three initial 150+100 overhead pairs were too short for stable throughput estimates (one baseline duration was more than twice another). One worker clock sample showed a 14.7 ms epoch/monotonic discrepancy. Preemption between clock reads is a hypothesis, not a demonstrated clock step. Those raw trials are retained. New telemetry brackets every epoch read with two monotonic readings and records the read uncertainty; clock-step checks subtract that uncertainty and still reject uncertainty above 10 ms.

Register a second overhead campaign `overhead-v2-{1,2,3}`, each with 300 warm-up + 600 measured records, the same on/off order, source, artifacts and processing. Use one controller monotonic clock from the observation of the first measured publication ledger entry to observation of the final DB count, avoiding an unsynchronized host/VM epoch subtraction. Start observation cadence is 10 ms; final DB-count polling is 100 ms plus request time. Keep the initial campaign separate, with no deletion or rewriting of measurements. No primary runs have started. The 5% investigation rule still applies. Recovery readiness is an observed upper bound: the first post-restart committed record appears in the asynchronous ledger after Kafka acknowledgement, plus the controller's 10 ms observation cadence and filesystem scheduling.

Resource collection for the primary/API/recovery series discovers all current containers of the unique evaluation project on each sample, including the DB observer, browser, transient replay and HTTP clients. Very short-lived containers may finish between samples; these are not treated as having zero CPU/RAM. Resource CPU/RAM summaries use the controller's measured window; Docker CPU percentages have their own preceding averaging interval. No claim of physical-device latency or CPU power/temperature measurement is made.

## A3 — overhead investigation, before the primary series

Campaign v2 throughput overhead was approximately 9.51%, 3.16%, 32.94% in the three registered pairs (median 9.51%). All observations are retained; no primary runs were released. The writer flushed whenever its queue became empty, often once per message/poll. This causes frequent shared-filesystem operations, even though outside the processing thread; causality for the observed slowdown has not been established.

Register campaign v3 with the identical three pair orders and 300+600 records. Change only telemetry buffering to at most one scheduled flush per second, with immediate background flush for the first post-start/recovery committed message and clean shutdown. Queue loss remains explicit. Start timing now observes a single small first-publication-ack marker written once per phase in both arms; it no longer depends on periodic ledger flushes. This marker is outside the recorded publication-ack span. Readiness-after-restart uses the immediate first-message flush, so recovery detection is not delayed by the one-second general buffer. No ML or DB/checkpoint behavior is changed. The registered primary design remains 300+3600, five repetitions per mode.
