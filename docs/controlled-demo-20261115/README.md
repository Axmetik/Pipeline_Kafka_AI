# Контрольована демонстрація: штучне підвищення Appliances

**Це демонстраційні дані зі штучним втручанням, не реальна несправність та не незалежний тест якості.** Справжній конвеєр: Kafka → незмінений integrated ML worker → PostgreSQL → read-only REST API → production Dashboard у Chrome. Готові оцінки, рішення й епізоди в БД не вставлялися. Змінено тільки файли цього каталогу документації, не код застосунку.

## План, джерело та контексти

План [plan.json](plan.json) записано **до запуску**. Його SHA-256 підтверджений в [execution.json](execution.json). Джерело коду: `5eab359e9e2956e4bdc0becbe9945ea653e38f18`, гілка `feature/sources-catalog`. Використано чинні адаптер `producer/appliances_dataset.py:iter_appliances`, `integration.energy_worker.run_worker`, контракт `processing/energy_schema.py` та схему Alembic `0003_email` без модифікацій. За основу інфраструктури взято ізольований browser harness попереднього каталогу (`tests/source_catalog_browser.py`), шаблон його локального API proxy використано без зміни middleware. За основу producer/worker — наявні replay та real-model email demo, **не synthetic notification fixture**.

- Оригінальний файл: `data/energy/raw/energydata_complete.csv`; SHA-256 `2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`.
- Джерело: `appliances-house-1` / `uci-appliances`.
- Кожен потік: **300 вимірювань**, `2016-04-30T07:20:00` — `2016-05-02T09:10:00`, без розривів, крок 600 с. Це naive labels датасету; часовий пояс не призначався.
- До втручання: 180 незмінених записів. HGB20, IF та AE готові з 7-го запису; RF21 формує перший прогноз на 144-му, residual оцінює його на 145-му. Це визначено за `EnergyProcessor`, `BenchmarkFeatures` та `StreamDetector`, а не припущено.
- Ін'єкція: індекси 180–191 (нумерація з нуля), **12 інтервалів × 10 хв = 120 хв інтервальної енергії**, мітки `2016-05-01T13:20:00` — `15:10:00`. З `15:20:00` повернуто оригінальний ряд, ще 108 записів.
- Формула: `Appliances_modified(t) = Appliances_original(t) + delta_wh` лише в цих 12 записах. `lights`, температури, вологості, решта payload, одиниці, event IDs та timestamps незмінні. Копії ізольовані run/topic/group; спільні event IDs не змішуються між run.
- Заздалегідь визначено delta `[150, 300, 450]` Wh і зупинку після першого нового позитивного рішення всередині втручання відносно парного контролю. 150 Wh відповідає 3 × 50 Wh IQR зі старого Stage 4 level_shift, 300 Wh — величині старих Kafka spike injections, але тепер тривалій; третій, сильніший варіант визначено до запуску. Пороги/моделі не змінювалися. Це не приховане продовження перебору після успіху.

Контексти: `controlled-demo-1a21d84b-control`, `controlled-demo-1a21d84b-plus-150`, `controlled-demo-1a21d84b-plus-300`, `controlled-demo-1a21d84b-plus-450`. У кожного власні topic/group з такою самою назвою. [context.json](context.json) фіксує обраний run для UI. Всі три спроби збережено, включно з двома без реакції на втручання.

## Незмінені моделі та правила

Trusted manifest: `artifacts/mvp/docker/manifest.json`, SHA-256 `472ecf45565e63df05e4f12db715f61c081885a33d92dff3ca26ee820694fecb`. Це поточні Docker provisioning artifacts; їх не ототожнюємо побітово з початковими науковими bundle Stage 3/4.

| Роль | model_version | feature_version | Поріг |
| --- | --- | --- | --- |
| Основний HGB20, `primary_forecast` | `hgb-energy-v1-9bb48a66deb359e6` | `energy-features-v1`, 20 ознак | Не детектор |
| RF21, `residual_reference` | `energy-anomaly-v1-14c9c4ce4d835763` | `benchmark-energy-v1`, 21 ознака | Не первинний прогноз |
| Isolation Forest | `energy-anomaly-v1-14c9c4ce4d835763` | `energy-anomaly-20-v1` | 0.6747213487966208 |
| Autoencoder | Так само | `energy-anomaly-20-v1` | 0.8288868594169614 |
| Residual: `abs(факт − попередній RF21)` | Так само | `benchmark-energy-v1` | 296.24602578530755 Wh |
| Unanimous | `combined-q99-v1-unanimous` | 3 із 3 готових позитивних рішень | Без змін frozen configuration |

Пороги: q99, `threshold_version=quantiles-v1-7ad1a9024c86e188`. HGB artifact SHA `087cbc03c4b9bd3fa0f94db903045c7c2a790ea95f03e35862aa21cb6b0727a3`; anomaly bundle SHA `06ecf75dcd4c1ad780194941803e5e5991274ad7d38d88936c728b8c40318566`. Повна registry й feature names — у кожному `*-summary.json`, `models`.

У цій гілці **немає інтегрованих sustained_high, residual OR sustained_high, flatline, interval_gap або low-правил**. Їх не імпортували з іншої гілки заради демонстрації. Є лише незмінений Unanimous. Тому цей дослід не є перевіркою hybrid-інтеграції.

## Реакція парних потоків

Позитивне рішення означає лише experimental threshold exceedance. Нерозмічений контроль не називаємо потоком без несправностей чи джерелом підтверджених false positives.

| Потік | Residual: true під час 12 інтервалів | AE | IF | Unanimous | Усі індивідуальні епізоди за run |
| --- | ---: | ---: | ---: | ---: | ---: |
| Незмінений контроль | 0 | 0 | 0 | 0 | 6 |
| +150 Wh | 0 | 0 | 0 | 0 | 6 |
| +300 Wh | 0 | 0 | 0 | 0 | 6 |
| +450 Wh | 1 | 9 | 7 | 0 | 12 |

На +300 Wh residual на першій точці = 286.559940 Wh, нижче незміненого порогу 296.246026 Wh. Поріг не знижували. Успіх досягнуто лише на третьому заздалегідь заданому варіанті; після нього перебір зупинено.

| Метод | Контроль: true за весь run / епізоди | +450: true за весь run / епізоди | Нові true всередині втручання | Перше true / затримка | Coverage втручання |
| --- | ---: | ---: | ---: | --- | ---: |
| Residual | 1 / 1 | 3 / 3 | 1 | 13:20 / **0 хв** | 12/12 |
| Autoencoder | 3 / 3 | 13 / 6 | 9 | 13:40 / **20 хв** | 12/12 |
| Isolation Forest | 6 / 2 | 15 / 3 | 7 | 14:10 / **50 хв** | 12/12 |
| Unanimous | 0 / 0 | 0 / 0 | 0 | Не спрацював | 12/12 |

Джерело обох таблиць: [comparison.csv](comparison.csv), поля `target_positive_points`, `total_positive_points`, `total_episodes`, `new_positive_points_vs_control`, `delay_dataset_minutes`, `target_available_points`. Доступність за всім run: IF/AE 294/300, residual/Unanimous 156/300 через початковий warm-up; відсутні рішення не рахували як false. На цільових 12 точках усі методи готові. Шість контрольних епізодів збереглися; нових епізодів загалом шість, з них чотири почалися під час втручання. Unanimous не активувався: три методи не були одночасно позитивними.

### Епізоди та повернення початкового ряду

| Метод | Початок — останнє true | Точок | Запис, на якому зафіксовано закриття | Походження |
| --- | --- | ---: | --- | --- |
| Residual | 13:20 — 13:20 | 1 | 13:30 | Новий, на початку підвищення |
| AE | 13:40 — 13:50 | 2 | 14:00 | Новий, під час підвищення |
| AE | 14:10 — 15:10 | 7 | 15:20 | Новий, під час підвищення |
| IF | 14:10 — 15:30 | 9 | 15:40 | Новий; триває ще 2 точки після втручання |
| Residual | 15:20 — 15:20 | 1 | 15:30 | Новий, під час повернення оригінального ряду |
| AE | 15:30 — 15:30 | 1 | 15:40 | Новий, після завершення втручання |
| Residual | 16:50 — 16:50 | 1 | 17:00 | **Такий самий епізод є в контролі** |

Усі дати в цій таблиці — 2016-05-01, dataset-naive. Усі перелічені епізоди мають `status=closed`, `closed_reason=below_threshold`. `end_timestamp` у БД означає **останню позитивну точку**, а не наступний запис, що закрив епізод. Моменти закриття виведено з наступного непозитивного рішення; це не вимірювання wall-clock затримки. Джерело: [episode-timeline.csv](episode-timeline.csv), точні episode IDs і перевірка меж проти per-point flags.

За даними [key-points.csv](key-points.csv), о 13:20 факт 540 Wh, раніше сформований HGB20 ≈104.598 Wh, RF21 ≈103.440 Wh; residual ≈436.560 Wh >296.246 Wh. О 13:30 RF21 уже ≈482.227 Wh при факті 520 Wh, residual ≈37.773 Wh: він перестав сигналізувати, хоча втручання тривало. Це фактична зміна прогнозу на цьому потоці, не підтвердження надійного виявлення тривалих подій.

О 15:40 всі три рішення вперше після повернення ряду негативні; пізніше о 16:50 є згадане спільне з контролем residual-спрацювання. На фінальному записі `2016-05-02T09:10:00`: факт 60 Wh; IF 0.397843 <0.674721, AE 0.031108 <0.828887, residual 2.381184 Wh <296.246026 Wh, всі flag=false. Післядія IF/AE узгоджується з наявністю лагів у поточних ознаках, але окремого експерименту причинності конкретної ознаки не проводили.

## Скриншоти справжнього застосунку

Chrome, 1500×1200, timezone Pacific/Honolulu для перевірки відсутності конвертації naive labels. Браузер → localhost proxy → API → PostgreSQL, без підміни відповідей/чисел/статусів. Усі модифіковані знімки — run `controlled-demo-1a21d84b-plus-450`, джерело `uci-appliances`, будівля `appliances-house-1`. Графіки показують однакові останні 144 фактичні точки `2016-05-01T09:20:00` — `2016-05-02T09:10:00`; HGB20 має додаткову прогнозну точку на 09:20, без вигаданого факту.

| Представлення | Файл |
| --- | --- |
| Контрольний потік, те саме вікно | [control-overview-desktop.png](control-overview-desktop.png) |
| До/під час/після підвищення, tooltip на початку | [injection-overview-desktop.png](injection-overview-desktop.png) |
| Scores, власні пороги й стан після втручання | [detectors-desktop.png](detectors-desktop.png) |
| Реальний журнал епізодів | [episodes-desktop.png](episodes-desktop.png) |
| Після завершення, tooltip на фінальній точці | [after-intervention-desktop.png](after-intervention-desktop.png) |

**Межа чинного UI:** журнал явно показує останні 50 епізодів **за весь вибраний run**, а не лише 144 точки графіка. Тому на його скриншоті видно також старі контрольні спрацювання 30 квітня. Їх не приховували і не зараховували до нової реакції. Контекст запуску й джерела узгоджений; часовий scope журналу ширший за графік і прямо підписаний застосунком. Окремий фільтр журналу в цьому завданні не додавали. Точні URI, scopes і вікно — [browser-verification.json](browser-verification.json).

## Виконані вузькі перевірки

1. Усі 4×300 повідомлень пройшли чинну JSON/schema validation, мають крок 600 с. Порівняння копій підтвердило: відрізняється лише `energy.value` у заданих 12 записах; CSV не змінено. Вихідні/нові числа всіх трьох варіантів — [interventions.csv](interventions.csv).
2. На кожен run: 300 унікальних measurements, 600 forecasts, 900 scores, 300 Unanimous decisions; відхилень і дублів немає. Kafka offsets 0–299, DB checkpoint = Kafka committed = end offset =300. Всі 300 wire records дорівнюють відправленим; всі delivery ledger payload hashes перевірено. Документи: `*-summary.json`, `integrity`, `worker`, `counts`; `*-worker.log` — реальні компактні логи worker.
3. На контролі та обраному +450 усі API measurements/forecasts/scores/Unanimous/events звірено з DB exports: значення, null, flags, thresholds, timestamps, IDs, статуси й межі епізодів. RF21 origin +600 с = target = timestamp факту. Деталі: `browser-verification.json:api_checks`.
4. Усі епізоди всіх чотирьох run незалежно відновлено з фактичних послідовних true/false/null та зіставлено зі збереженими межами/count/status. Registry моделей однакова. [analysis-verification.json](analysis-verification.json). Аналіз — тільки читання експортів, без повторного inference.
5. Реальні графіки/tooltip у Chrome, experimental labels, поточні значення й відсутність JS errors. Знімки переглянуто візуально; числових редагувань зображень немає.
6. Синтаксис лише нових `run.py`, `pipeline.py`, `analyze.py`, `browser.mjs` перевірено; production код не змінювався. Повну suite/CI/E2E/performance campaign не запускали.

Сповіщення навмисно **не перевірялися**: `EMAIL_NOTIFICATIONS_ENABLED=false`, notifier і Mailpit не запускали, outbox 0 в кожному контексті, зовнішнього SMTP немає. Це не доказ доставки листа. Чинний застосунок має сповіщення для ML/Unanimous; sustained_high/hybrid у цій гілці відсутні, тож їхню email-підтримку тут не демонструємо.

## Відтворення та збереження

Потрібні вже наявні перевірені локальні `artifacts/mvp/docker/manifest.json`, HGB/bundle, оригінальний CSV, побудований frontend саме цієї гілки, Docker images `energy-monitoring-backend:local`, `postgres:18-alpine`, `apache/kafka:3.9.0`, Chrome і встановлені dashboard dependencies. Скрипт **не готує/перенавчає моделі й не перебудовує Docker images**. Для цієї перевірки використано вже наявний production frontend build.

```sh
# Новий output: збережені докази не перезаписуються.
python3 docs/controlled-demo-20261115/run.py --output /tmp/energy-controlled-demo-repeat-01
# Повторити лише табличний аналіз уже збережених доказів, без Kafka/ML:
python3 docs/controlled-demo-20261115/analyze.py --input /tmp/energy-controlled-demo-repeat-01
```

Кожен повтор створює нові run/topic/group та власні імена Docker network/контейнерів. PostgreSQL у tmpfs, Kafka без named volume, без опублікованих DB/broker ports; API loopback-only за окремим proxy на випадковому localhost port. По завершенні прибираються **лише власні** контейнери/мережа, не робочі Docker volumes. Моделі та репозиторій змонтовані read-only. Докази лишаються у вибраному output; великі похідні потоки/моделі не зберігаються. Тут збережені лише компактні per-point CSV, metadata, зміни 12 точок і скриншоти, а не копії повного датасету.

SHA-256 оригінального CSV, обох model artifacts, manifest і Unanimous config збіглися до/після досліду (`execution.json:inputs_sha256_unchanged`). Основне demo, робоча БД, Stage 6 checkout, попередні досліди й магістерська не змінювалися. Тимчасові сервіси зупинено після фіксації результатів. У run.py додано можливість нового output і явні імена worker-контейнерів для безпечного повторення/cleanup; це не зміна моделей або протоколу.

Це один реальний історичний фрагмент одного будинку з трьома заздалегідь заданими втручаннями. Не розраховували Precision/Recall/F1, SLA, продуктивність реальних smart meters або незалежну узагальнюваність. Наявність видимої реакції на +450 Wh не означає достатню операційну якість; +150/+300 не були виявлені в цільових інтервалах, а контроль уже мав шість епізодів.

Зміни фіксуються **локальним комітом**. Push/merge не виконуються, щоб не запускати автоматичну повну CI-матрицю всупереч межам цього завдання.
