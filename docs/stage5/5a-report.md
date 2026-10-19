# Stage 5A — короткий звіт

PR#3 Stage4 із фінальним аудитом злито merge-комітом `ac5a04d` після успішного
CI. Робота5A виконана в `feature/energy-monitoring-mvp` від оновленого main.
**FastAPI, Dashboard і підетапи5B/5C не реалізовувалися. Злиття5A не виконано.**

## Реалізовано

- PostgreSQL schema та незалежна початкова Alembic migration0001_mvp:
  runs, sources, model registry, measurements, forecasts, scores, experimental
  episodes, raw-delivery receipts, quarantine errors і consumer checkpoints.
- SQLAlchemy repository з атомарним збереженням усіх наслідків повідомлення
  разом із DB next_offset; explicit Kafka commit виконується лише після DB commit.
- Ledger та унікальні ключі run/source/event усувають повторні доменні записи;
  duplicate перевіряється до ML history, conflicting payload quarantine.
- Startup reconciliation Kafka/DB/log bounds/cluster, retained-log fingerprints,
  checkpoint digest; manual partition assignment без automatic offset reset.
- Recovery144 raw measurements/source, перевірка hash і повторюваності прогнозу,
  відновлення original pending value/generated_at та відкритих DB episodes.
- Advisory ownership lock, checkpoint row lock та memory-position fence проти
  застарілого worker; після rollback/невизначеного стану processor непридатний
  до продовження без recovery.
- Окремі registry roles: HGB20 primary та RF21 residual_reference, явні versions
  і purpose. IF/AE/residual/episodes мають maturity=experimental.
- Naive UCI time, nullable UTC і окремі real generated/received timestamps.
- Відтворюваний private setup, hash-verified local manifest, register existing
  artifacts або prepare з frozen training/calibration configs у новому ignored
  каталозі. Prepare фактично виконано на повному dataset; original models не змінено.
- Isolated localhost-only Docker PostgreSQL/Kafka infrastructure з persistent
  volumes. Legacy compose змінено лише для прив'язки9092/8080 до localhost.
- Новий окремий CI job для реальних PostgreSQL/Kafka recovery tests.

Команди setup/replay/status/recovery: [runbook](5a-runbook.md).

## Перевірки

Повний локальний suite: **67 passed** —52 unit,3 legacy Kafka,12 нових
PostgreSQL/Kafka integration tests. Пропущені tests не зараховуються як pass.

Критичний тест запускає окремі процеси й завершує їх через `os._exit`, без
finally: до DB commit транзакція не лишає measurement; після150-го DB commit
DB next_offset=150, Kafka commit=149. Наступний worker перевіряє150 ledger
records, відновлює RF history і завершує170 records без дублів. Окремо
перевірено незмінність old forecasts/generated_at, продовження тих самих
відкритих episodes, recovery до завершення warmup, конфлікти event_id,
несумісні sources/model context, migration upgrade/downgrade та stale-worker fence.

Перевірки відмови: Kafka offset попереду DB, checkpoint поза log, втрачений
DB checkpoint, змінений early Kafka prefix після topic recreation (навіть при
тому самому останньому anchor), зіпсований checkpoint digest або history hash.
Worker зупиняється, не перескакує через неузгоджені записи.

## Реальний прогін із повними локальними моделями

[Machine-readable report](5a-verification.json) містить точний implementation
commit, hashes integration source, model/feature/threshold versions, run/topic,
DB version і dataset checksum. Використано artifacts, заново підготовлені з
оригінального UCI CSV за fixed configs — не tiny test-моделі.

| Показник | Результат |
|---|---:|
| Унікальні вимірювання | 300 |
| Повторні доставки | 2 |
| Delivery receipts | 302 |
| Прогнози, HGB+RF разом | 600 |
| Anomaly score rows, включно з warmup | 900 |
| Ready IF / AE / residual scores | 294 / 294 / 156 |
| DB next_offset / Kafka committed | 302 / 302 |
| Відновлені/звірені retained records при restart | 150 |

Worker зупинено після150 вимірювань і відновлено з DB. Усі раніше збережені
forecasts/generated_at лишилися побітово незмінними на рівні прочитаних DB
значень. Усі значення/status/flags зіставлено з offline inference за тим самим
потоком і trusted artifacts. Для floating scores tolerance1e-5/1e-6, forecast
values1e-12; flags/status збігаються точно. UCI timestamps лишилися naive, UTC
measurement поле null. Збережений experimental episode не є підтвердженою
несправністю. Це функціональний integration test, не новий accuracy experiment.

## Збереження і межі

[Preservation evidence](5a-preservation.json) підтверджує407 hashes Stage4,
незмінність його original bundle і захищених старих source/results paths.
Локальні credentials/.env/model artifacts не додані до Git. Stage2/3/4 metrics,
thresholds, scenarios, protocols та artifacts не перезаписувалися.

Підтримується один worker/partition0. Startup retained-log verification лінійний
за розміром доступного processed log; для масштабування потрібне окреме рішення.
Гарантія — at-least-once + ідемпотентний DB sink, не end-to-end exactly-once.
Тести покривають визначені crash windows; не заявляють вичерпну перевірку всіх
можливих мережевих і апаратних відмов. Локальна безпека — loopback defaults,
private generated credentials і trusted local artifacts; зовнішнє розгортання
не входить у5A. Anomaly quality залишається обмеженою висновками Stage4.

**Наступний крок після перевірки5A — погоджений read-only FastAPI підетап5B.**
