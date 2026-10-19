# Stage 5A — PostgreSQL і надійний інтегрований worker

Статус підетапу: persistence/worker, **без FastAPI і Dashboard**. До5B
переходимо після перевірки5A. Оригінальні IoT/Energy/Parquet сценарії,
експерименти й моделі Stage2/3/4 збережено.

## З чистого clone

Потрібні Python3.13 і Docker із Compose. Команди виконувати з кореня repo.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-mvp.txt
python -m integration.setup
docker compose --env-file .env.mvp -p energy-mvp -f docker/docker-compose.mvp.yml up -d --wait
alembic upgrade head
```

На Linux для тестового/CPU середовища можна встановити torch2.11.0 з офіційного
CPU index, потім `pip install -r requirements-ci.txt`; цей subset вже включає
requirements-mvp.txt. CI використовує саме цей шлях.

`integration.setup` створює ignored `.env.mvp` з випадковим локальним паролем
і permissions0600; існуючий файл не перезаписує й пароль не друкує.
`.env.example` містить лише порожні credential-поля. Не додавайте .env/model
files у Git. PostgreSQL доступний на127.0.0.1:15432, Kafka —127.0.0.1:19092;
named volumes зберігають обидва журнали між звичайними перезапусками Compose.
Інфраструктура ізольована project name `energy-mvp`, без конфлікту зі старим
Kafka9092. У legacy compose прив'язку9092/8080 також обмежено localhost;
логіку IoT/старих consumers не змінено.

### Варіант А: перевірені локальні артефакти вже є

```bash
python -m integration.artifacts register \
  --hgb artifacts/energy/appliances-hgb-bound-v1/model.joblib \
  --anomaly artifacts/energy-anomaly/v1/bundle.joblib \
  --output artifacts/mvp/local/manifest.json
```

Шляхи — приклад наявних локальних Stage2/4 артефактів. Register перевіряє
контракти HGB20/RF21, binding sources, threshold version і зберігає file hashes
та ML library versions. Завантажувати лише trusted local pickle/joblib artifacts.
Manifest не додається в Git. Worker перевіряє hashes **до десеріалізації**.

### Варіант Б: у чистому clone моделей немає

```bash
python -m producer.download_appliances --output data/energy/raw/energydata_complete.csv
OMP_NUM_THREADS=1 python -m integration.artifacts prepare \
  --dataset data/energy/raw/energydata_complete.csv \
  --output artifacts/mvp/local
```

Якщо CSV уже є, download пропустіть: він навмисно не перезаписує файл.
Prepare перевіряє зафіксований SHA-256 датасету, використовує Stage2 HGB config
і Stage4 train-only IF/AE/RF + calibration configuration. Новий локальний fit
може тривати кілька хвилин; progress друкується. Немає inference fallback або
онлайн-навчання. Original artifacts/results не відкриваються на запис;
нові моделі й допоміжні результати створюються тільки в новому ignored output.
95+95 anomaly scenarios не перезапускаються. Для іншої output-директорії
встановіть MVP_ARTIFACT_MANIFEST у .env.mvp або environment.

Повторний prepare/register має використовувати новий output. Для одного run
не можна підмінювати manifest, versions, sources або model files: це буде
відхилено до обробки. Missing/corrupt artifact дає зрозумілу помилку з командами
prepare/register, а не мовчазну роботу без прогнозів.

## Replay і worker

Спочатку replay створює **явно** configured single-partition topic і публікує
повідомлення через незмінений producer.energy_producer:

```bash
python -m integration.replay --dataset data/energy/raw/energydata_complete.csv --limit 300 --sleep 0
OMP_NUM_THREADS=1 python -m integration.energy_worker --max-messages 300 --idle-timeout 15
python -m integration.status
```

Після створення topic можна запускати worker у першому терміналі без limit,
а replay в іншому зі `--sleep 0.1`. Run/topic/group беруться з тієї самої
.env.mvp — це усуває неузгоджені теми в різних терміналах. Worker показує ready
і progress кожні50 повідомлень. Невалідні повідомлення потрапляють у DB quarantine.
Для нового незалежного replay задайте нові MVP_RUN_ID, MVP_GROUP_ID і MVP_TOPIC.
Для **restart з продовженням** залиште всі три й ті самі artifacts незмінними.
Повторні вже отримані event IDs у тому самому run не створюють нових series rows
і не просувають lag history вдруге; окремий receipt фіксує повторну доставку.

Наявні stages2/4 CLI та legacy compose доступні як раніше. MVP worker пише
PostgreSQL, а не неатомарну пару DB+Parquet. Legacy Parquet архіви не мігруємо.

## Семантика даних

- Основний forecast: HGB20, purpose `primary_forecast`.
- Окремий прогноз RF21 для residual: purpose `residual_reference`. Він не
  підміняє HGB і не є автоматичною інтеграцією Stage3 RF у production forecast.
- IF/AE/residual scores і episodes: `maturity=experimental`; flag означає
  перевищення порога, не підтверджену несправність і не probability.
- На кожне прийняте вимірювання зберігаються2 forecast rows і3 score rows,
  у тому числі nullable warmup/incompatible statuses. Після перших6 predecessor
  readings HGB/IF/AE готові; residual потребує144 predecessors. Null не є0/false.
- UCI2016 timestamps зберігаються як original/local naive, UTC-поле null.
  UTC використовується лише для реального received/generated/scored time або
  повідомлень з явним offset. Timestamp contract підготовлено для5B.
- Sources мають незмінний semantic binding; зміна binding під тим самим ID
  quarantine. Нове несумісне джерело можна архівувати з null scoring,
  не застосовуючи до нього довільну модель.

## DB, checkpoint і recovery

Одна транзакція PostgreSQL атомарно фіксує measurement, обидва forecasts,
три scores, відкриття/подовження/закриття episodes, delivery receipt та next_offset.
Лише після commit виконується явний Kafka commit. Auto commit вимкнено також
під час cleanup. Run/group/topic/model context незмінний.

На startup worker перевіряє cluster, offset bounds і Kafka committed position.
Kafka commit позаду DB або відсутній допустимий після перевірки журналу.
Kafka commit попереду DB, DB поза log bounds, відсутній checkpoint при наявному
ledger/commit, втрачений anchor чи несумісний retained log зупиняють worker.
Не використовується automatic earliest/latest fallback. Кожен ще доступний
оброблений Kafka record порівнюється з DB ledger, не тільки останній anchor;
перевіряється й checkpoint digest. Вартість startup лінійна за довжиною
retained processed log — прийнятний компроміс для цього невеликого MVP.

Потім відтворюються останні144 committed compatible raw measurements кожного
source. Hash history, status і прогноз мають відповідати persisted forecast;
pending RF value та original generated_at беруться зі збереженого запису.
DB forecasts не перезаписуються. Відкриті episodes — авторитетні DB rows,
кожне наступне рішення оновлює їх у тій самій транзакції без нового дубля.
Після gap/unknown попередній епізод закривається з причиною.

MVP підтримує **один worker і partition0**. PostgreSQL advisory lock та row lock
checkpoint не дозволяють одночасному worker використовувати ту саму group/topic.
Додатковий memory-position fence зупиняє processor, якщо DB checkpoint змінився
поза його локальним станом (зокрема при втраті ownership session): чужий прогрес
не перетворюється на пропуск оновлення lag history.
Після rollback або невизначеного commit outcome in-memory processor непридатний
для подальшої роботи: процес зупиняється, restart відновлює committed стан.
Це at-least-once доставка з ідемпотентним DB sink, не обіцянка end-to-end exactly-once.

Помилки reconciliation виправляються з узгодженої DB/Kafka резервної копії або
новим явно окремим run/group/topic. Не видаляйте DB checkpoint/ledger і не
скидайте offsets навмання, щоб «продовжити» старий run.

## Перевірки

```bash
python tests/run_suite.py --suite unit
python tests/run_suite.py --suite kafka   # legacy broker localhost:9092
python tests/run_suite.py --suite mvp     # isolated MVP PostgreSQL/Kafka
# Усі: потрібні обидві Kafka інфраструктури
python tests/run_suite.py --suite all
```

MVP tests створюють лише власні random schemas/topics і прибирають їх. Вони
перевіряють міграцію upgrade/downgrade, дублі/конфлікти, завершення процесу через
os._exit до DB commit і після150-го DB commit до Kafka commit, відновлення
неповної історії/pending forecasts/open episodes, зміни model context, ownership,
змінений Kafka prefix (навіть коли останній anchor збігається), fingerprint history
і checkpoint digest. Потрібні реальні PostgreSQL і Kafka; skip не зараховується
як успішний suite. CI має окремий MVP recovery job.

Повний прогін з локальними, а не tiny test-моделями:

```bash
OMP_NUM_THREADS=1 python -m integration.verify \
  --dataset data/energy/raw/energydata_complete.csv \
  --output data/mvp-verification-001.json
python -m integration.status --list-runs
python -m integration.status --run-id <run_id_із_звіту>
```

Verify створює окремий run/topic, надсилає300 унікальних+2 повторні повідомлення,
зупиняє worker після150, продовжує й зіставляє всі predictions/scores з offline
inference. Topic/run лишаються для перегляду; результат не є новим accuracy
експериментом. Старі Stage4 metrics не коригуються.

Для зупинки: `docker compose --env-file .env.mvp -p energy-mvp -f docker/docker-compose.mvp.yml stop`.
`down` зберігає named volumes; **down -v видаляє їх**, не використовуйте для
звичайного restart. Stage5B/5C та злиття Stage5 потребують окремого погодження.
