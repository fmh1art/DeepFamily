#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

# This is the implementation surface frozen before a held-out evaluation is
# unblinded. Documentation, data, runtime outputs, and evaluator answer keys
# are deliberately outside the surface.
{
  find backend/src -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0
  printf '%s\0' backend/pyproject.toml backend/uv.lock data/pilots/heldout-v1-plan.json
  find experiments -type f -name '*.py' ! -path 'experiments/results/*' -print0
  printf '%s\0' scripts/hash_evaluation_surface.sh scripts/unblind_coda_heldout.py
} \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | awk '{print $1}'
