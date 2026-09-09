#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
host_config="$project_root/infra/ecs/host-nginx.conf.example"
nginx_image="$(
  awk '$1 == "FROM" && $2 ~ /^nginxinc\/nginx-unprivileged:/ {print $2; exit}' \
    "$project_root/frontend/Dockerfile"
)"

if [[ ! "$nginx_image" =~ ^nginxinc/nginx-unprivileged:[^@]+@sha256:[0-9a-f]{64}$ ]]; then
  printf 'Could not resolve a digest-pinned Nginx image from frontend/Dockerfile.\n' >&2
  exit 1
fi
if [[ ! -f "$host_config" ]]; then
  printf 'Host Nginx template is missing: %s\n' "$host_config" >&2
  exit 1
fi
command -v docker >/dev/null 2>&1 || {
  printf 'Docker is required for the host Nginx syntax check.\n' >&2
  exit 1
}
command -v openssl >/dev/null 2>&1 || {
  printf 'OpenSSL is required to create the syntax-check certificate.\n' >&2
  exit 1
}

syntax_root="$(mktemp -d /tmp/askdu-nginx-syntax.XXXXXX)"
cleanup() {
  case "$syntax_root" in
    /tmp/askdu-nginx-syntax.*) find "$syntax_root" -depth -delete ;;
    *) printf 'Refusing to clean unexpected path: %s\n' "$syntax_root" >&2 ;;
  esac
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj /CN=demo.example.com \
  -keyout "$syntax_root/privkey.pem" \
  -out "$syntax_root/fullchain.pem" >/dev/null 2>&1
# These are throwaway test bytes mounted into an unprivileged/user-namespaced
# container, not deployment credentials.
chmod 0755 "$syntax_root"
chmod 0644 "$syntax_root/fullchain.pem" "$syntax_root/privkey.pem"

docker run --rm --network none --user 101:101 \
  --cap-drop ALL --security-opt no-new-privileges \
  --entrypoint nginx \
  --mount "type=bind,src=$host_config,dst=/etc/nginx/conf.d/default.conf,readonly" \
  --mount "type=bind,src=$syntax_root,dst=/etc/nginx/certs/demo.example.com,readonly" \
  "$nginx_image" -t

printf 'PASS: host Nginx template parses with the digest-pinned production-family image.\n'
