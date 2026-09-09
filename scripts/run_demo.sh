#!/usr/bin/env bash
# One-command local launcher for the verified Ask, Don't Upload Web Demo.
#
# Usage:
#   ./scripts/run_demo.sh          # stable verified pilot (no external model)
#   ./scripts/run_demo.sh agentic # question-only run over the open CoDA release
#   ./scripts/run_demo.sh status   # show containers and the readiness response
#   ./scripts/run_demo.sh logs     # follow API/Web logs; Ctrl-C only exits log view
#   ./scripts/run_demo.sh stop     # stop containers while preserving run data
#
# Agentic mode reads the API key from ASKDU_PRIVATE_ENV_FILE (default: .env),
# pins the endpoint/model below, and uses one shared client for every LLM stage.
# The private file is never sourced or printed. Neither mode touches sealed data.
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

# Bind only to loopback. Mode-specific configuration is applied before Compose.
export ASKDU_BIND_ADDRESS=127.0.0.1
export ASKDU_HTTP_PORT=8080
export ASKDU_RUN_RETENTION_HOURS=0

compose=(docker compose --env-file "$project_root/.env.example")
demo_url="http://127.0.0.1:8080"

usage() {
  printf 'Usage: %s [start|agentic|status|logs|stop]\n' "$0"
}

configure_registry() {
  export ASKDU_CATALOG_MODE=single
  export ASKDU_PLANNER_MODE=registry
  unset ASKDU_LLM_BASE_URL ASKDU_LLM_MODEL ASKDU_LLM_API_KEY
  unset ASKDU_LLM_API_STYLE ASKDU_LLM_AUTH_SCHEME ASKDU_LLM_TOKEN_FIELD
  unset ASKDU_LLM_TRUST_ENV_PROXY ASKDU_LLM_TIMEOUT_SECONDS ASKDU_LLM_MAX_RETRIES
  compose=(docker compose --env-file "$project_root/.env.example")
}

configure_agentic() {
  local private_env=${ASKDU_PRIVATE_ENV_FILE:-$project_root/.env}
  if [ ! -f "$private_env" ] || [ -L "$private_env" ]; then
    printf 'ERROR: create a regular, non-symlink private env file: %s\n' "$private_env" >&2
    printf 'It only needs ASKDU_LLM_API_KEY=<secret>; set permissions to 600.\n' >&2
    return 1
  fi
  local permissions
  permissions=$(stat -c '%a' "$private_env")
  if (( (8#$permissions & 077) != 0 )); then
    printf 'ERROR: private env permissions must be owner-only (currently %s): %s\n' \
      "$permissions" "$private_env" >&2
    return 1
  fi
  if ! grep -Eq '^ASKDU_LLM_API_KEY=.+$' "$private_env"; then
    printf 'ERROR: private env must contain a non-empty ASKDU_LLM_API_KEY.\n' >&2
    return 1
  fi
  if grep -Ev '^(#.*)?$|^ASKDU_LLM_API_KEY=.+$' "$private_env" | grep -q .; then
    printf 'ERROR: the private env for this launcher may contain only ASKDU_LLM_API_KEY.\n' >&2
    return 1
  fi

  # These values are intentionally pinned. The private file supplies only the key.
  export ASKDU_CATALOG_MODE=coda_open_release
  export ASKDU_PLANNER_MODE=agentic
  export ASKDU_LLM_BASE_URL='https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview'
  export ASKDU_LLM_MODEL='gpt-5.5-2026-04-24'
  export ASKDU_LLM_API_STYLE=azure_chat
  export ASKDU_LLM_AUTH_SCHEME=api_key
  export ASKDU_LLM_TOKEN_FIELD=max_completion_tokens
  export ASKDU_LLM_TRUST_ENV_PROXY=false
  export ASKDU_LLM_ALLOW_TEST_PROVIDER=false
  unset ASKDU_LLM_API_KEY
  compose=(
    docker compose
    --env-file "$project_root/.env.example"
    --env-file "$private_env"
  )
}

require_docker() {
  command -v docker >/dev/null 2>&1 || {
    printf 'ERROR: Docker is required.\n' >&2
    return 1
  }
  docker compose version >/dev/null
  docker info >/dev/null 2>&1 || {
    printf 'ERROR: Docker daemon is not reachable.\n' >&2
    return 1
  }
}

pilot_assets_are_valid() (
  data_root="$project_root/data/external/coda-bench"
  [ -d "$data_root" ] || return 1
  cd "$data_root"
  sha256sum -c "$project_root/data/manifests/coda-community-43.sha256" >/dev/null 2>&1 &&
    sha256sum -c "$project_root/data/manifests/coda-community-52.sha256" >/dev/null 2>&1 &&
    sha256sum -c "$project_root/data/manifests/coda-community-43-csv.sha256" >/dev/null 2>&1 &&
    sha256sum -c "$project_root/data/manifests/coda-community-52-csv.sha256" >/dev/null 2>&1
)

ensure_public_pilots() {
  if pilot_assets_are_valid; then
    printf 'PASS: public community_43/community_52 pilot assets already match their manifests.\n'
    return 0
  fi
  printf 'Public pilot assets are missing or stale; downloading pinned copies.\n'
  "$project_root/scripts/fetch_research_assets.sh" --coda-pilots
  pilot_assets_are_valid || {
    printf 'ERROR: public pilot verification still fails after download.\n' >&2
    return 1
  }
}

probe_readiness() {
  local readiness
  command -v curl >/dev/null 2>&1 || {
    printf 'ERROR: curl is required for the readiness probe.\n' >&2
    return 1
  }
  readiness=$(curl --silent --show-error --noproxy '*' --fail "$demo_url/readyz")
  printf '%s' "$readiness" | "${compose[@]}" exec -T api python -c '
import json
import sys

payload = json.load(sys.stdin)
if payload.get("status") != "ready" or payload.get("version") != "0.4.0":
    raise SystemExit(f"unexpected readiness payload: {payload!r}")
print("PASS: readiness =", json.dumps(payload, separators=(",", ":")))
'
}

start_compose() {
  require_docker
  if ! "${compose[@]}" up -d --build --wait --remove-orphans; then
    printf 'ERROR: Compose failed; recent service state follows.\n' >&2
    "${compose[@]}" ps >&2 || true
    "${compose[@]}" logs --tail=120 api web >&2 || true
    return 1
  fi
  probe_readiness
  printf '\nDemo is ready: %s\n' "$demo_url"
}

start_demo() {
  configure_registry
  ensure_public_pilots
  start_compose
  printf 'Primary scenario: 959 — Join repair\n'
  printf 'Stop safely with: ./scripts/run_demo.sh stop\n'
}

start_agentic_demo() {
  configure_agentic
  command -v uv >/dev/null 2>&1 || {
    printf 'ERROR: uv is required for first-time open-release synchronization.\n' >&2
    return 1
  }
  if ! uv run --project backend python scripts/sync_coda_open_release.py \
    --status --require-complete >/dev/null; then
    printf 'The pinned public CoDA release is incomplete; synchronizing all open communities.\n'
    uv run --project backend python scripts/sync_coda_open_release.py --all-open
  fi
  start_compose
  printf 'Mode: question-only agentic · coda-open-v1 · 30 public communities\n'
  printf 'All LLM stages use the pinned ModelHub endpoint/model; no paper-trained model is loaded.\n'
}

show_status() {
  require_docker
  "${compose[@]}" ps
  probe_readiness
}

action=${1:-start}
if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi

case "$action" in
  start)
    start_demo
    ;;
  agentic)
    start_agentic_demo
    ;;
  status)
    show_status
    ;;
  logs)
    require_docker
    "${compose[@]}" logs --tail=200 --follow api web
    ;;
  stop)
    require_docker
    "${compose[@]}" down --remove-orphans
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
