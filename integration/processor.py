"""One DB transaction per Kafka record, with fault-injection hooks for tests."""
import base64
import json
from sqlalchemy import create_engine
from processing.energy_schema import validate_energy
from processing.message_schema import InvalidMessage
from storage.postgres.repository import identity,RepositoryError
from integration.runtime import Runtime
from integration.checkpoints import CheckpointError


def payload_digest(key,value):
    return identity({'key':base64.b64encode(key).decode() if key is not None else None,
                     'value':base64.b64encode(value).decode() if value is not None else None})


def normalized_fingerprint(record):
    return identity(record)


class Processor:
    def __init__(self,repository,artifacts,failpoint=None):
        self.repository,self.artifacts=repository,artifacts
        self.failpoint=failpoint or (lambda stage:None)
        checkpoint=repository.checkpoint()
        if checkpoint is None:
            raise CheckpointError('Recovery requires a DB checkpoint')
        self.runtime_next_offset=checkpoint['next_offset']
        self.runtime=Runtime(artifacts)
        self.runtime.restore(repository.histories())
        if repository.checkpoint()['next_offset']!=self.runtime_next_offset:
            raise CheckpointError('DB advanced during history recovery; restart required')
        self.poisoned=False

    def process(self,offset,key,value):
        if self.poisoned:
            raise RepositoryError('Worker state invalid after failure; restart/recover from committed DB history')
        repo=self.repository
        digest=payload_digest(key,value)
        encoded={'key':base64.b64encode(key).decode() if key is not None else None,
                 'value':base64.b64encode(value).decode() if value is not None else None}
        raw=record=None;problem=None
        try:
            raw=json.loads(value)
            record=validate_energy(raw)
            if key is not None and json.loads(key)!=[record['building_id'],record['source_id']]:
                raise InvalidMessage('Kafka key must identify the same building/source')
            if record['timezone'] is not None and len(record['timezone'])>80:
                raise InvalidMessage('Timezone identifier exceeds MVP schema limits')
            if len(record['event_id'])>200 or len(record['building_id'])>160 or len(record['source_id'])>160:
                raise InvalidMessage('Identifiers exceed MVP schema limits')
        except (ValueError,TypeError,UnicodeDecodeError,InvalidMessage) as exc:
            problem=('invalid_message',str(exc))
        try:
            with repo.engine.begin() as c:
                checkpoint=repo.checkpoint(c,lock=True)
                if not checkpoint or checkpoint['run_id']!=repo.settings.run_id:
                    raise CheckpointError('Missing or incompatible DB checkpoint')
                expected=checkpoint['next_offset']
                if expected!=self.runtime_next_offset:
                    raise CheckpointError('DB checkpoint advanced outside this worker; recover model history before reuse')
                if offset<expected:
                    receipt=repo.receipt(c,offset)
                    if not receipt or receipt['payload_sha256']!=digest:
                        raise CheckpointError('Replayed Kafka coordinates differ from committed ledger')
                    return {'outcome':'offset_duplicate','next_offset':expected}
                if offset!=expected:
                    raise CheckpointError('Noncontiguous Kafka offsets; refusing to skip unprocessed records')
                mid=None;outcome='accepted'
                if not problem:
                    fingerprint=normalized_fingerprint(record)
                    existing=repo.existing_event(c,record)
                    if existing:
                        if existing['normalized_sha256']==fingerprint:
                            mid=existing['measurement_id'];outcome='message_duplicate'
                        else:
                            problem=('event_conflict','Existing event_id has different normalized content; history unchanged')
                    else:
                        problem=repo.source_problem(c,record)
                        if not problem:
                            result=self.runtime.compute(raw)
                            mid=repo.persist(c,offset,raw,record,fingerprint,result)
                if problem:
                    outcome=problem[0]
                repo.finish(c,offset,digest,outcome,mid,
                    {'kind':problem[0],'reason':problem[1][:1000],'payload_base64':encoded} if problem else None)
                self.failpoint('before_db_commit')
            self.runtime_next_offset=offset+1
            self.failpoint('after_db_commit')
            return {'outcome':outcome,'next_offset':offset+1}
        except Exception:
            # DB rollback or ambiguous commit must never leave a reusable advanced ML history.
            self.poisoned=True
            raise
