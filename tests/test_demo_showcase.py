"""Lifecycle/safety boundaries; no Docker daemon or model training required."""
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from integration import demo, showcase


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.root = root
        self.stack.enter_context(patch.object(showcase, 'ROOT', root))
        self.stack.enter_context(patch.object(demo, 'ROOT', root))
        self.env = self.stack.enter_context(patch.object(demo, 'environment', return_value={
            'MVP_ARTIFACT_MANIFEST': 'artifacts/mvp/docker/manifest.json', 'MVP_COMPOSE_PROJECT': 'test-demo'}))
        self.setup = self.stack.enter_context(patch.object(demo, 'setup'))
        self.prepare = self.stack.enter_context(patch.object(demo, 'prepare'))
        self.compose = self.stack.enter_context(patch.object(demo, 'compose', return_value=SimpleNamespace(stdout='backend\ndashboard\n')))
        self.docker = self.stack.enter_context(patch.object(showcase, 'docker', return_value=SimpleNamespace(stdout='', returncode=0)))
        self.stack.enter_context(patch.object(showcase.shutil, 'which', return_value='/docker'))
        self.stack.enter_context(patch.object(showcase, 'announce'))
        self.replay = self.stack.enter_context(patch.object(showcase, 'replay'))
        self.wait = self.stack.enter_context(patch.object(showcase, 'wait_processed', return_value={'unique_measurements': 3}))
        self.args = SimpleNamespace(limit=3, sleep=.5, hgb=None, anomaly=None)
        dataset = root / showcase.DATASET; dataset.parent.mkdir(parents=True)
        dataset.write_text('date,Appliances\na,1\nb,2\nc,3\n')
        self.stack.enter_context(patch.object(showcase, 'DATASET_SHA256', hashlib.sha256(dataset.read_bytes()).hexdigest()))
        folder = root / 'artifacts/mvp/docker'; folder.mkdir(parents=True)
        entries = {}
        for name in ('hgb', 'anomaly'):
            path = folder / (name + '.joblib'); path.write_bytes(name.encode())
            entries[name] = {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        self.manifest = folder / 'manifest.json'
        self.manifest.write_text(json.dumps({'artifacts': entries}))

    def test_ready_environment_skips_build_prepare_and_uses_fresh_context(self):
        before = {p: p.read_bytes() for p in self.manifest.parent.iterdir()}
        showcase.run(self.args); first = json.loads((self.root/'artifacts/mvp/showcase-last.json').read_text())
        showcase.run(self.args); second = json.loads((self.root/'artifacts/mvp/showcase-last.json').read_text())
        self.prepare.assert_not_called()
        self.assertNotEqual(first['run_id'], second['run_id'])
        for state in (first, second):
            self.assertEqual(state['run_id'], state['topic']); self.assertEqual(state['run_id'], state['group_id'])
            self.assertEqual(state['phase'], 'complete')
        for path, data in before.items(): self.assertEqual(path.read_bytes(), data)
        up = [call for call in self.compose.call_args_list if call.args[0] == 'up']
        self.assertEqual(len(up), 2); self.assertIn('--no-build', up[0].args)
        self.assertEqual(sum(call.args[0]=='stop' for call in self.compose.call_args_list), 2)

    def test_corrupt_model_is_not_replaced(self):
        (self.manifest.parent/'hgb.joblib').write_bytes(b'changed')
        with self.assertRaisesRegex(showcase.ShowcaseError, 'пошкоджений'): showcase.run(self.args)
        self.prepare.assert_not_called(); self.replay.assert_not_called()

    def test_corrupt_dataset_and_exhausted_limit_fail_before_start(self):
        self.args.limit=4
        with self.assertRaisesRegex(showcase.ShowcaseError, '3 вимірювань'): showcase.run(self.args)
        self.args.limit=3; (self.root/showcase.DATASET).write_text('wrong')
        with self.assertRaisesRegex(showcase.ShowcaseError, 'контрольну суму'): showcase.run(self.args)
        self.replay.assert_not_called()

    def test_nonempty_artifact_directory_without_manifest_is_preserved(self):
        self.manifest.unlink()
        with self.assertRaisesRegex(showcase.ShowcaseError, 'непорожній'): showcase.run(self.args)
        self.prepare.assert_not_called()

    def test_missing_image_reuses_prepare_without_overwriting_models(self):
        def docker(*args, **kwargs):
            return SimpleNamespace(stdout='', returncode=1 if args[0]=='image' else 0)
        self.docker.side_effect=docker
        showcase.run(self.args)
        self.prepare.assert_called_once_with(self.args, build=True)

    def test_missing_dataset_uses_prepare_without_unnecessary_build(self):
        dataset=self.root/showcase.DATASET; original=dataset.read_bytes(); dataset.unlink()
        self.prepare.side_effect=lambda *a,**kw: dataset.write_bytes(original)
        showcase.run(self.args)
        self.prepare.assert_called_once_with(self.args, build=False)

    def test_daemon_lease_rejects_second_controller_without_stopping_worker(self):
        self.docker.side_effect=lambda *a,**kw: SimpleNamespace(stdout='', returncode=int(a[0]=='create'))
        with self.assertRaisesRegex(showcase.ShowcaseError,'lease'): showcase.run(self.args)
        self.replay.assert_not_called()
        self.assertFalse(any(c.args[0]=='stop' for c in self.compose.call_args_list))
        self.assertFalse(any(c.args[0]=='rm' for c in self.docker.call_args_list))

    def test_foreign_port_owner_not_stopped(self):
        self.docker.side_effect=lambda *a,**kw: SimpleNamespace(stdout='other-project\n' if a[0]=='ps' else '',returncode=0)
        with self.assertRaisesRegex(showcase.ShowcaseError,'зайнятий'): showcase.run(self.args)
        self.setup.assert_not_called(); self.replay.assert_not_called()

    def test_failure_releases_only_owned_lease_and_preserves_failure_context(self):
        self.compose.side_effect=lambda *a,**kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1,['docker'])) if a[0]=='up' else SimpleNamespace(stdout='backend\n')
        with self.assertRaises(showcase.ShowcaseError): showcase.run(self.args)
        self.docker.assert_any_call('rm','test-demo-showcase-lease',check=False)
        self.assertEqual(json.loads((self.root/'artifacts/mvp/showcase-last.json').read_text())['phase'],'interrupted_or_failed')
        self.replay.assert_not_called()

    def test_invalid_sleep_no_docker_or_preparation(self):
        for value in (math.nan, math.inf, -.1):
            self.args.sleep=value
            with self.assertRaises(showcase.ShowcaseError): showcase.run(self.args)
        self.docker.assert_not_called(); self.setup.assert_not_called()

    def test_docker_absent_has_actionable_error(self):
        with patch.object(showcase.shutil,'which',return_value=None),self.assertRaisesRegex(showcase.ShowcaseError,'Docker Desktop'):
            showcase.run(self.args)

    def test_showcase_default_sleep_does_not_change_legacy_default(self):
        with patch.object(showcase,'run') as run:
            demo.main(['showcase']); self.assertEqual(run.call_args.args[0].sleep,.5)
        demo.main(['replay'])
        self.assertEqual(self.compose.call_args.args[-1],'0.15')
        for command in ('restart','status','logs','stop'):
            demo.main([command]); self.assertEqual(self.compose.call_args.args[0],{'restart':'restart','status':'ps','logs':'logs','stop':'stop'}[command])


class ProducerCleanupTests(unittest.TestCase):
    def test_interrupt_reaps_cli_and_stops_exact_named_producer(self):
        args=SimpleNamespace(limit=300,sleep=.5)
        process=Mock(); process.poll.return_value=None
        with patch.object(demo,'environment',return_value={}),patch.object(showcase.subprocess,'Popen',return_value=process),patch.object(showcase,'status',side_effect=KeyboardInterrupt),patch.object(showcase,'docker',return_value=SimpleNamespace(returncode=0)) as docker:
            with self.assertRaises(KeyboardInterrupt): showcase.replay(args,showcase.new_context(),'test-demo')
            call=docker.call_args
            self.assertEqual(call.args[:3],('stop','--time','30'))
            self.assertTrue(call.args[3].startswith('test-demo-showcase-producer-'))
            process.wait.assert_called_once_with(timeout=10)

    def test_completion_requires_exact_counts_and_checkpoint(self):
        context=showcase.new_context()
        correct={'unique_measurements':300,'forecasts':600,'anomaly_scores':900,'duplicate_deliveries':0,'rejected_messages':0,'checkpoints':[{'next_offset':300}]}
        with patch.object(showcase,'status',return_value=correct):
            self.assertEqual(showcase.wait_processed(context,300),correct)
        for key,value in [('duplicate_deliveries',1),('rejected_messages',1),('forecasts',599),('anomaly_scores',899)]:
            with self.subTest(key=key),patch.object(showcase,'status',return_value={**correct,key:value}),self.assertRaises(showcase.ShowcaseError):
                showcase.wait_processed(context,300)
