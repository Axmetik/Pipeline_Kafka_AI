# Реальні канали Appliances Energy Prediction

Розширення `feature/sources-catalog` від `b73e65aa273b6d187ecce5b613592d73ce208d43`. Попередній каталог і його докази залишено у батьківському каталозі; цей каталог містить окремі нові перевірки.

## Аудит і походження

[Офіційний опис UCI](https://archive.ics.uci.edu/dataset/374/appliances+energy+prediction) є джерелом відповідності колонок зонам та одиниць. Локальний оригінальний CSV: `data/energy/raw/energydata_complete.csv`. [dataset-audit.json](dataset-audit.json) містить SHA-256, межі, кількість рядків і придатних чисел для кожної колонки: 19 735 рядків, 2016-01-11 17:00:00 — 2016-05-27 18:00:00. У цій копії всі 20 використаних колонок мають 19 735 числових значень. Це аудит файла, а не твердження про повноту будь-якого replay у базі.

| Категорія / канал | Колонки CSV | Одиниці | Призначення |
| --- | --- | --- | --- |
| Побутові прилади / `appliances` | `Appliances` | Wh за 600 с | Чинна аналітика, HGB20, детектори, епізоди, історія сповіщень |
| Освітлення / `lights` | `lights` | Wh за 600 с | Власний графік та описова статистика |
| Кухня / `zone-1` | `T1`, `RH_1` | °C, % | Два окремі узгоджені графіки |
| Вітальня / `zone-2` | `T2`, `RH_2` | °C, % | Так само |
| Пральня / `zone-3` | `T3`, `RH_3` | °C, % | Так само |
| Кабінет / `zone-4` | `T4`, `RH_4` | °C, % | Так само |
| Ванна кімната / `zone-5` | `T5`, `RH_5` | °C, % | Так само |
| Зовні будівлі, північна сторона / `zone-6` | `T6`, `RH_6` | °C, % | Це зовнішня зона, не погодна станція `T_out` |
| Кімната для прасування / `zone-7` | `T7`, `RH_7` | °C, % | Два окремі графіки |
| Кімната підлітка №2 / `zone-8` | `T8`, `RH_8` | °C, % | Так само |
| Спальня батьків / `zone-9` | `T9`, `RH_9` | °C, % | Так само |

Немає індивідуальних рядів холодильника, пральної машини тощо. Назва «Пральня» означає зону температури/вологості, а не споживання пральної машини. Картки не встановлюють серійний номер або наявність конкретного фізичного пристрою.

## Зберігання й API

Аудит коду підтвердив: чинний `producer/appliances_dataset.py:iter_appliances` уже переносить необхідні дані. `T1`/`RH_1` потрапляють у `environment.temperature_c` / `environment.relative_humidity_pct`, інші колонки — в `additional_parameters`; `rv1`/`rv2` адаптер відкидає. `storage/postgres/repository.py` зберігає початкове повідомлення в `measurements.wire_record`. Тому зміни імпорту, Worker, схеми БД, міграції й backfill не потрібні.

Логічна ідентичність: **run_id + building_id + source_id + channel_id**. Нових фіктивних sources/measurements у робочій БД немає. Енергія приладів читається з `energy_wh`; інші канали — зі своїх полів архівного `wire_record`. Розпізнавання UCI-набору вимагає dataset + scope appliances + ключів `lights`, `T2`, `RH_2`; окремий ключ температури довільного джерела не оголошується кухнею. Розпізнавання базується на контракті колонок адаптера, а не на криптографічному засвідченні походження довільного payload.

- `GET /api/channels?run_id=...&building_id=...&source_id=...&category=zones&search=Кухня`: bounded каталог, cursor pagination, останнє значення навіть якщо воно null, назва, колонки, одиниці, capabilities та unknown activity.
- `GET /api/channel-series?run_id=...&building_id=...&source_id=...&channel_id=zone-1&limit=144`: точки та min/max/mean/count для **повернутого вікна**. Підтримує start inclusive/end exclusive, time_basis та cursor. Статистика наступної сторінки стосується лише тієї сторінки; сторінки не оголошуються повним історичним рядом.
- Ліміти: 1–1000, default catalog 24; UI 24 картки, вікна 72/144/288. Каталог виконує 2 SELECT/CTE запити незалежно від кількості карток (дані + будівлі). Window SQL переглядає вимірювання scope; стала швидкість на довільному масштабі не вимірювалася.
- Старі `/api/sources`, `/api/source-summaries`, `/api/measurements`, forecasts/scores/events/notifications не змінювалися. Нові series не читають таблиці моделей або подій.

Відсутні ключі/JSON null/нечислові значення не стають нулями. Якщо необхідних архівних полів немає, додаткові канали не вигадуються. Старі fixture-записи з порожнім wire_record не дають карток зон. Немає завантаження CSV всередині API чи прихованого доповнення робочої БД.

## UI

Категорії, будівля, запуск, пошук за назвою/ID/колонкою; прямі посилання `?view=source&run=...&building=...&source=...&channel=lights` або `channel=zone-1`. Посилання без channel продовжує відкривати чинну аналітику приладів. Зміна повного scope очищає попередні дані через useResource; polling 5 с без паралельних запитів, retry/backoff, cleanup.

Освітлення та зони мають окрему сторінку без запитів forecasts/scores/events/notifications. Доступні останнє значення, графік, мінімум/максимум/середнє/count. Невідомі значення показуються тире, пропуски не з’єднуються. Історичний час збережено як naive label без конвертації браузером; час надходження позначено операційним. Вікно відкривається від останніх наявних записів, не від сьогодні. Активність джерела невідома; API availability не є heartbeat. Чужих прогнозів чи подій на нових каналах немає.

## Виконані перевірки

| Перевірка | Результат | Доказ |
| --- | --- | --- |
| Реальна PostgreSQL: чинні API + попередній каталог + нові канали | 22 passed, 0 skipped | [api-tests.log](api-tests.log) |
| Frontend unit | 38 passed у 9 файлах | [verification.json](verification.json), [frontend-tests.log](frontend-tests.log), `ChannelView.test.tsx` |
| TypeScript, production build | Успішні | [typecheck.log](typecheck.log), [build.log](build.log); Vite warning про bundle >500 kB |
| Chrome → production UI → API → тимчасова PostgreSQL | Успішно; 1440/900/390 px | [browser-verification.json](browser-verification.json) |
| Усі додаткові канали проти оригінального CSV | 10 рядів × 144 точки; кожна точка зіставлена за timestamp і контекстом; також межі та statistics | [fixture-provenance.json](fixture-provenance.json), browser script |
| HGB20, детектори й події Appliances | Залишилися доступними у власному каналі | browser-verification.json |
| Нові канали не завантажують модельні результати | Перевірено мережеві запити + API-контракти | browser script, unit tests |

SQL-тести перевіряють всі колонки/одиниці, null замість fallback на Appliances, ізоляцію run/building/source, search і literal %, категорії, cursor/filter mismatch, часові межі, timezone validation, limits, порожні результати та сталу кількість SQL-запитів. Браузер перевірив фільтри, пошук назв і колонок, прямі посилання/reload, відсутній scope, вікно 72/144, API 503/retry, регресію HGB20/детекторів/подій, відсутність overflow та runtime errors. Для фіксування 503 використано окрему тестову підміну помилки; дані скриншотів отримано справжнім SQL.

```sh
# У наявному середовищі з окремою тестовою PostgreSQL:
RUN_API_INTEGRATION=1 MVP_TEST_DATABASE_URL=... python -m unittest discover -s tests -p 'test_channels_api.py' -v
# Також фактично виконані test_source_catalog_api.py і test_api_integration.py.
npm --prefix dashboard test
npm --prefix dashboard run typecheck
npm --prefix dashboard run build
# Лише ізольоване середовище; потрібні наявні локальні artifacts/CSV/images та Chrome:
SOURCE_UI_RELATIVE_OUTPUT=docs/sources-catalog/channels-20261115 \
SOURCE_UI_SCRIPT=dashboard/e2e/channels-smoke.mjs \
python3 tests/source_catalog_browser.py
```

Новий PostgreSQL test module включено до чинного API CI suite. Фінальний CI не вважається успішним без перевіреного Actions run. Повні Kafka/E2E/performance кампанії та нові експерименти не запускалися; виконано саме ізольовану browser-перевірку каталогу/API.

## Походження скриншотів

Одноразова PostgreSQL у tmpfs, окремі Docker network/контейнери, localhost ephemeral порт; жодних підключень до робочої бази. Сервіси основного demo не перебудовувалися й не перезапускалися. Контейнери перевірки мали repository read-only; notifier не запускався, EMAIL_NOTIFICATIONS_ENABLED=false. Контейнери й мережу прибрано за власними унікальними назвами; datasets, named volumes, artifacts та Stage 6 checkout не змінювалися.

Нові поля для знімків взято безпосередньо з CSV через чинний адаптер, зіставлено за **timestamp + building/source**, не позицією рядка. 144 timestamp з уже збереженого HGB-файла задають демонстраційне вікно 2016-04-30 08:30:00 — 2016-05-01 08:20:00. Енергію CSV додатково звірено зі збереженим фактом; жодного нового ML inference. SHA CSV/HGB/scores та очікувані значення збережено у fixture-provenance.json. Saved HGB20 та Stage 4 scores слугують лише регресійним presentation fixture; operational received/generated timestamp і episode/outbox fixture не є новими науковими результатами. Run ID `source-saved-review` та окремі тестові контексти створено тільки у цій disposable БД. Контрольні не-UCI/warm-up/довгі ID записи не входять у показані канали UCI.

| Представлення | Desktop | Mobile |
| --- | --- | --- |
| Каталог усіх категорій | [catalog-desktop.png](catalog-desktop.png) | [catalog-mobile.png](catalog-mobile.png) |
| Освітлення | [lights-desktop.png](lights-desktop.png) | [lights-mobile.png](lights-mobile.png) |
| Кухня: температура + вологість | [zone-1-desktop.png](zone-1-desktop.png) | [zone-1-mobile.png](zone-1-mobile.png) |

Desktop-знімки зроблено після reload та стабілізації viewport, щоб виключити compositor artifact після mobile → desktop resize; перевірено єдину DOM-оболонку і візуально переглянуто знімки.

Моделі, пороги, метрики дослідів і магістерську не змінено. Злиття та розгортання не виконувалися. Щоб побачити канали у звичайному середовищі, потрібні API/frontend цієї гілки та записи зі збереженими UCI wire columns; автоматичного rebuild основного demo цей етап не робить.

Наявний до початку роботи невідстежуваний `docs/energy-rules/` залишено без змін і не включено до цих комітів.
