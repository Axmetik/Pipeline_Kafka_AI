# Traceability: твердження → джерело → перевірка → результат → межа

База `c156668`, 27.10.2026. [CI snapshots](ci-evidence.json) — прочитані на GitHub
результати, не нові запуски. [Verified values](verified-values.json) — перерахунок
saved data, без inference. Посилання на код нижче належать аудованій базі.

## Докази CI

- **C7C:** [40420232238](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40420232238),
  head `7e8b7d7…`, 6/6 success. Git tree `c04fde43…` збігається з merge base
  `c156668…`. Тому тести відносяться до того самого вмісту системи, а не лише назви гілки.
- **C7B:** [40412405686](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40412405686),
  `dff6282…`, 6/6 success, включно з no-eligible-rule fallback fix.
- **C6:** [39297827898](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/39297827898),
  `8c56e5a…`, 6/6 success для старішого performance implementation. Це не доказ
  завершення primary campaign, не поточний performance run.

У C7C логи підтверджують 85 unit, 13 PostgreSQL/Kafka/recovery, 23 API SQL
(15 наявних+8 Email). Інші jobs: Kafka smoke та frontend/TypeScript/build/browser.
Повний browser job підтвердив live replay, повторний Showcase й combined parity.
Email SMTP mocked у CI; реальна **локальна Mailpit** доставка — окремий saved proof.
Немає C7C evidence відправлення листів у зовнішній SMTP, і це не стверджується.

## Матриця тверджень

| ID / твердження | Первинне джерело | Експеримент / тест | Підтверджений результат | Обмеження |
|---|---|---|---|---|
| S01: interval energy, не power | [UCI](https://archive.ics.uci.edu/dataset/374/appliances%2Benergy%2Bprediction), `producer/appliances_dataset.py`, schema | read CSV hash, 19735 rows; schema tests у C7C | Appliances Wh, крок600s; checksum pinned | один historical household, naive timezone |
| S02: Stage2 baseline trade-off | `artifacts/mvp/docker/hgb/{test_predictions.parquet,metrics.json}`; [review](../energy-review-followup.md) | verifier MAE/RMSE із saved predictions | HGB20 MAE28.34712524/RMSE61.10721634; persistence26.63963507/66.43671272 | HGB20 не виграв MAE; artifact version локального Docker окрема |
| S03: validation-selected RF | [selection](../forecast-benchmark/results/selection.json), [trials](../forecast-benchmark/results/validation_trials.json) | `test_selection_and_refit_reproducible_and_test_independent`, static selection/run review | RF validationMAE26.44345773 < HGB21 26.54491375 | test не дозволяє перевибір; історична exposure |
| S04: test forecasting comparison | [test_predictions](../forecast-benchmark/results/test_predictions.csv), [metrics](../forecast-benchmark/results/metrics.csv) | independent arithmetic у verifier | HGB21 test26.13252350/58.92021238; RF26.63038504/59.37452075; baseline26.63963507/66.43671272 | 3946 спільних target; descriptive, не unseen або significance |
| S05: causal seasonal feature | `benchmark/features.py`, saved test predictions + original CSV | verifier target−24h, origin+600; `test_seasonal_uses_target_minus_day_not_origin_minus_day`, future/split tests | seasonal target alignment і disjoint target membership підтверджені | ранні observed test actuals дозволені для one-step history |
| S06: peak evaluation | [peak_metrics](../forecast-benchmark/results/peak_metrics.csv), metadata | verifier train P90/peak predictions; peak unit test C7C | train P90=210Wh, test count312; RF peakMAE127.31752821, baseline150.28846154 | high loads ≠ faults; mean errors не control savings |
| S07: frozen anomaly thresholds | [thresholds](../energy-anomaly/results/thresholds.json), [protocol](../energy-anomaly/protocol.md), checksums | 407 SHA match; train/calibration isolation unit C7C | q99 IF.6747213488, AE.8288606024, residual296.2460258Wh | original models; local live AE threshold інший |
| S08: poor mixed anomaly quality | [metrics](../energy-anomaly/results/metrics.csv), saved scores/manifests | independent flags/point/event recomputation, 5 seeds | IF/AE F1=0; residualF1=.0037735849/eventF1=.0111111111 | synthetic labels/background assumption, не verified physical faults |
| S09: Unanimous selection і нуль mixed recall | [selection](../stage7b/results/selection.json), [summary](../stage7b/results/test-summary.csv) | verifier 6 methods + C7B fallback test | validation-selected Unanimous; test mixedF1/recall=0 | level_shift eventF1=.01481481, тому не «нуль всюди» |
| S10: metrics matching не доводить causality | `anomaly/evaluate.py`, [diagnostics](../energy-anomaly/diagnostic-audit.md) | event-overlap/sole residual hit saved data; diagnostic tests C7C | one-to-one overlap; residual14:00 new crossing cleanFalse/modifiedTrue | pre-existing episode може match; post-hoc analysis не новий blind experiment |
| T01: 300→600→900 streaming records | [C7C job](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40420232238/job/121912551892), `integration/showcase.py` | saved SHOWCASE_VERIFIED у CI snapshot | двічі300/600/900; duplicates/rejected0, checkpoint300 | це рядки з warm-up/null; перші300 у training period |
| T02: реальні live DOM updates | той самий C7C job, `dashboard/e2e/showcase.spec.ts` | partial counts14/11, automatic selection, no reloads | нові записи з'являлись у браузері; errors[] | finite visible window, polling≈2s, не кожен стан гарантовано видимий |
| T03: idempotent DB checkpoint | `integration/processor.py`, `storage/postgres/repository.py` | C7C recovery job; duplicate/conflict/rollback tests | event+offset redelivery без перезапису моделей/історії | лише узгоджений run/group/topic; не глобальний exactly-once |
| T04: recovery без silent skip | `integration/checkpoints.py`, `energy_worker.py`, `Runtime.restore` | C7C crash-before/after, journal mismatch, retention, stale processor, open episode tests | Kafka commit після DB; pending generated_at/forecasts збережено | немає HA/DB corruption recovery; несумісність зупиняє worker |
| T05: combined offline/streaming parity | C7C COMBINED_VERIFIED; `integration/combined_verify.py` | clean300 + injected644, duplicate delivery, restart | combined300/644; broker/DB301/645 при навмисному duplicate; immutable forecasts | injected3events matched0; фонова1episode не успішне detection |
| T06: API read-only contracts | `api/main.py`, `query.py`, [schemas](../../api/schemas.py) | C7C SQL job23 tests; filtering/cursor/null/time/aggregation/security | actualSQL, UTC/naive, target alignment, Wh sums, 503 redaction | локальний API; no auth; worker_status unknown |
| T07: Insights | `dashboard/src/insights.ts`, `combined.ts`, [Stage7A.1 proof](../stage7a1/verification.json) | C7C unit/browser; saved Showcase strings | детерміноване описове порівняння фактів/прогнозу/coverage | не LLM, не causal diagnosis, не окремо валідований fault classifier |
| T08: notification atomicity / dedup | `notifications/outbox.py`, migration0003 | C7C `test_email_postgres`8, rollback/new episode/duplicates | один initial outbox за kind/episode/recipient; suppression persisted | один exact scope/recipient; disabled default; no historical backfill |
| T09: retry/claim recovery | `notifications/notifier.py`, `test_email.py` | mocked SMTP + real PostgreSQL claims; ambiguous acceptance crash | SKIP LOCKED/token/lease, bounded attempts, permanent stop | SMTP duplicates можливі; auth4xx category limitation; no inbox guarantee |
| T10: Mailpit delivery | [verification](../stage7c/verification.json), [HTML screenshot](../stage7c/mailpit-preview.png) | saved synthetic creation+fresh notifier twice; real ML replay300 | synthetic1outbox/1sent; real6episodes→3sent+3cooldown | local SMTP, не external provider; synthetic event не оцінка ML |
| P01: bounded pilot latency | read-only archive Stage6 raw, pilot-latencies.csv | verifier producer send_mono→worker DB ack, 3 v7 runs | p50 slow61.041/demo57.409/max1481.779ms | 60 measured/run, один repeat, old source version |
| P02: replay speed та queue/drain | Stage6 throughput.csv/raw integrity | saved publication, commit, completion rates; offset correlation | max384.866publication/s vs18.228commit/s; final backlog0 | не max sustainable capacity; continuous peak lag не оцінено |
| P03: recovery timing | Stage6 raw recovery run.json/before-restart | saved one trial | restore1.991s/startup6.330s/restart→new observed commit8.015s | 0 open episode у цьому пілоті; не п'ять repeats |
| P04: performance campaign incomplete | Stage6 closure-status.json/evidence-index.json | inventory/hashes291archives; no new campaign | 0/15 completeprimary, 1 interrupted; API-load0/20 | primary interruption user-requested, не доведена системна відмова |
| O01: local-only boundaries | Compose files, API entrypoint/middleware, nginx | source review + C7C local/CORS SQL tests | Web loopback; DB/Kafka private; MailpitSMTP internal | не penetration test або production security certification |
| O02: local deployment freshness gap | [operational snapshot](operational-snapshot.json), `showcase.py` | read-only image code hash inspection | default backend застарілий, немає0003/notifier | до Stage8B потрібен explicit rebuild, не auto retrain |

## Доступність і довіра до доказів

Stage 2 Docker artifacts і Stage 6 archive мають абсолютні локальні paths у
verified-values. Original Stage3/4 weights також hash-verified у старій копії,
яка під час аудиту не виконувалась і не редагувалась. Ці файли не додаються до Git.
Clone підтверджує checked-in results/CI, але не замінює збереження зовнішнього
архіву. Stage6 archive — `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/docs/stage6/`.

Hashes підтверджують цілісність збережених файлів відносно manifest, а не
істинність усіх можливих наукових тверджень. Успішний CI — доказ виконання
конкретних тестів/fixtures, не універсальний доказ відсутності дефектів чи leakage.
Відсутність нового replay у Stage8A не дає підстав позначати поточні local images
готовими; source/CI readiness і deployment readiness розділені.
