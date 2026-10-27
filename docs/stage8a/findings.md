# Findings — Stage 8A

База `c156668`, дата 27.10.2026. **Автоматичних виправлень runtime не виконано.**
Класифікація стосується локального дослідницького MVP та коректності тез роботи;
обмеження наукового висновку не означає, що весь pipeline технічно не працює.

| Категорія | Кількість |
|---|---:|
| Blocker | 0 |
| Major | 7 |
| Minor | 3 |
| Documentation | 3 |
| Future Work | 3 |
| Разом | 16 |

## Major

**M01 — Недостатня якість anomaly detection.** Mixed test: IF/AE/Unanimous F1=0;
Residual point F1=0.0037735849, event F1=0.0111111111. Джерело:
[recomputed values](verified-values.json), первинні Stage 4/7B CSV.
Наслідок: не можна захищати твердження про надійне виявлення фізичних несправностей.
Мінімальна дія: показати негативний результат, experimental labels та відсутність
fault ground truth; не переналаштовувати thresholds за test.

**M02 — Раніше переглянутий test і повторно використані сценарії.** Stage 3 test
переглядався у Stage 2; Stage 4 RF hyperparameters мали Stage 3 validation exposure;
Stage 7B повторно використовує Stage 4 scores/injections, уже розглянуті раніше.
Protocols/selection files підтверджують validation-only формальне правило, але не
скасовують історичну обізнаність. Це не незалежний unseen holdout і не новий blind
anomaly experiment. Дія: обов'язково зазначити обмеження, без test-based reselection.

**M03 — Неповний Stage 6; інша версія системи.** Є лише 3 фінальні пілоти v7
(по 60 measured), 3 overhead пари, 1 recovery-пілот; 0/15 завершених primary,
0/5 повних recovery, 0/20 API-load. Перший primary перервано за рішенням користувача.
Performance source_commit `09d79ed…` передує Stage 7B/7C; ці значення не є
вимірюванням поточної повної системи з combined/outbox. Дія: звітувати як пілоти,
не заявляти граничний throughput, повторюваність, API p99 або production SLA.

**M04 — Частина доказів доступна лише в локальному архіві.** Stage 6 raw і
оригінальні weights Stage 3/4 збережені поза main; hashes перевірено, але clone
сам по собі не містить повного набору. `verified-values.json` фіксує абсолютні
шляхи й SHA, а не пакує raw. Дія перед передачею роботи: окремо погодити
недеструктивний backup/доступ до архіву. У цьому PR нічого з архіву не переносилось.

**M05 — Поточний локальний default backend image застарілий.** Read-only inspection
image `sha256:31ff3473738c886c04bed3cd052d6801c8d07086579bfabccbb3e60f3ab33000`
не знайшов `notifications/notifier.py` і `0003_email.py`; hashes API/schema/repository
не збігаються з checkout. [Snapshot](operational-snapshot.json).
`integration/showcase.py` перевіряє наявність image, не code revision, тому може
повторно використати його. Це **preflight stop** для локальної демонстрації останніх
функцій, не спростування успішного clean CI. Мінімальна дія у Stage 8B: явно
перебудувати backend/API/dashboard images із потрібного checkout, застосувати
тільки upgrade migrations. Не reset/clean, не retrain, не видаляти volumes.
Покращення image freshness guard — окрема майбутня зміна, не частина аудиту.

**M06 — Один household, dataset replay, не фізичний smart meter.** Архітектурні
building/source IDs не є multi-building експериментом. Поточні artifacts прив'язані
до Appliances source. Дія: формулювати результат як локальний streaming MVP на
історичному ряді, без узагальнення на всі будівлі/пристрої.

**M07 — Live Docker artifacts не тотожні оригінальним benchmark weights.** Оригінал
Stage 4 bundle SHA `2ac3a9c7…`, локальний Docker — `06ecf75d…`; live model_version
`energy-anomaly-v1-14c9c4ce4d835763`, original `energy-anomaly-v1-44600700f5a3be9c`.
AE q99: 0.8288868594169614 live проти 0.828860602378845 original. IF/residual q99
збігаються. Перевірено лише metadata/hash через trusted manifest, inference не
виконувався. Код provisioning відтворює frozen конфігурацію у власному середовищі,
але причина числової різниці тут не досліджувалась. Дія: прив'язувати числові
benchmark-висновки до original artifacts, live demo — до власних model/threshold
versions; не називати їх побітово тим самим експериментом.

## Minor

**N01 — Worker liveness невідомий.** `/api/pipeline-status` чесно повертає `unknown`:
checkpoint доводить завершену обробку, не активність процесу. Дія: під час demo
показати приріст counts/offset або logs; heartbeat — окремий запит.

**N02 — Усі SMTPAuthenticationError класифікуються permanent.**
`notifications/notifier.py:category` повертає retry=False навіть для можливого
тимчасового auth-коду 454. Це не порушує локальний Mailpit demo (без auth), але
звужує SMTP retry semantics. Мінімальна майбутня правка: розрізнити 4xx/5xx auth
і додати один mocked test; у Stage 8A код не змінюється.

**N03 — Open episode при закінченні replay не означає триваючу фізичну аварію.**
Episode завершується наступним non-flag/gap/context transition; EOF не є новим
вимірюванням і не закриває його. End timestamp — остання flagged точка.
Дія: пояснювати status у контексті доступних даних, не додавати вигаданий кінець.

## Documentation

**D01 — Не змішувати HGB20 Stage 2 та HGB21 Stage 3.** У Stage 2 Persistence
кращий за MAE, HGB20 — за RMSE. У Stage 3 HGB21 має кращі test MAE/RMSE, але
validation winner — RF21. Порівняння Stage 2→3 не ізолює ефект одного алгоритму.
Цей аудит надає правильні таблиці, початкові results не редагуються.

**D02 — Email processed_at — measurement.received_at, не ML completion.**
У `outbox.enqueue` поле бере server-default PostgreSQL `now()` (час початку
транзакції), не окремий виміряний час завершення inference. SMTP attempt і DB
sent_at — інші timestamps. Дія: у роботі називати це часом реєстрації/транзакції,
не використовувати для inference latency. Первинні листи не переписуються.

**D03 — Showcase не є quality benchmark; counts включають null.**
Стандартний replay починає CSV з початку, тому графік перших 300 точок лежить
у training period. Успішний UI не є доказом holdout accuracy. 600 forecasts / 900
scores — кількість рядків, не всі готові числові результати. Дія: benchmark показати
окремими таблицями; warm-up/coverage назвати явно. Email ML demo має інший,
заданий start і не є тим самим run.

## Future Work

**F01 — Незалежна зовнішня валідація.** Нові будівлі/сезони/фізичні smart meters,
підтверджені labels, blind holdout і реалістичні interventions. Не запускати зараз.

**F02 — Production security та експлуатація.** Auth/RBAC, managed secrets,
backup/restore drills, retention, queue administration, alert routing/acknowledgement,
SMTP deliverability/bounces, HA. Наявний local-only MVP цього не замінює.

**F03 — Окремі дослідження якості й продуктивності.** Новий попередньо зафіксований
протокол після дозволу користувача: повтори performance на конкретній версії та
покращення detectors без test leakage. Скасовану Stage 6 campaign не відновлювати.

## Підсумок готовності

Source-level blocker, що робить збережені ключові результати недостовірними,
не виявлено в межах перевірених доказів. **Локальне середовище as-is ще не готове
показати всю актуальну систему через M05.** Після погодженого preflight rebuild /
upgrade без зміни models воно придатне для локальної дослідницької демонстрації,
якщо обмеження M01–M07 озвучені. Stage 8A не виконує цей preflight і не засвідчує
новий live запуск. Це умовна готовність, не production acceptance.
