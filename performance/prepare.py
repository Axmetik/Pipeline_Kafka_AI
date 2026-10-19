"""Build evaluation images and verify existing trusted artifacts. NEVER fits models."""
import os
from pathlib import Path
import tempfile
from integration.setup import main as setup
from performance.run import ROOT,CONFIG,execute,environment
import json


def main():
    setup()
    config=json.loads(CONFIG.read_text())
    if not (ROOT/config['manifest']).exists():
        raise SystemExit('Trusted Docker manifest missing. Register the frozen Stage5 artifacts as documented in docs/stage5/5c-report.md. Stage6 does not train replacements.')
    with tempfile.TemporaryDirectory(prefix='stage6-build-') as directory:
        env={**os.environ,'PERF_RUN_DIR':directory,'MVP_ARTIFACT_MANIFEST':config['manifest']}
        command=['docker','compose','--env-file','.env.mvp','-p','energy-performance-build',
                 '-f','docker/docker-compose.dashboard.yml','-f','docker/docker-compose.performance.yml']
        print('Building evaluation images; model files remain read-only.',flush=True)
        execute([*command,'build','worker','dashboard'],env=env,timeout=1200,log=Path(directory)/'build.log')
        execute(['docker','build','-f','docker/Dockerfile.performance-browser','-t','energy-performance-browser:local','.'],env=env,timeout=600,log=Path(directory)/'browser-build.log')
    execute(['docker','run','--rm','--network','none','-v',str(ROOT/'artifacts')+':/app/artifacts:ro',
             'energy-monitoring-backend:local','python','-c',
             'from integration.artifacts import load_manifest; load_manifest("/app/'+config['manifest']+'"); print("Frozen artifacts verified")'],timeout=120)
    environment()
    print('Ready. Run pilot, overhead and recovery pilot; validate the gate before main.')


if __name__=='__main__':main()
