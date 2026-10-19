# Stage 6: system-performance evaluation

Status is tracked in [execution-status.md](execution-status.md); that file does not imply the main series is complete. The registered design is [protocol.md](protocol.md), with transparent pre-main [amendments](protocol-amendments.md). All model artifacts, features, thresholds and business transactions are unchanged.

Use the existing Stage5 setup and trusted Docker artifact manifest. Stage6 never trains or downloads model replacements. The full historical CSV must match the registered SHA256. Do not run performance series concurrently, run local tests during measurements, or use port 8089 for another service. The ordinary MVP on 8088 is preserved.

```sh
source .venv/bin/activate
python -m performance.prepare
python -m performance.run pilot
python -m performance.run overhead
python -c 'from performance.run import Run; Run("pilot-recovery-v6","demo",150,60).run(recovery=True)'
python -m performance.gate
python -m performance.run main
python -m performance.run recovery
python -m performance.run api
python -m performance.report
python -m performance.plots
python -m performance.archive
```

The `main` command refuses to start without the pilot gate. Main series runs sequentially in the registered order; it takes more than six hours. API replay series add roughly 90 minutes. Keep the host awake, Docker running, and power/background conditions stable. Scripts do not change host power settings. Record interruptions rather than silently replacing runs. Every run receives a new context and fresh DB/Kafka volumes; only that run's volumes are removed after retained integrity checks.

The long sequential series can also be run as `python -m performance.campaign`.
On macOS an optional temporary idle-sleep assertion is `caffeinate -i python -m performance.campaign`.
Backend/browser bulk telemetry uses a fresh Docker-local `telemetry` volume and is exported after writers stop; small control markers and external Docker resource samples remain on the host. If export fails, volumes are retained for diagnosis. The final pilot repeats all three modes with this storage policy; earlier diagnostic campaigns remain separate.

Cross-process latency now uses a verified shared VM monotonic domain (amendment A5).
Worker/API/tools boot IDs, time namespaces and clock implementation must match;
producer/observer/worker emit their actual domains. Browser exchanges bridge its
monotonic timeline into that same domain. Epoch clock corrections are retained as
diagnostics, not silently subtracted or mistaken for message delay. This method
must not be generalized to separate physical devices or hosts.

Raw JSONL/JSON, limits, logs and a real browser screenshot are under `raw/<run_id>/`. `latencies.csv` retains per-run p50/p95/p99 and validity flags. `summary.json` includes clock uncertainty, visibility bounds, censored browser IDs, SQL/ML latency, resource sample intervals and HTTP outcomes. Model binaries and credentials remain ignored. `environment.json` contains a whitelist of hardware/Docker information and trusted manifest checksums, never Docker environment variables or DB URLs.

Dashboard DOM observations are committed React snapshots, not physical display measurements. Independent PostgreSQL polling bounds availability; it does not claim an exact commit timestamp. API load is a separate scenario, not hidden in primary worker results. `worker_status=unknown` remains unchanged in the normal API. Anomalies remain experimental threshold exceedances.

Unit and existing PostgreSQL/Kafka integration suites exercise telemetry math, loss, clock-read uncertainty, warm-up exclusion, censoring, actual DBAPI commit spans and parity with unchanged model outputs. Full performance series are intentionally not run inside GitHub Actions.
