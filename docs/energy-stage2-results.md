# Energy Pipeline — результати етапу 2

Робоча гілка: `feature/energy-pipeline`. База: `02c7361`.
Зміни реалізовано локально; злиття в main не виконувалося.

## Реалізація

Окремий Energy Dataset → Kafka → Preprocessing → HGB/persistence → Parquet сценарій.
IoT producer/consumer, детектори та їхні типові параметри не змінено.
Спільний EnergyProcessor застосовується в навчанні та потоковому inference.
Фактичні вимірювання та прогнози збережено в окремих архівах зі стабільними Arrow-схемами.
Контракт підтримує dataset/smart_meter та Wh/kWh; модель цього етапу приймає
інтервальну енергію appliances за 600 секунд. Потужність W та накопичувальні показники відхиляються.

Часи розділено: measurement_timestamp/forecast_origin — час вихідного вимірювання,
forecast_generated_at_utc — фактичний час виконання прогнозу, forecast_target_timestamp —
цільова мітка t+600 секунд. Історичним даним часовий пояс не призначався.

## Фактичний експеримент

- Джерело: UCI Appliances Energy Prediction, DOI 10.24432/C5VC8G, CC BY 4.0.
- Оригінальних записів: 19735.
- SHA-256 CSV: `2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`.
- Версія моделі: `hgb-energy-v1-d4803b89fb86f5e9`.
- Ознаки: `energy-features-v1`; 20 колонок.
- Train: 15782 цілей, 2016-01-11T18:10:00 — 2016-04-30T08:20:00.
- Test: 3946 цілей, 2016-04-30T08:30:00 — 2016-05-27T18:00:00.
- Поділ 80/20 за часом цілі; shuffle та early stopping вимкнені.
- Горизонт: наступний 10-хвилинний інтервал; energy у Wh, не W.
- Вікно історії: 7 послідовних вимірювань; перші 6 — insufficient_history.
- Пропуски енергії не заповнюються; розриви скидають історію.
- Скейлінг/перенавчання у consumer відсутні.
- Параметри не підбиралися за результатами тестової вибірки.

| Модель | MAE, Wh | RMSE, Wh |
|---|---:|---:|
| HistGradientBoostingRegressor | 28.34712524 | 61.10721634 |
| Persistence | 26.63963507 | 66.43671272 |

HGB має нижчий RMSE, але вищий MAE: це не безумовне покращення над baseline.
Оцінювання послідовне: раніше отримані test-вимірювання використовуються як історія,
але модель залишається незмінною. Ознаки не використовують майбутні значення.

## Перевірки

Повний набір: **23/23 тести успішно**, 8.503 с, пропусків немає.
Включено старі IoT-тести та обидва Kafka smoke tests. Нові тести покривають одиниці,
валідацію, timestamp/timezone, lag/rolling, gaps, дублікати, ізоляцію джерел,
незалежність навчання від test-значень, save/load, метрики та окремі архіви.

Повний реальний replay запустив producer.energy_producer та consumer.energy_consumer:

- Надіслано й прийнято 19735 валідних записів.
- Відхилено 1 навмисно некоректне повідомлення; потік продовжився.
- Збережено 19735 записів прогнозів, з них 19729 готових.
- 6 записів прогріву мають null-прогнози.
- Зіставлено всі 3946 test-прогнози з фактичними вимірюваннями.
- Offline і streaming прогнози збігаються (перевірка rtol=atol=1e-12); метрики однакові.
- Останній прогноз поза датасетом не має actual і не включається в оцінювання.
- Тимчасові Kafka topics видалено після перевірок.

PyArrow виводив повідомлення про обмежений доступ до характеристик CPU у sandbox;
тести й replay завершилися з кодом 0.

## Відтворення

```sh
OMP_NUM_THREADS=1 python -m ai.train_energy_forecaster --dataset data/energy/raw/energydata_complete.csv --output artifacts/energy/new-run
OMP_NUM_THREADS=1 RUN_KAFKA_SMOKE=1 python -m unittest discover -s tests -v
OMP_NUM_THREADS=1 python -m ai.verify_energy_replay --dataset data/energy/raw/energydata_complete.csv --experiment artifacts/energy/new-run --output artifacts/energy/new-replay --full-dataset --inject-invalid
```

Команди запускаються з кореня репозиторію у його .venv; Docker/Kafka мають працювати.
Шляхи вихідних експериментів повинні бути новими. Дані та моделі не включаються в Git.

## Створені файли

- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/ai/energy_forecaster.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/ai/train_energy_forecaster.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/ai/verify_energy_replay.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/consumer/energy_consumer.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/processing/energy_processor.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/processing/energy_schema.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/producer/appliances_dataset.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/producer/download_appliances.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/producer/energy_producer.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/schemas/energy-message-v1.schema.json`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/storage/energy_storage.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/energy_helpers.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/test_energy_dataset.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/test_energy_features.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/test_energy_forecasting.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/test_energy_kafka_smoke.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/tests/test_energy_schema.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/docs/energy-stage2-results.md` (цей звіт)

## Змінені файли

- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/.gitignore`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/README.md`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/config.py`
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/storage/parquet_storage.py`

## Артефакти експерименту

- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/artifacts/energy/appliances-hgb-v1` — model.joblib, metadata.json, metrics.json, test_predictions.parquet.
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/artifacts/energy/replay-v1` — producer.log, consumer.log, replay_report.json, окремі Parquet-архіви.
- `/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/artifacts/energy/validation/tests.log` — повний журнал тестів.

## Залишені обмеження

- Kafka auto-commit, буферизація Parquet та відсутність транзакції між двома архівами.
- Історія й дедуплікація лише в пам'яті; рестарт або rebalance потребують прогріву,
  можливі повтори та втрата незаписаних буферів. Один consumer writer на каталог.
- Запізнілі записи відхиляються, resampling і checkpointing ще немає.
- Значення timestamp у датасеті — вихідна мітка; її положення відносно інтервалу не доведено.
- Модель навчена на одному будинку; перенесення на інші будівлі не оцінювалося.
- Energy-ознаки підготовлені для подальших IF/Autoencoder адаптерів;
  навчання та калібрування енергетичних детекторів відкладено згідно з погодженим планом.
- PostgreSQL, FastAPI, dashboard не реалізовувалися.
