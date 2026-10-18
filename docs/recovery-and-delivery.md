# Recovery and delivery limits

This prototype does **not** guarantee exactly-once or crash-safe at-least-once
processing. The following limits apply to the current Kafka consumers; the Energy
scenario additionally has two independent output archives.

## State is local to the process

Energy lag/rolling history, the last accepted timestamp and source semantics are
held in memory. They are not checkpointed or restored from Kafka or Parquet.
After restart, the model artifact reloads, but feature history starts empty:
seven consecutive accepted measurements are needed to generate a forecast.
The first six records have `insufficient_history` and null predictions.
Duplicate/out-of-order checks operate only within the current process lifetime;
they are not a durable event registry. A consumer rebalance does not transfer or
reconcile this state. Use one writer per output directory in the current prototype.

## Kafka offsets are not output acknowledgements

Consumers use `enable_auto_commit=True`. A committed group offset records Kafka
consumption progress, not confirmation that corresponding Parquet data is durable.
`auto_offset_reset=earliest` applies only if the group has no usable committed
offset; restarting the same group does not automatically replay the topic.

A normal exit attempts to flush Parquet before closing the consumer. This is not a
transaction: consumer close may commit offsets even if the flush raised an error,
because cleanup runs in `finally`. SIGKILL, power loss, default SIGTERM termination
or a container crash may bypass cleanup completely.

## Failure windows

| Failure point | Possible outcome after restart |
| --- | --- |
| Offset committed, records still buffered | The same group resumes past records absent from Parquet: missing output. |
| Parquet written, offset not committed | Kafka redelivers records; new UUID files append duplicate logical records. |
| Measurements written, forecasts not written (or vice versa) | Archives disagree; there is no atomic transaction covering both. |
| Process dies during a Parquet write | A partial/corrupt file may remain; writes do not use atomic temporary-file rename or fsync. |
| Restart or rebalance with committed offsets | Lost lag/rolling history causes another warm-up period, even if measurements existed before the restart. |
| Kafka retention expires or broker storage disappears | Historical replay may be impossible from Kafka alone. The current Compose file has no explicit persistent broker volume. |

UUID filenames prevent accidental filename replacement; they do not provide
idempotency, deduplication or atomic durability. CSV/Parquet differences in the IoT
scenario are similarly possible because those writes are separate.

## Manual recovery for experiments

1. Stop writers and preserve the existing archives, model metadata, logs and group
   offsets. Do not blindly delete files or reset offsets in the existing run.
2. Treat output from an interrupted run as incomplete until record counts, file
   readability, timestamp coverage and measurement/forecast joins are checked.
3. For the reproducible Appliances experiment, replay the original checksummed CSV
   with the matching model into a **new output directory and new Kafka group/topic**.
   Include six preceding observations when replaying a held-out range for warm-up.
4. Keep the recovered run separate. Do not concatenate both runs without checking
   duplicate event identities and forecast keys (building/source/origin/target/model).
5. For a future live meter without a retained source archive, recovery requires
   sufficient Kafka retention or another durable source; the current code cannot
   reconstruct lost measurements.

Checkpointed feature state, idempotent writes, durable event identifiers, atomic
Parquet publication and offsets coordinated with completed writes remain future
work. These are documented limitations, not implemented guarantees.
