# Етап 2/6 — два реальні запуски інтегрованої системи

## Версія та межі

Гілка `integration/energy-intelligence-complete`; код застосунку **a6c1287ea8532aacb2d04c346d96d5d2595b9ad1**. На цьому етапі змінено лише скрипти й докази в `docs/integration/`, без змін Worker/API/UI, моделей, порогів, правил, міграцій або попередніх результатів. Виконано рівно два фіксовані сценарії, без підбору відхилення. Це демонстраційна перевірка на історичних даних того самого будинку, не нова незалежна оцінка якості чи продуктивності.

План зафіксовано перед першою публікацією: [plan.json](plan.json), його SHA256 у [environment.json](environment.json). Усі timestamps вимірювань — `dataset_naive`, без призначення UTC. Усі значення енергії — Wh за 600 секунд.

## Історія й фактична готовність

`processing/energy_rules.py::RuleConfig/_context/process`: останні сім **календарних дат**, поточна дата виключена; потрібні ≥3 попередні дати й ≥18 придатних значень тієї самої години. Медіана й MAD визначають незмінений поріг:

`median + max(3 × 1.4826 × MAD, 50 Wh, 0.5 × median)`.

Шість послідовних перевищень підтверджують сигнал. Розрив 600-секундного кроку скидає кандидата; запис після такого розриву не поповнює придатну історію. Вимога — достатній погодинний контекст, а не просто певне загальне число записів. Профіль активного кандидата заморожується; при зміні години використовується відповідна година цього профілю. Пропуски тут не додавалися.

Попередніх 180 записів перед втручанням недостатньо для мінімальних трьох попередніх дат. Додано **1008 оригінальних записів** (сім діб) перед незмінним 300-точковим фрагментом. Це консервативне заповнення повного семиденного контексту, а не твердження, що мінімум правила дорівнює 1008 записам.

| Властивість | Обидва запуски |
|---|---|
| Поданий ряд | 23.04.2016 07:20 — 02.05.2016 09:10 |
| Кількість вимірювань | 1308 |
| Незмінений початковий фрагмент | 30.04.2016 07:20 — 02.05.2016 09:10; 300 записів |
| Перед початком втручання | 1188 записів: 1008 доданих +180 початкових |
| Перший доступний sustained_high | 26.04.2016 08:00; 18 точок /3 дати; це ще не гарантує готовність усіх годин того дня |
| Gate перед публікацією хвоста | 01.05.2016 13:10: sustained_high ready/false; median60, MAD10, поріг110 Wh, факт100 Wh; 42 точки /7 дат |
| Контекст усіх 24 годин у gate | По42 точки /7 дат |
| ML у gate | IF, AE, residual ready; HGB20 і RF21 future forecasts ready |

**Gate справді виконувався до публікації решти 120 записів**, включно з втручанням. Потім Worker відновив стан із PostgreSQL, перевірив 1188 збережених Kafka payload-ів і продовжив той самий run. Попередні прогнози, включно з часом їх формування, залишилися незмінними. Це штатна зупинка/відновлення, не тест аварії чи вимірювання recovery time.

Джерела: `*-summary.json::first_high_available`, `readiness_gate`, `worker_phases`, `integrity`; у логах є `READINESS_GATE` до другого Worker ready.

## Дані, втручання, версії

Оригінальний UCI CSV монтувався read-only; шлях і SHA256 — `plan.json` / `environment.json`. `producer.appliances_dataset.iter_appliances` зберіг початкові `building_id=appliances-house-1`, `source_id=uci-appliances`, часові мітки й усі додаткові колонки. Ізоляція здійснюється за run/topic/group; зміна source_id зробила б артефакти несумісними.

У копії **лише Appliances +=450 Wh** у12 інтервалах 01.05.2016 13:20–15:10 включно. З15:20 — знову оригінальний ряд. Кожне вихідне/змінене значення збережено в `plus-450-summary.json::changes`. Валідовано всі1308 повідомлень кожного потоку, крок600 секунд і рівність решти полів; Wire records у БД повністю збігаються з реально опублікованими повідомленнями.

| Компонент | Версія |
|---|---|
| HGB20, primary_forecast | hgb-energy-v1-9bb48a66deb359e6; energy-features-v1 |
| RF21 residual reference / IF / AE / residual bundle | energy-anomaly-v1-14c9c4ce4d835763 |
| RF21 features | benchmark-energy-v1 |
| IF/AE features | energy-anomaly-20-v1 |
| ML threshold version | quantiles-v1-7ad1a9024c86e188 |
| IF /AE /residual q99 | 0.6747213487966208 /0.8288868594169614 /296.24602578530755 Wh |
| Rules | energy-rules-v2-a83ff8cf889d4981 |
| Hybrid | residual-high-v1-0e2d29e530f2d68e910d5ea5; residual OR sustained_high |
| Unanimous | configs/combined-rule-v1.json, combined-q99-v1-unanimous |

`MVP_ENERGY_RULES_ENABLED=true`; `EMAIL_NOTIFICATIONS_ENABLED=false`. Low не підключений. Застосовано наявні base`0003_email` і optional`0001_rules`; нових міграцій немає. Manifest перевіряється штатним `load_manifest`; артефакти не перенавчалися й не прирівнюються до оригінальних наукових bundle без окремого доказу ідентичності. Джерела точних моделей, конфігурацій та SHA: `*-summary.json::models`, `readiness_gate.high.configuration`, `environment.json::inputs_sha256`, `launch-config.json`.

## Результати проходження

| Перевірка /записи | Контроль | +450 Wh |
|---|---:|---:|
| run /topic /group | ei-stage2-aedbd416-control | ei-stage2-aedbd416-plus-450 |
| Measurements, унікальні event IDs | 1308 | 1308 |
| Forecasts (HGB20 +RF21, включно з warmup) | 2616 | 2616 |
| ML scores (IF +AE +residual) | 3924 | 3924 |
| Rule assessments (high +flatline +gap) | 3924 | 3924 |
| Hybrid decisions | 1308 | 1308 |
| Unanimous decisions | 1308 | 1308 |
| ML episodes за весь поданий ряд | 14 | 20 |
| Hybrid episodes за весь поданий ряд | 15 | 17 |
| Unanimous episodes за весь ряд | 1 | 1 |
| Message/offset duplicates; rejected | 0 /0; 0 | 0 /0; 0 |
| DB next_offset =Kafka committed =Kafka end | 1308 | 1308 |
| Notifications | 0 | 0 |

Це кількості збережених записів і епізодів, **не** Precision/Recall чи кількості підтверджених несправностей. У контролі є фонові сигнали; він не оголошується аномалійно чистим.

Коротка перевірка реакції **лише на12 інтервалах втручання** (до наступного етапу аналізу):

| Метод | Позитивних точок: контроль /копія | Перша позитивна точка копії | Затримка за часом вимірювань |
|---|---:|---|---:|
| residual | 0 /1 | 01.05 13:20 | 0 хв |
| AE | 0 /9 | 01.05 13:40 | 20 хв |
| IF | 0 /7 | 01.05 14:10 | 50 хв |
| sustained_high | 0 /7 | 01.05 14:10 | 50 хв |
| residual OR sustained_high | 0 /8 | 01.05 13:20 | 0 хв |
| Unanimous | 0 /0 | Не спрацював | Недоступна /немає виявлення |

Затримка тут не є обчислювальною latency чи повним event-matching оцінюванням. Джерело: `verification.json::preliminary_during_intervention_reactions`; усі вихідні точки — `*-points.csv`. Повернення початкового ряду не означає миттєвого припинення всіх сигналів: у копії residual ще true о15:20, high уже false. Повний подієвий аналіз і screenshots відкладено.

## Мінімальні перевірки та відтворення

- `pipeline.py`: усі записи валідні; лише12 енергетичних значень змінено; cadence, унікальність IDs, збіг wire records, **кожного** ledger payload hash і Kafka offset перевірено. Тристанний OR перевірено для всіх1308 точок кожного запуску.
- `api-checks.json`: усі сторінки10 REST-ресурсів для кожного run прочитано; кількості збіглися з БД, опційний канал available. Warmup/null збережені: ML156 warmup; hybrid435 unavailable і1 partial_positive в кожному run. Детальні статуси — `*-summary.json::statuses`.
- `verify.py` /`verification.json`: API-звірка кожного з300 початкових значень,900 ML-рядків,900 правил,300 hybrid-рішень,300 HGB20-прогнозів за target time та300 причинних RF21-прогнозів **кожного** run. Evidence, null/false/true, походження й dataset_naive збігаються. Каталог повертає11 каналів для кожного run.
- Syntax: AST усіх4 нових Python-скриптів пройдено. Production code не змінено; нові unit/повні тести, CI, browser E2E, training і performance не запускалися. Production Dashboard index і assets доступні через проксі; **візуальну працездатність браузера на цьому етапі не перевірено**.
- Стартова проблема прав нового Kafka volume усунута до першого replay; [startup-note.json](startup-note.json). Моделі/пороги не коригувалися; сценарій не повторювався.

Скрипти запускати з кореня цього worktree. Наявні докази й середовище **не переписуються**:

```sh
# Лише повторна read-only звірка вже збережених результатів:
python3 docs/integration/stage2/verify.py
# Відтворення ДВОХ replay тільки за наступним дозволом у НОВИЙ каталог:
python3 docs/integration/stage2/run.py --output /tmp/energy-stage2-new-evidence
```

Перед відтворенням потрібні вже перевірені локальні trusted artifacts/CSV за шляхами plan.json, наявні images та production `dashboard/dist` цієї інтегрованої версії. Скрипт не завантажує й не навчає моделі, не будує images. Після документаційних комітів перевіряє відсутність відмінностей runtime-коду від a6c1287. Повторно запускати `run.py` зараз не потрібно.

## Збережене середовище для етапів3–6

На завершення PostgreSQL, Kafka й API+Dashboard **залишено запущеними**; кінцеві Worker штатно зупинилися після finite replay. Дані збережено у named volumes, Kafka retention8760 годин (не безстроковий архів). Назви/URL — `environment.json`.

- Dashboard/API: **http://127.0.0.1:49308/**; API через той самий reverse proxy, `/health/ready` та `/api/...`.
- Контроль: http://127.0.0.1:49308/?run=ei-stage2-aedbd416-control&building=appliances-house-1&source=uci-appliances#analytics
- Копія: http://127.0.0.1:49308/?run=ei-stage2-aedbd416-plus-450&building=appliances-house-1&source=uci-appliances#analytics
- Network`ei-stage2-aedbd416`, контейнери`...-pg`, `...-kafka`, `...-api`.
- Volumes`ei-stage2-aedbd416-pg-data`, `ei-stage2-aedbd416-kafka-data` містять повний ряд, результати/стани й Kafka журнал; CSV у Git містять лише початкові300 точок кожного run для компактності.
- PG/Kafka host ports не опубліковані; frontend/proxy прив'язано до127.0.0.1. API слухає loopback усередині контейнера; local-only middleware не послаблено. PostgreSQL trust — лише для цієї локальної ізольованої Docker network без DB host port; це не production security configuration.
- API та Worker використовують один read-only bind цього worktree; trusted artifacts і CSV — окремі read-only mounts. API не виконує inference. Жодного notifier/Mailpit/зовнішнього SMTP не запускали.
- Якщо Docker буде зупинено, відновлення **тільки цих** контейнерів: `docker start ei-stage2-aedbd416-pg ei-stage2-aedbd416-kafka ei-stage2-aedbd416-api`; URL перевірити через`docker port ei-stage2-aedbd416-api 8099/tcp`. Не запускати інший Compose project поверх них.

Для наступного етапу є обидва збережені run, причинно суміщені прогнози, evidence, episode IDs і доступний read-only API. Фінальний аналіз, візуальна перевірка та скриншоти ще не виконані. Основне demo, робоча БД, Stage6 checkout, оригінальні CSV/artifacts і попередні докази не змінювалися; push/merge не виконувалися.
