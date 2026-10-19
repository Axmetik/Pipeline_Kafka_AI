# Instrumentation overhead investigation

The final estimate uses all three registered v7 pairs, with no favorable subset selection. Earlier campaigns are retained commissioning diagnostics, not pooled into this estimate.

| Pair | Instrumented completion (messages/s) | Original worker completion (messages/s) | Signed throughput difference (%) | Output parity |
|---|---:|---:|---:|---|
| overhead-v7-1 | 21.8664 | 22.1431 | 1.2498 | True |
| overhead-v7-2 | 20.4413 | 17.1069 | -19.4914 | True |
| overhead-v7-3 | 19.7677 | 21.5629 | 8.3255 | True |

Median signed difference: **1.2498%**; min -19.4914%, max 8.3255%. Positive values mean lower instrumented throughput; negative values do not demonstrate a causal acceleration from instrumentation.

The common controller measures first-publication-ack observation to final committed-count observation on its own monotonic clock. Start polling is 10 ms; completion uses a dedicated read-only PostgreSQL checkpoint probe every 100 ms, followed by CLI return/export overhead. No synthetic HTTP completion polling is used in this final campaign. Original-worker trials deliberately contain no per-message worker timing, DB observer or DOM callback. Both arms retain the small producer ledger, normal dashboard, startup clock checks and external Docker resource sampler; this is an incremental overhead estimate, not a measurement of zero-tool production performance.

## Checks and diagnosis

Every final pair has exact forecast/score output parity, full event-ID/offset/DB correlation, zero unexpected duplicates/rejections and complete telemetry. Instrumented spans and browser clock bridges passed the verified shared-kernel monotonic-domain checks. All recorded data are retained.

Initial diagnostics identified frequent shared-filesystem flushes, a shared CLOCK_REALTIME correction and one exhausted Docker-network pool. Buffering/local-volume export, a verified monotonic clock bridge, complete cleanup and 200 ms visibility polling address those measurement risks. They do not change ML, database transactions, Kafka commit/recovery or source bindings.

The 200 ms independent DB observer trades temporal precision for less query load. Availability-to-DOM is reported with lower/upper bounds plus synchronization uncertainty; midpoint values are estimates. CPU/RAM samples and their actual cadence are in each summary/raw resource file. Resource sampler cost common to both arms is not separately identified.

With three sequential pairs on a shared laptop, scheduling, caching and other host activity can influence signed differences. These data do not establish a unique cause for the remaining overhead or a statistically precise universal correction. No timing is numerically adjusted, and no additional campaign is chosen to obtain a favorable median.

The 5% value remains an investigation trigger. Primary results describe the instrumented system, with the budget-exceeded flag preserved if applicable. They must not be represented as uninstrumented throughput or a physical-smart-meter SLA.

Campaign v6 used HTTP status polling during completion and is retained as commissioning evidence, not pooled into the v7 estimate. The v7 correction is registered in protocol amendment A8.
