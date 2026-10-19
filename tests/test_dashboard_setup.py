"""Lifecycle config validation without Docker or ML imports."""
import os
import unittest
from unittest.mock import patch
from integration.demo import environment


class DashboardSetupTests(unittest.TestCase):
    def test_container_manifest_is_separate_and_never_changes_host_environment(self):
        with patch.dict(os.environ,{'MVP_ARTIFACT_MANIFEST':'artifacts/existing/manifest.json'},clear=True):
            result=environment()
            self.assertEqual(result['MVP_ARTIFACT_MANIFEST'],'artifacts/mvp/docker/manifest.json')
            self.assertEqual(os.environ['MVP_ARTIFACT_MANIFEST'],'artifacts/existing/manifest.json')
            self.assertNotIn('LOCAL_UID',os.environ)

    def test_invalid_bind_artifact_paths_are_rejected(self):
        for value in ['/etc/passwd','artifacts/../../elsewhere','data/manifest.json']:
            with self.subTest(value=value),patch.dict(os.environ,{'MVP_DOCKER_ARTIFACT_MANIFEST':value}),self.assertRaises(ValueError):
                environment()
