#!/bin/sh
# Requires the already trusted local image, dataset and artifacts matching plan.json.
# No prepare/build/training/download. Use a NEW output directory; run1 is immutable.
set -eu
: "${1:?Pass a new absolute output directory outside the repository}"
case "$1" in /*) ;; *) echo 'Output path must be absolute' >&2; exit 2 ;; esac
if [ -e "$1/run1" ]; then echo 'Refusing to overwrite run1' >&2; exit 2; fi
mkdir -p "$1"
docker run --rm --pull never --network none --read-only \
 --cap-drop ALL --security-opt no-new-privileges --memory 2g --cpus 1 --user 0:0 \
 --tmpfs /tmp:size=128m -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=1 \
 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e MPLCONFIGDIR=/tmp/matplotlib \
 -v "$PWD:/work:ro" -v "$1:/output:rw" -w /work \
 sha256:3be9a8ff7a2eedf156ae4b85e4b2bd064b1fda84aa0057bf4718ab2f9ed4a865 \
 python -m diagnostics.rule_complementarity --output /output/run1
