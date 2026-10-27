# Наукова готовність і перевірені результати

Дата аудиту: 27.10.2026. Числа нижче походять зі збережених predictions/scores/raw,
а не з нового навчання або replay. [Read-only verifier](verify_evidence.py) та
[машиночитний результат із SHA джерел](verified-values.json) дозволяють простежити
перерахунок. `pyarrow` використано тільки для читання Parquet; моделей verifier
не імпортує/не завантажує. Окрема metadata inspection trusted Docker artifacts
не виконувала inference: [operational snapshot](operational-snapshot.json).

## 1. Датасет і межі предметної області

[Офіційна картка UCI](https://archive.ics.uci.edu/dataset/374/appliances%2Benergy%2Bprediction)
описує 19 735 спостережень одного low-energy household, крок 10 хвилин,
Appliances у Wh; це не W. DOI: 10.24432/C5VC8G, Candanedo (2017), CC BY 4.0.
Локальний CSV має SHA-256
`2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`.
Перевірено 19 735 рядків, 2016-01-11T17:00:00—2016-05-27T18:00:00.

У системі відтворюється історичний ряд для моделювання streaming ingestion.
Це не сучасна телеметрія фізичного smart meter. Контракт зберігає interval energy
Wh за 600 s; історичні naive labels не локалізуються у вигаданий UTC.
Розширювані building/source IDs не доводять accuracy на кількох будівлях;
моделі bound до конкретного джерела. Узагальнення потребує інших даних.

## 2. Stage 2 — чинний primary HGB20

Первинні матеріали: [review validation](../energy-review-followup.md),
`ai/train_energy_forecaster.py`, локальний
`artifacts/mvp/docker/hgb/{metadata.json,metrics.json,test_predictions.parquet}`.
Локальний Docker artifact перевірений за власним manifest SHA, не прирівнюється
за binary identity до початкової macOS-моделі. Test predictions повторно зведено
до MAE/RMSE без запуску predict.

Хронологічно 15 782 train / 3 946 test; горизонт 600 s, 20 ознак.
Train targets 2016-01-11 18:10—2016-04-30 08:20, test з 08:30 того дня.

| Модель | Test MAE, Wh | Test RMSE, Wh |
|---|---:|---:|
| hgb20 | 28.34712524 | 61.10721634 |
| persistence | 26.63963507 | 66.43671272 |

**Persistence має нижчий MAE, HGB20 має нижчий RMSE.** Твердження «ML краще за
baseline за всіма метриками» для Stage 2 неправдиве. Менший RMSE означає меншу
квадратичну помилку в цій вибірці, не автоматичний доказ кращого управління будівлею.

## 3. Stage 3 — порівняльний benchmark

[Protocol](../forecast-benchmark/protocol.md), [selection.json](../forecast-benchmark/results/selection.json),
[metrics.csv](../forecast-benchmark/results/metrics.csv),
[test_predictions.csv](../forecast-benchmark/results/test_predictions.csv),
[splits.json](../forecast-benchmark/results/splits.json),
[metadata.json](../forecast-benchmark/results/metadata.json).

| Split (target time, 2016) | N | Діапазон |
|---|---:|---|
| train | 11699 | 2016-01-12T17:00:00 — 2016-04-02T22:40:00 |
| validation | 3946 | 2016-04-02T22:50:00 — 2016-04-30T08:20:00 |
| test | 3946 | 2016-04-30T08:30:00 — 2016-05-27T18:00:00 |

Train/validation/test не перемішуються; origin передує target на 600 s.
Усі чотири методи мають ті самі 3 946 test targets. Verifier підтвердив actual
із CSV, Persistence=actual(origin), Seasonal Naive=actual(target−24 h), унікальність
і порядок split targets. Немає fixed-origin multi-step forecast: раніше отримані
test actuals можуть ставати історією наступного one-step прогнозу.

RF/HGB мають 21 causal feature (20 Stage 2 + seasonal), explicit median imputer:
fit лише train під час tuning; фінальний refit — train+validation. Test не входить
у підбір параметрів. HGB early_stopping=False; seed42, один thread.
`benchmark/selection.py` не отримує test; вибір збережено перед test predictions.
Causality/split/imputation тести присутні в успішному базовому CI.

| Модель | Validation MAE, Wh | Validation RMSE, Wh | Test MAE, Wh | Test RMSE, Wh |
|---|---:|---:|---:|---:|
| persistence | 28.441460 | 71.973308 | 26.639635 | 66.436713 |
| seasonal_naive | 60.255955 | 127.374457 | 53.623923 | 112.108981 |
| random_forest | 26.443458 | 61.236618 | 26.630385 | 59.374521 |
| hist_gradient_boosting | 26.544914 | 60.992506 | 26.132523 | 58.920212 |

Validation winner залишається **Random Forest**, MAE 26.44345773 проти HGB21
26.54491375. Його parameters: n_estimators=400, max_depth=12, min_samples_leaf=10,
n_jobs=1, random_state=42. HGB21: learning_rate=.05, max_iter=100,
max_leaf_nodes=15, l2_regularization=0, random_state=42.

На вже переглянутому test HGB21 має найменші MAE/RMSE, але це **описовий результат**,
не підстава змінювати зафіксованого переможця. RF test MAE покращений щодо
Persistence лише приблизно на 0.0347%, HGB21 — на 1.9036%; статистичну значущість
не доведено. Offline HGB21 не є primary HGB20; різні ознаки, train partitions,
параметри/refit не дозволяють приписати різницю лише назві алгоритму.

### Пікове навантаження та timing

Train-only P90=210 Wh, strict actual>210; 312 test points. Високі навантаження
не є автоматично аномаліями. Peak MAE/RMSE також звірено з predictions.

| Модель | Peak MAE, Wh | Peak RMSE, Wh |
|---|---:|---:|
| persistence | 150.288462 | 199.223653 |
| seasonal_naive | 250.512821 | 288.870479 |
| random_forest | 127.317528 | 176.812507 |
| hist_gradient_boosting | 126.282739 | 175.824965 |

[Saved timing](../forecast-benchmark/results/timing.csv): median one-row prediction
0.75 µs Persistence/Seasonal, 9618.4375 µs RF, 422.792 µs HGB; 1280 calls each.
Це imputation+predict, не Kafka end-to-end latency: loading/features/DB виключені.
Вимірювання залежить від середовища й не використане для вибору winner.

**Test уже переглядався у Stage 2; це не unseen holdout.** Одна будівля й один
split, без доказу міжбудинкової узагальнюваності або статистичної переваги.

## 4. Stage 4 — anomaly methodology

[Protocol](../energy-anomaly/protocol.md),
[model metadata](../energy-anomaly/results/model_metadata.json),
[thresholds](../energy-anomaly/results/thresholds.json),
[metrics](../energy-anomaly/results/metrics.csv),
[diagnostic audit](../energy-anomaly/diagnostic-audit.md).

Train 11 699 (до 2016-04-02 22:40); calibration 1973 (04-02 22:50—04-16 15:30);
validation 1973 (04-16 15:40—04-30 08:20); test3946 (04-30 08:30—05-27 18:00).
Preprocessing fit train-only. RF hyperparameters мають історичну Stage 3 validation
exposure; Stage 4 RF заново fit лише Stage 4 train, не Stage 3 train+validation weights.
IF: median+scaler, 300 trees/max_samples256. AE: 20→16→8→16→20, MSE; внутрішній
хронологічний train split для epochs, потім refit train-only. Немає adaptive online fit.
Residual=abs(actual−previously formed RF forecast), у Wh. IF — negative score_samples;
AE — reconstruction MSE standardized features. Абсолютні scores між методами
не порівнюються і не є probability.

| Detector | q98 | q99 (primary) | q99.5 |
|---|---:|---:|---:|
| isolation_forest | 0.653787801 | 0.674721349 | 0.692888172 |
| autoencoder | 0.616504879 | 0.828860602 | 1.090164976 |
| residual | 219.028595347 | 296.246025785 | 399.178309167 |

Пороги — calibration quantiles, strict score>threshold, не підібрані на test.
6 типів (spike/drop/level_shift/drift/stuck/context_load), 3 severity, 5 seeds,
90 окремих +5 mixed сценаріїв на split; 144 preceding context points. Копії даних,
оригінали не змінюються. Параметри/seed/placement train-derived, без score-based
placement; події не перетинаються, minimum gap144, досяжна частка може бути <2%.
Stuck severity repetitions не означають різні фізичні amplitudes.
Історія після injection перераховується зі змінених даних, tail144 не виключений
з background errors. Detector labels не використовують під час inference.

Event matching: contiguous flagged episodes, greedy earliest unmatched overlapping
event, максимум один match/event/episode, strict [start,end], no point adjustment.
**Episode може початися до injection і за overlap отримати match**; це не доказ,
що саме втручання спричинило тривогу. Post-hoc diagnostic onset/clean-counterpart
аналіз не змінює початкові правила чи метрики.

## 5. Stage 7B і mixed-test порівняння

Повторний аудит взяв saved Parquet flags/labels і manifests п'яти mixed test seeds,
незалежно перерахував point/event metrics і звірив їх із Stage 4/7B CSV.
Stage 7B не навчає нові detectors, не створює нових незалежних сценаріїв.

| Метод | Precision | Recall | Point F1 | Event recall | Event F1 | Clean background rate, % |
|---|---:|---:|---:|---:|---:|---:|
| isolation_forest | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.709579 |
| autoencoder | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.582869 |
| residual | 0.00606061 | 0.00273973 | 0.00377358 | 0.05000000 | 0.01111111 | 0.810948 |
| or | 0.00289855 | 0.00273973 | 0.00281690 | 0.05000000 | 0.00888889 | 1.723264 |
| majority | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.304105 |
| unanimous | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.00000000 | 0.076026 |

Це macro means за 5 seeds, не pooling усіх точок. Background rates — окремий
незмінений test, не synthetic FPR і не confirmed false positives. Original UCI
не має надійної fault ground truth. Mixed synthetic FPR IF/AE/residual:
isolation_forest=0.00723664, autoencoder=0.00594438, residual=0.00816703.
FPR умовний до припущення, що unlabeled background негативний. Alarms/day у
первинних файлах — flagged points / eligible interval-days, не episodes чи листи.

Unanimous вибрано за validation protocol: OR перевищив clean budget1%
(1.419159%), Majority та Unanimous мали eventF1=0, нижчий background rate обрав
Unanimous (0 проти 0.152053%). Це **консервативний validation-selected rule**,
а не operational winner. На mixed test усі його point/event detection metrics=0.
Residual/OR мають event recall .05 і mean matched-event median delay0 min;
це delay лише успішних matches, не «миттєве виявлення всіх аномалій».
Missed events мають null delay, а не 0. Для IF/AE/Unanimous mixed delay undefined.

Coverage partition=100% тільки після 144 preceding context points. Cold IF/AE
unready6; residual144; common combined coverage починається лише коли всі ready.
Не можна заявляти 100% ready з першого повідомлення або приховувати warm-up.

### Типи interventions та діагностика

У таблиці нижче — Unanimous macro event F1 з saved test-by_type; не робимо
з помилкового «zero mixed» висновок «zero для абсолютно всіх сценаріїв».

| Type | Unanimous event F1 |
|---|---:|
| context_load | 0.00000000 |
| drift | 0.00000000 |
| drop | 0.00000000 |
| level_shift | 0.01481481 |
| mixed | 0.00000000 |
| spike | 0.00000000 |
| stuck | 0.00000000 |

Level_shift має ненульовий event F1=0.01481481, event recall0.01111111;
інші listed types — 0. За типами/силою усі IF/AE/residual метрики збережені в
[by_type.csv](../energy-anomaly/results/by_type.csv) та
[by_severity.csv](../energy-anomaly/results/by_severity.csv). Це не окремі незалежні
будинки; stuck severity повністю повторює transformation.

Оригінальні primary-q99 event F1 за типами (macro across saved seeds/severities;
не mixed-only summary):

| Type | Isolation Forest | Autoencoder | Residual |
|---|---:|---:|---:|
| context_load | 0.00000000 | 0.00512821 | 0.00701754 |
| drift | 0.07677878 | 0.00000000 | 0.02656085 |
| drop | 0.00000000 | 0.01878112 | 0.00759555 |
| level_shift | 0.06645191 | 0.02570370 | 0.04475143 |
| mixed | 0.00000000 | 0.00000000 | 0.01111111 |
| spike | 0.00444444 | 0.04634259 | 0.13251435 |
| stuck | 0.00000000 | 0.00000000 | 0.00000000 |

Ці значення не отримано новим підбором scenarios або thresholds.

Єдиний residual hit у mixed test: 2016-05-26 14:00, clean80→modified380 Wh,
forecast79.43206598 однаковий до надходження current actual, score
0.56793402→300.56793402 Wh при порозі296.24602579 Wh. Clean alarm у цій точці
немає; цей hit не є pre-existing alarm. Наступного інтервалу forecast уже
реагує на змінену історію: score2.59635116 Wh, нижче порога. Це приклад
адаптації forecast до втручання, не доказ єдиної причини низького recall усіх методів.

[Paired diagnostic CSV](../energy-anomaly/diagnostics/paired_by_type_strength.csv)
показує зростання багатьох scores, але перекриття distributions/поріг не дає
надійного detection. Пороги не змінені. Дозволений висновок: за цим протоколом
та цими intervention strengths жоден метод не готовий до operational fault detection.
Недозволено: «нейромережа довела відсутність несправностей» або «усі великі Wh — аварії».

## 6. Відмінність original і локальних live artifacts

Original Stage 3 усі 4 weights і original Stage 4 bundle повторно перевірені
у read-only архіві за записаними SHA. Локальний trusted Docker manifest також
пройшов hash перевірку, але це окрема binary identity. Live AE q99
0.8288868594169614 відрізняється від original0.828860602378845; IF/residual q99
збігаються. [Snapshot](operational-snapshot.json) фіксує обидві версії через
посилання на original metadata і local threshold_version. Причинність числового
розходження не перевірялась. **Не переносимо точні original benchmark metrics
на іншу live model/threshold version без окремого експерименту.**

## 7. Stage 6 — тільки завершені локальні пілоти

Первинний архів, **не main**:
`/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI/docs/stage6/`.
Джерела: summary.md, closure-status.json, evidence-index.json, pilot-latencies.csv,
throughput.csv, raw/*/{run.json,summary.json,producer.jsonl.gz,worker.jsonl.gz,integrity.json.gz}.
[Audit JSON](verified-values.json) містить paths/SHA; 291 compressed та original
archive checksum збігаються. Read-only перерахунок з producer.send_mono_ns до
worker.db_ack_mono_ns підтвердив усі наведені p50/p95/p99 й correlation event/offset.
Пілоти не об'єднані з commissioning, overhead, interrupted primary.

| Mode | Warm-up / measured | Send→DB ack p50 / p95 / p99, ms | Publication/s | DB commits/s | Completion/s |
|---|---:|---|---:|---:|---:|
| slow | 150 / 60 | 61.041 / 101.134 / 131.735 | 0.993423 | 0.993535 | 1.008852 |
| demo | 150 / 60 | 57.409 / 160.176 / 172.094 | 6.442463 | 6.480652 | 6.476351 |
| max | 150 / 60 | 1481.779 / 2954.583 / 3140.701 | 384.866275 | 18.227988 | 17.900403 |

Slow pause1s, demo .15s, max0s. Кожен — **один** run із 60 measured, не п'ять
повторень 3600. Publication rate=(N−1)/(last send−first send), commit rate=(N−1)/(last DB ack−first DB ack),
completion rate=N/(last DB ack−first send). Ці формули також звірені з raw;
controller-observed completion має додаткову затримку й не підміняє їх.
Publication throughput не дорівнює worker capacity: max producer
публікував ≈384.87/s, але DB commits≈18.23/s. Вищий send→DB latency узгоджується
з чергою; точний continuous peak Kafka consumer lag тут не заявляємо. Після drain
кожного пілота DB/Kafka/end next offsets210/210/210, measurements210,
forecasts420, scores630, unique IDs210, duplicates/rejected0. Warm-up рядки включені.

Send→DB ack включає Kafka/чергу, ML/DB, але виключає подальший Kafka commit.
Worker=Processor.process; transaction включає ML усередині Engine.begin;
SQL sum, DBAPI commit acknowledgement та Kafka commit виміряні окремо й вкладені,
їх не можна складати. CLOCK_MONOTONIC — перевірений спільний Docker VM domain,
не historical event time й не універсальна синхронізація фізичних пристроїв.

Recovery-пілот один: restoration1.991130043s, startup6.330347211s,
restart→first observed newly committed record8.014616750s; останнє включає
контролер/replay/observation. 0 open/1 closed episode перед restart — не доказ
recovery відкритої події; її підтверджують окремі CI fixtures. Прогнози/generated_at
і scores збережено. Немає статистики recovery median/min/max п'яти повторів.

Dashboard availability→DOM — bounded estimate з DB probe≈200ms та clock exchange;
fetch/data-ready→DOM починається після load/JSON, не на початку HTTP. Видиме вікно144,
polling≈2s після попереднього fetch; усі60 measured IDs спостерігались. Для max
лише2 оновлення з новими IDs, тому rendering p99 нестійкий. CPU/RAM sampling≈2s
із помилками короткоживучих контейнерів; це не повна resource trace.

Overhead: три v7 пари 300 warm-up+600 measured/arm, signed throughput difference
+1.2498%, −19.4914%, +8.3255%, median+1.2498%. Це спільний ноутбук, причинність
різниці лише від instrumentation не доведена; correction не застосована.

Середовище Stage 6: Apple M1/16GB host; Docker VM5CPU/6 212 689 920bytes RAM,
фонові сервіси задокументовані. **15 primary не завершено за рішенням користувача**:
0 complete, 1 interrupted (1062 records, 300 warm-up+762 measured), без фінального
integrity snapshot; 0/5 primary recovery, 0/20 API-load. API latency під навантаженням
не відома. Початковий pilot-report містить історичне «proceed», яке superseded
closure-status; не поновлюємо campaign. Stage 6 source_commit09d79ed… — до
combined/outbox. Ці пілоти не доводять SLA, інші hardware або поточний Stage 7C throughput.

## 8. Матеріали для захисту

Допустимо: окремі таблиці Stage2/Stage3 forecasting, validation decision,
peak errors; negative anomaly benchmark і score-distribution plots; Kafka/DB
idempotency/recovery evidence; обмежені Stage6 pilot latency/throughput; Email
outbox/Mailpit функціональна демонстрація. [Traceability](traceability-matrix.md).

Рекомендовані рисунки: Mermaid architecture, saved forecasting overview/errors/
peak plots, Stage4 paired/distribution plots, Stage7B comparison, live Dashboard
screenshot, Mailpit HTML. Не малювати нові «кращі» результати і не називати
поточні скриншоти independent evaluation. Висновок: інтеграційно працездатний
локальний дослідницький MVP; forecasting baseline trade-offs і низька anomaly
якість експериментально видимі. Перед фізичним застосуванням потрібна нова валідація.
