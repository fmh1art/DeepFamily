#!/usr/bin/env bash
set -euo pipefail

mode="${1:---preview}"
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${ASKDU_ARTIFACT_OUTPUT_DIR:-$project_root/artifacts/release}"

case "$mode" in
  --preview | --public) ;;
  *)
    printf 'Usage: %s [--preview|--public]\n' "$0" >&2
    exit 2
    ;;
esac

version="$(awk -F'"' '/^version = / {print $2; exit}' "$project_root/backend/pyproject.toml")"
if [[ -z "$version" ]]; then
  printf 'Could not determine the project version.\n' >&2
  exit 1
fi

license_member=""
for candidate in LICENSE LICENSE.txt LICENSE.md; do
  if [[ -f "$project_root/$candidate" ]]; then
    if [[ -n "$license_member" ]]; then
      printf 'Refusing ambiguous root licenses: %s and %s\n' \
        "$license_member" "$candidate" >&2
      exit 1
    fi
    license_member="$candidate"
  fi
done

if [[ "$mode" == "--public" && -z "$license_member" ]]; then
  printf 'Refusing a public bundle: the authors have not selected a root code license.\n' >&2
  exit 1
fi

bundle_members=(
  .dockerignore
  .env.example
  .github
  .gitignore
  ARTIFACT.md
  Makefile
  README.md
  backend
  compose.yaml
  compose.model-smoke.yaml
  data/README.md
  data/manifests
  data/pilots
  docs
  experiments
  frontend
  infra
  paper
  scripts
  third_party/README.md
)
if [[ -n "$license_member" ]]; then
  bundle_members+=("$license_member")
fi

for member in "${bundle_members[@]}"; do
  if [[ ! -e "$project_root/$member" ]]; then
    printf 'Required artifact member is missing: %s\n' "$member" >&2
    exit 1
  fi
done

mkdir -p "$output_dir"
suffix="preview"
if [[ "$mode" == "--public" ]]; then
  suffix="release"
fi
archive="$output_dir/ask-dont-upload-artifact-v${version}-${suffix}.tar.gz"
temporary_archive="$(mktemp --tmpdir="$output_dir" --suffix=.tar.gz .askdu-artifact.XXXXXX)"
trap 'rm -f -- "$temporary_archive"' EXIT

(
  cd "$project_root"
  tar \
    --sort=name \
    --mtime='UTC 1970-01-01' \
    --owner=0 \
    --group=0 \
    --numeric-owner \
    --mode='u+rwX,go+rX,go-w' \
    --pax-option=delete=atime,delete=ctime \
    --transform="s,^,ask-dont-upload-v${version}/," \
    --exclude='*/.env' \
    --exclude='*/.env.*' \
    --exclude='*/.venv' \
    --exclude='*/.venv/**' \
    --exclude='*/node_modules' \
    --exclude='*/node_modules/**' \
    --exclude='*/dist' \
    --exclude='*/dist/**' \
    --exclude='*/test-results' \
    --exclude='*/test-results/**' \
    --exclude='*/playwright-report' \
    --exclude='*/playwright-report/**' \
    --exclude='*/__pycache__' \
    --exclude='*/__pycache__/**' \
    --exclude='*/.pytest_cache' \
    --exclude='*/.pytest_cache/**' \
    --exclude='*/.mypy_cache' \
    --exclude='*/.mypy_cache/**' \
    --exclude='*/.ruff_cache' \
    --exclude='*/.ruff_cache/**' \
    --exclude='experiments/results' \
    --exclude='experiments/results/**' \
    --exclude='data/pilots/heldout-v1-questions.json' \
    --exclude='data/manifests/coda-community-45-extracted.sha256' \
    --exclude='paper/main.pdf' \
    --exclude='paper/main.build.json' \
    --exclude='paper/acmart.cls' \
    --exclude='paper/pvldb.sty' \
    --exclude='paper/ACM-Reference-Format.bst' \
    --exclude='paper/*.aux' \
    --exclude='paper/*.bbl' \
    --exclude='paper/*.blg' \
    --exclude='paper/*.fdb_latexmk' \
    --exclude='paper/*.fls' \
    --exclude='paper/*.log' \
    --exclude='paper/*.out' \
    --exclude='paper/*.synctex.gz' \
    --exclude='frontend/*.tsbuildinfo' \
    -cf - "${bundle_members[@]}"
) | gzip -n -9 > "$temporary_archive"

# Inspect the bytes that will actually ship, including ignored/hidden files
# that a worktree rg scan could miss. Never extract the candidate for this check.
# Only internal previews may retain the exact credential-free pinned provider.
python3 "$project_root/scripts/audit_artifact_archive.py" "$temporary_archive" \
  --expected-root "ask-dont-upload-v${version}" --mode "${mode#--}"

listing="$(tar -tzf "$temporary_archive")"
if printf '%s\n' "$listing" | rg -q --pcre2 \
  '(^|/)(data/external|supported_research_paper|node_modules|experiments/results|runtime|artifacts)(/|$)|(^|/)data/pilots/heldout-v1-questions\.json$|(^|/)data/manifests/coda-community-45-extracted\.sha256$|third_party/(?!README\.md$)'; then
  printf 'The candidate archive contains a forbidden path.\n' >&2
  printf '%s\n' "$listing" | rg --pcre2 \
    '(^|/)(data/external|supported_research_paper|node_modules|experiments/results|runtime|artifacts)(/|$)|(^|/)data/pilots/heldout-v1-questions\.json$|(^|/)data/manifests/coda-community-45-extracted\.sha256$|third_party/(?!README\.md$)' >&2
  exit 1
fi

if printf '%s\n' "$listing" | rg -q '(^|/)\.env($|\.)' &&
   printf '%s\n' "$listing" | rg '(^|/)\.env($|\.)' | rg -qv '/\.env\.example$'; then
  printf 'The candidate archive contains a private environment file.\n' >&2
  exit 1
fi

mv -- "$temporary_archive" "$archive"
trap - EXIT
(
  cd "$output_dir"
  sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256"
)

printf 'Created %s\n' "$archive"
printf 'Members: %s\n' "$(printf '%s\n' "$listing" | wc -l | tr -d ' ')"
printf 'SHA-256: %s\n' "$(awk '{print $1}' "$archive.sha256")"
if [[ "$mode" == "--preview" ]]; then
  printf 'Status: internal preview; only the exact pinned provider configuration is permitted.\n'
  printf 'Public release still requires author licensing and removal of concrete provider configuration.\n'
fi
