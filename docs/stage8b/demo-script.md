# Захист: сценарій показу на 5–7 хвилин

Це сценарій демонстрації, не початок написання магістерської. Наявний завершений run: `showcase-20261101-112252-c10e040c0b71`. Для нового live показу — один окремо запущений Showcase за runbook; не перезапускати його багаторазово для пошуку «гарних» alerts.

| Час | Показ | Коректне пояснення |
|---|---|---|
| 0:00–0:45 | Overview, run/building/source, API | Історичний UCI household; Kafka replay моделює надходження. Це не фізичний smart meter зараз. |
| 0:45–1:40 | Live count або saved replay-in-progress, потім300 | Kafka→worker→PostgreSQL→API→React. Якщо producer завершено, показати completion evidence, не називати статичний графік live ingestion. |
| 1:40–2:40 | Actual/HGB20, next target, timestamp details, window | Wh/10 хв, origin/target600s і generated_at різні; naive dataset time не UTC. RF21 — residual reference. 600 forecast rows включають149null, не600готових прогнозів. |
| 2:40–3:40 | IF/AE/residual, coverage та episodes | Окремі шкали, experimental. Усього один AE threshold episode; останнє144вікно без перевищень. Combined Unanimous не спрацював, це допустимо. Score не probability; епізод не fault. |
| 3:40–4:20 | Insights та pipeline | Описові правила звірені з даними. 300/600/900, checkpoint300, duplicates/rejected0. Worker status невідомий без heartbeat. |
| 4:20–5:20 | Mailpit HTML/Text | Окремий synthetic delivery test: один outbox, sent1, multipart. Не доказ ML accuracy; не outbox стандартного Dashboard. |
| 5:20–6:30 | Stage8A scientific tables / limitations | Stage2 MAE baseline краще, RMSE HGB краще; Stage3 RF validation winner. Anomaly quality низька, Unanimous mixed event recall0. Stage6 лише пілоти. Live models та original benchmarks різні. |
| 6:30–7:00 | Readiness/provenance/runbook | GO для локального дослідницького MVP; повторюваний показ із trusted artifacts без retraining. Production SLA/physical faults/HA не доведені. |

[Dashboard](http://127.0.0.1:8088/?run=showcase-20261101-112252-c10e040c0b71) · [Mailpit](http://127.0.0.1:8026) · [скриншоти та SHA manifest](screenshots/manifest.json) · [Stage8A scientific readiness](../stage8a/scientific-readiness.md).

Ручний restart опційний, у цьому Stage8B не виконувався: використано вже валідоване CI recovery evidence. Не витрачати показ на новий stress test або training.
