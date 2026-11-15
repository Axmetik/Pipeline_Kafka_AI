# Контекст одного завдання, етапи 1–6

- Репозиторій: Axmetik/Pipeline_Kafka_AI.
- Єдина локальна гілка: integration/energy-intelligence-complete.
- Єдиний worktree: /Users/oslavych/Documents/Codex/energy-intelligence-integration.
- Початкова копія збережена: /Users/oslavych/PycharmProjects/Pipeline_Kafka_AI_main, feature/sources-catalog @516dfaef1f758bacbae84e2da59f26d6c530f22e; її untracked docs/energy-rules не включати до комітів.
- Stage6 checkout /Users/oslavych/PycharmProjects/Pipeline_Kafka_AI не чіпати.
- Етап 1: аудит і локальна інтеграція виконані. Джерела: sources-catalog @516dfae, energy-rule-detectors @c2bf4a2, product-dashboard-p1 @e778932. Merge commits854f757/a074306; остаточний SHA читати git rev-parse HEAD після завершального локального коміту.
- Докази та точні версії: docs/integration/stage1/README.md, git-audit.json, artifact-preflight.json, preservation-check.json, config-check.json, targeted logs.
- Default rules switch=false. Optional migration0001_rules окремо від base0003_email; не створювати нову без потреби. Hybrid residual OR sustained_high; low вимкнено; telemetry_quality окремо.
- Sustained_high потребує попередніх днів (3/18 same-hour minimum, 7-day context), не лише144/300 вимірювань. Frozen rules-v2-a83ff8cf889d4981; нинішній layer residual-high-v1-0e2d29e530f2d68e910d5ea5.
- Перевірено60 Python targeted +8 email/mocked SMTP +26 frontend targeted, TS/build, Compose static defaults/forwarding, trusted artifact load без inference.
- Не перевірено реальний наскрізний replay після інтеграції; етапи2–6 чекати окремого завдання. Нового досліду/ін'єкції/скриншотів на етапі1 немає.
- Ні push, ні main merge, ні full CI/suite, ні training/performance. Основне demo/робочу БД/volumes не змінювати й не зупиняти. Artifacts/datasets read-only, попередні результати зберегти. Магістерську не редагувати, зовнішнього SMTP не використовувати.
- Email ML/Unanimous існує, hybrid/rule Email не підключений. Mailpit delivery на етапі1 не перевірявся.
