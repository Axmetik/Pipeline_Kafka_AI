# Stage 8B — Go/No-Go checklist

**GO — локальна історична демонстрація Energy Intelligence, 01.11.2026.**
Run `showcase-20261101-112252-c10e040c0b71`. Не production certification.

- [x] Runtime source `51e4b946…`, окрема feature branch, початкове дерево чисте.
- [x] До змін зафіксовано Docker/projects/ports/images/volumes; обрано project основного checkout.
- [x] CSV SHA/19 735 рядків; trusted manifest/обидві models/metadata hashes валідні.
- [x] Точні бібліотеки збігаються з manifest; trusted models завантажуються без inference/training під час preflight.
- [x] Backend/API/Dashboard явно rebuild; 89 runtime Python files та Graphite tokens перевірено.
- [x] `0003_email` до і після; окремий upgrade не потрібен, auto migrate — no-op.
- [x] Один новий ізольований run/topic/group; 300 /600 /900 /300; warm-up/null звіт окремий.
- [x] Kafka payloads/event IDs/offsets збігаються з DB ledger; checkpoint300, duplicates/rejected0.
- [x] Target alignment600s, HGB20 primary/RF21 residual, preceding forecast перевірені.
- [x] API/read-only counts/contracts/nulls/experimental семантика узгоджені з DB.
- [x] Real Chromium live updates/reload/72–144–288, console errors0; desktop Graphite оглянуто.
- [x] Insights arithmetic відповідає фактичним даним; без causal fault claims.
- [x] Один AE episode, zero combined episodes коректно показано; нуль тривог допустимий.
- [x] Один synthetic multipart email, outbox `sent`, один attempt; duplicate/restart без повтору.
- [x] Окремий Email project/DB; реальний SMTP не використано.
- [x] Localhost-only ports; API8000 недоступний із worker network.
- [x] Всі старі volumes та попередні run records збережені; hashes artifacts/CSV незмінні.
- [x] 14 Showcase +6 mocked Email targeted tests; real runtime/API/MIME evidence збережено.
- [x] Screenshots розділені на live та synthetic delivery; немає frontend fixtures або нових benchmark plots.
- [x] Runbook, scientific limitations та demo script підготовлено.
- [x] Повні локальні E2E/performance/retraining не запускались; recovery evidence — попередній CI.
- [x] PR не злитий; release tag і написання магістерської не розпочато.

[Machine-readable verification](verification.json) · [звіт](final-demonstration.md) · [runbook](reproducibility-runbook.md).

**NO-GO для нового повторення**, якщо manifest/CSV/hash/library gate не проходить, DB revision невідома/несумісна, images не звірені з source або counts/checkpoints розходяться. У такому разі зберегти diagnostics і зупинитись; не train/prepare/reset/prune. Поточний GO не гарантує незмінність майбутнього локального середовища.
