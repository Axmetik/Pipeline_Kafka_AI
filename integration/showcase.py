"""Small foreground orchestrator for the existing local demo; no ML changes."""
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from integration.settings import ROOT

DATASET = Path('data/energy/raw/energydata_complete.csv')
DATASET_SHA256 = '2820bf712ad0275cb18b85a05250926100d8e65ebb9f4d2d016ca91ea152a25d'


class ShowcaseError(ValueError):
    pass


def announce(message):
    print(message, flush=True)


def docker(*args, check=True):
    return subprocess.run(['docker', *args], cwd=ROOT, check=check,
                          capture_output=True, text=True, timeout=60)


def new_context():
    token = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:12]
    name = 'showcase-' + token
    return {'MVP_RUN_ID': name, 'MVP_TOPIC': name, 'MVP_GROUP_ID': name}


def dataset_rows(path, limit):
    if hashlib.sha256(path.read_bytes()).hexdigest() != DATASET_SHA256:
        raise ShowcaseError('CSV має іншу контрольну суму. Файл збережено; підключіть оригінальний Appliances Dataset.')
    with path.open(newline='') as stream:
        count = sum(1 for _ in csv.DictReader(stream))
    if limit > count:
        raise ShowcaseError(f'У датасеті {count} вимірювань; --limit не може бути більшим.')
    return count


def protected_files(manifest):
    """Hash existing trusted files without loading pickle/joblib on the host."""
    result = {}
    if manifest.exists():
        try:
            metadata = json.loads(manifest.read_text())
            for name in ('hgb', 'anomaly'):
                entry = metadata['artifacts'][name]
                path = (manifest.parent / entry['path']).resolve()
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                    raise ShowcaseError(f'Артефакт {name} відсутній або пошкоджений; автоматичної заміни не буде.')
                result[path] = entry['sha256']
            result[manifest] = hashlib.sha256(manifest.read_bytes()).hexdigest()
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ShowcaseError('Некоректний manifest. Збережено без змін; використайте prepare --hgb … --anomaly … з перевіреними файлами.') from exc
    return result


def status(context):
    # Exec through the existing private API namespace: works on the host and in
    # the isolated CI browser, without opening another API port or trusting proxies.
    from integration.demo import compose
    query = '/api/pipeline-status?run_id=' + context['MVP_RUN_ID']
    script = ('import urllib.request; print(urllib.request.urlopen('
              + repr('http://127.0.0.1:8000' + query) + ',timeout=3).read().decode())')
    response = compose('exec', '-T', 'api', 'python', '-c', script,
                       env_overrides=context, capture_output=True, text=True, timeout=10)
    return json.loads(response.stdout)


def wait_processed(context, limit, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = status(context)
        count = result['unique_measurements']
        if result['rejected_messages'] or result['duplicate_deliveries'] or count > limit:
            raise ShowcaseError('Неочікувані rejected/duplicates/count. Дані збережено; перевірте integration.demo logs.')
        if count == limit:
            if result['forecasts'] != 2 * limit or result['anomaly_scores'] != 3 * limit:
                raise ShowcaseError('Кількість результатів не узгоджена; перевірте журнали worker.')
            checkpoints = result['checkpoints']
            if len(checkpoints) == 1 and checkpoints[0]['next_offset'] == limit:
                return result
        announce(f'Оброблено {count}/{limit}; прогнози {result["forecasts"]}; scores {result["anomaly_scores"]}.')
        time.sleep(2)
    raise ShowcaseError('Час очікування worker вичерпано. Результати збережено; перевірте status/logs і виконайте restart.')


def save_state(data):
    path = ROOT / 'artifacts/mvp/showcase-last.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def replay(args, context, project):
    from integration.demo import compose_command, environment
    name = project + '-showcase-producer-' + uuid.uuid4().hex[:12]
    env = {**environment(), **context}
    command = [*compose_command(env), 'run', '--rm', '--no-deps', '--name', name,
               'tools', 'python', '-m', 'integration.replay', '--dataset', str(DATASET),
               '--limit', str(args.limit), '--sleep', str(args.sleep)]
    process = None
    try:
        process = subprocess.Popen(command, cwd=ROOT, env=env)
        deadline = time.monotonic() + args.limit * (args.sleep + 1) + 180
        while process.poll() is None:
            if time.monotonic() > deadline:
                raise ShowcaseError('Producer не завершився вчасно; його буде зупинено без видалення даних.')
            result = status(context)
            announce(f'Надходять дані: {result["unique_measurements"]}/{args.limit}; '
                     f'прогнози {result["forecasts"]}; scores {result["anomaly_scores"]}.')
            time.sleep(2)
        if process.returncode:
            raise ShowcaseError(f'Kafka replay завершився з кодом {process.returncode}. Перевірте logs; повторний showcase створить новий context.')
    finally:
        # Stop only the exact producer owned by this invocation. A stopped --rm
        # container disappears automatically; no volumes or other producers touched.
        # Reap the attaching CLI first, so it cannot create a late container
        # after an early Ctrl+C cleanup has already checked its name.
        if process is not None:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        try:
            stopped = docker('stop', '--time', '30', name, check=False)
            if stopped.returncode:
                remaining = docker('inspect', '--format', '{{.State.Running}}', name, check=False)
                if remaining.returncode == 0 and remaining.stdout.strip() == 'true':
                    announce(f'Не вдалося підтвердити зупинку producer. Після відновлення Docker виконайте: docker stop {name}')
        except (OSError, subprocess.SubprocessError):
            announce(f'Docker недоступний; після його відновлення зупиніть точний producer: docker stop {name}')


def _run(args):
    from integration.demo import compose, environment, prepare, setup
    if not math.isfinite(args.sleep) or args.sleep < 0 or args.limit < 1:
        raise ShowcaseError('--limit має бути додатним, --sleep — скінченним невід’ємним числом.')
    if not shutil.which('docker'):
        raise ShowcaseError('Docker CLI не знайдено. Встановіть і запустіть Docker Desktop, потім повторіть showcase.')
    try:
        docker('info', '--format', '{{.ServerVersion}}')
        docker('compose', 'version')
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShowcaseError('Docker недоступний. Запустіть Docker Desktop і дочекайтеся готовності; перевірте доступ до Docker socket.') from exc
    env = environment()
    project = env.get('MVP_COMPOSE_PROJECT', 'energy-dashboard')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', project):
        raise ShowcaseError('MVP_COMPOSE_PROJECT має бути короткою lowercase Docker Compose назвою.')
    try:
        port = int(env.get('MVP_WEB_PORT', '8088'))
        if not 1 <= port <= 65535: raise ValueError
    except ValueError:
        raise ShowcaseError('MVP_WEB_PORT має бути коректним TCP-портом.') from None
    owners = docker('ps', '--filter', f'publish={port}', '--format', '{{.Label "com.docker.compose.project"}}').stdout.splitlines()
    if any(owner != project for owner in owners):
        raise ShowcaseError(f'Порт {port} зайнятий іншим Docker project. Не зупиняємо його; задайте інший MVP_WEB_PORT.')
    setup()
    manifest = ROOT / env['MVP_ARTIFACT_MANIFEST']
    protected = protected_files(manifest)
    if not manifest.exists() and manifest.parent.exists() and any(manifest.parent.iterdir()) and not args.hgb:
        raise ShowcaseError('Каталог моделей непорожній, але manifest відсутній. Дані не змінено; зареєструйте наявну довірену пару через prepare --hgb … --anomaly ….')
    if (ROOT / DATASET).exists():
        dataset_rows(ROOT / DATASET, args.limit)
    images = compose('config', '--images', capture_output=True, text=True).stdout.splitlines()
    images_ready = all(docker('image', 'inspect', '--format', '{{.Id}}', image, check=False).returncode == 0 for image in set(images))
    if not images_ready or not manifest.exists() or not (ROOT / DATASET).exists():
        announce('Початкова підготовка через наявний prepare. Перевірені артефакти не перезаписуються; перший запуск може тривати довше.')
        prepare(args, build=not images_ready)
    else:
        announce('Середовище підготовлено: Docker build і підготовку моделей пропущено.')
        try:
            compose('run', '--rm', '--no-deps', 'tools', 'python', '-c',
                    'from integration.artifacts import load_manifest; from integration.settings import Settings; load_manifest(Settings.from_env().artifact_manifest)',
                    capture_output=True, text=True)
        except subprocess.CalledProcessError:
            raise ShowcaseError('Перевірка моделей у контейнері не пройшла: перевірте manifest, контрольні суми та точні версії бібліотек. Артефакти не замінено; підключіть сумісну довірену пару через prepare.') from None
    dataset_rows(ROOT / DATASET, args.limit)
    for path, digest in protected.items():
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ShowcaseError('Перевірений артефакт змінився під час підготовки; запуск припинено.')
    # Atomic daemon-wide lease, including separate working copies/controllers.
    # A hard-killed command leaves a conservative stale lease, never auto-steals it.
    lease = project + '-showcase-lease'
    acquired = docker('create', '--name', lease, '--network', 'none',
                      '--label', 'energy.showcase=lease', 'energy-monitoring-backend:local',
                      'python', '-c', 'pass', check=False)
    if acquired.returncode:
        raise ShowcaseError(f'Інша демонстрація активна або залишила lease {lease}. Не запускайте дві одночасно. Якщо попередню команду вже завершено, видаліть лише lease: docker rm {lease}')
    lease_id = acquired.stdout.strip()
    if not lease_id:
        raise ShowcaseError('Docker не повернув ідентифікатор lease; перевірте Docker Desktop перед повторним запуском.')
    context = new_context()
    state = {'run_id': context['MVP_RUN_ID'], 'topic': context['MVP_TOPIC'], 'group_id': context['MVP_GROUP_ID'],
             'project': project, 'limit': args.limit, 'sleep': args.sleep, 'phase': 'starting',
             'dashboard_url': f'http://127.0.0.1:{port}/?run={context["MVP_RUN_ID"]}'}
    try:
        save_state(state)
        announce('Новий запуск: ' + context['MVP_RUN_ID'])
        announce('Попередні результати залишаються в PostgreSQL. Запускаємо компоненти…')
        compose('stop', 'worker')  # finish old transaction before changing context
        compose('up', '-d', '--no-build', '--wait', '--wait-timeout', '180', env_overrides=context)
        announce(f'Dashboard: http://127.0.0.1:{port}')
        announce('Саме цей запуск: ' + state['dashboard_url'])
        if args.limit <= 144:
            announce('Увага: Residual потребує 144 попередні інтервали; короткий replay може завершитися під час warm-up.')
        state['phase'] = 'replaying'; save_state(state)
        replay(args, context, project)
        announce('Replay завершено. Очікуємо підтвердження обробки…')
        result = wait_processed(context, args.limit)
        state.update(phase='complete', results=result); save_state(state)
        announce(f'Готово: {args.limit} measurements / {2*args.limit} forecasts / {3*args.limit} score records; дублів і відхилень немає.')
        announce('Dashboard залишається працювати. Безпечна зупинка: python3 -m integration.demo stop')
    except BaseException:
        state['phase'] = 'interrupted_or_failed'; save_state(state)
        announce('Дані збережено. Перевірка: python3 -m integration.demo status; python3 -m integration.demo logs. Новий showcase створить незалежний запуск.')
        raise
    finally:
        docker('rm', lease_id, check=False)  # only the stopped lease container, no volumes


def run(args):
    try:
        return _run(args)
    except KeyboardInterrupt:
        announce('Демонстрацію перервано користувачем. Worker/DB залишаються доступними; producer цієї команди зупинено або наведено точну інструкцію його зупинки.')
        raise SystemExit(130) from None
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShowcaseError('Компонент Docker не завершив дію: ' + type(exc).__name__ +
                            '. Дані не видалено. Перевірте Docker Desktop, потім integration.demo status та logs; повторіть showcase для нового context.') from None
