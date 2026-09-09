#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

# Bind a human rehearsal to the source and deployment surface that determines
# what the participant actually sees and executes. Generated output, tests,
# documentation, private configuration, and downloaded data stay outside this
# digest; the registered public-data checksums remain inside it.
{
  find backend/src -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0
  find backend/deployment -type f ! -path '*/__pycache__/*' ! -name '*.pyc' -print0
  printf '%s\0' \
    backend/Dockerfile \
    backend/pyproject.toml \
    backend/uv.lock
  find frontend/src frontend/public -type f -print0
  printf '%s\0' \
    frontend/Dockerfile \
    frontend/index.html \
    frontend/package.json \
    frontend/package-lock.json \
    frontend/tsconfig.app.json \
    frontend/tsconfig.json \
    frontend/tsconfig.node.json \
    frontend/vite.config.ts
  find infra/nginx -type f -print0
  printf '%s\0' \
    .dockerignore \
    .env.example \
    compose.yaml \
    data/manifests/coda-bench-v1-open-release.json \
    data/manifests/coda-community-43-csv.sha256 \
    data/manifests/coda-community-43.sha256 \
    data/manifests/coda-community-52-csv.sha256 \
    data/manifests/coda-community-52.sha256 \
    data/manifests/coda-public-source-provenance-v1.json \
    scripts/run_demo.sh \
    scripts/sync_coda_open_release.py \
    scripts/hash_demo_surface.sh
} \
  | LC_ALL=C sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | awk '{print $1}'
