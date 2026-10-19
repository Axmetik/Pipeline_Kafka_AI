# Stage 4 — Energy Anomaly Detection: план для погодження

Статус: пропозиція, реалізацію не розпочато. Нова гілка після погодження:
`feature/energy-anomaly-detection` від main із завершеними Stage 2/3.

## 1. Архітектура

Окремий offline цикл: dataset → chronological partitions → causal features →
fit preprocessing/models → calibrate thresholds → validation selection → frozen
artifacts → test evaluation. Потоковий процес тільки завантажує артефакти;
онлайн-перенавчання й автоматичної зміни порогів у цьому етапі немає.

Окремий consumer із власною Kafka group читає той самий energy topic:
validation → source-isolated history → IF + AE + residual → anomaly Parquet.
Чинний energy_consumer і його HGB-прогнози продовжують працювати незалежно.
IoT-код, старі моделі, протоколи та результати не переписуються.

Результат на кожен доступний detector/measurement: event_id, building/source,
measurement_timestamp, detected_at_utc, detector/version, feature_version,
score, threshold, flag, status (ok/warmup/gap/incompatible), а для residual —
forecast_origin, forecast_target_timestamp, forecast model/version, prediction,
actual і signed residual. Історичним naive timestamps не додаємо timezone.
Мітки синтетичних подій зберігаються окремо й не передаються детекторам.

## 2. Ознаки та сумісність прогнозувальника

IF і AE отримують однакові 20 причинних ознак чинного EnergyProcessor:
поточна енергія, 6 лагів, rolling mean/std, температура/вологість, індикатори
пропусків і циклічні часові ознаки. Використовуємо одну реалізацію offline/online.
Заповнювач пропусків і scaler навчаються лише на train. Не інтерполюємо з майбутнього.
Невалідну енергію не перетворюємо на модельну аномалію: це data-quality event.

Для residual пропонуємо **окремий RF із параметрами Stage 3**:
400 дерев, max_depth=12, min_samples_leaf=10, seed=42. Він використовує точні
21 ознаку benchmark.features: ті самі 20 + seasonal_energy_wh. HGB залишається
альтернативою; висновок Stage 3 не переглядаємо.

Готовий RF Stage 3 навчений на train+validation, тому повторно використовувати
його для калібрування на цій validation не можна. Створюємо новий Stage 4
артефакт RF, навчений лише на train Stage 4, без зміни старого артефакту.
Це окремий прогнозувальник лише для residual; чинний HGB із 20 ознаками не замінюємо.
Адаптер RF перевіряє точний порядок/версію 21 ознаки, horizon=600, source binding,
одиниці й timestamp semantics; 20→21 не доповнюємо нулями й не робимо silent fallback.

Для прогнозу на t RF використовує ознаки з origin=t−10 хв і seasonal E(t−24 год).
Прогноз зберігаємо до приходу фактичного E(t); лише після його приходу обчислюємо
r(t)=E(t)−forecast(t). Потім оновлюємо історію і прогнозуємо наступну точку.
Для порівняння всіх детекторів використовуємо однакові точки після спільного
прогріву: 144 послідовних попередніх вимірювання плюс поточне фактичне значення.
Після розриву не позначаємо warmup як норму; окремо рахуємо coverage.

## 3. Детектори і пороги

Пропонований фіксований стартовий набір (записати в протокол до виконання):

- IF: 300 дерев, max_samples=256, random_state=42; score = −score_samples,
  більший score означає більшу незвичність. Не використовуємо contamination
  як оцінку справжньої частоти аномалій; рішення визначає наш калібрований поріг.
- AE: PyTorch MLP 20→16→8→16→20, ReLU у прихованих шарах, лінійний вихід,
  standardized-feature MSE як score; Adam lr=0.001, batch=128, максимум 100 епох.
  Early stopping з patience=10 на останніх 15% train; preprocessing fit лише на
  перших 85% під час цього вибору. Потім refit на всьому train на обрану кількість
  епох, заново fit preprocessing на train. CPU, фіксовані seeds, eval/no_grad.
- Residual: абсолютна помилка |r(t)| у Wh; знак зберігаємо для пояснення.
  Нормалізацію за режимами навантаження не додаємо без окремої перевірки.

Для кожного детектора tau = емпіричний 99-й перцентиль score на незміненій
calibration, flag = score > tau. Цільовий номінальний alarm budget — 1%; це
не гарантія 1% на майбутніх даних. Додаткові наперед задані точки 0.5% і 2%
показуємо як sensitivity analysis; не обираємо з них найкращу за test.
Основний режим — рішення на кожне вимірювання, без прихованого згладжування.

## 4. Часовий протокол і leakage

Зберегти часові межі Stage 3 для train/test. Його 3,946 validation targets
розділити послідовно навпіл:

| Частина | Кількість | Призначення |
|---|---:|---|
| Train | 11,699 | Fit RF, IF, AE, preprocessing; AE internal early stopping |
| Calibration | 1,973 | Пороги на незмінених даних, без fit моделей |
| Validation | 1,973 | Порівняння детекторів на окремих synthetic scenarios |
| Test | 3,946 | Одноразова підсумкова оцінка за зафіксованим протоколом |

Точні timestamp boundaries та membership manifest фіксуємо до запуску.
Після calibration/validation моделі НЕ перенавчаємо на цих частинах: інакше
пороги більше не відповідатимуть моделі. Вибір детектора — validation event F1
за обмеження background alarm rate ≤1%; tie-break: нижча затримка, потім нижчий
alarm rate. Якщо ніхто не проходить обмеження, не оголошуємо готового переможця.
Усі три детектори все одно звітують test results.

Відомі минулі значення з попередньої частини можуть прогрівати наступну;
майбутні — ніколи. Ін'єкції не перетинають межі вибірок. Після ін'єкції всі
лаги/rolling/прогнози перебудовуємо з реально доступного зміненого потоку,
а не з прихованого оригіналу. Оригінал доступний лише evaluator.

Весь UCI test уже переглянуто, а параметри RF раніше вибиралися з використанням
Stage 3 validation (нині calibration/validation). Новий refit усуває пряме
навчання RF на calibration, але не скасовує історичного використання цих даних.
Це повторне дослідження на відомому корпусі, не незалежний holdout; нові seeds
ін'єкцій також не роблять будинок або часовий ряд незалежним.

## 5. Контрольовані аномалії

Оригінальний CSV залишається незмінним. Створюємо окремі копії replay і manifest:
scenario_id, event start/end, тип, сила, seed, original/modified energy та
поточкові мітки. Позитивний клас — саме втручання генератора, а не діагноз
реальної несправності. Фонові дані не мають перевіреної розмітки справжніх аномалій.

| Сценарій | Втручання | Тривалість |
|---|---|---|
| Імпульс угору | Додати 2/4/6 train-IQR енергії | 1–3 інтервали |
| Падіння/нуль | Множник 0.5/0.2/0 із збереженням невалідних значень поза сценарієм | 1–6 |
| Тривалий зсув | +1/2/3 train-IQR або множник 1.5/2/3 | 6–18 |
| Дрейф | Лінійне наростання від 0 до 1/2/3 train-IQR | 12–36 |
| Зависання лічильника | Повтор останнього доступного значення | 6–36 |
| Контекстне навантаження | Додаткове плато в низькоактивні години, визначені лише train | 6–18 |

IQR обчислюємо лише на train; нульовий IQR має зафіксований у протоколі fallback.
Значення залишаються невід'ємними Wh/600 с. Сценарії пропусків, дублювання,
неправильних одиниць і out-of-order тестуємо окремо як data-quality, не змішуємо
з Precision/Recall моделей. Нуль чи плато в реальному житті можуть бути нормою;
їхня мітка тут відома тільки тому, що це контрольована підміна.

Окремі набори за типом/силою та один змішаний набір. Пропонована частка змінених
точок змішаного набору — 2%, п'ять seeds на validation (101–105) і п'ять інших
на test (201–205). Планувальник фіксує фактичну частку, не допускає накладання
подій і не обирає їх за scores моделей. Повторні seeds — варіації ін'єкцій на
тому самому ряді, а не незалежні будинки.

Для ізольованих сценаріїв перед подією даємо щонайменше добу незміненого контексту.
У змішаному потоці зберігаємо всі наслідки втручання в історію; не очищуємо її
за ground-truth. Тривоги після завершення ін'єкції рахуємо окремо як recovery-tail
і включаємо у фонові помилки — не приховуємо їх виключенням незручних точок.

Звичайні незмінені піки залишаються контрольними прикладами. Поріг train P90
використовуємо тільки для стратифікації оцінки (звичайні/високі навантаження).
Для реальних даних вихід — кандидат на аномалію; істинну несправність потребує
підтвердження експерта, журналу обладнання або зовнішніх міток.

## 6. Метрики

Поточкові Precision, Recall, F1 та FPR=FP/(FP+TN), окремо для типів, сили й seeds.
На незміненому UCI звітуємо **background alarm rate**, а не доведений true FPR:
відсутність ін'єкції не доводить нормальність оригінального спостереження.
Для синтетичного benchmark FPR/Precision умовні щодо synthetic labels.

Події: один alarm може відповідати максимум одній ін'єкції; event recall —
частка подій з alarm усередині [start,end]; event precision/F1 — після фіксованого
групування послідовних alarm-точок. Не застосовуємо point adjustment, який
перетворює всі точки події на TP через єдине влучання.

Затримка = час першого alarm у події мінус onset; median/p95 для виявлених
подій, частка пропущених окремо, без присвоєння їм нульової затримки. При кроці
10 хв мінімальна роздільність такої оцінки — один інтервал. Окремо заміряємо
wall-clock processing latency, яка не залежить від історичної дати чи replay speed.
Також: alarms/day, coverage/warmup, звичайні високі навантаження, recovery tails.
Усі детектори оцінюємо на однакових timestamps; пропуски score не стають TN.

## 7. Файли після погодження

Нові модулі (шляхи від кореня репозиторію):

- `anomaly/features.py`, `anomaly/artifacts.py`: спільні ознаки, контракти,
  source binding, version/checksum та перевірки сумісності.
- `anomaly/detectors.py`: IF/AE inference і уніфікований score API.
- `anomaly/residual.py`: RF-21 adapter, pending forecasts, exact timestamp join.
- `anomaly/train.py`, `anomaly/calibrate.py`: offline fit і пороги.
- `anomaly/inject.py`, `anomaly/evaluate.py`, `anomaly/run_experiment.py`:
  контрольовані сценарії, метрики, відтворюваний runner.
- `consumer/energy_anomaly_consumer.py`, `storage/energy_anomaly_storage.py`:
  окремий stream inference і Parquet archive.
- `configs/energy-anomaly-v1.json`, `docs/energy-anomaly/protocol.md`:
  параметри й протокол, коміт до виконання експерименту.
- `docs/energy-anomaly/results/`: per-point scores/labels, events, метрики,
  графіки, manifests, hashes, versions і звіт.
- `tests/test_energy_anomaly_*.py`, `tests/test_energy_anomaly_kafka_smoke.py`.

Змінити README з командами; CI залежності — лише за необхідності. Наявний
runner автоматично включить нові unit/Kafka tests за його naming convention.
Моделі — в окремому ignored `artifacts/energy-anomaly/v1/`. Старі результати
та benchmark-код використовувати без редагування.

## 8. Перевірка завершення

Unit: future perturbation не змінює попередні scores; fit/imputation/calibration
не бачать наступних вибірок; правильні residual timestamps; 20/21 mismatch
відхиляється; source isolation; gaps/warmup; save/load parity; deterministic
injection manifests; контрольні метрики й event matching.

Kafka: реальний replay нормального й ін'єктованого потоку → окремий consumer →
всі три scores → Parquet; порівняння з offline replay за ключами і толерантністю.
Ground-truth labels недоступні inference. Перезапуск і дублікати перевіряємо
окремо, з явним звітом про відновлення історії/coverage. Не заявляємо exactly-once:
чинні обмеження Kafka offset і Parquet залишаються задокументованими.

Потім повний експеримент, всі старі/нові тести та GitHub Actions. Реалізація —
лише після погодження цього плану; merge Stage 4 потребуватиме окремого дозволу.

Технічне джерело для напрямку score IF:
https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
