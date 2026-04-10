#!/bin/zsh
set -euo pipefail
cd ~/plane-history
/usr/bin/python3 src/ingest.py --once >> data/ingest.log 2>&1
/usr/bin/python3 src/enrich_registry.py >> data/ingest.log 2>&1
/usr/bin/python3 src/enrich_operator.py >> data/ingest.log 2>&1
/usr/bin/python3 src/build_passes.py >> data/ingest.log 2>&1
