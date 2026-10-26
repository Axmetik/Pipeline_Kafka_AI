# Stage 7B — frozen reuse protocol (before validation comparison)

Base: origin/main 04266bbbd5b5e59c68b50cb0bdf3268b885937f3.
Only reuse immutable Stage 4 scores/manifests and original q99 thresholds.
No fitting, recalibration, new injections for model selection, or performance campaigns.

Candidates: IF, AE, residual baselines; OR (>=1), majority (>=2), unanimous (=3).
A vote requires a finite score/threshold and a ready result. Missing is not false.
All comparisons use the identical common-ready timestamps of the three original
methods, and separately report individual/common coverage and excluded/warm-up counts.
Fail on missing/misaligned timestamps, non-contiguous saved partitions, label/manifest
mismatch or changed Stage 4 checksums. Do not concatenate scenarios into episodes.

First evaluate validation only. Select among the three ensemble rules using the
Stage 4 clean-validation background budget <=1%. Rank by macro event F1 across the
five validation mixed scenarios, then mean successful-event median delay (none=inf),
then clean background alarm rate, then fixed OR/majority/unanimous order.
If none meet budget, select no operational rule; OR may be displayed as an explicitly
unqualified reference, with this fallback recorded. All candidates remain experimental
regardless of ranking or budget compliance. Never call a selected rule production-ready.
Persist selection JSON and versioned configuration before evaluating test.
Test has already been inspected in Stage 4 and is not an unseen independent holdout.

Reuse Stage 4 point metrics and chronological greedy one-to-one alarm-episode/event
overlap, detection window [start,end], no slack or point adjustment. A pre-existing
alarm episode can overlap a later injection: preserve this original convention and
explicitly report this limitation, not as proof that injection caused detection.
Also report newly started-in-event alarm episodes as an additional diagnostic.
Missing detections have null delay, never zero. Report precision/recall/F1, event
recall/F1, alarm episode counts, successful-event delay, coverage, clean alarm rate
and alarms/day. Clean UCI alarms are not confirmed false positives. Compare mixed
scenarios as primary summary; publish all 95 scenarios/split and per-type aggregates.
Post-event effects remain in the stored scores and background denominators.

Streaming: versioned stateless rule over the three original current scores only;
partial coverage gives nullable full decision/flag, never a complete 0/3.
New derived decision/episode tables in the existing transaction; no original record
backfill/rewrite. Episodes persist in DB, close on false decision, missing coverage,
gap or changed version/context, and continue across restart without duplication.
A flagged episode can change agreement count; keep maximum/last simultaneous count
and union of methods, explicitly distinguished in API/UI. No Telegram implementation.

Demo: unchanged standard 300-record showcase, plus a separate context using the
frozen Stage 4 spike severity 2 / seed 201 manifest on test with 144 predecessors
and 500 partition records (same injection mechanism). Keep original CSV untouched,
original q99, real model scores, report no detection honestly. This demo is not used
for selection. Unit fixtures may exercise flags but are not experimental results.

Outputs: docs/stage7b/results/{selection,summary,controls,metrics,coverage,event_outcomes,
by_type,provenance}; rule config; report; real CI/browser evidence. Hash every input.
