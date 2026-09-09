#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_image="${ASKDU_API_IMAGE:-ask-dont-upload-api:latest}"
web_image="${ASKDU_WEB_IMAGE:-ask-dont-upload-web:latest}"
trivy_image="aquasec/trivy:0.74.0@sha256:62b1e65e8869bc4b4c6aa4fa2b21595256c7c2f6018a9d9ad61caf87187c1969"
temp_base="${TMPDIR:-/tmp}"

command -v docker >/dev/null 2>&1 || {
  printf 'ERROR: docker is required for production-image scanning.\n' >&2
  exit 2
}

for image in "$api_image" "$web_image"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    printf 'ERROR: required image is absent: %s\n' "$image" >&2
    printf 'Run docker compose build from %s first.\n' "$project_root" >&2
    exit 2
  fi
done

scan_dir="$(mktemp -d "$temp_base/askdu-image-audit.XXXXXX")"
cleanup() {
  case "$scan_dir" in
    "$temp_base"/askdu-image-audit.*)
      rm -rf -- "$scan_dir"
      ;;
    *)
      printf 'Refusing to clean unexpected image-audit path: %s\n' "$scan_dir" >&2
      ;;
  esac
}
trap cleanup EXIT

mkdir "$scan_dir/inputs" "$scan_dir/cache"
printf 'Exporting final API and Web images for daemon-isolated scanning...\n'
docker image save --output "$scan_dir/inputs/api.tar" "$api_image"
docker image save --output "$scan_dir/inputs/web.tar" "$web_image"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --tmpfs /tmp:size=512m,mode=1777 \
  --mount type=bind,src="$scan_dir/inputs",dst=/scan,readonly \
  --mount type=bind,src="$scan_dir/cache",dst=/cache \
  --entrypoint /bin/sh \
  "$trivy_image" \
  -c '
    set -eu
    for archive in /scan/api.tar /scan/web.tar; do
      trivy image \
        --input "$archive" \
        --cache-dir /cache \
        --scanners vuln \
        --pkg-types os,library \
        --severity HIGH,CRITICAL \
        --ignore-unfixed \
        --exit-code 1 \
        --no-progress \
        --format table
    done
  '

printf 'PASS: final API and Web images have no detected fixable High/Critical vulnerabilities.\n'
printf 'INFO: this is a point-in-time lookup using the vulnerability database fetched at run time.\n'
