# Stage 8A — Фінальна валідація системи та аудит наукових результатів

**Дата:** 27.10.2026. **База:** `c156668a1bc41e20eb7c3c175eb5da1afd9037d7`.
Гілка `feature/final-system-validation`, основна копія
`/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main`.

## Executive summary

Підтверджено інтеграційно працездатний локальний дослідницький MVP, не
production fault-monitoring систему. Підстави — актуальний успішний CI, його
saved live proofs, збережені прогнозні/anomaly результати, raw pilot telemetry,
контрольні суми й read-only перевірки. Runtime код не змінено, моделі не навчались,
synthetic scenarios не генерувались, replay/SMTP/performance campaign не запускались.

- Базовий [PR8 CI](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40420232238)
  має 6/6 success; його tested head7e8b7d7 і merge c156668 мають однаковий Git tree.
  Логи: 85 unit, 13 MVP PostgreSQL/Kafka/recovery, 23 API SQL tests, інші jobs
  підтверджують Kafka smoke і frontend/TypeScript/build/browser.
- Stage2 HGB20 програє Persistence за MAE, виграє RMSE. Stage3 validation winner
  залишається RF21; HGB21 має кращий descriptive test, без reselection.
- IF/AE/Unanimous mixed F1=0; residual виявляє дуже мало контрольованих подій.
  Немає підстав оголошувати operational anomaly detection успішним.
- Stage6 — завершені обмежені пілоти; повна15-run кампанія перервана користувачем.
  Вони не вимірюють поточну Stage7C версію й не встановлюють SLA.
- Kafka→DB correctness/recovery, API/Dashboard і локальний Email механізм
  підтверджені конкретними integration evidence. Combined/outbox облік окремий.
- **Локальні default Docker images застарілі. As-is середовище не готове до
  повної фінальної демонстрації останньої версії.** Потрібен погоджений preflight
  rebuild images + migrations upgrade, зі збереженням trusted artifacts і volumes.
  У межах Stage8A це не виконувалося.

Виявлено **0 Blocker, 7 Major, 3 Minor, 3 Documentation, 3 Future Work (16)**.
[Findings з діями](findings.md). Source-level blocker у межах перевірених доказів
не знайдено; це не гарантія відсутності невідомих помилок.

## Матеріали аудиту

1. [Архітектура й Mermaid diagrams](architecture.md).
2. [Наукова готовність, точні таблиці й Stage6](scientific-readiness.md).
3. [Traceability matrix](traceability-matrix.md).
4. [Класифіковані findings](findings.md).
5. [План Stage8B — без реалізації](stage8b-demo-plan.md).
6. [Verified values / input SHA](verified-values.json), [CI snapshot](ci-evidence.json),
   [локальні artifacts/images](operational-snapshot.json), [read-only verifier](verify_evidence.py).

## 1. Що перевірено без повторення експериментів

- Прочитано producer/schema/features, training selection, Runtime/Processor,
  repository/checkpoints, episodes/combined, Alembic, API/query, Dashboard/Insights,
  notifications і Compose. [Архітектура](architecture.md) відповідає цьому коду.
- Saved Stage3 forecasts повторно зведено до MAE/RMSE й peak metrics, звірено
  split membership, origin/target600s та exact target-minus-day Seasonal Naive.
- Saved local HGB20 test Parquet перераховано, зіставлено з первинним Stage2 report.
- Saved mixed-test Parquet/manifests незалежно зведено до point/event metrics
  трьох detectors і трьох правил; жодного inference/recalibration.
- Перевірено 407 original Stage4 file checksums, original 4 Stage3 weights і
  Stage4 bundle у архівній копії; локальний Docker manifest/artifacts hashes.
- Stage6: 291 compressed+uncompressed archive checksums; producer/worker/DB
  event-ID/offset correlation; всі 3 pilot send→DB quantiles перераховано з raw.
  Completed/overhead/commissioning/interrupted evidence не pooled.
- CI прочитано через GitHub; saved live300→600→900, duplicate/restart parity,
  initial/final model generation timestamps та Email mocked tests простежуються.
- Коротка read-only inspection наявних images та trusted artifact metadata
  в одноразових network=none/read-only контейнерах, без DB/services/inference.
- Поточні tracked text files до2MB перевірено на вибрані private-key/GitHub/AWS
  patterns: 0 matches; tracked env — тільки `.env.example`. Це не повний secret
  scanner усієї Git history і не формальний security audit.

Verifier читає стару копію тільки як файловий архів. Не запускає там Python,
Git, training чи process controllers; не створює cache. Всі його explicit input
hashes наприкінці збігаються. Артефакти великого розміру не дублювались у docs.
PyArrow видав sandbox warnings щодо CPU sysctl inspection; читання Parquet та
арифметичні asserts завершились exit0; це не warning про цілісність даних.

## 2. Матриця функціональної повноти

«Підтверджено» нижче означає конкретне CI/saved evidence для source-бази,
не новий запуск кожної функції у нинішніх застарілих images.

| № / функція | Модулі | Наявний тест / доказ | Обмеження | Статус |
|---|---|---|---|---|
| 1 Отримання вимірювання | producer.energy_producer, appliances_dataset | C7C live replay300, stable event IDs | historical dataset, не live meter | Підтверджено CI |
| 2 Валідація | energy_schema, energy-message-v1.schema | unit invalid/time/unit/source; MVP quarantine/conflict tests | current models тільки bound source/600s | Підтверджено CI |
| 3 Kafka processing | energy_worker, processor | C7C broker/MVP integration і live browser | одна partition, один active owner/group | Підтверджено CI |
| 4 Forecast | runtime, energy_processor, energy_forecaster | saved300→600rows; null/target alignment; metric recomputation | HGB20 primary, warm-up; quality Stage2 окремо | Підтверджено функцію |
| 5 Anomaly scores | anomaly.features/residual/detectors | saved900original scores, offline/stream parity | experimental, низький recall | Підтверджено обчислення, не fault accuracy |
| 6 Combined | anomaly.combined, postgres.combined | C7C clean300 / controlled644 parity, fallback test C7B | mixed detection0; cold coverage144unready | Підтверджено правило, обмежена якість |
| 7 Episodes | Repository.update_episode, persist_combined | open/closed/gap/restart tests; saved event counts | threshold episode ≠ physical incident; EOF open possible | Підтверджено CI |
| 8 PostgreSQL | schema, repository, migrations0001–0003 | actualSQL migration roundtrip, atomic rollback, ledger checks | спільна DB залежність; backup/HA поза MVP | Підтверджено CI |
| 9 API | api.main/query/schemas | C7C23SQL tests: cursor/filter/null/time/Wh/security | read-only/local-only, worker liveness unknown | Підтверджено CI |
| 10 Dashboard | App/useMonitor/data, Recharts | liveDOM14/11intermediate, no reloads/errors, viewport tests | вікно144, polling, новий локальний build потрібен | Підтверджено CI; local preflight |
| 11 Insights | insights.ts, combined.ts | C7C strings + unit, Stage7A.1 evidence | описові правила, не causal explanation | Підтверджено CI |
| 12 Email generation | outbox hooks, migration0003 | C7C8EmailSQL tests, synthetic1outbox, actual6episodes | disabled default, exact scope, no backfill | Підтверджено CI/local saved proof |
| 13 Mailpit delivery | notifier/message, email overlay | saved1synthetic HTML+text /1sent, real3sent; screenshot | локальний SMTP, не external inbox guarantee | Підтверджено saved local proof |
| 14 Redelivery | processor.existing_event/receipt | coordinate+event duplicates, conflict, immutable forecasts | idempotence scoped run/source; email ambiguous SMTP window | Підтверджено CI |
| 15 Restart/recovery | reconcile, Runtime.restore, DB episodes, notifier claims | before/after DB crashes, openepisodes, combined parity, expired/stale claim | припинення при missing retention/corruption; no HA | Підтверджено CI |

Ключі C7C/C7B/C6, точні файли й tests наведені в
[traceability-matrix.md](traceability-matrix.md), а не лише посилання на існування коду.

## 3. Час, одиниці та інтерпретація

Measurement event time2016 не є processing clock. Forecast origin і target
відрізняються на600s; generated_at — реальний час формування. DB received_at,
SMTP attempt та sent_at — інші моменти, не підміни одного одним. Naive API labels
не проходять через browser timezone conversion. Aggregation sums Wh для
інтервалів; немає автоматичного перетворення цих чисел у W.

600forecast /900score rows включають nullable warm-up/incompatible стани;
combined decisions і notifications не входять у ці лічильники.
Статистичний score, synthetic label, combined agreement і фізична несправність —
чотири різні поняття. Original UCI background alarms не confirmed false positives.

## 4. Security / operational висновки

- Local-only API/nginx, loopback Web ports, private DB/Kafka в основному Compose;
  Mailpit SMTP не має host port. Notifier egress потрібний лише явно дозволеному SMTP.
- SMTP credentials не повертаються API/звичайним логом; opt-in, TLS, exact scope;
  tests mocked. `sent` — SMTP acceptance, можливий повтор у crash window.
- `.env.*`/datasets/artifacts ignored; read-only model mounts, checksum/version gates.
  Trusted pickle — вимога довіри до джерела, SHA сам по собі її не створює.
- Немає production authentication, hardened multi-tenant deployment, HA/SLA,
  queue admin, disaster recovery certification. Локальний MVP не публікувати
  віддалено без окремого review й додаткових заходів.
- Деструктивні migrations/reset/clean/volume removal не виконувались. Існуючі
  downgrade/drop-schema calls у tests належать їх disposable schemas, не runbook
  для користувацької PostgreSQL. Stage8A їх не запускав.

## 5. Готовність до фінальної демонстрації

**Підтверджена інтеграційна база — так; негайний local запуск поточних images — ні.**
M05 вимагає перед demo явно перебудувати images із погодженого checkout та
застосувати additive migrations. Existing trusted artifacts мають валідні hashes;
їх не потрібно перенавчати. Runtime fix для нового ML не потрібний. Далі —
тільки погоджений [Stage8B plan](stage8b-demo-plan.md), з existing300-record Showcase,
чіткими units/time, чесним negative anomaly result та окремою Email delivery fixture.

Stage8A не починає Stage8B, не запускає нових services/replay і не пише магістерську.
PR цього аудиту містить тільки `docs/stage8a/`; merge потребує погодження.
Фінальний docs-only commit має `[skip ci]`: нові push/pull_request прогони
навмисно не ініціюються, workflow не змінено. Це не новий «зелений CI гілки»;
використано перевірений C7C базового коду та локальні read-only audit asserts,
syntax/hash/JSON/link/fence checks. Якщо repository вимагає нові required checks,
вони можуть залишатись pending: перед merge потрібне окреме погоджене рішення,
не bypass. [Механіка skip у GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).
