#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file=""
archive=""
expected_sha256=""
new_volume_name=""
created_volume=""
staging_volume=""
verification_archive=""

usage() {
  printf '%s\n' \
    "Usage: $0 --env-file PATH --archive PATH --expected-sha256 HEX --new-volume-name NAME" >&2
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  [[ -z "$verification_archive" ]] || rm -f -- "$verification_archive"
  if [[ -n "$staging_volume" ]]; then
    docker volume rm "$staging_volume" >/dev/null 2>&1 || true
  fi
  if [[ -n "$created_volume" ]]; then
    docker volume rm "$created_volume" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      env_file="$2"
      shift 2
      ;;
    --archive)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      archive="$2"
      shift 2
      ;;
    --expected-sha256)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      expected_sha256="$2"
      shift 2
      ;;
    --new-volume-name)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      new_volume_name="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$env_file" && -n "$archive" && -n "$expected_sha256" && -n "$new_volume_name" ]] || {
  usage
  exit 2
}
[[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] || die "expected SHA-256 must be 64 lowercase hexadecimal characters"
[[ "$new_volume_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "new volume name is unsafe"
(( ${#new_volume_name} <= 180 )) || die "new volume name is too long"
[[ -f "$env_file" && ! -L "$env_file" ]] || die "env file must be a regular, non-symlink file"
[[ -f "$archive" && ! -L "$archive" ]] || die "snapshot must be a regular, non-symlink file"
env_file="$(cd "$(dirname "$env_file")" && pwd -P)/$(basename "$env_file")"
archive="$(cd "$(dirname "$archive")" && pwd -P)/$(basename "$archive")"

actual_sha256="$(sha256sum "$archive" | awk '{print $1}')"
[[ "$actual_sha256" == "$expected_sha256" ]] || die "snapshot SHA-256 does not match the explicit expected value"
uv run --project "$project_root/backend" python \
  "$project_root/scripts/runtime_snapshot.py" verify --archive "$archive"

compose=(
  docker compose
  --project-directory "$project_root"
  --env-file "$env_file"
  --file "$project_root/compose.yaml"
)
current_volume="$("${compose[@]}" config --format json | python3 -c '
import json, sys
configuration = json.load(sys.stdin)
print(configuration["volumes"]["askdu-runtime"]["name"])
')"
[[ "$current_volume" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "rendered current runtime volume name is unsafe"
[[ "$new_volume_name" != "$current_volume" ]] || die "restore refuses to overwrite the currently configured runtime volume"
if docker volume inspect "$new_volume_name" >/dev/null 2>&1; then
  die "restore volume already exists; choose a fresh name"
fi

image_reference="$("${compose[@]}" config --format json | python3 -c '
import json, sys
configuration = json.load(sys.stdin)
service = configuration["services"]["api"]
print(service.get("image") or configuration["name"] + "-api")
')"
image_id="$(docker image inspect --format '{{.Id}}' "$image_reference" 2>/dev/null || true)"
[[ -n "$image_id" ]] || die "API image is absent; build the deployment before restoring"

docker volume create \
  --label askdu.runtime.snapshot-sha256="$expected_sha256" \
  --label askdu.runtime.restored=true \
  "$new_volume_name" >/dev/null
created_volume="$new_volume_name"
staging_volume="askdu-snapshot-stage-${new_volume_name}-$$"
if docker volume inspect "$staging_volume" >/dev/null 2>&1; then
  die "temporary snapshot staging volume already exists"
fi
docker volume create \
  --label askdu.runtime.snapshot-staging=true \
  "$staging_volume" >/dev/null

docker run --rm --interactive \
  --network none \
  --read-only \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --mount "type=volume,src=$staging_volume,dst=/runtime" \
  --mount "type=bind,src=$project_root/scripts/runtime_snapshot.py,dst=/ops/runtime_snapshot.py,readonly" \
  --entrypoint python \
  "$image_id" \
  /ops/runtime_snapshot.py stage \
    --output /runtime/runtime.tar.gz \
    --expected-sha256 "$expected_sha256" \
  < "$archive"

docker run --rm --interactive \
  --network none \
  --read-only \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --mount "type=volume,src=$new_volume_name,dst=/runtime" \
  --mount "type=volume,src=$staging_volume,dst=/snapshot,readonly" \
  --mount "type=bind,src=$project_root/scripts/runtime_snapshot.py,dst=/ops/runtime_snapshot.py,readonly" \
  --entrypoint python \
  "$image_id" \
  /ops/runtime_snapshot.py restore \
    --archive /snapshot/runtime.tar.gz \
    --target /runtime \
    --confirm-empty-target

docker volume rm "$staging_volume" >/dev/null
staging_volume=""

umask 077
verification_archive="$(mktemp --tmpdir .askdu-runtime-restore-check.XXXXXX)"
docker run --rm --interactive \
  --network none \
  --read-only \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --mount "type=volume,src=$new_volume_name,dst=/runtime,readonly" \
  --mount "type=bind,src=$project_root/scripts/runtime_snapshot.py,dst=/ops/runtime_snapshot.py,readonly" \
  --entrypoint python \
  "$image_id" \
  /ops/runtime_snapshot.py create --source /runtime --output - \
  > "$verification_archive"
restored_sha256="$(sha256sum "$verification_archive" | awk '{print $1}')"
[[ "$restored_sha256" == "$expected_sha256" ]] || die "restored volume did not reproduce the snapshot byte-for-byte"

created_volume=""
printf 'PASS: snapshot restored and reproduced byte-for-byte in new volume %s.\n' "$new_volume_name"
printf 'Set ASKDU_RUNTIME_VOLUME_NAME=%s in the external env file, rerun ecs-preflight, then start Compose.\n' \
  "$new_volume_name"
printf 'Rollback remains available by restoring ASKDU_RUNTIME_VOLUME_NAME=%s; that volume was not modified.\n' \
  "$current_volume"
