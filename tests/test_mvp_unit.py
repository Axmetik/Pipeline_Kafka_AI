import json
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace
from integration.checkpoints import reconcile,CheckpointError
from integration.runtime import clock
from integration.processor import payload_digest
from integration.artifacts import load_manifest,ArtifactError
from integration.settings import Settings,env_file


class MVPUnitTests(unittest.TestCase):
    def test_checkpoint_reconciliation_expected_crash_windows(self):
        self.assertEqual(reconcile(0,10,None,None),0)
        self.assertEqual(reconcile(0,10,5,7),7)
        self.assertEqual(reconcile(0,7,None,7),7)
        self.assertEqual(reconcile(0,7,7,7),7)
        for args in [(0,10,1,None),(1,10,None,None),(4,10,4,3),(0,3,4,4),(0,10,8,7),(7,10,7,7)]:
            with self.subTest(args=args),self.assertRaises(CheckpointError):
                reconcile(*args)

    def test_naive_time_not_assigned_utc(self):
        result=clock('2016-01-01T15:20:00')
        self.assertIsNone(result['utc']);self.assertIsNone(result['local'].tzinfo)
        self.assertEqual(result['basis'],'dataset_naive')
        aware=clock('2016-01-01T15:20:00+02:00')
        self.assertEqual(aware['utc'].hour,13)
        self.assertEqual(aware['local'].hour,15)

    def test_digest_distinguishes_key_value_boundaries_and_tombstone(self):
        self.assertNotEqual(payload_digest(b'a',b'bc'),payload_digest(b'ab',b'c'))
        self.assertNotEqual(payload_digest(None,b''),payload_digest(b'',None))
        self.assertEqual(payload_digest(b'a',b'b'),payload_digest(b'a',b'b'))

    def test_missing_artifact_has_setup_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ArtifactError,'prepare or register'):
                load_manifest(Path(directory)/'missing.json')

    def test_manifest_version_mismatch_rejected_before_pickle_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'manifest.json'
            path.write_text(json.dumps({'schema_version':1,'libraries':{},'artifacts':{}}))
            with self.assertRaisesRegex(ArtifactError,'dependency versions'):
                load_manifest(path)

    def test_env_reader_does_not_modify_process_environment(self):
        import os
        previous=dict(os.environ)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'.env';path.write_text('# local\nMVP_RUN_ID=example\n')
            self.assertEqual(env_file(path),{'MVP_RUN_ID':'example'})
        self.assertEqual(dict(os.environ),previous)

    def test_environment_file_is_private_and_credentials_not_printed(self):
        import contextlib,io
        from unittest.mock import patch
        from integration import setup
        with tempfile.TemporaryDirectory() as directory:
            out=io.StringIO()
            with patch.object(setup,'ROOT',Path(directory)),contextlib.redirect_stdout(out):
                setup.main()
            path=Path(directory)/'.env.mvp'
            values=env_file(path)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertNotIn(values['POSTGRES_PASSWORD'],out.getvalue())
            before=path.read_bytes()
            with patch.object(setup,'ROOT',Path(directory)),contextlib.redirect_stdout(out): setup.main()
            self.assertEqual(path.read_bytes(),before)

    def test_artifact_checksum_checked_before_deserialization(self):
        from integration.artifacts import versions
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bad.joblib').write_bytes(b'not a trusted model')
            entry={'path':'bad.joblib','sha256':'0'*64}
            (root/'manifest.json').write_text(json.dumps({'schema_version':1,'libraries':versions(),'artifacts':{'hgb':entry,'anomaly':entry}}))
            with self.assertRaisesRegex(ArtifactError,'checksum mismatch'): load_manifest(root/'manifest.json')
