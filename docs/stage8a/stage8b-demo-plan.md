# Stage 8B — план фінальної демонстрації (ще не виконується)

Цей документ не запускає Stage8B і не створює нової інфраструктури.
Підстава: [findings](findings.md), [traceability](traceability-matrix.md).
Мета — продемонструвати наявний локальний MVP, а наукові якості показати
**окремими зафіксованими benchmark таблицями**, без нової кампанії.

## 1. Go / no-go до початку показу

Наразі **no-go для показу as-is**: M05, default backend image застарілий.
Після окремого погодження Stage8B потрібні наведені нижче preflight дії;
готовність source/CI вже підтверджена, але ними не замінюємо local image readiness.

- Працювати з `~/PycharmProjects/Pipeline_Kafka_AI_main` на погодженому main/SHA;
  зберегти `git status`, branch/SHA і compose project name. Старий Stage6 checkout
  не запускати й не використовувати як робочий каталог.
- Підтвердити запущений Docker, вільні localhost ports8088/8025 або вибрати інші.
  Не зупиняти чужі projects. Одна активна копія на один Compose project.
- Перевірити CSV checksum і наявний trusted Docker manifest, artifacts hashes та
  library versions. Не виконувати prepare/training «для виправлення» несумісності.
  За missing/corrupt/incompatible artifacts — stop, підключити погоджену trusted пару.
- Явно перебудувати images з цього checkout. `showcase` сам не визначає, що старий
  image містить старий код. Приклад без retraining, зі стандартним project:

```bash
cd ~/PycharmProjects/Pipeline_Kafka_AI_main
# Лише після погодження Stage8B:
docker compose --env-file .env.mvp -p energy-dashboard \
  -f docker/docker-compose.dashboard.yml build worker api dashboard
```

`integration.demo.environment()` для звичайних demo commands вибирає
`artifacts/mvp/docker/manifest.json`. Для прямих Compose команд env override
`MVP_ARTIFACT_MANIFEST=artifacts/mvp/docker/manifest.json` потрібен там, де
сервіс реально читає models; не підставляти host manifest. Credentials не друкувати.
Наступний Showcase застосує `alembic upgrade head` через migrate service.
Revision має бути `0003_email`, тільки additive upgrade; жодних downgrade/reset/clean.

Оскільки стандартний Showcase автоматично викликає prepare за відсутності
артефактів, **спочатку** підтвердити їх наявність. Цей план не дозволяє нове навчання.
За startup error зберегти logs, не видаляти volumes і не повторювати довгі спроби.

## 2. Основний показ Dashboard / Kafka

Потрібні existing services: PostgreSQL, Kafka, migrate/bootstrap (one-shot),
worker, FastAPI, nginx/React Dashboard. Без Mailpit/notifier для цього run.

```bash
python3 -m integration.demo showcase --limit 300 --sleep 0.15
```

Existing orchestrator створить окремий run/topic/group та дасть URL з `?run=...`.
Відкрити його на `http://127.0.0.1:8088`. Показати:

1. Надходження нових вимірювань без reload; run/building/source і підпис часу
   «Час датасету, часовий пояс не визначено».
2. Actual Wh/10хв і primary HGB20 forecast. Пояснити origin, target t+600s,
   generated_at; forecast line прив'язана до target, не часу обчислення.
3. Warm-up/null спочатку; IF/AE/residual з окремими шкалами/thresholds і
   experimental labels. Нуль тривог — допустимий результат, не доказ відсутності faults.
4. Combined coverage/trigger count і episodes; RF21 — лише residual_reference,
   не прихована підміна HGB20. Unanimous може нічого не виявити; показати
   зафіксований негативний mixed-test результат, а не підкручувати scores.
5. Intelligent Energy Insights: описове поточне споживання/коротка динаміка/
   primary next forecast; не causal diagnosis й не LLM.
6. Завершення producer не означає, що worker помер; worker_status=unknown без
   heartbeat. Показати завершені counts і checkpoint, не вигаданий liveness.

Очікувано: 300 measurements /600forecast rows /900original score rows,
300combined decisions окремо; duplicates/rejected0, checkpoint300.
Rows warm-up можуть бути null; не заявляти600числових forecasts.
Стандартні перші300CSV належать training period: це function demo, не test accuracy.
Для quality відкрити Stage2/3 saved tables і plots, не оцінювати «на око» графік.

## 3. Короткий restart, якщо потрібен під час захисту

Перед restart зберегти API counts, run і останні generated_at/pending target.
Використати existing `python3 -m integration.demo restart`, не новий run/replay.
Після ready відкрити **той самий** run, перевірити counts і попередні прогнози.
Не вимірювати recovery latency за startup контейнера; якщо потрібні числа —
послатися на saved Stage6 одиничний recovery-пілот, чесно зазначивши його scope.

Це заздалегідь перевірений CI сценарій; на захисті перезапуск опційний,
без fault injection, нового stress test або очищення DB.

## 4. Email delivery — окремий, явно тестовий показ

Якщо після Stage7C вже запущено Mailpit proof іншої копії на8025, не перевикористовувати
той самий project паралельно. Обрати окремий project і порт, наприклад:

```bash
EMAIL_COMPOSE_PROJECT=energy-email-defense EMAIL_MAILPIT_WEB_PORT=8026 \
  python3 -m integration.email_demo synthetic
```

Ця existing команда збере Email backend image, запустить PostgreSQL+Mailpit у
окремому project, мігрує DB, створить `email-delivery-test-*`, проведе episode→outbox→
notifier→Mailpit, перевірить повторну подію й повторний запуск notifier.
Не навчає моделей; реальні SMTP адресати заборонені в цьому demo.
Відкрити `http://127.0.0.1:8026`, показати `[ТЕСТ ДОСТАВКИ]`, HTML і Text,
2016 dataset time окремо від processing/SMTP attempt, status `sent`.
Це механізм доставки, **не ML detection success**. Standard Dashboard project не
бачитиме outbox іншої PostgreSQL — статус підтверджує demo JSON у консолі й saved
evidence, не вигаданий запис у standard Dashboard.

Якщо потрібен **другий**, необов'язковий real-model Email scenario, лише після
явної згоди на цей невеликий replay:

```bash
EMAIL_COMPOSE_PROJECT=energy-email-defense EMAIL_MAILPIT_WEB_PORT=8026 \
  python3 -m integration.email_demo replay
```

Потрібні наявні Docker artifacts/dataset. Очікувати конкретні числа можна лише
для відповідної model/threshold version; saved Stage7C run мав6individual/0combined,
3sent/3cooldown. Не вимагати такого результату для іншого artifact hash.
Continuous notifier/manual overlay налаштування вже описані в
[Stage7C](../stage7c/email-notifications.md); новий адмінсервіс не потрібний.

## 5. Скриншоти / матеріали для захисту

| Рисунок / таблиця | Що показати | Чого не стверджувати |
|---|---|---|
| Architecture Mermaid | фактичні worker/DB/API/UI/outbox межі | вигадані microservices, physical devices, dual PostgreSQL+Parquet commit |
| Dashboard during replay | run/source, partial counts, timestamp semantics | real2016eventtime як wall-clock latency |
| Dashboard completed | 300/600/900, target alignment, experimental scales | усі рядки ready або600точних прогнозів |
| Combined panel | availability/3votes, збережені episodes | consensus = real fault probability |
| Forecast tables/plots | Stage2 MAE/RMSE trade-off, Stage3 validation RF winner | вибір HGB за вже переглянутим test |
| Anomaly comparison/distributions | негативні mixed результати, limits | operational precision на physical faults |
| Stage6 pilot table | n60, один repeat, всі3modes | завершені15runs або production SLA |
| Mailpit HTML + Text | test label, units, clocks, один received letter | доказ ML accuracy чи guaranteed exactly-once |

Використовувати primary saved plots за посиланнями в scientific-readiness.
Нові screenshots Stage8B мають містити run/model context і бути відокремлені від
експериментальних графіків. Не відкривати credentials/.env у видимому терміналі.

## 6. Stop / збереження

Зупиняти тільки погоджений project через `compose ... stop` з його правильним
compose file/env (або existing demo stop). Ніколи `down -v`, prune, clean, reset,
видалення artifacts/datasets. Не чіпати Stage6 controllers/raw. Зберегти demo
run ID, console summary, SHA images/artifacts і screenshots. У разі невдачі
показати saved CI/screenshot як **історичний proof**, не видавати за новий live run.
Stage8B та написання роботи потребують окремого дозволу.
