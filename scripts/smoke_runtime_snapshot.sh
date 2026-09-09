#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_volume="askdu-runtime-smoke-source-${BASHPID}-${RANDOM}"
restore_volume="askdu-runtime-smoke-restore-${BASHPID}-${RANDOM}"
backup_dir="$(mktemp -d /tmp/askdu-runtime-smoke.XXXXXX)"

cleanup() {
  docker volume rm "$restore_volume" >/dev/null 2>&1 || true
  docker volume rm "$source_volume" >/dev/null 2>&1 || true
  case "$backup_dir" in
    /tmp/askdu-runtime-smoke.*) rm -r -- "$backup_dir" ;;
  esac
}
trap cleanup EXIT

compose=(
  docker compose
  --project-directory "$project_root"
  --env-file "$project_root/infra/ecs/production.env.example"
  --file "$project_root/compose.yaml"
)
image_reference="$("${compose[@]}" config --format json | python3 -c '
import json, sys
configuration = json.load(sys.stdin)
service = configuration["services"]["api"]
print(service.get("image") or configuration["name"] + "-api")
')"
docker image inspect "$image_reference" >/dev/null 2>&1 || {
  printf 'ERROR: API image is absent; run make compose-build first.\n' >&2
  exit 1
}

docker volume create "$source_volume" >/dev/null
docker run --rm \
  --network none \
  --read-only \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --mount "type=volume,src=$source_volume,dst=/runtime" \
  --entrypoint /bin/sh \
  "$image_reference" \
  -c 'mkdir -p /runtime/runs/demo/artifacts /runtime/empty && printf "%s\n" "{\"status\":\"completed\"}" > /runtime/runs/demo/state.json && printf "%s\n" "verified report" > /runtime/runs/demo/artifacts/report.md'

ASKDU_RUNTIME_VOLUME_NAME="$source_volume" \
  "$project_root/scripts/backup_runtime_volume.sh" \
  --env-file "$project_root/infra/ecs/production.env.example" \
  --output-dir "$backup_dir"

mapfile -t archives < <(
  find "$backup_dir" -maxdepth 1 -type f -name '*.tar.gz' -print
)
[[ ${#archives[@]} -eq 1 ]] || {
  printf 'ERROR: snapshot smoke expected exactly one archive.\n' >&2
  exit 1
}
archive="${archives[0]}"
[[ -f "$archive.sha256" ]] || {
  printf 'ERROR: snapshot smoke checksum is missing.\n' >&2
  exit 1
}
checksum="$(awk '{print $1}' "$archive.sha256")"

if ASKDU_RUNTIME_VOLUME_NAME="$source_volume" \
  "$project_root/scripts/restore_runtime_volume.sh" \
  --env-file "$project_root/infra/ecs/production.env.example" \
  --archive "$archive" \
  --expected-sha256 "$checksum" \
  --new-volume-name "$source_volume" \
  >/dev/null 2>&1; then
  printf 'ERROR: restore unexpectedly accepted the active volume name.\n' >&2
  exit 1
fi
docker volume inspect "$source_volume" >/dev/null

ASKDU_RUNTIME_VOLUME_NAME="$source_volume" \
  "$project_root/scripts/restore_runtime_volume.sh" \
  --env-file "$project_root/infra/ecs/production.env.example" \
  --archive "$archive" \
  --expected-sha256 "$checksum" \
  --new-volume-name "$restore_volume"

printf 'PASS: Docker runtime snapshot smoke restored a fresh volume byte-for-byte.\n'
