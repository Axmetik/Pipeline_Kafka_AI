# Stage 7C — Автоматизовані Email-сповіщення

База: `69c5f86d39e794e5281b468ef88acaab11c9c288`. Гілка:
`feature/email-anomaly-notifications`. Наявні ML artifacts, thresholds, Kafka schema,
Stage 4/7B results, Stage 6 evidence та основний Showcase не змінюються.

## Архітектура

`Kafka → Worker → PostgreSQL (episode + outbox + checkpoint) → Notifier → SMTP`

`Repository.update_episode()` / `persist_combined()` викликають `enqueue()` тільки
після вставлення **нового** episode. Outbox, episode та checkpoint фіксуються
тією самою транзакцією. SMTP/HTTP у worker відсутні. Тривалість одного епізоду
не впливає на кількість листів. Повторні Kafka coordinates / event IDs проходять
наявну ідемпотентну обробку без нового enqueue. Відновлення ML-історії,
pending forecasts і checkpoint не змінено.

Міграція `0003_email` додає лише `mvp_notification_outbox` та індекси, без backfill.
Існуючі записи не змінює. Worker і API вимагають актуальної міграції.

Outbox містить ID повідомлення/епізоду, run/building/source, kind/method, recipient,
незмінний snapshot початку епізоду, fingerprint конфігурації, timestamps,
status/attempt_count/claim_token/claimed_until/next_retry_at/sent_at,
error_category/suppression_reason. `UNIQUE(kind, episode_id, recipient)` забезпечує
один початковий запис. Episode ID є поліморфним посиланням на одну з двох таблиць;
SQL FK на обидві таблиці одночасно не застосовується. Production hook обирає його
лише з щойно вставленого епізоду. Run має SQL FK.

## Увімкнення, scope та restart

Без конфігурації доставка **вимкнена**, режим `individual`.

| Змінна | Default / призначення |
|---|---|
| `EMAIL_NOTIFICATIONS_ENABLED` | `false`; явне ввімкнення |
| `EMAIL_ALERT_MODE` | `individual`, `combined`, `both` |
| `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT` | `mailpit`, `1025` |
| `EMAIL_SMTP_USERNAME`, `EMAIL_SMTP_PASSWORD` | порожні, тільки env / локальний `.env.*` |
| `EMAIL_SMTP_SECURITY` | `none`, `starttls`, `ssl` |
| `EMAIL_FROM`, `EMAIL_TO` | один ASCII email без display name; обов'язкові при ввімкненні |
| `EMAIL_RUN_ID`, `EMAIL_BUILDING_ID`, `EMAIL_SOURCE_ID` | усі три обов'язкові; точна відповідність, без wildcard |
| `EMAIL_COOLDOWN_MINUTES` | `30`, processing wall-clock PostgreSQL, не історичний event time |
| `EMAIL_REAL_DELIVERY_ENABLED` | `false`; окремий opt-in для SMTP поза локальним Mailpit |
| `EMAIL_MAILPIT_WEB_PORT` | `8025`, bind виключно `127.0.0.1` |

SMTP connect/operations timeout: 10 s; TLS перевіряє сертифікат системним trust store.
Автентифікація дозволена тільки через TLS. Зовнішній SMTP вимагає TLS та
`EMAIL_REAL_DELIVERY_ENABLED=true`. Локальні адреси у цьому контракті означають
контрольований Mailpit без relay. Не налаштовуйте forwarding/relay для нього.

Старі episodes не скануються: ввімкнення не створює листи для вже відкритого
епізоду. Scope не виводиться з історії/останнього run; задавайте окремий новий
run/topic/group. Нові episodes у цьому явно дозволеному run можуть містити
історичний dataset time, що є нормальним для replay. SMTP credentials не входять
у fingerprint: їх ротація може продовжити pending delivery без нового event.

Процеси читають конфігурацію на старті. Після зміни env перезапустіть worker і
notifier. Зміна режиму/адресата/транспорту/cooldown у межах поточного scope
придушує ще не відправлені записи зі старим fingerprint (`configuration_changed`).
Вони не перенаправляються новому адресату. Інші scope залишаються в черзі й не
обробляються поточним notifier. За незмінної конфігурації pending/retrying
зберігаються після restart. Вимкнений notifier не захоплює задач; черга зберігається.
Повернення до попереднього явно дозволеного scope/config може продовжити його
pending delivery. Це відновлення вже створеної черги, не backfill епізодів.

## Lifecycle, cooldown та гарантії

`pending → sending → sent` або `retrying → sending`, `failed`, `suppressed`.

Cooldown серіалізується PostgreSQL advisory transaction lock за
run/building/source/kind/method/recipient. Individual method — detector;
combined method — версія правила. Відлік від останнього непридушеного outbox
запису; продовження придушених епізодів не подовжує його. Придушення записується
з причиною `cooldown`. Природний темп історичних вимірювань не замінює реальні
30 хвилин під час прискореного replay.

Notifier захоплює задачі короткою транзакцією `FOR UPDATE SKIP LOCKED`, з token
і lease 120 s. SMTP виконується в окремій notifier-транзакції з row lock, щоб
інший notifier не перевідправив активну задачу навіть після expiry lease.
Worker не використовує цей delivery lock; SMTP outage не блокує Kafka.
Після process crash lock звільняється, прострочений claim відновлюється.
Застарілий token не може виконати доставку чи змінити її статус.

Тимчасові 4xx/connection errors: до 5 спроб, backoff 30/60/120/240 s
(функція обмежена максимумом 900 s). Постійні 5xx, auth, recipient/message errors:
`failed`, без нескінченних повторень. Зберігаються лише безпечні категорії помилок,
не raw SMTP відповіді/паролі. Failed записи автоматично не скидаються;
ручний повтор потребує окремого операторського рішення. Адміністрування черги
не входить у цей MVP.

`sent` означає **прийняття SMTP-сервером**, а не доставку в inbox/прочитання.
Абсолютної exactly-once SMTP доставки немає: після прийняття листа, але до
успішного DB commit, можливе повторне надсилання. Стабільний Message-ID не
гарантує дедуплікацію поштовим сервером. Окремий тест відтворює цей crash window.
Відмова PostgreSQL припиняє нові delivery claims; відновлення — після доступності DB.
Немає нових Redis/Celery, ML або сторонніх платних залежностей.

## Локальна демонстрація — одна команда

У feature branch із встановленим і запущеним Docker:

```bash
python3 -m integration.email_demo synthetic
```

Команда зберігає наявний `.env.mvp` або створює його через чинний setup,
збирає backend, запускає **окремий** Compose project `energy-email-demo`
(PostgreSQL + Mailpit), застосовує міграції та створює ізольований
`email-delivery-test-*` run. Створюється штучний episode з test model metadata,
а не ML inference. Повторюються створення тієї самої події й запуск notifier
у новому процесі: має залишитися один outbox та один multipart лист.
Це **перевірка доставки**, не якості детектора. Моделі не навчаються.

Відкрийте **http://127.0.0.1:8025**, виберіть лист із `[ТЕСТ ДОСТАВКИ]`.
UI доступний лише локально, SMTP port на host не публікується. Mailpit зберігає
листи у власному volume. Фактичний HTML-лист: [скриншот](mailpit-preview.png).
Demo завжди примусово обирає Mailpit, `@example.test` адресата та
`EMAIL_REAL_DELIVERY_ENABLED=false`, незалежно від зовнішнього SMTP env.

Для реальних результатів незмінених моделей:

```bash
python3 -m integration.email_demo replay
```

Потрібні вже підготовлені **trusted** Docker artifacts
`artifacts/mvp/docker/manifest.json` і dataset
`data/energy/raw/energydata_complete.csv` (див. Stage 5 runbook).
Demo не запускає prepare/training й не створює відсутні ML artifacts.
Створює окремі `email-ml-*` run/topic/group і обробляє 300 оригінальних вимірювань
з `2016-04-30T07:20:00`. Scores/thresholds не підмінюються. Нуль combined alerts
є допустимим результатом. Повторні demo використовують нові ідентифікатори.

Додатково: `EMAIL_COMPOSE_PROJECT` / `EMAIL_MAILPIT_WEB_PORT` задають окремий
project/UI port. Не запускайте різні checkouts у тому самому Compose project.
Backend image overlay — `energy-email-backend:local`; стандартний Showcase
не вмикає profile/overlay. Зупинка лише demo services, без видалення volumes:

```bash
docker compose -p energy-email-demo stop
```

## Постійний локальний notifier та реальний SMTP

Для наявного локального MVP скопіюйте `.env.mvp` у локальний `.env.email`
(обидва поза Git). Додайте Email env із таблиці, точно узгодивши
`MVP_RUN_ID` / `MVP_GROUP_ID` / `MVP_TOPIC` та `EMAIL_RUN_ID`.
Після перебудови image застосуйте міграції, потім запустіть scoped worker,
notifier і Mailpit через overlay:

```bash
docker compose --env-file .env.email -p energy-dashboard \
  -f docker/docker-compose.dashboard.yml -f docker/docker-compose.email.yml \
  --profile notifications build worker notifier

docker compose --env-file .env.email -p energy-dashboard \
  -f docker/docker-compose.dashboard.yml -f docker/docker-compose.email.yml \
  --profile notifications run --rm migrate

docker compose --env-file .env.email -p energy-dashboard \
  -f docker/docker-compose.dashboard.yml -f docker/docker-compose.email.yml \
  --profile notifications up -d worker notifier mailpit
```

Перед цими командами чинний MVP PostgreSQL/Kafka має бути запущений.
Не запускайте replay іншого run під старим worker config. Для реального SMTP
явно задайте host/port/security, username/password, FROM/TO і
`EMAIL_REAL_DELIVERY_ENABLED=true`. Не використовуйте real SMTP у demo/CI.
У production-подібному зовнішньому розгортанні потрібні окремий security review,
автентифікація й керування секретами; цей етап лишається локальним MVP.

## API / Dashboard

`GET /api/notifications?run_id=...&building_id=...&source_id=...&limit=20`
повертає ID, episode, type/method, created/sent timestamps, status, attempt count,
safe error/suppression category. Recipient, SMTP credentials, config fingerprint
та raw snapshot не повертаються. Стабільна cursor pagination, newest first;
фільтри run/building/source/status, limit ≤1000. Created time — реальний UTC,
не dataset time. Dashboard використовує існуючий polling і максимум 20 записів.
Таблиця не є панеллю налаштування чи підтвердження фізичних несправностей.

## Формат листа

Український HTML + text/plain, escaped identifiers, deterministic Message-ID.
Будівля/джерело відображаються їх чинними ID: у реєстрі немає окремих назв.
Окремо подані measurement timestamp, processing time і SMTP attempt time;
остаточний SMTP acknowledgement time міститься в DB `sent_at`.
Для UCI: «Час датасету, часовий пояс не визначено», без вигаданого UTC.
Енергія — Wh / 10 хв; residual score/threshold — Wh, IF/AE — власна шкала.
Combined — 3/3 та назви детекторів, тільки frozen Unanimous.

Приклад plain text:

> Energy Intelligence — Експериментальне попередження
>
> Будівля: appliances-house-1; Джерело: uci-appliances
>
> Час вимірювання: 2016-05-26T14:00:00
>
> Час датасету, часовий пояс не визначено
>
> Енергія: 380 Wh / 10 хв; Статус: Experimental
>
> Це попередження не підтверджує фізичну несправність обладнання.

## Перевірки й фактичні результати

Targeted unit tests використовують mocked SMTP. PostgreSQL тести — справжні SQL
в ізольованих schemas, без Kafka/browser/model fitting. Покривають eligibility,
dedup, continuation, rollback, offset/event redelivery, cooldown, mode/scope,
claim locking/recovery, bounded retry, permanent errors, ambiguous SMTP acceptance,
HTML/plain-text, additive migration roundtrip і read-only API pagination.

```bash
python3 -m unittest discover -s tests -p 'test_email.py' -v
RUN_API_INTEGRATION=1 python3 -m unittest discover -s tests -p 'test_email_postgres.py' -v
```

За потреби `MVP_TEST_DATABASE_URL` задає **окрему** локальну PostgreSQL для тестів.
CI workflow не змінено: нові DB tests включені в чинну API suite через test selector;
у автоматичних тестах SMTP mocked, жодного реального листа.
Повний Kafka/browser E2E та performance benchmark вручну не запускалися.

| Перевірка | Результат |
|---|---|
| Email unit | 6 passed |
| Email PostgreSQL integration | 8 passed |
| Чинні API contracts | 4 passed |
| Чинні SQL API integration | 15 passed |
| Frontend unit | 28 passed |
| TypeScript + production build | passed; чинне попередження bundle >500 kB |
| Перевірка синтаксису змінених Python modules | passed |
| Mailpit synthetic | 1 episode / 1 outbox / 1 sent / 1 HTML+text лист |
| Mailpit ML replay | 300 measurements / 600 forecasts / 900 scores; 6 individual episodes / 0 combined; 3 sent / 3 suppressed cooldown |

[JSON evidence](verification.json) розділяє сценарії, містить run IDs/statuses.
Початкові тестові листи перед зміною мережевої конфігурації Mailpit також
експортовано локально; попередні наукові результати не змінювалися.

## Інтерпретація та обмеження

Усі сигнали **experimental**, score не probability, «sent» не фізичний alarm.
Unanimous має нульовий event recall на Stage 7B mixed test: combined-only режим
може не надсилати листів. Відсутність повідомлень не доводить нормальність роботи.
Позитивна доставка синтетичної події підтверджує лише notification механізм.
Cooldown навмисно зменшує кількість листів під час швидкого historical replay.
Один адресат і один exact scope на конфігурацію; backpressure/retention/queue admin,
SMTP provider deliverability, bounce/webhook tracking і production SLA поза етапом.
Спільна PostgreSQL залишається залежністю worker, але відмови SMTP ізольовані.
