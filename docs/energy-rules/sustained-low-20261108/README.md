# Sustained low v1 — користь і ціна додаткового правила

План, формулу, конфігурацію та всі 32 сценарії зафіксовано **до реалізації/виконання** (`8cc7334`); перевірений код до inference — `a228124`. Жодного підбору параметрів після результатів, перенавчання або інтеграції. Історичний UCI, той самий будинок і вже переглянуті дати: це контрольований дослід, не незалежний holdout або перевірка фізичних несправностей.

## Короткий висновок

| Що перевірено | Без low | З low | Внесок low |
|---|---:|---:|---|
| Нові18 подій споживання | 6/18 | 8/18 | +2 виявлення,0 втрат |
| Лише12 нових падінь | 0/12 | 2/12 | Сильні падіння до20% на60/120хв, початок22:50 |
| Відомі6 падінь | 0/6 | 0/6 | Не закрито |
| Парні епізоди, нові consumption-сценарії | 204 | 204 | net0, не підтверджені false positives |
| Парні епізоди, відомі6 | 33 | 33 | net0 |
| Епізоди у вікнах6 нормальних контролів | 0 | 2 | Неробочий режим і benign zero |

**Користь обмежена.** Два додаткові виявлення мали затримку50хв і нові парні переходи; всі інші нові падіння та відомі шість залишилися пропущеними. Low coverage нових цільових точок —50%; у новому OR рішення доступне на60.2% точок проти100% baseline. Основна причина null у цільових вікнах — непозитивний нижній поріг через широку історичну мінливість; це властивість зафіксованої формули, не доказ відсутності відхилення. common-ready-onset діагностика дає baseline3 → з low5 виявлень, але решта цілей не вилучена з основного знаменника.

Рекомендація: **залишити standalone experimental**, не вмикати автоматичні сповіщення або інтеграцію за цими результатами. Пороги/тривалість не змінювалися. Врахування календаря роботи та відрізнення легітимного низького навантаження потребують окремої погодженої методики, а не корекції параметрів за цим test.

Вартість low.process у повному scoring scope: медіана п’яти p50 **0.653мс**, p95 **0.766мс**. У rules-only scope — **0.491/0.819мс**. Для V2+cached residual+OR повний144-record потік: медіана510.55 →601.75мс; медіана парного overhead **+91.67мс (+18.00%)**. У full scoring парні delta нестабільні: **−4.97…+10.15%**, медіана **+0.51%**; це шумний локальний вимір, не доведене прискорення/стабільна оцінка overhead. Окремі p50/p95/total кожного повтору збережено нижче й у CSV.

## Незмінна формула

Окремий `processing/energy_low_rule.py`, `LowRuleConfig`, версія `sustained-low-v1-20c2dc71216149ab`. За попередні 7 календарних дат у тій самій годині потрібно не менше 18 придатних точок із 3 дат. Медіана m, MAD d; нижній поріг:

```text
L = m − max(3 × 1.4826 × d, 10 Wh, 0.5 × m)
```

Коли m<20 Wh — null/low_reference_energy; коли L≤0 — null/no_positive_lower_threshold. Інакше значення строго нижче L протягом 6 послідовних вимірювань формують review signal. Немає довільного від’ємного порогу або твердження про споживання нижче нуля. Шість інтервалів по600с представляють60 хв енергії, але від першого до шостого label —50 хв.

Погодинні профілі фіксуються до першої точки кандидата, окремо для всіх24 годин. Перехід години/півночі використовує власний заморожений поріг наступної години; його відсутність/непридатність повертає null із причиною й перериває кандидата. Розрив cadence також перериває кандидата. Немає поточного дня/майбутніх даних у reference. Окремий стан кожного building/source, точний retry останнього повідомлення не змінює стан. Durable recovery/ledger не додавався.

## Компактне порівняння: нові18 подій і відомі6 окремо

| Когорта | Метод | Виявлено / цільових | Coverage події | Медіана затримки, хв | Парні епізоди: весь потік / вікно події |
|---|---|---:|---:|---:|---:|
| new | residual | 2/18 | 100.0% | 0 | 162 / 0 |
| new | sustained_high | 4/18 | 100.0% | 60 | 51 / 0 |
| new | sustained_low | 2/18 | 50.0% | 50 | 0 / 0 |
| new | residual_high_or | 6/18 | 100.0% | 50 | 204 / 0 |
| new | residual_high_low_or | 8/18 | 60.2% | 50 | 204 / 0 |
| known_regression | residual | 0/6 | 100.0% | — | 33 / 2 |
| known_regression | sustained_high | 0/6 | 100.0% | — | 0 / 0 |
| known_regression | sustained_low | 0/6 | 50.0% | — | 0 / 0 |
| known_regression | residual_high_or | 0/6 | 100.0% | — | 33 / 2 |
| known_regression | residual_high_low_or | 0/6 | 50.0% | — | 33 / 2 |

## Що конкретно додав sustained_low

- **new:** об’єднання 6/18 → 8/18; додано 2, втрачено 0; компонентних low-only виявлень 2. Парні епізоди 204 → 204, net +0.
- **known_regression:** об’єднання 0/6 → 0/6; додано 0, втрачено 0; компонентних low-only виявлень 0. Парні епізоди 33 → 33, net +0.

| Когорта | Спрацювали компоненти за строгим onset-matching | Подій |
|---|---|---:|
| known_regression | none | 6 |
| new | none | 10 |
| new | residual | 2 |
| new | sustained_high | 4 |
| new | sustained_low | 2 |

Епізоди обох OR перебудовано з повних nullable потоків, не складено з компонентів. Строге зіставлення: початок сигналу в межах першого/останнього label події, без credit за раніше розпочатий епізод і без післяподієвого grace. Додаткові й втрачені event-matches по кожному випадку — у contributions.csv. [Окремо злиті/замінені початки епізодів](union-episode-deltas.csv): новий timestamp початку не завжди означає окрему нову фізичну подію.

## Coverage, пропуски та контролі

| Когорта | Метод | Availability всього потоку | Недоступні точки подій | Пропущені події | Нові переходи відносно raw-пари |
|---|---|---:|---:|---:|---:|
| new | residual | 88.5% | 0 | 16 | 2 |
| new | sustained_high | 65.4% | 0 | 14 | 4 |
| new | sustained_low | 51.7% | 67 | 16 | 2 |
| new | residual_high_or | 65.6% | 0 | 12 | 6 |
| new | residual_high_low_or | 52.6% | 56 | 10 | 5 |
| known_regression | residual | 88.5% | 0 | 6 | 0 |
| known_regression | sustained_high | 65.4% | 0 | 6 | 0 |
| known_regression | sustained_low | 50.1% | 21 | 6 | 0 |
| known_regression | residual_high_or | 65.5% | 0 | 6 | 0 |
| known_regression | residual_high_low_or | 50.3% | 21 | 6 | 0 |

Усі недоступні й пропущені випадки збережено; недоступність не підмінено негативним рішенням. Event recall знаменник не скорочено через warm-up. Окрема common-ready-onset діагностика та причини null збережені в summary.csv і unavailable-reasons.csv. Новий парний перехід зараховується лише коли raw flag=false в момент modified onset; raw null окремо невідомий.

| Контроль | Low: onsets / flagged points | Low coverage | Baseline OR → OR з low: onsets у вікні |
|---|---:|---:|---:|
| control-benign-zero | 1 / 1 | 50.0% | 0 → 1 |
| control-low-background | 0 / 0 | 0.0% | 0 → 0 |
| control-normal-night | 0 / 0 | 100.0% | 0 → 0 |
| control-raw | 0 / 0 | 50.0% | 0 → 0 |
| control-regular-nonwork | 1 / 7 | 100.0% | 0 → 1 |
| control-zero-background | 0 / 0 | 0.0% | 0 → 0 |

**Календар роботи відсутній.** Регулярні вихідні/неробочі години, законне вимкнення обладнання та нормальне нульове споживання можуть дати сигнал low відносно історії робочих днів. Це важливе обмеження, не встановлена несправність. Постійний фон0/5Wh має null через недостатній простір нижнього порогу — це не доказ нормальності. Нічний контроль змінює профіль у відповідну годину, а неробочий контроль явно моделює weekday/weekend у всій історії; це синтетичні нормальні режими, не fault-labels UCI.

Flatline і gap перевірено окремо в telemetry-рядках cases.csv/gaps.csv; вони не входять у18/6 consumption-цілей. Gap виявляється після наступного запису. Повторювані, зокрема нульові, значення не названо підтвердженим зависанням. Парні UCI-епізоди — **не підтверджені хибні тривоги**. Їх суми включають повторювані контексти окремих сценаріїв і не є унікальними фізичними днями/подіями.

## Обчислювальна вартість — окремо від очікування 6 інтервалів

Apple M1,16GiB RAM; існуючий CPU Docker image на Linux arm64, 1 CPU/2GiB/1thread, network=none. П’ять парних повторів, заздалегідь заданий чергований порядок. Однаковий незмінений потік144 вимірювань із May12 08:00, попередня історія7 календарних дат. Моделі/дані завантажено, історії прогріто, еквівалентні snapshot відновлено **до таймерів**. Немає файлового IO чи логування всередині вимірюваного циклу. Monotonic perf_counter_ns в одному процесі, clock sync між процесами не потрібна.

`rules_only` — v2 і той самий заздалегідь обчислений causal residual flag та OR; treatment додає low і розширений OR. `full_scoring` — незмінений StreamDetector (наявні IF/AE/RF/residual), v2 та OR, плюс low у treatment. Таким чином full scope включає чинні scorers, а не тільки дешеве порівняння residual із порогом.

| Scope | Variant | Медіана 5 record-p50, мс | Медіана 5 record-p95, мс | Медіана total144, мс |
|---|---|---:|---:|---:|
| full_scoring | baseline | 28.0345 | 33.0741 | 4121.63 |
| full_scoring | plus_low | 28.1310 | 31.6286 | 4089.43 |
| rules_only | baseline | 3.2158 | 4.6985 | 510.55 |
| rules_only | plus_low | 3.7123 | 5.8962 | 601.75 |

Це медіани **п’яти окремих оцінок**, не об’єднана вибірка всіх записів. Повні повтори:

| Scope | Повтор | Baseline total144, мс | З low total144, мс | Δ, мс | Δ,% |
|---|---:|---:|---:|---:|---:|
| rules_only | 1 | 509.22 | 600.89 | +91.67 | +18.00% |
| rules_only | 2 | 519.07 | 588.62 | +69.54 | +13.40% |
| rules_only | 3 | 488.39 | 625.99 | +137.60 | +28.17% |
| rules_only | 4 | 510.55 | 609.48 | +98.93 | +19.38% |
| rules_only | 5 | 513.09 | 601.75 | +88.66 | +17.28% |
| full_scoring | 1 | 4251.70 | 4683.05 | +431.35 | +10.15% |
| full_scoring | 2 | 4121.63 | 3916.96 | -204.67 | -4.97% |
| full_scoring | 3 | 4290.55 | 4089.43 | -201.12 | -4.69% |
| full_scoring | 4 | 4065.81 | 4086.47 | +20.66 | +0.51% |
| full_scoring | 5 | 4011.43 | 4100.52 | +89.09 | +2.22% |

Кожен record p50/p95 і виміряна в treatment окрема low.compute оцінка — в timing-summary.csv; кожний запис — timing-records.csv. Два додаткові читання monotonic timer навколо low включено у treatment totals, тому overhead не віднято штучно. Total також включає мінімальне збирання часових samples в RAM. Цей короткий вимір на raw-потоці не є worst-case benchmark заморожування профілів.

Існуючі сервіси/навантаження хоста не зупинялися. Docker VM, scheduling, thermal state й фонові процеси можуть спричиняти шум та навіть від’ємну paired total delta; її не можна трактувати як прискорення від нового правила. Немає висновків про універсальну вартість або production SLA. Очікування50хв від першого до шостого label — evidence latency, а наведені мілісекунди — compute time.

## Відтворюваність і перевірки

- [План](plan.md), [машинний протокол](plan.json), [manifest усіх32 випадків](scenarios.json), [нова конфігурація](low-config-v1.json).
- [Таблиці](results/run1/summary.csv), [усі case×method](results/run1/cases.csv), [внесок компонентів](results/run1/contributions.csv), [епізоди](results/run1/episodes.csv), [контролі](results/run1/controls.csv), [причини null](results/run1/unavailable-reasons.csv).
- [Повторення timing](results/run1/timing-summary.csv), [парні delta](results/run1/timing-paired-deltas.csv), [усі samples](results/run1/timing-records.csv), [контейнерне середовище](results/run1/timing-environment.json), [host](host-environment.json).
- [Автоматичний звіт](results/run1/report.md), [provenance](results/run1/provenance.json), [точна регресія відомих потоків](results/run1/v2-regression.json), [host audit](execution-context.json), [журнал](execution.log), [107 успішних тестів](targeted-tests.log).
- 64 Parquet містять fresh paired scores/flags, v2 evidence, нові low thresholds/evidence та OR contributors. Усі32 сценарії збережено, нові/відомі не об’єднувалися.
- Оригінальні scores відомих6 читалися **лише після** нового inference для точної регресійної звірки, не використовувалися замість результатів. Frozen inputs/weights/configs та старі результати незмінні.
- Batch low wrapper та прямий streaming process збігаються на кожному записі обох потоків усіх сценаріїв. `git_commit=null` у контейнерному provenance через відсутній git; hash runner/module незалежно перевірено на host проти pre-execution commit, початковий provenance не редагувався.

Для повторення з кореня repo потрібні ті самі наявні trusted artifacts/dataset/image. Не виконувати prepare/build/training. [reproduce.sh](reproduce.sh) приймає **нову** абсолютну output-directory, не перезаписує run1. [verify_results.py](verify_results.py) перевіряє збережені файли без inference/навчання.

## Графіки, зафіксовані до запуску

- [known-drop-s1-n6](results/run1/plots/known-drop-s1-n6.png)
- [new-drop-s1-n6-f0.2](results/run1/plots/new-drop-s1-n6-f0.2.png)
- [new-drop-s2-n12-f0.6](results/run1/plots/new-drop-s2-n12-f0.6.png)
- [control-normal-night](results/run1/plots/control-normal-night.png)
- [control-regular-nonwork](results/run1/plots/control-regular-nonwork.png)
- [control-zero-background](results/run1/plots/control-zero-background.png)
