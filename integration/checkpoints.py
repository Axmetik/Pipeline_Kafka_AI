"""Strict reconciliation; no implicit earliest/latest fallback."""

class CheckpointError(RuntimeError):
    pass


def reconcile(begin,end,committed,database_next):
    if begin<0 or end<begin:
        raise CheckpointError('Invalid broker offset bounds')
    if database_next is None:
        if committed is not None:
            raise CheckpointError('Kafka offset exists without a DB checkpoint; use a new run/group/topic')
        if begin != 0:
            raise CheckpointError('Fresh run requires the full log from offset 0; retained history is missing')
        return 0
    if not begin<=database_next<=end:
        raise CheckpointError('DB checkpoint lies outside available Kafka log; no records skipped')
    if committed is not None and committed>database_next:
        raise CheckpointError('Kafka committed offset is ahead of DB checkpoint; refusing silent data loss')
    if committed is not None and committed<0:
        raise CheckpointError('Invalid Kafka committed offset')
    if database_next>0 and database_next-1<begin:
        raise CheckpointError('Checkpoint anchor has expired; cannot verify log identity')
    # Lagging/missing Kafka commit is the expected crash-after-DB-commit case.
    return database_next
