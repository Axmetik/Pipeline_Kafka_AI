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

## Етап 4/6 — UI-перевірка та screenshots

- Перевірено живий read-only Dashboard http://127.0.0.1:49308/ тієї самої версії a6c1287; фактичні frontend asset SHA збігаються з Stage2 build, API image/mount/code/settings підтверджено. Жодних replay/inference/зміни даних/rebuild/restart/міграцій/тестової suite/CI. Email=false; основне demo й Stage6 checkout не чіпали.
- docs/integration/stage4/README.md: підписи, обмеження й рекомендації. Збережено8 PNG (каталог, контроль, копія, ML scores, останній rules/hybrid, hybrid episodes, післядія, контрольний фон), нативні незмінені JPEG-оригінали, crops/SHA в screenshots.json та DOM-докази. PNG — лише форматні копії/дозволені фрагменти, без редагування даних чи масштабування.
- UI не має довільного часового діапазону/brush. Використано144 точки:01.05 09:20—02.05 09:10; HGB20 target до09:20. Контроль/копія мають однакову автоматичну шкалу0–600Wh. Журнал — увесь run/source, не лише графік чи втручання.
- Вузька verify.py звірка:1296 API-рядків/run незмінні проти Stage3 export;288 фактичних і290 HGB20 rendered точок зіставлено з persisted values/target timestamps;15/17 hybrid episode UI rows збігаються з контрольними/зміненими DB результатами. ML visible-window counts9/10/3 — не target counts7/9/1.
- UI коректно показує два hybrid епізоди13:20—13:20 і14:10—15:20,closed/negative, і спільний фон16:50 в обох run. Прогалини: немає історії high/hybrid flags; показано лише фінальне рішення02.05 09:10. Close-measurement timestamps13:30/15:30 в UI не виведено. Походження обох компонентів за весь епізод не означає обидва true в кожній точці; точка15:20 походить лише від residual (Stage3/API). High-епізод із flags не називати persisted.
- Чотири false13:30—14:00, high=false15:20/hybrid=true, усіfalse15:40 підтверджені read-only API, але не заявляємо відображення їхніх flags у відсутній UI історії. UI-код не змінювали/нових панелей не додавали.
- Для основного тексту рекомендовано02+03 (парні осі) та06 (два hybrid-епізоди);04 для thresholds/додатків. Фінальний SHA читати з локального коміту Stage4. Не push/merge. Наступний етап5 і Email перевірку автоматично не починати.

## Об’єднання в main — нове погоджене завдання

- 23.11.2026 користувач дозволив об’єднати готові компоненти застосунку в main. Це скасовує попередню заборону push/merge лише для цього завдання; нових експериментів, deploy/rebuild чи етапів5–6 не дозволено.
- Поточна інтеграційна версія включає Stage1–4, каталог, Product P1, default-off rules/hybrid. Перед PR оновлено застаріле резюме README без змін моделей, параметрів, наукових результатів або старих доказів.
- Об’єднання виконувати звичайним PR зі збереженням історії та гілок, після успішних чинних CI-перевірок; не обходити branch protection і не використовувати skip ci/force push. Автоматичний CI GitHub може запускати власні ізольовані тести; локальне demo й дані не чіпати.
