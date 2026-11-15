# Контекст одного завдання, етапи 1–6

- Репозиторій: Axmetik/Pipeline_Kafka_AI.
- Єдина локальна гілка: integration/energy-intelligence-complete.
- Єдиний worktree: /Users/oslavych/Documents/Codex/energy-intelligence-integration.
- Початкова копія збережена: /Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main, feature/sources-catalog @516dfaef1f758bacbae84e2da59f26d6c530f22e; її untracked docs/energy-rules не включати до комітів.
- Stage6 checkout /Users/oslavych/PycharmProjects/Pipeline_Kafka_AI не чіпати.
- Етап 1: аудит і локальна інтеграція виконані. Джерела: sources-catalog @516dfae, energy-rule-detectors @c2bf4a2, product-dashboard-p1 @e778932. Merge commits854f757/a074306; остаточний SHA читати git rev-parse HEAD після завершального локального коміту.
- Докази та точні версії: docs/integration/stage1/README.md, git-audit.json, artifact-preflight.json, preservation-check.json, config-check.json, targeted logs.
- Default rules switch=false. Optional migration0001_rules окремо від base0003_email; не створювати нову без потреби. Hybrid residual OR sustained_high; low вимкнено; telemetry_quality окремо.
- Sustained_high потребує попередніх днів (3/18 same-hour minimum, 7-day context), не лише144/300 вимірювань. Frozen rules-v2-a83ff8cf889d4981; нинішній layer residual-high-v1-0e2d29e530f2d68e910d5ea5.
- Перевірено60 Python targeted +8 email/mocked SMTP +26 frontend targeted, TS/build, Compose static defaults/forwarding, trusted artifact load без inference.
- Не перевірено реальний наскрізний replay після інтеграції; етапи2–6 чекати окремого завдання. Нового досліду/ін'єкції/скриншотів на етапі1 немає.
- Ні push, ні main merge, ні full CI/suite, ні training/performance. Основне demo/робочу БД/volumes не змінювати й не зупиняти. Artifacts/datasets read-only, попередні результати зберегти. Магістерську не редагувати, зовнішнього SMTP не використовувати.
- Email ML/Unanimous існує, hybrid/rule Email не підключений. Mailpit delivery на етапі1 не перевірявся.

## Етап 2/6 — виконано

- Runtime-код a6c1287ea8532aacb2d04c346d96d5d2595b9ad1 незмінний. Нові скрипти/докази/короткий звіт: docs/integration/stage2/README.md; plan.json, environment.json, launch-config.json, *-summary.json, *-points.csv, *-worker.log, api-checks.json, verification.json.
- Виконано РІВНО два real Kafka→Worker→PostgreSQL replay: ei-stage2-aedbd416-control та ei-stage2-aedbd416-plus-450 (run/topic/group однакові в межах сценарію, окремі між сценаріями). Не повторювати без нового дозволу.
- Оригінальний ряд 23.04.2016 07:20—02.05.2016 09:10;1308 точок/run. Додано1008 оригінальних точок до фрагмента30.04 07:20;1188 перед втручанням. +450Wh рівно12 інтервалів01.05 13:20—15:10;з15:20 початковий ряд.
- Rules=true, Email=false; low не підключено. Наявні міграції base0003_email +optional0001_rules застосовано до нової приватної БД. Пороги/правила/моделі незмінні.
- Перший non-null sustained_high26.04 08:00 (18точок/3дні). ДО публікації втручання виконано persisted readiness gate01.05 13:10: high ready/false, поріг110Wh,факт100;42точки/7дат у всіх24годинах, ML ready. Після gate відновлено Worker зі штатного checkpoint1188, збережені прогнози й generated_at не переписані.
- Кожний run:1308 measurements,2616 forecasts,3924 scores,3924 rule assessments,1308 hybrid,1308 Unanimous;0duplicates/rejected/notifications;DBcheckpoint=Kafka committed=end=1308. Warmup/null і тристанний OR перевірено, API counts та значення початкових300точок/run звірено;каталог11каналів.
- Реакції копії під час втручання: residual/hybrid13:20;AE13:40;IF/sustained_high14:10;Unanimous немає. У контролі у цих12точках позитивних рішень цих методів немає; фонові епізоди в решті ряду є. Не трактувати як нові узагальнені метрики якості.
- Середовище ЗАЛИШЕНО: http://127.0.0.1:49308/ ;networkei-stage2-aedbd416;контейнериei-stage2-aedbd416-{pg,kafka,api};namedvolumes...-pg-data/...-kafka-data. Worker finite replay завершено. Деталі URL/run і відновлення доступу —stage2/README.md/environment.json. Не демонтувати/не очищати; основне demo не зачіпати.
- Стартовий Kafka permission issue виправлено тільки для нового власногоvolume до replay, описаноstartup-note.json. Production code не змінено;додаткових дослідів/навчання/повноїsuite/CI/browser E2E немає.
- Етапи3–6 ще не починалися;фінальні аналіз/скриншоти відкладено. Наступний дозвіл користувача потрібен для продовження завдання;не запускайте додатковий replay автоматично. Push/main merge заборонені.

## Етап 3/6 — виконано, лише аналіз

- Read-only аналіз повних 1308-точкових запусків етапу 2. Жодних replay/inference/training/нових сценаріїв/тестів/CI/screenshots. Звіт і stdlib-скрипт: docs/integration/stage3/README.md та analyze.py; за замовчуванням повністю офлайн із source-api.json.gz.
- У копії на 12 інтервалах: residual 1true/11false; AE 9/3; IF 7/5; Unanimous 0/12; high 7/5; hybrid 8/4. Null=0 для всіх; контроль 0true/12false. Перші true: residual/hybrid 13:20, AE 13:40, IF/high 14:10. Затримки за event labels 0/20/50 хв, не processing latency.
- Hybrid: 1 residual-only +7 high-only, 0 both; охоплення 1/12→8/12 (+58,33 п.п.). Чотири false 13:30—14:00: НЕ один суцільний епізод. Збережені hybrid-епізоди 13:20—13:20 (close13:30) та 14:10—15:20 (close15:30). High-послідовність 14:10—15:10, negative15:20 — обчислена з assessments, власних DB high-епізодів немає.
- Додаткові сигнали після повернення: residual15:20 (новий одиничний епізод), AE15:30 (новий одиничний епізод), IF15:20/15:30 (продовження), hybrid15:20 (продовження, джерело residual), high/Unanimous0. Усі false15:40. Residual/hybrid16:50 спільні в обох потоках, не додаткові. Closure updated_at звірено з received_at наступного негативного вимірювання; це не commit ack.
- До втручання рішення потоків ідентичні. Порівняння шести методів на спільних 752 доступних точках: residual6, AE4, IF6, Unanimous1, high24, hybrid30 true. Отже high додає й фонові сигнали; це не підтверджені false positives. Знаменники/виключені null для кожного методу — paired-periods.csv/json. Немає втрачених позитивних чи зміни доступності між потоками.
- Flatline: 15 спільних позитивних точок у восьми послідовностях до втручання; під час/після0. Interval_gap: перший null, решта1307 false/run. Позитивний gap-сценарій не перевірявся.
- Збережено source-flags, перераховані епізоди, 12-точкову таблицю, post-return аналіз, перевірку сумісності/OR/джерел. Повний аналіз і таблиці в stage3. Скриншоти етапу4+ чекають дозволу. API/PG/Kafka залишено без змін; Email=false. Нічого не публікувати/не зливати.
