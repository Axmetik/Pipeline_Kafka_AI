# Product P1 — чотири розділи Energy Intelligence

Дата: 2026-11-01. База: `e285efd926c5f9682243a4f571b35ee141c5af15`. Гілка: `feature/product-dashboard-p1`. P2 не реалізовано; merge не виконано.

## P0 та реалізація

[P0 assessment](../p0-assessment.md) зафіксовано **до** рефакторингу комітом `5d6deaa`. UI та тести: `27d2521`.

| Розділ | Реалізовано |
|---|---|
| Огляд | Поточна інтервальна енергія, наступний HGB20-прогноз із target/origin, чесний run-wide лічильник, відкриті індивідуальні епізоди серед завантажених останніх 50, реальне джерело/обсяг обліку, графік, Insights, переходи до аналітики та подій |
| Будівлі | Каталог зареєстрованих джерел за building ID; тип, scope, інтервал, timezone; вибір джерела в поточному run, окремі стани відсутності даних/невідомої сумісності/incompatible; retry і повідомлення про обмежений каталог |
| Аналітика | Існуючі графік, target alignment, Insights і таблиця останніх вимірювань. Scores, threshold/model versions, combined decisions та pipeline status — у закритій за замовчуванням розширеній секції |
| Події | Read-only індивідуальні та combined experimental episodes, джерело/час/стан/деталі, фільтр типу історії, окремі Email delivery records. Пріоритет фізичної несправності не вигадується |

Shared shell, URL selection і hash navigation зберігають один `useMonitor`, видиме вікно й обмежений polling близько 2 секунд під час переходів. Back navigation та старі `#models`/`#detectors` перевірено. Повторний вибір активного розділу повертає до його заголовка. Немає нових npm dependencies.

Каталог робить один bounded GET `/api/sources?limit=1000` при відкритті/зміні run/retry, а не кожні 2 секунди. Дані відсутнього в run джерела не підміняються переходом з каталогу: кнопка недоступна. UI не припускає узагальнення моделі на інші будівлі.

## Файли

- `dashboard/src/App.tsx`: спільний стан і композиція сторінок (~120 рядків замість ~950).
- Нові `dashboard/src/pages/{OverviewPage,BuildingsPage,AnalyticsPage,EventsPage}.tsx`.
- Нові `dashboard/src/components/{ProductShell,SourceFilters,KpiCards,ForecastChart,ScoreChart,MeasurementTable,EpisodeTable,DemoStatus,PipelineStatus,ModelRegistry}.tsx`, `presentation.ts`, `view.ts`.
- Нові `dashboard/src/navigation.ts`, `usePortfolio.ts`; `types.ts` додає optional metadata fields, які API вже повертає.
- `dashboard/src/style.css`, `dashboard/index.html`: узгоджений Graphite product layout і branding.
- `dashboard/vite.config.ts`: optional dev-only `DASHBOARD_API_TARGET`; старий default збережено.
- `dashboard/src/product.test.tsx`, `dashboard/e2e/product.spec.ts`, `product-live.spec.ts`: нові component/browser/read-only actual-API checks.
- `dashboard/e2e/{contracts,graphite,live,showcase}.spec.ts`: навігація до відповідних сторінок; наукові assertions збережено. Graphite captures тепер пишуть у ignored `test-results/`, а не перезаписують frozen evidence.
- `integration/browser_tests.py`: default frontend CI suite включає contracts, Graphite і product tests. Жодної зміни runtime pipeline.
- `docs/product/p0-assessment.md`, цей звіт, `screenshots/`: оцінка та підтвердження P1.

## Перевірки

| Перевірка | Результат |
|---|---|
| TypeScript `npm run typecheck` | PASS |
| Frontend `npm test` | **36/36**, включно з усіма попередніми 28 і 8 новими |
| Production `npm run build` | PASS; існуюче попередження про JS chunk >500 kB, без нових dependencies |
| Browser contracts + Graphite + product | **13/13** (2 + 7 + 4), Chromium у Docker; responsive 320/390/834/1280/1920 px |
| Opt-in browser test на існуючому API | **1/1**, GET-only; чотири сторінки, advanced scores, target/time labels, counts/checkpoint, без replay |
| Stage8B saved evidence та local protected hashes | **GO**, `saved_evidence_valid=true`, `local_hashes_verified=true` |

Один проміжний product-test мав неправильний Playwright role selector для native `<summary>`; виправлено на `.row-details summary`, повторний тест успішний. Це була помилка тесту, не зміна метрик або inference.

Тестовий browser timezone — **Pacific/Honolulu**, UCI labels залишаються literal `2016-…` без UTC/browser conversion. Перевірено null/warm-up/incompatible, HGB20 primary-only requests, API outage/retry, run/source filters, URL/back, розділення Email UTC і dataset clock. Backend/Kafka/recovery тести не змінені; повний workflow залишається обов’язковим CI. Локальні важкі replay/training/recovery не повторювалися на збереженому користувацькому середовищі.

CI: [workflow runs](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/workflows/tests.yml). Остаточний результат конкретного head наводиться в PR та підсумковому повідомленні; локальні результати не підміняють автоматичний CI.

## Реальні дані та скриншоти

Run `showcase-20261101-112252-c10e040c0b71`, `appliances-house-1 / uci-appliances`. Існуючий replay, не новий експеримент. До й після read-only перевірки: **300 measurements / 600 forecasts / 900 scores**, duplicates **0**, rejected **0**, next offset **300**. Джерело враховує Appliances, а не всю електроенергію будівлі.

Останній факт: **180 Wh за 600 секунд**, `2016-01-13 18:50:00`. Наступний primary HGB20 прогноз **265.2 Wh**, target `19:00`; aligned попередній прогноз у рядку `18:50` — **141.5 Wh**. Значення не змішуються. Вікно 144 точки; один завершений AE episode у run history, поза цим вікном. Email records для цього run відсутні; існуючий Mailpit іншого synthetic proof не використано як подію UCI.

- [Огляд](screenshots/overview.png)
- [Будівлі](screenshots/buildings.png)
- [Аналітика](screenshots/analytics.png)
- [Розширена аналітика](screenshots/analytics-advanced.png)
- [Події](screenshots/events.png)
- [Provenance та status before/after](screenshots/provenance.json)
- [SHA256 скриншотів](screenshots/sha256.json)

Скриншоти — actual UI/API, 1440px Chromium, без fixture interception. Додаткові synthetic fixture sources існують лише в тестах, не в продукті або evidence.

## Як переглянути без зміни поточного MVP

Основні Dashboard `http://127.0.0.1:8088` та Mailpit залишено працювати. Для frontend review з цієї feature branch:

```sh
cd ~/PycharmProjects/Pipeline_Kafka_AI_main/dashboard
npm ci
DASHBOARD_API_TARGET=http://127.0.0.1:8088 npm run dev -- --port 5173 --strictPort
```

Відкрити `http://127.0.0.1:5173/?run=showcase-20261101-112252-c10e040c0b71#overview`. Сервіси мають уже працювати; ця команда не запускає replay/training/migrations. P1 preview під час розробки працює на 5173; 8088 показує старий Docker image до окремо погодженої перебудови.

Відтворення read-only browser evidence (тільки за наявності run): `E2E_REAL=1 E2E_BASE_URL=<local-preview> E2E_PRODUCT_RUN=<existing-run> npm run e2e -- e2e/product-live.spec.ts`. `E2E_PRODUCT_CAPTURE=1` явно дозволяє оновити P1 screenshots/provenance. За замовчуванням цей test skip і не генерує даних. Для Docker Desktop тестового браузера localhost preview потребує лише додаткового конкретного Vite allowed host: `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=host.docker.internal`; API доступний через існуючий локальний proxy, не оприлюднюється.

## Обмеження та збереження

- Немає registry довільних human-readable names/addresses/площі: UI показує тільки building IDs і наявні source metadata. Реальні дані підтверджують одну будівлю; multi-building navigation перевірено fixtures, а не заявлено як перевірку ML-generalization.
- Каталог обмежено 1000 sources із явним truncation warning. Run-wide counters не є building totals. Історії містять останні 50 individual/50 combined/20 Email; це не повна статистика.
- Worker liveness `unknown`; checkpoint не є heartbeat. Ознаки `ready` не означають, що кожна модель вже вийшла з warm-up.
- Open-episode KPI охоплює лише завантажені individual records, а не загальний alert budget. Combined rule залишається frozen Unanimous. Scores не probabilities, episodes не підтверджені несправності.
- `data.ts`, `useMonitor.ts`, `insights.ts`, `combined.ts`, API, worker, checkpoint/recovery, model artifacts, thresholds та datasets не змінені. Stage2–8B scientific evidence й Stage6 checkout збережено. Docker volumes не очищались; основні сервіси не перебудовувались і не перезапускались.
- Події read-only, без workflow acknowledge/resolve та без вигаданої severity. Cost/tariff, авторизація і public deployment поза P1.

## Пропозиція P2 — лише план для погодження

1. Окремий versioned tariff contract: валюта, ціна за kWh, validity range, source/building applicability, правила податків/округлення та часовий пояс тарифного розкладу. Для dataset-naive не вгадувати timezone; time-of-use cost блокувати до явного обґрунтованого mapping.
2. Вартість тільки за завершеними валідними інтервалами: `Wh / 1000 × tariff_per_kWh`; пропуски не заповнювати нулями, показувати coverage і неповні періоди. Не масштабувати Appliances на весь будинок.
3. Розділити фактичну вартість, прогноз наступного інтервалу та явно позначені сценарії. Не називати сценарні різниці доведеними заощадженнями.
4. Погодити schema/migration та read-only API для tariff/cost перед реалізацією. Додати тести меж validity, decimal rounding, gaps, timezone ambiguity і source scope; лише потім product UI.

P2 не розпочато. Цей P1 очікує review; merge в main не дозволено автоматично.
