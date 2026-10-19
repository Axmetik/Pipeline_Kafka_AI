# Stage 5B — read-only FastAPI

## Результат і межі

Реалізовано окремий локальний HTTP-сервіс поверх PostgreSQL. Він не читає
Parquet, не підключається до Kafka, не завантажує ML-артефакти, не навчає моделі
і не виконує inference. Worker, checkpoint/recovery, схема Alembic `0001_mvp`,
Stage 2/3/4 та IoT не змінені. Stage 5C не реалізовано.

Немає heartbeat: `worker_status=unknown`. Наявність checkpoint, свіжих записів
чи успішна готовність API не є доказом активності worker. Нової міграції немає.

## Відтворюваний запуск

З чистого clone: підготувати `.venv`, встановити залежності, виконати setup,
запустити PostgreSQL і міграції за [5A runbook](5a-runbook.md). API можна
запустити навіть без моделей і Kafka; із порожньою базою він повертає порожні
списки. Для наповнення потрібен окремий перевірений worker/replay за 5A runbook.
API не створює таблиці автоматично.

```bash
source .venv/bin/activate
python -m pip install -r requirements-mvp.txt -r requirements-api.txt -c requirements.txt
python -m api  # 127.0.0.1:8000, proxy headers disabled
```

Відкрити http://127.0.0.1:8000/docs. Конфігурація DB береться з приватного
`.env.mvp` або `MVP_DATABASE_URL`; не вставляти URL із паролем у Git чи звіти.
Версії FastAPI/Pydantic/Starlette/Uvicorn/HTTPX зафіксовані в
`requirements-api.txt`; ML-залежності залишені без змін.

## Endpoint та фільтри

| GET endpoint | Призначення / застосовні фільтри |
|---|---|
| `/health/live` | Процес API відповідає, без запиту DB |
| `/health/ready` | PostgreSQL відповідає, поточна схема `0001_mvp` доступна |
| `/api/runs` | Запуски; `run_id` |
| `/api/sources` | Джерела; `run_id`, `building_id`, `source_id` |
| `/api/measurements` | Фактичні інтервальні Wh; run/building/source, time_basis/start/end, status |
| `/api/measurements/aggregate` | Суми Wh за 60 або 1440 хвилин, ті самі фільтри + `bucket_minutes` |
| `/api/forecasts` | run/building/source, time_basis/start/end, model_id/model_version, purpose, status |
| `/api/anomaly-scores` | run/building/source, time_basis/start/end, model_id/model_version, detector, status |
| `/api/events` | run/building/source, time_basis/start/end, model_id/model_version, detector, status |
| `/api/models` | Безпечна частина registry; run_id, model_id/model_version |
| `/api/pipeline-status` | Метрики всіх запусків або `run_id`; без висновків про liveness |

Усі списки мають `items`, `next_cursor`, `order`. Default limit100, maximum1000;
невалідні ліміти, timestamps, cursor, невідомі параметри та незастосовні
предметні фільтри повертають422. `start` включно, `end` виключно. Довільний
status не допускається. Списки metadata мають ascending порядок, часові ряди
та агрегати — descending. Порядок визначає timestamp та унікальний ID;
агрегати додатково розділені за run/building/source. Cursor прив'язаний до
endpoint, фільтрів і часової семантики; при переході його треба передавати
разом із тими самими фільтрами. Розмір сторінки можна змінити.

Часовий фільтр прогнозів стосується **target**, а не origin. Для scores —
часу фактичного вимірювання; для events — **початку** епізоду (це не запит
усіх епізодів, що перетинають діапазон). Для runs/sources/models часові
фільтри не застосовуються. `time_basis` стосується часових рядів.
Models із run_id показують моделі, які вже використано в записаних forecast/score.

За замовчуванням немає фільтра календарної дати: перша сторінка часових рядів
показує останні наявні історичні дані. Для неперемішування replay обирайте run_id.
Для незмінного експорту треба зупинити replay; keyset pagination не є snapshot
усієї DB між HTTP-запитами. Нові записи попереду cursor не дублюють уже прочитані.

## Час, Wh та null

`time_basis=dataset_naive` за замовчуванням: UCI labels без timezone, наприклад
`2016-01-13T18:50:00`, `timezone=null`, `timestamp_reference=dataset_label`.
Не додавати `Z`, не передавати їх через браузерний `Date` для локальної
конвертації. Це labels датасету, а не обґрунтовані UTC-моменти.

Для smart meter із явним offset: `time_basis=offset_aware`, start/end повинні
містити offset або `Z`; SQL порівнює абсолютні UTC-моменти. Початковий offset
у measurement/origin/target strings збережено. Системні `received_at`,
`generated_at`, `scored_at`, `last_processed_at` є aware UTC. Час генерації
прогнозу не підміняє час вимірювання/target та не перераховується при читанні.

`energy_wh` — інтервальна енергія Wh за `interval_seconds` (Appliances:600).
`predicted_energy_wh` — прогноз енергії наступного600-секундного інтервалу;
це не миттєва потужність W. HGB20 має `purpose=primary_forecast`, окремий RF21
для residual — `purpose=residual_reference`; API не підміняє моделі.

Агрегація використовує SQL `date_bin`, збирає **вимірювання**, не прогнози,
і не змішує run/building/source чи time_basis. Для naive — годинні/денні bins
за labels; для aware — bins UTC. `bucket_reference=measurement_label`:
це групування за міткою запису, не відновлена фізична розкладка енергії всередині
години. Особливо для `dataset_label` не приписуємо їй start/end семантику.

Сума надається лише для повної групи:6 (або144) унікальних часових точок на
600-секундній сітці, правильні перша й остання мітки. Для обірваної межі replay,
пропусків або обрізаного фільтром bucket: `complete=false`, `energy_wh=null`,
збережено observed/expected counts. Інтервали з cadence, відмінним від600,
повертають422 для агрегації; для звичайного списку їхній interval_seconds явний.
Немає інтерполяції, перетворення W/Wh чи додавання прогнозу як факту.

`null` прогноз/score/flag залишається null. Стани ready/warmup/incompatible/gap
явні відповідно до ресурсу. IF/AE/residual та episodes мають
`maturity=experimental`. Score не є probability; подія
`experimental_threshold_exceedance` не є підтвердженою несправністю.

## Pipeline status і безпека

`last_processed_at` — max DB checkpoint updated_at, тобто час останньої
зафіксованої транзакції доставки, включно з дублем/карантином. Це не heartbeat.
`unique_measurements` — кількість рядків measurements у scope run.
`duplicate_deliveries` — зафіксовані receipts із outcome `message_duplicate`;
це не кількість усіх транспортних retry або повторного читання того самого offset,
яке worker пропускає без нового receipt. `rejected_messages` — інші негативні
outcomes receipts. `next_offset` — у кожному checkpoint, не поточний Kafka lag:
API не читає Kafka. checkpoint list обмежено100; count/truncated явні.
Останні10 помилок містять kind і координати, без reason/raw quarantine payload.

Кожен SQL-запит виконується у read-only транзакції з timeout5с, timezone UTC.
DB-збої/неготова схема дають503 із безпечним загальним повідомленням; live
продовжує відповідати200. Public Pydantic schemas відсікають wire_record,
payload_base64, config, DB URL, credentials, artifact paths. CORS — тільки
localhost/127.0.0.1:5173, GET, без credentials. CLI bind127.0.0.1 та middleware
відхиляє не-loopback клієнта. Не публікувати через reverse proxy/tunnel:
автентифікації для віддаленого доступу немає. Нових секретів у Git немає.

## Реальна перевірка

Локально: `OMP_NUM_THREADS=1 python tests/run_suite.py --suite all`:
**85 passed, 0 failures, 0 skips** (51.404с):56 unit,3 legacy Kafka,
12 PostgreSQL/Kafka MVP recovery,14 PostgreSQL API integration.

API-тести створюють випадкові окремі схеми в реальній PostgreSQL, застосовують
Alembic та виконують справжні SELECT. Перевірені всі списки/cursors, однакові
мітки часу, фільтри, порожні результати, warmup nulls, origin/target residual,
experimental events, UTC/+02:00/naive, Wh210 за6 інтервалів, неповні та off-grid
buckets, межі запитів, read-only SQL, CORS/local restriction, відмова DB без
витоку паролів та стабільні OpenAPI-контракти. Unit-тест підтверджує, що import
API не імпортує sklearn/torch/worker runtime. Наявні crash/recovery Kafka
перевірки також пройшли. Контрольні суми integration-коду з5A report незмінні.

HTTP smoke запущено окремим процесом Uvicorn на127.0.0.1:8102, через реальні
HTTP-запити до збереженого300-point replay Stage5A, без нового inference:

```bash
python -m api --port 8102
# в іншому терміналі
python -m api.smoke --base-url http://127.0.0.1:8102 \
  --run-id verification-a704b374790941059eaf0a1d786e3231 \
  --output docs/stage5/5b-smoke.json
```

Отримано **300 measurements,600 forecasts,900 score rows,1 experimental event**.
Перевірено всі3 detectors, forecast origin/target +600с, residual target alignment,
nulls, metadata endpoints та незмінність pipeline status до/після читання.
Числа не є новими результатами якості anomaly detection.
Повні фактичні приклади: [5b-smoke.json](5b-smoke.json).

Скорочені приклади відповідей (решта полів у JSON/OpenAPI):

```json
{"measurement_timestamp":"2016-01-13T18:50:00","time_basis":"dataset_naive","timezone":null,"interval_seconds":600,"energy_wh":180.0,"energy_unit":"Wh"}
```

```json
{"purpose":"residual_reference","forecast_origin":"2016-01-12T16:40:00","forecast_target_timestamp":"2016-01-12T16:50:00","predicted_energy_wh":null,"horizon_seconds":600,"status":"warmup"}
```

```json
{"detector":"residual","maturity":"experimental","score":null,"flag":null,"status":"warmup","score_semantics":"detector_score_not_probability"}
```

```json
{"worker_status":"unknown","unique_measurements":300,"duplicate_deliveries":2,"rejected_messages":0,"checkpoints":[{"run_id":"verification-a704b374790941059eaf0a1d786e3231","topic":"mvp-verification-a704b374790941059eaf0a1d786e3231","partition":0,"next_offset":302,"last_processed_at":"2026-10-19T09:59:20.292012Z"}]}
```

CI: додано окреме **Read-only API PostgreSQL integration** завдання з реальним
PostgreSQL18; unit, legacy Kafka та MVP recovery залишаються окремими.
[Workflow для робочої гілки](https://github.com/Axmetik/Pipeline_Kafka_AI/actions?query=branch%3Afeature%2Fenergy-monitoring-mvp).

## Файли й обмеження

Нові: `api/{main,query,schemas,__main__,smoke}.py`, `api/__init__.py`,
`requirements-api.txt`, `tests/test_api_contracts.py`, `tests/test_api_integration.py`,
цей звіт та `5b-smoke.json`. Оновлено README, requirements-ci, suite selector, CI.
Додаткові індекси/міграції, heartbeat та справжній transport-attempt counter
не додані. Великі запити обмежені timeout; для суттєво більших обсягів треба
окремо оцінити query plans/індекси. Dashboard та публічне розгортання відсутні.
Детектори залишаються experimental із незміненими результатами Stage4.

Технічні джерела: [FastAPI response models](https://fastapi.tiangolo.com/tutorial/response-model/),
[lifespan](https://fastapi.tiangolo.com/advanced/events/),
[CORS](https://fastapi.tiangolo.com/tutorial/cors/).
