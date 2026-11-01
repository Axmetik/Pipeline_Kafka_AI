# Залишкові обмеження Stage 8B

Наукові висновки Stage 8A не переглянуто. Першоджерела: [scientific readiness](../stage8a/scientific-readiness.md), [findings](../stage8a/findings.md), [traceability](../stage8a/traceability-matrix.md).

- **Дані:** один historical UCI household, інтервальні Wh/600s. Replay імітує надходження; зараз немає фізичного smart meter. Будівлі/source IDs не доводять узагальнення на інші будівлі. Timezone UCI не підтверджений.
- **Функція ≠ точність:** перші300 вимірювань належать training period; це функціональний показ, не незалежний test/accuracy benchmark. Next forecast без фактичного target у поточному300-run не оцінюється «на око».
- **Stage2:** Persistence кращий за MAE, HGB20 за RMSE. **Stage3:** RF21 залишається validation-selected; descriptive test HGB21 не є підставою перевибору. Test раніше переглядався, не unseen holdout.
- **Stage4/7B:** anomaly quality низька; Unanimous mixed-test event recall0. Combined agreement і scores не є ймовірністю фізичної несправності. Background alarms на UCI без істинної anomaly розмітки не confirmed false positives. High consumption саме по собі не fault.
- **Ідентичності моделей:** original benchmark bundle та Docker bundle різні; live AE threshold трохи відрізняється. Benchmark metrics не переносимо на live weights без окремого експерименту. Див. точні SHA/versions у verification та Stage8A.
- **Stage6:** тільки завершені обмежені пілоти, повна кампанія перервана. Вона не відновлювалась; нових p50/p95/p99/SLA/throughput/recovery claims немає.
- **UI:** polling приблизно2s, bounded visible window; між refresh можуть бути пропущені проміжні стани. Немає producer status/heartbeat: `unknown` є чесним, completed підтверджується orchestrator+Kafka/DB. Window detector counts та run-wide episodes мають різний scope. EOF не обов'язково закриває threshold episode.
- **Email:** synthetic event доводить лише episode→outbox→SMTP шлях. Його DB відокремлена від Dashboard DB. `sent` означає SMTP acceptance, не прочитання; SMTP crash-window потенційно допускає повтор, хоча конкретний duplicate/restart test не повторив лист. Реальну зовнішню доставку не перевіряли. Mapped SMTP auth454 limitation Stage8A N02 не виправляли.
- **Відтворюваність:** чистий clone не містить ignored dataset/ML artifacts/credentials. Потрібен trusted package із зафіксованими SHA й точними бібліотеками, без auto-prepare/training. SHA доводить цілісність, не безпечність невідомого pickle. Images потрібно явно rebuild/verify; existence tag не доводить freshness. Backend COPY docs означає, що docs-only зміни можуть змінити image ID при наступному rebuild без зміни runtime Python.
- **Середовище:** host venv не містить SQLAlchemy; host demo є stdlib orchestration, runtime та Email tests виконувались у Docker. Не потрібно встановлювати host ML залежності для показу.
- **Надійність/безпека:** single partition/local MVP, одна DB, без HA та production authentication. Worker manual restart і fault injection не повторювались; є попереднє CI evidence. API локальний; віддалене публічне розгортання не є погодженим результатом.

M05 операційно закрито для зафіксованих нових images. Решта наукових обмежень не маскуються успішною демонстрацією. Нові експерименти/оптимізації/калібрування не проводились.
