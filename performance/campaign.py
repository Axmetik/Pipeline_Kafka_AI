"""Sequential long-running series with retained progress, no automatic merge."""
import json
from pathlib import Path
import subprocess
import sys
from performance.run import ROOT


def main():
    output=ROOT/'docs/stage6'
    for phase in ('main','recovery','api'):
        print('CAMPAIGN PHASE',phase,flush=True)
        result=subprocess.run([sys.executable,'-m','performance.run',phase,'--resume'],cwd=ROOT)
        subprocess.run([sys.executable,'-m','performance.report'],cwd=ROOT,check=True)
        if result.returncode:
            raise SystemExit('Series stopped with retained incomplete results: '+phase)
    subprocess.run([sys.executable,'-m','performance.plots'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','performance.report'],cwd=ROOT,check=True)
    if not (output/'report.md').exists():raise SystemExit('Registered series incomplete; final report not generated')
    print('CAMPAIGN COMPLETE; results ready for verification, commit and CI. No merge performed.',flush=True)


if __name__=='__main__':main()
