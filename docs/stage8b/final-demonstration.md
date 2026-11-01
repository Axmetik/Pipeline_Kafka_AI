# Stage 8B — фінальна демонстрація та відтворюваність

**Дата:** 01.11.2026 (Europe/Kiev). **Результат: GO для локального показу дослідницького MVP.**
Runtime source: `51e4b94635ec775a6ab2111b894b8cc8034fd45b`. Гілка `feature/stage8b-final-demonstration` додає тільки докази й документацію, без функціональних змін. Merge/tag не виконано.

## Фактичний сценарій

Виконано **один** Showcase: `--limit 300 --sleep 0.15`, project `energy-dashboard-main`, нові run/topic/group `showcase-20261101-112252-c10e040c0b71`.
Це project основного checkout, з його наявними PostgreSQL/Kafka volumes. Старий `energy-dashboard` та checkout Stage 6 не запускались і не змінювались.
[Поточний Dashboard](http://127.0.0.1:8088/?run=showcase-20261101-112252-c10e040c0b71) · [runbook](reproducibility-runbook.md) · [machine-readable verification](verification.json).

| Об'єкт | Фактична кількість |
|---|---:|
| Унікальні measurements / event IDs | 300 / 300 |
| Forecast rows: HGB20 + RF21 | 600 |
| Original detector score rows | 900 |
| Combined decisions | 300 |
| Receipt ledger records | 300 accepted |
| Kafka begin / end / committed offset | 0 / 300 / 300 |
| DB next_offset | 300 |
| Unexpected duplicates / rejected / errors | 0 / 0 / 0 |
| Individual episodes | 1 (AE, closed, одна threshold point) |
| Combined threshold points / episodes | 0 / 0 |
| Standard-project notifications | 0 (Email вимкнено) |

Час даних: **2016-01-11 17:00 — 2016-01-13 18:50**, без приписаного timezone.
Обробка відбулась у листопаді 2026; історичний event time не використано як processing latency.

## Rows не означають ready values

| Метод / purpose | Рядків | Готових чисел | Warm-up/null |
|---|---:|---:|---:|
| HGB20 primary forecast | 300 | 294 | 6 |
| RF21 residual reference forecast | 300 | 157 | 143 |
| Isolation Forest | 300 | 294 | 6 |
| Autoencoder | 300 | 294 | 6 |
| Residual score | 300 | 156 | 144 |
| Combined decision | 300 | 156 готових рішень | 144 |

Для всіх forecast origin/target різниця 600 s. Готові residual scores звірено з **раніше збереженим RF21 forecast**, ціль якого дорівнює поточному measurement timestamp; його generated_at передує received_at поточного вимірювання. Primary HGB20 не підмінено RF21.

Один AE threshold episode: `2016-01-11T19:20:00`, одна точка, closed. Він поза останнім 144-точковим вікном, тому нуль перевищень на поточних detector charts узгоджується з ненульовою історією episodes. Це статистичне перевищення, **не підтверджена фізична несправність**.

## M05, images, міграції та provenance

Перед діями збережено [preflight](preflight.json): stopped containers, projects, ports, named volumes, image IDs, CSV та всі файли trusted model directory. Збіглись усі SHA; CSV містить 19 735 вимірювань. Manifest libraries: NumPy 2.4.4, scikit-learn 1.8.0, joblib 1.5.3, torch 2.11.0+cpu.

Явно виконано `build worker api dashboard` із поточного checkout. M05 усунуто позитивною перевіркою **89 Python-файлів** проти нової image, зокрема Combined, Email і `0003_email.py`; Graphite CSS перевірено у готовому nginx image. Це не припущення на підставі наявності тегу. Вихідні IDs поточного середовища відрізнялися від історичного snapshot Stage 8A; стару ознаку відсутності Email не переносимо автоматично на них.

| Image | Новий ID |
|---|---|
| Backend | `sha256:3be9a8ff7a2eedf156ae4b85e4b2bd064b1fda84aa0057bf4718ab2f9ed4a865` |
| Dashboard | `sha256:d38a48d60fdb74dd0cbb0f830404fa09c4024a4738aae3fd4ce80ea14a42f65f` |
| Email backend | `sha256:26a4783befe05d5f2d9a6ca33f2902b9ef6aac4a902722188dc6df46a3aebe8e` |

База **вже мала `0003_email`**. Окремий upgrade не запускався. Showcase автоматично запустив існуючий migrate service: `upgrade head` був no-op, schema не змінювалася. [History before](history-before.json) / [after](history-after.json) підтвердили незмінність обох старих runs та їхніх measurements, forecasts, scores, receipts, episodes, combined і checkpoint records. Додано лише новий run.

[Image/artifact verification](image-artifact-verification.json) містить точні model/feature/threshold versions та hashes. Це **trusted Docker models**, не побітово тотожні original Stage 3/4 benchmark weights. AE q99 live = 0.8288868594169614, original = 0.828860602378845. IF q99 = 0.6747213487966208; residual q99 = 296.24602578530755 Wh. Жодного threshold або artifact не змінено.

## Kafka → DB → API → Graphite

[Read-only verifier](verify_runtime.py) перевірив усі 300 journal payload hashes, event IDs, безперервні offsets, commit/checkpoint та значення CSV; також nullable states і Unanimous coverage/votes. [Результат](runtime-verification.json).

[API smoke](api-verification.json) перевірив всі рядки через пагіновані read-only endpoints, моделі (20 vs 21 ознака), одиниці Wh, time_basis, target alignment, nulls, experimental семантику, health. Лічильники збігаються з DB та UI.

[Browser evidence](browser-verification.json): реальний Chromium, **без API mocks**, 23 спостереження зміни count від 0 до 300, знімок під час replay; сторінка не перезавантажувалась для live updates. Після завершення перевірено reload, selectors 72/288/144, деталі origin/target/generated/received timestamps; console/page errors = 0. Browser timezone навмисно Pacific/Honolulu: UCI labels лишилися dataset-naive. Desktop Graphite читабельний; повну responsive campaign PR10 не повторювали.

Insights незалежно звірено арифметично: latest180Wh, mean останніх144 = 67.4305556Wh, +166.9%; next HGB20 = 265.205626Wh для 2016-01-13 19:00, +47.3% до останнього факту. Це описові правила, не причинна діагностика і не оцінка точності нового прогнозу.

UI чесно показує worker/replay status `unknown`: API не має heartbeat і producer expected count. Завершення підтверджує orchestrator `phase=complete` разом з DB/Kafka, а не вигаданий статус UI. [Local-only security check](operational-final.json): DB/Kafka без host ports, Dashboard тільки 127.0.0.1:8088, API8000 недоступний із worker network.

## Окремий Email delivery proof

Виконано тільки `integration.email_demo synthetic`, project `energy-email-defense`, [Mailpit](http://127.0.0.1:8026). Run `email-delivery-test-d2cca7d8d321` — **synthetic delivery test, не model replay**.

- 1 synthetic individual episode → 1 notification outbox record → `sent`, attempt_count1.
- Mailpit містить 1 multipart/alternative message з text/plain та text/html; є `[ТЕСТ ДОСТАВКИ]`, historical clock і experimental застереження.
- Existing demo повторно подав ту саму synthetic подію та повторно запустив notifier; повторного листа немає.
- SMTP лише internal Mailpit1025; адреси energy@example.test → viewer@example.test, real delivery false. Зовнішні листи не надсилались.
- Це окрема PostgreSQL: її outbox **не з'являється автоматично** у стандартному Dashboard. Там нуль notifications є очікуваним.

[MIME/DB proof](email-delivery-verification.json). Raw email не дублюється в Git; збережено MIME SHA та типи частин. Real-model Email replay не запускався.

## Targeted checks, обмеження та збереження

14 Showcase safety unit tests + 6 mocked Email unit tests пройшли. Початковий Email check у host venv мав import error (немає SQLAlchemy); його виконано в перевіреному backend image без мережі, без зміни host dependencies. [Точні перевірки](targeted-checks.json).

Один ручний Showcase та один synthetic Email scenario, а не новий benchmark. Повні локальні E2E/recovery/performance suites не повторювались. Для crash/recovery використано [успішні шість checks базового main](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40563712518), без нового live restart; не заявляємо нову recovery latency. Існуючий workflow GitHub може автоматично виконувати стандартні checks під час push/PR; це окреме ephemeral CI, не додатковий локальний replay або заміна цього evidence.

Усі старі named volumes збережені; наявні pgdata/kafkadata основного project повторно використано. Додано лише pgdata/mailpitdata нового Email project. Моделі, CSV та manifest після всіх дій мають ті самі SHA. Попередній last-showcase pointer збережено в [previous context](previous-showcase-context.json); стандартна команда оновила лише свій last-context pointer. Великі logs лишились локально в `/tmp`, secrets/.env в Git не додавались. [Final state](operational-final.json).

### Реальні screenshots

Усі [live знімки](screenshots/manifest.json) походять від цього replay, а не Graphite frontend fixtures:
[overview](screenshots/live/overview.png), [KPI](screenshots/live/kpi.png), [forecast](screenshots/live/forecast.png), [detectors](screenshots/live/detectors.png), [combined](screenshots/live/combined.png), [insights](screenshots/live/insights.png), [episodes](screenshots/live/episodes.png), [pipeline](screenshots/live/pipeline.png), [models](screenshots/live/models.png), [timestamps](screenshots/live/timestamps.png), [replay in progress](screenshots/live/replay-in-progress.png), [full dashboard](screenshots/live/desktop-full.png).

Окремо synthetic delivery: [inbox](screenshots/synthetic-email/mailpit-inbox.png), [HTML](screenshots/synthetic-email/mailpit-html.png), [HTML details](screenshots/synthetic-email/mailpit-html-details.png), [text](screenshots/synthetic-email/mailpit-text.png). Offline benchmark plots не додавались й не змінювались.

**GO стосується локального показу реалізації в магістерській**, за доступності Docker і цієї trusted конфігурації. Це не production SLA, не успішна operational anomaly detection і не нова валідація на фізичних smart meters. [Відомі обмеження](known-limitations.md), [checklist](readiness-checklist.md), [5–7 хв demo script](demo-script.md).
