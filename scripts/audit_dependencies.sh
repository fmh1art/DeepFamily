#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_versions="${ASKDU_AUDIT_PYTHON_VERSIONS:-3.10.20 3.12}"
pip_audit_version="${PIP_AUDIT_VERSION:-2.10.1}"
requirements_file="$(mktemp /tmp/askdu-dependency-audit.XXXXXX.txt)"

cleanup() {
  case "$requirements_file" in
    /tmp/askdu-dependency-audit.*.txt)
      [[ ! -e "$requirements_file" ]] || unlink "$requirements_file"
      ;;
    *) printf 'Refusing to clean unexpected path: %s\n' "$requirements_file" >&2 ;;
  esac
}
trap cleanup EXIT

uv export \
  --project "$project_root/backend" \
  --frozen \
  --no-dev \
  --no-emit-project \
  --output-file "$requirements_file" \
  >/dev/null

for python_version in $python_versions; do
  printf 'Auditing backend lock for Python %s...\n' "$python_version"
  uvx --python "$python_version" "pip-audit==$pip_audit_version" \
    --requirement "$requirements_file" \
    --require-hashes \
    --disable-pip \
    --progress-spinner off
done

(
  cd "$project_root/frontend"
  npm audit --omit=dev --audit-level=high
)

printf 'PASS: audited locked backend and production frontend dependencies.\n'
