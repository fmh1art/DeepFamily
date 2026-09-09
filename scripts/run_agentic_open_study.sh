#!/usr/bin/env bash
set -euo pipefail

# This is the optional research evaluation, NOT the command to start the website.
# It uses the already-frozen 180-case open study and the existing private .env.
# No prepare/refreeze, credential editing, hidden-data access, or case deletion.
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
study_dir=experiments/results/agentic-open-v1
mode=${1:-status}
if [[ $# -gt 1 || ( "$mode" != status && "$mode" != run ) ]]; then
  printf '%s\n' 'Usage: ./scripts/run_agentic_open_study.sh [status|run]' >&2
  exit 2
fi
if [[ "$mode" == status ]]; then
  # Reports an actual process lock as well as saved counters; no model calls.
  uv run --project backend python experiments/agentic_open_evaluation.py status
  if [[ -f "$study_dir/scoring-progress.json" ]]; then
    jq . "$study_dir/scoring-progress.json"
  fi
  exit 0
fi

for command_name in uv jq flock; do
  command -v "$command_name" >/dev/null || { printf 'Missing prerequisite: %s\n' "$command_name" >&2; exit 1; }
done
[[ -f "$study_dir/freeze.json" ]] || { printf '%s\n' 'No frozen plan. Refusing to prepare a new billable study automatically.' >&2; exit 1; }

# One supervisor at a time. Each frozen runner additionally holds its own lock.
exec 9>"$study_dir/supervisor.lock"
flock --nonblock 9 || { printf '%s\n' 'A study supervisor is already active.' >&2; exit 1; }
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1

# At most 30 batches of six new cases. Existing terminal/started cases are never
# rerun. Data/capability gaps stay in the denominator. Authentication failures
# stop this supervisor instead of spending the remaining budget on a bad key.
for study_batch in $(seq 1 30); do
  uv run --project backend python experiments/agentic_open_evaluation.py run --max-new-cases 6
  # A jq parse/read error is fatal, not mistaken for "no failure".
  auth_failure=$(jq -s 'any(.[]; ((.model_usage.http_status_counts["401"] // 0) + (.model_usage.http_status_counts["403"] // 0)) > 0)' "$study_dir"/predictions/*/result.json)
  if [[ "$auth_failure" == true ]]; then
    printf '%s\n' 'STOP: authentication failure recorded; frozen cases are retained.' >&2
    exit 1
  fi
  [[ -f "$study_dir/predictions/seal.sha256" ]] && break
done

# The scorer independently verifies the COMPLETE prediction seal before it can
# read reference answers. Judging uses the same configured model, fresh context,
# and no controller labels. It is not independent human factual review.
for study_judge_batch in $(seq 1 30); do
  uv run --project backend python experiments/agentic_open_evaluation.py score --max-new-judgements 6
  auth_failure=$(jq -s 'any(.[]; ((.http_status_counts["401"] // 0) + (.http_status_counts["403"] // 0)) > 0)' "$study_dir"/judgements/*/usage.json)
  if [[ "$auth_failure" == true ]]; then
    printf '%s\n' 'STOP: judge authentication failure recorded; sealed predictions are retained.' >&2
    exit 1
  fi
  [[ -f "$study_dir/scores.json" ]] && break
done

# Read-only audit of original files and independent re-aggregation; no LLM calls.
# Existing identical summaries are verified, while modified summaries are kept.
uv run --project backend python scripts/summarize_agentic_study.py \
  --output "$study_dir/audited-summary-v1"
