# Пристрої та джерела — каталог і персональна аналітика

Дата: 2026-11-15. Гілка `feature/sources-catalog`, від `origin/main` (`e285efd926c5f9682243a4f571b35ee141c5af15`).
Код перевірено на `5012a3712dab2f7035254d776870db3170307d64`; наступний документаційний коміт додає цей звіт і збережені докази.
Ця гілка не переносить незлитий experimental rules/hybrid-шар з `feature/energy-rule-detectors`.

## Сценарій і представлення

У навігації додано «Пристрої та джерела». Каталог дозволяє вибрати запуск і будівлю, шукати за ID джерела/будівлі, перегортати сторінки та перейти до аналітики. Перехід із моніторингу зберігає run/building. Одне джерело має окрему природну картку без фіктивних сусідів. Для завантаження, порожнього каталогу, порожнього пошуку й помилки API передбачено окремі стани.

Приклади URL після стандартного локального запуску актуального frontend/API:

```text
http://127.0.0.1:8088/?view=sources
http://127.0.0.1:8088/?view=sources&run=YOUR_RUN&building=YOUR_BUILDING
http://127.0.0.1:8088/?view=source&run=YOUR_RUN&building=YOUR_BUILDING&source=YOUR_SOURCE
```

Вкладки аналітики: огляд, детектори, епізоди, сповіщення, відомості про джерело. Огляд містить останню інтервальну енергію, наступний прогноз HGB20, цільовий час, графік факт/прогноз і описову статистику видимого вікна. Обмежені вікна — 72/144/288 вимірювань; за замовчуванням останні доступні історичні дані, без фільтра «сьогодні». Breadcrumbs і повернення до каталогу зберігають контекст; пряме посилання працює після reload. Невідоме джерело не підміняється іншим.

UCI позначено джерелом датасету сукупної енергії побутового обладнання будівлі, без вигаданого розподілу за приладами. Активність невідома без heartbeat. Wh — енергія за інтервал, не W. Dataset-naive labels не перетворюються через часовий пояс браузера. Null/warmup/incompatible/gap не перетворюються на нуль або негативну оцінку. Для несумісності показано доступну причину й явно зазначено, що API не надає детальнішої діагностики прив’язки моделі. Прогноз формується для наступного інтервалу та зіставляється за target timestamp; RF21 не підміняє HGB20.

## API та ізоляція

Новий read-only `GET /api/source-summaries`:

- обов’язковий `run_id`; фільтри `building_id`, `source_id`, `search`;
- стабільна cursor pagination за `(building_id, source_id)`, default limit 100, max 1000; UI запитує 24;
- для кожної пари повертає binding-поля, останню measurement timestamp/energy/feature status, фактичний received_at і чесний `activity_status=unknown`;
- latest визначається за UTC measurement time для aware джерел / local measurement label для naive, з ID tie-breaker;
- один window-function SQL для карток плюс один bounded DISTINCT для будівель, незалежно від кількості карток — без N+1;
- building options обмежено 1000 з явним `buildings_truncated`; пошук literal/escaped, параметризований;
- лише джерела, для яких є вимірювання у вибраному запуску; без вигаданих пристроїв і лічильників запуску на картках.

Аналітика використовує наявні `/api/sources`, `/api/measurements`, `/api/forecasts?purpose=primary_forecast`, `/api/anomaly-scores`, `/api/events`, `/api/combined-decisions`, `/api/combined-events`, `/api/notifications`. Кожен джерельний запит обмежено run + building + source. Спільний `loadSourceSeries` використано також у чинному моніторингу. Наявні ScoreChart, CombinedPanel і NotificationsPanel повторно використано без зміни алгоритмів або доставки.

Каталог оновлюється приблизно кожні 5 с, аналітика — кожні 2 с після завершення попереднього запиту. Є abort/deadline, backoff до 30 с, ручний retry та cleanup. Ключ ресурсу включає повний контекст; старі дані не відображаються під заголовком іншого джерела, запізніла відповідь не може замінити актуальну.

## Перевірки

| Перевірка | Фактичний результат |
| --- | --- |
| Нові catalog API + наявні API PostgreSQL regression | 18 passed, 0 skipped; з них 3 нові |
| Frontend unit suite | 35 passed у 8 файлах; з них 7 нових source/polling tests |
| TypeScript і production build | Passed (`tsc -b` + Vite) |
| Python syntax | 4 нових/змінених модулі перевірено через ast.parse |
| Browser, реальні FastAPI + PostgreSQL + production frontend | Passed |
| Browser page/неочікувані console errors | 0; навмисний API 503 під час retry-тесту є очікуваним |
| Desktop / tablet / mobile | 1440 / 900 / 390 px, без горизонтального прокручування сторінки |

Browser перевірив: каталог з одним джерелом, кілька джерел із однаковим ID у різних будівлях, run/building switching, direct link/reload, збереження контексту переходу з моніторингу, порожні результати, invalid source, warm-up із null-прогнозом і нульовим фактом, incompatible, відновлення після API 503, вкладки детекторів/епізодів/сповіщень, довгі ID, незмінений чинний моніторинг. Timezone браузера — Pacific/Honolulu; naive label залишився незміщеним. Гранична перевірка довгого ID виявила max-content overflow заголовка — виправлено max-width/min-width; перевірка також чекає завершення ResizeObserver Recharts після зміни viewport, не приховує переповнення сторінки.

Докази: [verification.json](verification.json), [API log](api-tests.log), [browser-verification.json](browser-verification.json), [provenance](fixture-provenance.json).

Команди перевірки:

```sh
# У середовищі з реальною ізольованою PostgreSQL:
RUN_API_INTEGRATION=1 MVP_TEST_DATABASE_URL=... python -m unittest discover -s tests -p 'test_source_catalog_api.py' -v
RUN_API_INTEGRATION=1 MVP_TEST_DATABASE_URL=... python -m unittest discover -s tests -p 'test_api_integration.py' -v
npm --prefix dashboard test
npm --prefix dashboard run build
# Explicit isolated browser harness, existing images, Chrome, saved local prediction files required:
python3 tests/source_catalog_browser.py
```

Нові PostgreSQL-тести класифіковано в наявний API CI suite, frontend tests входять у чинний frontend job. Повний Kafka/performance benchmark не запускався. Успіх CI для фінального коміту не заявляється без окремо перевіреного Actions run.

## Походження скриншотів

Скриншоти зроблено в реальному Chrome через production frontend і справжні SQL-запити до тимчасової PostgreSQL, без mock HTTP-відповідей для показаних даних:

- 144 оригінальні значення UCI та вже збережені HGB20 прогнози імпортовано з `artifacts/mvp/docker/hgb/test_predictions.parquet`;
- detector scores імпортовано з оригінального Stage 4 `docs/energy-anomaly/results/scores/test-clean.parquet`, з його власними model/threshold versions;
- джерело — `appliances-house-1` + `uci-appliances`; числові прогнози/факти не змінювалися і заново не обчислювалися;
- run/relational IDs, received_at/generated_at, окремі episode/outbox записи — лише операційні fixtures, не архівний час реального inference і не новий науковий результат;
- додаткові будівлі, warm-up, incompatible і довгі ID існували тільки у disposable fixture; у робочій базі нічого не створювалося;
- SMTP/notifier не запускався, листи не надсилалися. Оригінальні й Docker артефакти не ототожнюються: це presentation fixture зі збереженими версіонованими результатами.

| Представлення | Desktop | Mobile |
| --- | --- | --- |
| Каталог | [catalog-desktop.png](catalog-desktop.png) | [catalog-mobile.png](catalog-mobile.png) |
| Аналітика | [detail-desktop.png](detail-desktop.png) | [detail-mobile.png](detail-mobile.png) |

## Межі й збереження середовища

API лишається localhost-only; нової міграції, write endpoint, auth/external deployment, ML inference/training, порогів, Kafka-контрактів або recovery змін немає. Docker спочатку був вимкнений; відкрито Docker Desktop тільки для ізольованих перевірок. Тимчасові контейнери/мережі очищено за їхніми унікальними іменами; named volumes не створювалися й не видалялися. Демонстраційний Compose project, Stage 6 checkout, datasets і ML artifacts не змінювалися. Текст магістерської не редагувався.

Потрібні API та frontend цієї самої гілки: старий розгорнутий API ще не має `/api/source-summaries`. Гілка не розгортається автоматично. Каталог не є CRUD-реєстром пристроїв, не визначає Online/Offline і не обчислює частку джерела у споживанні будівлі. Повнота списку запусків/будівель обмежена зазначеними API limits; source pages пагінуються. Епізоди — останні 50, сповіщення — останні 20 на джерело, з явними підписами меж. Статистика — лише видиме вікно. Пошук/каталог мають bounded response, але віконний SQL переглядає вимірювання відповідного run/source scope; це не твердження про постійний час запиту на довільному масштабі.

Vite попереджає про bundle >500 kB; build успішний. Нову UI-бібліотеку не додано. Merge й deployment не виконуються.
