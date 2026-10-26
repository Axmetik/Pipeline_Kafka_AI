# Stage 7C — Email notifications

Implementation scope: transactional PostgreSQL outbox on newly inserted individual or
combined episodes; separate SMTP notifier; disabled by default. No retrospective scan,
model changes, threshold changes, or modification of historical experiment results.

Plan: frozen additive migration; narrowly scoped configuration and delivery authorization;
atomic deduplication/cooldown; bounded retry and crash recovery; Ukrainian multipart
HTML/text email; optional local-only Mailpit; targeted tests and two distinct demo paths.
