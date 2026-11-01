# Stage 8B — перевірений runbook без перенавчання

## Межі та поточний результат

Runtime source `51e4b94635ec775a6ab2111b894b8cc8034fd45b`. Фактичний checkout:
`/Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main`.

Поточний завершений Dashboard:
http://127.0.0.1:8088/?run=showcase-20261101-112252-c10e040c0b71

Mailpit: http://127.0.0.1:8026, project `energy-email-defense`, synthetic run `email-delivery-test-d2cca7d8d321`.
Сервіси залишено працювати для перегляду. Для перегляду збережених результатів **новий replay не потрібен**.

Основний project **`energy-dashboard-main`** належить новій робочій копії; `energy-dashboard` містить інший старий стек. Не використовувати їх паралельно з різних checkout. Стару папку `Pipeline_Kafka_AI` не запускати й не змінювати.

## Перед повторенням

Команди нижче виконуються поетапно, з перевіркою результату. За помилки — stop/diagnostics, а не автоматичний prepare. Не показувати `.env` або повний `docker compose config` (він містить credentials).

```sh
cd /Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main
git status --short
git rev-parse HEAD
docker info --format '{{.ServerVersion}}'
docker compose ls -a
docker ps -a --format '{{.Names}} {{.Image}} {{.Status}} {{.Ports}}'
docker image ls
docker volume ls
lsof -nP -iTCP:8088 -sTCP:LISTEN
lsof -nP -iTCP:8026 -sTCP:LISTEN
python3 docs/stage8b/verify_saved_evidence.py --check-local
```

`lsof` exit1 за вільного порту — не помилка. Зайнятий порт можна використовувати тільки якщо його власник — погоджений project; інакше зупинитися, не зупиняти чужі сервіси. Offline evidence verifier не завантажує pickle. `--check-local` перевіряє checksum усіх захищених local artifact files та CSV і зупиняється за відсутності/розбіжності.

### Чистий clone: передумови, не auto-training

У Git немає `.env.mvp`, CSV та ML artifacts. Чистий clone не є повністю самодостатнім. Окремо потрібні:

1. CSV `data/energy/raw/energydata_complete.csv`, SHA `2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d`.
2. Trusted backup **наявного Docker artifact directory** `artifacts/mvp/docker/`, з manifest, HGB model/metadata/metrics/test_predictions та anomaly bundle. Повний список SHA — `verification.json` → `protected_files_sha256`. Не брати невідомий joblib; hash не створює довіру до pickle. Не копіювати поверх наявних файлів. За відмінності — зупинитись і погодити конкретний trusted package, не train/prepare.
3. Docker Desktop, Compose та host Python3 для stdlib orchestration. Worker/API/ML/Email dependencies — у pinned Docker images. Повний host ML venv не потрібен.
4. Локальна `.env.mvp`: за відсутності **тільки** `python3 -m integration.setup` створить ignored credentials без друку. Якщо файл є — команда його зберігає. У поточному показі файл вже існував.

Тут не створювався другий чистий clone й не повторювався Showcase для нього; підтверджено наявну trusted конфігурацію та source-level [clean CI base](https://github.com/Axmetik/Pipeline_Kafka_AI/actions/runs/40563712518). Цей розділ пояснює явні prerequisites, не заявляє новий clean-clone експеримент. Не використовувати дві копії з однаковим project/ports одночасно; новий clone потребує окремо обраного context/вільних портів.

## 1. Явний build із правильним manifest

```sh
export MVP_COMPOSE_PROJECT=energy-dashboard-main
export MVP_DOCKER_ARTIFACT_MANIFEST=artifacts/mvp/docker/manifest.json
export MVP_ARTIFACT_MANIFEST=artifacts/mvp/docker/manifest.json

docker compose --env-file .env.mvp -p energy-dashboard-main \
  -f docker/docker-compose.dashboard.yml config --services
docker compose --env-file .env.mvp -p energy-dashboard-main \
  -f docker/docker-compose.dashboard.yml config --images
docker compose --env-file .env.mvp -p energy-dashboard-main \
  -f docker/docker-compose.dashboard.yml build worker api dashboard
```

Не переносити localhost DB/Kafka URL у container env. Чинний Compose використовує postgres:5432/kafka:29092; API loopback8000 та nginx8080 мають shared namespace. Публікується тільки127.0.0.1:8088.

Перевірити завантаження **існуючих** артефактів та точні library pins у новому image:

```sh
docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
  -v "$PWD/artifacts:/app/artifacts:ro" energy-monitoring-backend:local \
  python -c 'from integration.artifacts import load_manifest; load_manifest("/app/artifacts/mvp/docker/manifest.json"); print("Trusted artifacts verified; no inference or training")'
docker image inspect --format '{{.Id}}' energy-monitoring-backend:local
docker image inspect --format '{{.Id}}' energy-dashboard-main-dashboard:latest
```

Stage8B позитивно звірив 89 runtime files з checkout і Graphite tokens: `image-artifact-verification.json`. Наступні docs-only rebuild можуть мати інший image ID через `COPY docs`; збіг runtime/source/ML SHA важливіший за назву тегу. Наведені IDs фіксують конкретний виконаний показ.

## 2. Перевірка саме demo database

Перед стартом переглянути labels/mounts **без Config.Env**:

```sh
docker inspect --format '{{json .Mounts}}' energy-dashboard-main-postgres-1
docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' energy-dashboard-main-postgres-1

docker compose --env-file .env.mvp -p energy-dashboard-main \
  -f docker/docker-compose.dashboard.yml up -d --no-recreate --wait postgres

docker exec energy-dashboard-main-postgres-1 sh -c \
  'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version; select count(*) from mvp_runs;"'
```

У виконаному показі revision вже `0003_email`, було2старих runs. Окремий upgrade не потрібен. Showcase startup усе одно виконає existing migrate `upgrade head`: за head це no-op.

Лише якщо погоджена demo database справді відстає (або нова порожня DB) і перевірено її project/volume, застосувати additive migrations чинним service:

```sh
docker compose --env-file .env.mvp -p energy-dashboard-main \
  -f docker/docker-compose.dashboard.yml run --rm --no-deps migrate
```

Ця умовна upgrade-команда не була потрібна й окремо не виконувалась у цьому показі. На новій порожній DB відсутність `alembic_version` очікувана до першої міграції; для наявної бази це привід зупинитись і перевірити її identity. Жодних downgrade/reset/drop/volume recreation.

## 3. Guard проти автоматичного prepare та один Showcase

Showcase має fallback до prepare за відсутності image/manifest/dataset. Тому **не запускати його**, поки всі gates вище не пройшли. Додатково перевірити, що всі configured images вже існують:

```sh
python3 - <<'PY'
import subprocess
from integration.demo import compose
refs = set(compose('config', '--images', capture_output=True, text=True).stdout.splitlines())
for ref in refs:
    subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', ref], check=True)
print('All configured images exist; artifact/hash/version gates must also pass')
PY

python3 -m integration.demo showcase --limit 300 --sleep 0.15
```

Успішний запуск повідомляє, що build/prepare пропущено, дає **новий** run/topic/group і URL. За збою зберегти diagnostics; не повторювати одразу. Дані старих runs залишаються в PostgreSQL; `artifacts/mvp/showcase-last.json` — лише last-pointer, його попередній вміст у Stage8B збережено окремо.

Очікування: 300measurements,600forecast rows,900score rows,300combined decisions, checkpoint300, duplicates/rejected0. Ready counts для цієї пари models/перших300CSV: HGB294, RF157, IF294, AE294, residual156; combined156ready/144warmup. **Не підганяти alerts:** один AE episode й0combined — фактичний результат цієї моделі; інше джерело/weights не повинно автоматично застосовуватись.

## 4. Перегляд, read-only verification та збереження

Відкрити URL із нового command output, а не покладатися на історичний run із цього звіту. Перевірити 72/144/288, naive labels, actual/primary forecast target, experimental detectors, combined coverage і episodes. Час measurement, received_at та generated_at різний. Відкрити timestamp details у таблиці. Worker/replay `unknown` є очікуваним без heartbeat/producer contract.

Для наявних контейнерів після replay (не створює новий run і не рахує ML повторно):

```sh
STAGE8B_RUN=$(python3 -c 'import json; print(json.load(open("artifacts/mvp/showcase-last.json"))["run_id"])')
docker exec -i energy-dashboard-main-worker-1 python - \
  --run-id "$STAGE8B_RUN" --topic "$STAGE8B_RUN" --group-id "$STAGE8B_RUN" \
  < docs/stage8b/verify_runtime.py
MVP_COMPOSE_PROJECT=energy-dashboard-main python3 -m integration.security_check
```

Verifier перевіряє весь журнал і CSV, counts/nulls, target600s, preceding RF forecast та Unanimous. Він не змінює DB/checkpoints/offsets, не викликає model.predict і не надсилає Email. Для іншого context передати його власні run/topic/group. Output не містить DB URL/credentials/raw quarantine payloads.

Окремий live restart не потрібен: збережено [успішне CI recovery evidence](base-ci-evidence.json). UI reload перевірено в реальному показі; це не еквівалент crash recovery test чи latency benchmark.

## 5. Окремий synthetic Email delivery test

Перевірити, що `energy-email-defense` та8026 не зайняті іншим середовищем. Поточний існуючий proof вже містить один тестовий лист. Для перегляду — просто відкрити Mailpit, без повторного запуску команди. Для **нового погодженого повторення**:

```sh
EMAIL_COMPOSE_PROJECT=energy-email-defense \
EMAIL_MAILPIT_WEB_PORT=8026 \
python3 -m integration.email_demo synthetic
```

Existing command будує лише Email backend, запускає окремий postgres/mailpit, мігрує цю окрему DB, створює новий email-delivery-test run, повторну synthetic подію та notifier restart. Не викликає prepare/training або real-model replay. Якщо project використати вдруге, його inbox може містити старі листи: перевіряти рівно один **за новим run ID**, не вимагати global total1 для вже непорожнього inbox. У фактичному Stage8B project був новим, global total1.

У Mailpit відкрити `[ТЕСТ ДОСТАВКИ]`, HTML/Text, часові мітки та experimental disclaimer. Очікується1outbox/sent1/attempt1/multipart; addresses тільки `@example.test`, реальний SMTP вимкнено. Його outbox не пов'язаний із DB стандартного Dashboard. Не запускати `integration.email_demo replay` без окремого погодження.

## 6. Безпечна зупинка

```sh
MVP_COMPOSE_PROJECT=energy-dashboard-main python3 -m integration.demo stop
EMAIL_MAILPIT_WEB_PORT=8026 docker compose --env-file .env.mvp \
  -p energy-email-defense -f docker/docker-compose.dashboard.yml \
  -f docker/docker-compose.email.yml --profile notifications stop postgres mailpit
```

Ці stop-команди наведені для користувача; у Stage8B сервіси залишено працювати. Не використовувати `down -v`, `volume/system prune`, `git clean`, `reset --hard`, delete/recreate volumes або видалення artifacts. Після stop дані залишаються; не трактувати повторний Showcase як перегляд старого run — це новий run.

## Targeted checks

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_demo_showcase.py' -v
docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL \
  -v "$PWD/tests:/app/tests:ro" energy-monitoring-backend:local \
  python -m unittest discover -s tests -p test_email.py -v
python3 docs/stage8b/verify_saved_evidence.py --check-local
```

Пройшли14+6unit tests, actual Kafka/DB/API/browser/MIME перевірки. Host venv не мав SQLAlchemy для Email tests: використано container, залежності не встановлювали. Повні локальні suites, responsive/performance campaigns і повторне навчання не потрібні для цих docs-only змін.
