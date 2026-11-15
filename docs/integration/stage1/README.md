# Етап 1 із 6 — аудит та єдина інтеграційна версія

Виконано тільки аудит, об’єднання вже реалізованого коду та цільові перевірки. Новий контрольний дослід, inference потоків, підбір аномалій, training, replay, повний CI/E2E/performance та нові скриншоти **не виконувалися**.

## Git та збереження робочих копій

Репозиторій: `Axmetik/Pipeline_Kafka_AI`. Єдина гілка для всіх шести етапів: **`integration/energy-intelligence-complete`**. Окремий worktree: `/Users/oslavych/Documents/Codex/energy-intelligence-integration`.

`git fetch origin` виконано без prune, push або зміни робочого дерева. Готової версії з усіма компонентами серед отриманих refs не було.

| Джерело | Точний head | Що використано |
| --- | --- | --- |
| origin/main | `e285efd926c5f9682243a4f571b35ee141c5af15` | Стабільна історія Stage 2–8B, ML/Kafka/PostgreSQL/API/Email |
| feature/sources-catalog, локальний | `516dfaef1f758bacbae84e2da59f26d6c530f22e` | База нового worktree: 11 карток, аналітика каналів, попередній демонстраційний дослід |
| origin/feature/sources-catalog | `5eab359e9e2956e4bdc0becbe9945ea653e38f18` | Remote ще без локального демонстраційного коміту; його не втрачено |
| feature/energy-rule-detectors | `c2bf4a29a03134b1276015277b7dd10b33f6d225` | Rules v2, atomic storage/recovery, hybrid, optional read-only API та RulePanel |
| feature/product-dashboard-p1 | `e778932b5075a029e9b9222e807141f956e961a9` | Наявні Огляд / Будівлі / Аналітика / Події |

Локальні merge-коміти `854f757` та `a074306` зберігають оригінальні коміти всіх трьох feature-гілок як предків. Фінальні routing-перевірки/звіт фіксуються окремим локальним комітом. Точні SHA й факт ancestry: [git-audit.json](git-audit.json). Rebase/force push/destructive reset/merge у main не виконувалися.

Початкова копія `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main` лишається на `516dfae`; наявний невідстежуваний `docs/energy-rules/` не змінювали й не включали до нових комітів. Стару копію Stage 6 `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI` не використовували. Worktree має власний frontend build; для перевірки тимчасово використано існуючі node dependencies, без npm install чи зміни lockfile.

## Компоненти: код, підключення та докази

«Підключено» означає наявний шлях даних у цій гілці, **не запуск цього шляху з реальним Kafka/ML на цьому етапі**.

| Компонент | Реалізовано | Підключено | Перевірено на цьому етапі | Межі |
| --- | --- | --- | --- | --- |
| Каталог 11 каналів + lights/T1–T9/RH_1–RH_9 | Так: api/channels.py, source_catalog.py, SourcesWorkspace, ChannelView | PostgreSQL → API → окремі UI/прямі посилання | 7 SQL API tests каталогу/каналів; frontend scope/null/unit tests; routing, TS/build | Нового CSV-завантаження чи browser replay не було. Оригінальні CSV-скриншоти з попереднього етапу збережено |
| Основний HGB20 | Так: EnergyProcessor/EnergyForecaster | Worker → mvp_forecasts purpose=primary_forecast → API → графіки | Поточний trusted artifact завантажено, checksum/dependencies/20 ознак перевірено; off/on/recovery parity з doubles | Реальний прогноз тут не обчислювали. RF21 не підміняє HGB20 |
| RF21 residual, IF, AE | Так: anomaly/residual.py, features.py, artifacts.py | Worker → mvp_scores → API → окремі шкали/пороги | Artifact compatibility; SQL/стани; causal contract і стара parity через doubles | Не новий експеримент якості; threshold q99 незмінний |
| sustained_high v2 | Так: processing/energy_rules.py | За opt-in: Processor → RuleLayer → assessments → optional API → RulePanel | Rules v2 unit regressions, JSON recovery та SQL-транзакції | За замовчуванням off; потрібна історія попередніх днів, недостатність = null |
| flatline, interval_gap | Так: той самий frozen v2 | Такий самий opt-in шлях; окрема категорія telemetry_quality | Flatline suffix/tolerance/drift, gap/time/source tests; UI семантика | Повторення не підтверджує несправність. Gap виявляється після наступного запису, не watchdog |
| residual OR sustained_high | Так: integration/rule_layer.py:hybrid_or | Atomic decisions/state/episodes → API → продуктові Analytics/Events і Appliances detail | Усі 9 true/false/null комбінацій; PostgreSQL lifecycle/rollback/duplicates/recovery; panel/routing contracts | Лише experimental; low не підключений; Email для hybrid відсутній |
| ML/Unanimous та hybrid episodes | Так: окремі старі й нові таблиці | У транзакції повідомлення з ledger/checkpoint; API тільки читає | 7-day snapshot/candidate, crash до/після commit, старі rows/formation times, null/gap/config closure | Реальне Kafka restart/replay у спільній версії ще не запускали |
| Product Dashboard P1 | Так: pages/, components/, App.tsx | Чотири сторінки + каталог; RulePanel у розширеній Analytics та Events | 26 вибраних frontend checks, TS та production build | Browser E2E на цьому етапі не було |
| Email | Так: notifications/, чинний outbox | ML individual + Unanimous → outbox/notifier/API/Events | 8 вузьких config/safety/message/outbox tests; SMTP mocked | Не перевіряли Mailpit/SMTP delivery; hybrid/rules не enqueue листів |
| Low-кандидати | Є standalone-код з rules-гілки | **Ні**, як і раніше | Не перевіряли тут | Не активовано й не включено до експериментального hybrid |

HGB/IF/AE/RF21 точні model/feature/threshold versions, hashes та джерело сумісних артефактів: [artifact-preflight.json](artifact-preflight.json). Поточні локальні trusted Docker artifacts доступні в **початковій копії**, не скопійовані в Git або нову worktree. Перевірка завантаження виконана в network=none контейнері, `/trusted` змонтовано read-only, без виклику predict/score.

## Конфігурація й шлях даних

- `MVP_ENERGY_RULES_ENABLED=false` — незмінний default. Settings приймає true/false/1/0, відхиляє помилкові значення. Compose тепер передає цей уже існуючий перемикач у контейнер.
- Rules: `energy-rules-v2-a83ff8cf889d4981`. Config: high=6 інтервалів, flatline=6, tolerance=0 Wh, context_days=7, minimum_context_days=3, minimum_context_points=18, MAD multiplier=3, min excess=50 Wh, relative excess=0.5.
- Для поточних artifacts layer version: `residual-high-v1-0e2d29e530f2d68e910d5ea5`. Він залежить від frozen config та residual model/feature/threshold versions. `low_enabled=false`.
- Уже наявна optional migration: `alembic -c alembic-rules.ini upgrade head`, revision `0001_rules`, окремий ledger `alembic_rule_layer_version`. Base revision лишається `0003_email`. Нової міграції не створено; backfill немає.
- Без optional schema й з flag=false старий worker працює без звертання до rule tables; API повертає `not_connected`. З flag=true відсутня schema — явна startup помилка, а не мовчазне ігнорування.
- Нові таблиці: `mvp_rule_assessments`, `mvp_hybrid_decisions`, `mvp_rule_states`, `mvp_hybrid_episodes`. ML `mvp_scores`, HGB/RF `mvp_forecasts`, Unanimous tables не замінені.
- Processor.compute чинного Runtime → RuleLayer.compute → Repository.persist + rules.persist → ledger/checkpoint → DB commit → незмінений Kafka commit. Duplicate delivery не повторює state update. Після exception Processor poisoned і вимагає recovery.
- JSON snapshot містить календарну історію до 7 попередніх днів, eligibility, flatline suffix, candidate count/start та **всі заморожені погодинні high references**. Є version/checksum/measurement-offset anchor. Це не recovery лише з останніх 144 записів.
- Read-only `/api/rule-assessments`, `/api/hybrid-decisions`, `/api/hybrid-events` мають той самий run/building/source/time scope; API нічого не рахує. Відсутність даних не перетворена на false.
- Спільний loadSourceSeries завантажує optional pages для Appliances; ChannelView lights/zones, як і раніше, запитує тільки channel-series, без чужих ML/rules/events.

## Вирішені конфлікти та мінімальні зміни

1. README, Pydantic schemas та TypeScript types: збережено обидва набори контрактів; видалено дублікати energy_scope/timestamp_reference після product merge.
2. data.ts: збережено shared scoped loader каталогу та завантаження optional rules/hybrid; прибрано конфліктний доступ до models поза його scope.
3. App.tsx: збережено Product P1 як існуючий основний UI та окрему маршрутизацію SourcesWorkspace. ProductShell має посилання на каталог із поточним контекстом; з каталогу повернення в product/advanced routes також зберігає run/building/source.
4. RulePanel підключено до вже існуючих продуктових Analytics/Events і Appliances detail. Його тип звужено до чотирьох фактичних полів даних; алгоритм/текстові рішення не змінювалися. Сховані раніше при merge панелі не втрачені.
5. index.html: збережено product title/theme та наявний favicon.
6. tests/run_suite.py: об’єднано списки API/PostgreSQL test modules. Повний runner не запускався.
7. Compose раніше не передавав MVP_ENERGY_RULES_ENABLED; Dockerfile не копіював alembic-rules.ini. Додано лише forwarding з default=false та COPY вже наявного config. Images не перебудовувалися. Міграції не запускалися на demo.

Нових детекторів, формул, порогів, model training або функціональних вимог не додавали. Старі reports зі словами «standalone/not connected» залишено як історичні докази відповідних фаз; актуальний стан описаний тут.

## Цільові перевірки та результати

| Перевірка | Фактичний результат | Доказ |
| --- | --- | --- |
| Rules-v2 + RuleLayer unit + real PG recovery + rule/catalog/channel API | **60 passed**, 0 skipped/errors/failures | [targeted-python.log](targeted-python.log) |
| Email config/safety/message mocks + 2 real-PG outbox scenarios | **8 passed**, 0 skipped/errors/failures | [targeted-email.log](targeted-email.log) |
| Product/RulePanel/rule-data/sourceData/ChannelView/useResource | **23 passed**, 6 файлів | [targeted-frontend.log](targeted-frontend.log), перший запуск |
| Новий integration-routing suite | **3 passed** | [routing-tests.log](routing-tests.log), фінальний запуск |
| TypeScript + production Vite build | Успішно | [typecheck.log](typecheck.log), [build.log](build.log) |
| Compose config default=false та opt-in=true; container addressing | Статично успішно, без запуску сервісів | [config-check.json](config-check.json) |
| Trusted manifest/dependency/feature/source binding compatibility | Успішно, **без inference** | [artifact-preflight.json](artifact-preflight.json) |
| Історичні artifacts/result blobs та старий науковий код | Незмінні | [preservation-check.json](preservation-check.json) |

Python модулі: test_energy_rules (41), test_rule_layer_unit (5), test_rule_layer_postgres (4), test_rule_api (3), test_source_catalog_api (3), test_channels_api (4). Email: 6 unit tests + test_episode_outbox_rollback_duplicates_continuation_and_cooldown, test_disabled_filters_no_backfill_and_mode_changes. SQL використовував приватну PostgreSQL18 у tmpfs, окрему internal network, без published ports; моделі в транзакційних тестах — doubles. Кожну тимчасову PG/мережу прибрано за власним унікальним ім’ям; named volumes не створювали й не видаляли.

Перший запуск нового routing test натрапив на відсутній scrollIntoView у jsdom, не production помилку. Додано scrollIntoView/scrollTo mocks лише у фікстуру; фінальний окремий запуск 3/3 успішний. Початковий trace збережений у targeted-frontend.log. Vite має warning bundle >500 kB; build успішний, оптимізацію bundle в цю інтеграцію не включали.

## Межа готовності та наступний етап

**Підтверджено інтеграцію коду й цільові контракти. Не підтверджено новий наскрізний дослід з реальними Kafka/ML/rules у цій спільній версії.** Код готовий як основа для наступного окремо погодженого етапу підготовки; не оголошуємо весь конвеєр повторно end-to-end валідованим.

Перед контрольним дослідом потрібно:

1. В окремому ізольованому DB/topic/group/run context змонтувати поточну worktree й trusted artifacts/CSV **read-only**. Вони лишаються за `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main/artifacts/mvp/docker` і `data/energy/raw/energydata_complete.csv`. У новому worktree немає скопійованих локальних моделей, datasets або .env.
2. Застосувати тільки вже наявні base та optional migrations у **новій тестовій БД**; для потрібного worker явно встановити `MVP_ENERGY_RULES_ENABLED=true`. Автоматично на demo цього не робили.
3. Визначити достатню історію для sustained_high: мінімум 3 попередні дні та 18 придатних same-hour точок; кандидат підтверджується шістьма інтервалами. Консервативна підготовка — сім повних діб (1008 записів) до кандидата з перевіркою доступності кожної потрібної години. Попередній 300-record replay не забезпечує такий контекст.
4. Окремо погодити/зафіксувати новий парний сценарій. Не переносити готові scores/flags старого досліду в новий потоковий run.
5. Перевірити Kafka → реальний worker → optional tables → API/UI, causal RF21, доступність high, hybrid provenance та епізоди — **на наступних етапах**. Якщо потрібна пошта, лише ізольований Mailpit для вже підтримуваних ML/Unanimous; hybrid Email поки не реалізований.

Не запускати integration.demo prepare/showcase без окремого рішення: такі команди можуть provisioning/train або зачепити звичний Compose project. Для цього завдання використовується нове ізольоване середовище й одна integration branch. Етапи 2–6 ще не виконані.
