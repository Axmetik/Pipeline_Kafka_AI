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
