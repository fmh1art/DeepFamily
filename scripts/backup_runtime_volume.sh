#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file=""
output_dir=""
temporary_archive=""
temporary_checksum=""

usage() {
  printf 'Usage: %s --env-file PATH --output-dir PATH\n' "$0" >&2
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  [[ -z "$temporary_archive" ]] || rm -f -- "$temporary_archive"
  [[ -z "$temporary_checksum" ]] || rm -f -- "$temporary_checksum"
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      env_file="$2"
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      output_dir="$2"
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

[[ -n "$env_file" && -n "$output_dir" ]] || { usage; exit 2; }
[[ -f "$env_file" && ! -L "$env_file" ]] || die "env file must be a regular, non-symlink file"
env_file="$(cd "$(dirname "$env_file")" && pwd -P)/$(basename "$env_file")"

if [[ ! -e "$output_dir" ]]; then
  install -d -m 700 -- "$output_dir"
fi
[[ -d "$output_dir" && ! -L "$output_dir" ]] || die "backup output must be a real directory"
output_dir="$(cd "$output_dir" && pwd -P)"
case "$output_dir/" in
  "$project_root/"*) die "runtime backups must be stored outside the repository" ;;
esac
permissions="$(stat -c '%a' "$output_dir")"
if (( (8#$permissions & 077) != 0 )); then
  die "backup output directory must not be accessible by group or other users"
fi

compose=(
  docker compose
  --project-directory "$project_root"
  --env-file "$env_file"
  --file "$project_root/compose.yaml"
)
running="$("${compose[@]}" ps --status running -q)"
[[ -z "$running" ]] || die "stop the Compose services before taking a consistent snapshot"

volume_name="$("${compose[@]}" config --format json | python3 -c '
import json, sys
configuration = json.load(sys.stdin)
print(configuration["volumes"]["askdu-runtime"]["name"])
')"
[[ "$volume_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "rendered runtime volume name is unsafe"
docker volume inspect "$volume_name" >/dev/null 2>&1 || die "runtime volume does not exist: $volume_name"

image_reference="$("${compose[@]}" config --format json | python3 -c '
import json, sys
configuration = json.load(sys.stdin)
service = configuration["services"]["api"]
print(service.get("image") or configuration["name"] + "-api")
')"
image_id="$(docker image inspect --format '{{.Id}}' "$image_reference" 2>/dev/null || true)"
[[ -n "$image_id" ]] || die "API image is absent; build the deployment before taking a snapshot"

umask 077
temporary_archive="$(mktemp --tmpdir="$output_dir" .askdu-runtime.XXXXXX)"
docker run --rm --interactive \
  --network none \
  --read-only \
  --user 10001:10001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 64 \
  --mount "type=volume,src=$volume_name,dst=/runtime,readonly" \
  --mount "type=bind,src=$project_root/scripts/runtime_snapshot.py,dst=/ops/runtime_snapshot.py,readonly" \
  --entrypoint python \
  "$image_id" \
  /ops/runtime_snapshot.py create --source /runtime --output - \
  > "$temporary_archive"

uv run --project "$project_root/backend" python \
  "$project_root/scripts/runtime_snapshot.py" verify --archive "$temporary_archive"
snapshot_sha256="$(sha256sum "$temporary_archive" | awk '{print $1}')"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive_name="askdu-runtime-${timestamp}-${snapshot_sha256:0:12}.tar.gz"
archive_path="$output_dir/$archive_name"
[[ ! -e "$archive_path" && ! -e "$archive_path.sha256" ]] || die "snapshot destination already exists"
mv -- "$temporary_archive" "$archive_path"
temporary_archive=""
temporary_checksum="$(mktemp --tmpdir="$output_dir" .askdu-runtime-checksum.XXXXXX)"
printf '%s  %s\n' "$snapshot_sha256" "$archive_name" > "$temporary_checksum"
chmod 600 "$temporary_checksum"
mv -- "$temporary_checksum" "$archive_path.sha256"
temporary_checksum=""

printf 'PASS: stopped-volume runtime snapshot created.\n'
printf 'Volume: %s\nArchive: %s\nSHA-256: %s\n' \
  "$volume_name" "$archive_path" "$snapshot_sha256"
