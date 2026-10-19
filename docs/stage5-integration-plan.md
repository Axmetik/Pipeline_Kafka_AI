# Stage 5 — інтеграція Energy Monitoring MVP: план для погодження

Статус: **лише технічний план**. Нові сервіси, таблиці, API та UI ще не
реалізуються. Початок — після погодження архітектури, в окремій
`feature/energy-monitoring-mvp` від main із погодженим Stage4.

## 1. Мінімальний результат

Однією командою підняти Kafka, PostgreSQL, worker, FastAPI і Dashboard;
окремою командою відтворити датасет із явно заданою швидкістю та лімітом.
У браузері бачити фактичні Wh/10хв, прогнози на наступний інтервал,
anomaly scores/пороги/status кожного методу й історію експериментальних подій.
Показувати progress: received/processed/persisted/rejected, останній Kafka
offset, lag, останній час прийому й причину warmup/incompatible/error.
Порожній екран має пояснювати «очікуємо producer», «прогрів» або «немає
даних у вибраному діапазоні», а не залишати користувача здогадуватися.

Це локальний MVP для одного відомого source/building і 600-секундного інтервалу;
ідентифікатори в схемі залишають можливість додати інші будівлі. Оновлення
екрана раз на2с; WebSocket, TimescaleDB, оповіщення про несправності та зовнішня
публікація не входять у першу реалізацію.

## 2. Архітектура і повторне використання

`Energy Kafka topic → окремий MVP worker (forecast + anomaly scoring) → PostgreSQL → FastAPI → Dashboard`.

Новий worker використовує існуючі EnergyProcessor, EnergyForecaster і
StreamDetector через адаптери. Він має власну consumer group і не переписує
чинні consumer.energy_consumer / consumer.energy_anomaly_consumer. Legacy
IoT/Energy/Parquet сценарії залишаються доступними. У профілі MVP PostgreSQL
є джерелом даних для API; API не читає випадкові поточні Parquet-батчі і не
виконує повторний inference. Збережені Stage2/3/4 експерименти не мігруємо,
не перераховуємо й не перезаписуємо.

Пропонований стек: звичайний PostgreSQL18, SQLAlchemy2 + psycopg + Alembic,
FastAPI, React + TypeScript + Vite + Recharts. Версії залежностей та image digest
фіксуємо на початку погодженої реалізації. TimescaleDB можна оцінити після
отримання вимірювань реального обсягу; для поточного датасету він не потрібен.

MVP worker — один процес, послідовна обробка partition, одна partition у
початковому demo topic. Producer вже ключує записи за building/source.
Артефакти завантажуються один раз; fit/calibration у worker/API відсутні.
Доступні локальні trusted artifacts монтуються read-only; їхня наявність,
checksums і source/feature contracts перевіряються перед готовністю scoring.

## 3. Які прогнози та оцінки показуємо

- Основна лінія прогнозу зберігає чинний source-bound **HGB Stage2,20 ознак**.
- RF Stage3 залишається вибраним forecasting-кандидатом за validation; це
  рішення не дорівнює вже виконаній заміні чинного HGB.
- **Окремий RF Stage4,21 ознака**, refit train-only, обслуговує experimental
  residual detector. Його прогноз зберігаємо як `purpose=residual_reference`,
  а не підміняємо ним основну HGB-лінію. За потреби UI показує його окремо.
- IF, AE та residual мають `maturity=experimental`; score не є ймовірністю
  несправності. IF/AE/RF feature versions не змішуємо.
- На кожному повідомленні спочатку оцінюємо residual проти прогнозу з попереднього
  інтервалу, потім формуємо прогноз наступного. Зберігаємо origin, target,
  generated_at, actual timestamp, detector/model/threshold versions.
- Warmup, gaps і incompatible source — явні стани з null score/forecast.
  Null не перетворюємо на0, false або «нормально». Первинні показання можна
  зберігати з `scoring_status=incompatible`, без автоматичного навчання чи
  застосування моделі до нового довільного джерела.

## 4. Дані PostgreSQL

Запропоновані таблиці й ключі:

| Таблиця | Призначення / ключ |
|---|---|
| sources | building/source, source_type, semantics, interval, timezone policy |
| ingestion_runs | run_id, replay/live, dataset hash, config hash, start/stop/status |
| model_registry | artifact hash/version, purpose, ordered features, allowed sources, maturity |
| measurements | `(run_id,building_id,source_id,event_id)`; energy Wh, environment, raw JSON, times |
| forecasts | `(run_id,source,origin_event_id,model_version,purpose)`; origin/target/value/status |
| anomaly_scores | `(run_id,source,event_id,detector_version,threshold_version)`; score/threshold/flag/status |
| score_events | contiguous experimental exceedance episodes; stable identity/start/end/count/status |
| ingestion_errors | raw payload, Kafka coordinates, validation/scoring error; quarantine |
| consumer_checkpoints | `(group,topic,partition)` → next offset, run/model context; committed with data |

Показання з одним event_id і різним payload не перезаписуємо мовчки:
фіксуємо конфлікт у quarantine. Повторне доставлення з однаковим payload
ідемпотентне. `run_id` розділяє незалежні replay; restart того самого запуску
має використовувати той самий run_id. Унікальні обмеження + ON CONFLICT
підтримують повторне доставлення, але не замінюють коректне відновлення стану.

Індекси: `(run_id,source,measurement_time)`, forecast target/model, detector/time,
event start/status. Вибірки обмежені за діапазоном/кількістю; UI для довгого
періоду запитує агрегацію, а не всі сирі точки. Для енергії в бакеті показуємо
суму Wh, для температури — середнє; forecast/actual порівнюємо лише за однаковим
цільовим інтервалом. Незавершені бакети позначаємо.

### Часова семантика

Історичні UCI naive timestamps не записуємо як вигаданий UTC. Зберігаємо
оригінальний рядок, `measurement_time_local TIMESTAMP WITHOUT TIME ZONE`,
`measurement_time_utc TIMESTAMPTZ NULL`, time_basis/timezone і timestamp_reference.
Для UCI UTC-поле залишається null. Час прийому/генерації/запису — окремий UTC.
Майбутні smart meter UTC timestamps підтримуємо через явний контракт.
API фільтрує за вказаним time_basis; UI для UCI підписує «час датасету,
часовий пояс не визначено» і не конвертує його через часовий пояс браузера.
Вікно Dashboard за замовчуванням відноситься до останнього measurement time,
а не до поточної календарної дати: інакше replay2016 буде невидимим.

## 5. Доставка, restart і стан

MVP worker використовує `enable_auto_commit=False`.
Одна DB-транзакція зберігає measurement, forecast(s), score(s), зміни episode
і next_offset checkpoint. Kafka offset підтверджується **після успішного commit DB**.
За помилки DB offset не просувається. Обробка в partition послідовна; не
комітимо позицію поверх невирішеної помилки попереднього повідомлення.
Невалідне повідомлення можна quarantine+checkpoint в одній транзакції.

Критичні crash cases:

1. До DB commit — транзакція відкотиться, Kafka повторить повідомлення.
2. Після DB commit, до Kafka commit — DB checkpoint відсікає дубль **до зміни
   in-memory history**; ключі не дають створити повторні доменні записи.
3. DB rollback після оновлення in-memory history — worker зупиняється і
   відновлює стан із committed history; не продовжує з неузгодженим буфером.

На startup/reassignment worker звіряє DB checkpoint, consumer offsets і retention,
відновлює active score episodes та останні144 committed вимірювання кожного source
і причинно відтворює їх у тому самому артефактному контексті. Це відновлює
pending RF forecast; основному HGB достатньо коротшого контексту. Уже збережений
у DB pending forecast разом з original generated_at лишається авторитетним; replay
перевіряє його значення, але не підміняє історичний час генерації новим. За недостатньої
історії — warmup, а не прихований fallback. Відновлення не створює повторних
публічних forecasts/events; run/model versions залишаються фіксованими.

DB checkpoint — авторитетна оброблена позиція для MVP group. Retention gap,
зміна артефактів посеред run і конкурентне володіння partition мають давати
явну помилку/новий run, а не тихе пропускання даних. На MVP обмежуємо worker
одним instance; перевірки reassignment потрібні навіть для цього режиму.
Це at-least-once Kafka delivery з ідемпотентними DB-записами; гарантію
end-to-end exactly-once між Kafka/DB/Parquet не заявляємо.

Існуючі Parquet archives залишаються в legacy сценаріях. Новий DB worker не
робить обов'язковий одночасний запис DB+Parquet: це повернуло б проблему
неатомарного dual write. Подальший DB→Parquet export — окрема мала задача.

## 6. Події та позначення experimental

Подія MVP — епізод перевищення порога, а не встановлена несправність.
Identity включає run/source/detector/threshold version. Послідовні flagged
measurement intervals подовжують епізод; unflagged закриває; gap/unknown
закриває попередній епізод з відповідним status, не заповнює прогалину.
Active episode зберігається у DB і відновлюється після restart.

Ground-truth injection events Stage4 не є operational score_events. Поточне
правило offline overlap matching не переносимо в UI як доказ несправності.
За бажанням пізніше можна додати ручний review-label, але не генеруємо
«підтверджено» з самого model flag. На екрані: **Experimental score exceedance**,
коротке пояснення низької перевіреної якості та посилання на Stage4 звіт/аудит.
Немає автоматичних зовнішніх повідомлень у цьому MVP.

## 7. FastAPI і Dashboard

API пропоную read-only для доменних даних; worker працює окремим сервісом,
не в FastAPI background task, щоб API reload не дублював Kafka consumers.
Lifespan керує лише DB pool; readiness відображає доступність DB, worker
heartbeat/checkpoints і наявність даних, не вимагає «нормальних» scores.

Endpoints: `/health/live`, `/health/ready`, `/api/runs`, `/api/sources`,
`/api/measurements`, `/api/forecasts`, `/api/anomaly-scores`, `/api/events`,
`/api/pipeline-status`, `/api/models`. Фільтри run/building/source/time_basis/
from/to/model/detector/status; cursor pagination, limits, стабільне сортування,
response schemas з nullable status, units, model maturity. SQL параметризований;
індекси й bounds на вибірки перевіряємо інтеграційно.

Dashboard: вибір run/source/time range; графік фактичного Wh та прогнозів,
суміщених за target time; три окремі score panels зі своїми порогами; список
experimental episodes; detail панель із actual/forecast/origin/target/versions;
прогрес producer/worker/DB, warmup та data-quality errors. Не малюємо IF/AE і
Wh на одній спільній шкалі; normalized score/threshold, якщо використовується,
чітко підписаний і не називається probability. Polling2с із retry/backoff та
видимим станом зв'язку. Контроль replay лишається CLI-командою з README;
кнопки довільного retrain/injection не входять у перший UI.

## 8. Файли майбутньої реалізації

- `integration/energy_worker.py`, `integration/runtime.py`, `integration/checkpoints.py`;
- `storage/postgres/{models,repository,session}.py`, `migrations/` (Alembic);
- `api/{main,schemas,dependencies}.py`, `api/routes/{series,events,status,models}.py`;
- `dashboard/` (React/TypeScript app, chart and event components);
- `docker/docker-compose.mvp.yml`, worker/API/UI Dockerfiles, `.env.example`;
- `scripts/mvp_replay.py` або wrapper на чинний producer із єдиним topic/run config;
- `tests/test_mvp_*`, DB/Kafka integration tests, browser E2E;
- `docs/stage5/{architecture,runbook}.md`, README з одним узгодженим запуском.

Наявні `processing/`, forecasting/anomaly training та legacy consumers зберігаємо;
якщо адаптеру потрібен суттєвий refactor, це окремо пояснюємо до зміни архітектури.

## 9. Порядок і критерії прийняття

1. Схема DB, міграції, індекси та ідемпотентний repository.
2. Worker: причинний inference → транзакція DB → offset, restart/replay тести.
3. Read API зі статусами, time contracts і bounded queries.
4. Dashboard із actual/forecast/experimental scores/events.
5. Docker profile, scripted replay, наскрізний smoke/E2E та README.

Приймання: replay300+ вимірювань відображається в браузері; primary forecasting
починається після короткого прогріву, residual — після144 predecessors;
forecast origin/target не переплутані; event list відтворюється після перезавантаження
UI; два crash cases до/після DB commit не гублять committed records і не створюють
дублів; replay/restart із тією самою history/model версією зберігає причинні scores;
пізні/невалідні повідомлення видимі як quality status. Empty/offline UI стани
перевірено браузерним тестом. Усі старі unit/Kafka tests мають пройти; нові
PostgreSQL та API/browser перевірки додаються в CI окремими jobs.

## Технічні джерела

- PostgreSQL INSERT/ON CONFLICT: https://www.postgresql.org/docs/current/sql-insert.html
- Kafka consumer offset settings: https://kafka.apache.org/39/configuration/consumer-configs/
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/

Ці джерела підтверджують можливості компонентів; наведена інтеграційна
архітектура — наша пропозиція для погодження, а не вже реалізована функція.
