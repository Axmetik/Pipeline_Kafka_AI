"""Lossless deterministic raw-data compression after writers have stopped."""
import gzip
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]/'docs/stage6'
    index={}
    for directory in sorted((root/'raw').iterdir()):
        manifest=directory/'run.json'
        if not manifest.exists():continue
        run=json.loads(manifest.read_text())
        if not run.get('ended_at') or run['status'] not in ('complete','failed'):continue
        for path in [*directory.glob('*.jsonl'),directory/'integrity.json',directory/'before-restart.json']:
            if not path.exists():continue
            original=path.read_bytes();compressed=gzip.compress(original,mtime=0)
            if gzip.decompress(compressed)!=original:raise RuntimeError('Raw archive verification failed')
            target=Path(str(path)+'.gz');target.write_bytes(compressed)
            path.unlink()
        for path in directory.glob('*.gz'):
            index[str(path.relative_to(root))]={'compressed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'original_sha256':hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()}
    (root/'raw-checksums.json').write_text(json.dumps(index,indent=2)+'\n')


if __name__=='__main__':main()
