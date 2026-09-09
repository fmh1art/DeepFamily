#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
version="$(awk -F'"' '/^version = / {print $2; exit}' "$project_root/backend/pyproject.toml")"
archive="${1:-$project_root/artifacts/release/ask-dont-upload-artifact-v${version}-preview.tar.gz}"
archive="$(realpath -e "$archive")"
archive_name="$(basename "$archive")"
checksum_file="$archive.sha256"
expected_root="ask-dont-upload-v${version}"

case "$archive_name" in
  *-preview.tar.gz) rebuild_mode="--preview" ;;
  *-release.tar.gz) rebuild_mode="--public" ;;
  *)
    printf 'Artifact name must end in -preview.tar.gz or -release.tar.gz: %s\n' \
      "$archive_name" >&2
    exit 1
    ;;
esac

if [[ ! -f "$archive" || ! -f "$checksum_file" ]]; then
  printf 'Artifact archive or checksum is missing: %s\n' "$archive" >&2
  exit 1
fi

# A sidecar must verify this archive, not an unrelated path chosen by its text.
if [[ "$(awk 'END {print NR}' "$checksum_file")" != "1" ]]; then
  printf 'Artifact checksum must contain exactly one record.\n' >&2
  exit 1
fi
read -r checksum_digest checksum_target < "$checksum_file"
if [[ ! "$checksum_digest" =~ ^[a-f0-9]{64}$ || "$checksum_target" != "$archive_name" ]]; then
  printf 'Artifact checksum must name this archive and a SHA-256 digest.\n' >&2
  exit 1
fi

(
  cd "$(dirname "$archive")"
  sha256sum -c "$(basename "$checksum_file")"
)

python3 "$project_root/scripts/audit_artifact_archive.py" "$archive" \
  --expected-root "$expected_root" --mode "${rebuild_mode#--}"

listing="$(tar -tzf "$archive")"
if [[ -z "$listing" ]]; then
  printf 'Artifact archive is empty.\n' >&2
  exit 1
fi

roots="$(printf '%s\n' "$listing" | awk -F/ 'NF {print $1}' | LC_ALL=C sort -u)"
if [[ "$roots" != "$expected_root" ]]; then
  printf 'Artifact must contain exactly the root %s; found:\n%s\n' \
    "$expected_root" "$roots" >&2
  exit 1
fi

if printf '%s\n' "$listing" | rg -q '(^/|(^|/)\.\.(/|$))'; then
  printf 'Artifact contains an unsafe member path.\n' >&2
  exit 1
fi

unexpected_types="$(tar -tvzf "$archive" | cut -c1 | rg -v '^[-d]$' || true)"
if [[ -n "$unexpected_types" ]]; then
  printf 'Artifact contains links or special filesystem members.\n' >&2
  exit 1
fi

if printf '%s\n' "$listing" | rg -q --pcre2 \
  '(^|/)(data/external|supported_research_paper|node_modules|experiments/results|runtime|artifacts)(/|$)|(^|/)data/pilots/heldout-v1-questions\.json$|(^|/)data/manifests/coda-community-45-extracted\.sha256$|third_party/(?!README\.md$)'; then
  printf 'Artifact contains a forbidden member.\n' >&2
  exit 1
fi

if printf '%s\n' "$listing" | rg -q '(^|/)\.env($|\.)' &&
   printf '%s\n' "$listing" | rg '(^|/)\.env($|\.)' | rg -qv '/\.env\.example$'; then
  printf 'Artifact contains a private environment file.\n' >&2
  exit 1
fi

license_members="$(
  printf '%s\n' "$listing" |
    rg "^$expected_root/LICENSE(?:\.txt|\.md)?$" || true
)"
license_count="$(printf '%s\n' "$license_members" | sed '/^$/d' | wc -l | tr -d ' ')"
if [[ "$rebuild_mode" == "--public" && "$license_count" != "1" ]]; then
  printf 'Public artifact must contain exactly one root license; found %s.\n' \
    "$license_count" >&2
  exit 1
fi
if (( license_count > 1 )); then
  printf 'Artifact contains ambiguous root license files.\n' >&2
  exit 1
fi

if printf '%s\n' "$listing" | rg -q \
  "^$expected_root/paper/(acmart\.cls|pvldb\.sty|ACM-Reference-Format\.bst)$"; then
  printf 'Artifact must fetch checksum-pinned upstream paper templates, not redistribute them.\n' >&2
  exit 1
fi

required_members=(
  .env.example
  README.md
  ARTIFACT.md
  Makefile
  backend/pyproject.toml
  backend/src/askdu/adapters/repository.py
  backend/src/askdu/adapters/provider_metering.py
  backend/src/askdu/application/agentic_pipeline.py
  backend/src/askdu/application/analysis_notebook.py
  backend/src/askdu/application/report_writer.py
  backend/src/askdu/api/app.py
  backend/tests/test_repository.py
  backend/uv.lock
  compose.yaml
  compose.model-smoke.yaml
  data/README.md
  data/manifests/coda-public-source-provenance-v1.json
  data/manifests/coda-bench-v1-open-release.json
  backend/deployment/api.py
  backend/deployment/repository.py
  backend/deployment/service.py
  docs/evaluation.md
  docs/demo-interface.md
  docs/stage-io-validation.md
  docs/agentic-open-evaluation.md
  docs/heldout-protocol.md
  docs/user-trials/README.md
  docs/user-trials/facilitator-protocol.md
  docs/user-trials/participant-task-card.md
  docs/user-trials/record.example.json
  docs/video-narration.md
  docs/video-review.example.json
  docs/vldb2027-status.json
  experiments/evidence/dependency-license-inventory-v0.4.0.json
  experiments/evidence/demo-path-latency-v0.4.0.json
  experiments/agentic_open_evaluation.py
  experiments/evidence/agentic-question-only-smoke-2026-09-09.json
  frontend/package-lock.json
  frontend/src/App.tsx
  frontend/src/components/ResearchWorkflowPanel.tsx
  frontend/src/components/ReportPanel.tsx
  frontend/e2e/research-workflow.spec.ts
  frontend/e2e/capture-agentic-replay.mjs
  frontend/src/reportExport.ts
  frontend/public/notices/dependency-license-inventory-v0.4.0.json
  infra/ecs/askdu-compose.service.example
  infra/ecs/host-nginx.conf.example
  infra/ecs/production.env.example
  paper/citation-audit-v1.json
  paper/main.tex
  paper/references.bib
  paper/TEMPLATE_SOURCE.md
  paper/figures/agentic-replay-v1/capture.json
  paper/figures/agentic-replay-v1/overview.pdf
  scripts/audit_artifact_archive.py
  scripts/audit_dependencies.sh
  scripts/audit_dependency_licenses.py
  scripts/audit_submission_readiness.py
  scripts/benchmark_demo_path.py
  scripts/build_artifact_bundle.sh
  scripts/check_demo_video.py
  scripts/check_ecs_deployment.py
  scripts/check_host_nginx_syntax.sh
  scripts/check_vldb2027_status.py
  scripts/fetch_paper_template.sh
  scripts/hash_demo_surface.sh
  scripts/hash_user_trial_protocol.sh
  scripts/mock_chat_provider.py
  scripts/run_demo.sh
  scripts/sync_coda_open_release.py
  scripts/mux_demo_narration.py
  scripts/verify_demo_latency.py
  scripts/verify_artifact_bundle.sh
  scripts/verify_paper_citations.py
)
for member in "${required_members[@]}"; do
  if ! printf '%s\n' "$listing" | rg -qFx "$expected_root/$member"; then
    printf 'Artifact is missing required member: %s\n' "$member" >&2
    exit 1
  fi
done

scratch="$(mktemp -d /tmp/askdu-artifact-verify.XXXXXX)"
cleanup() {
  case "$scratch" in
    /tmp/askdu-artifact-verify.*) find "$scratch" -depth -delete ;;
    *) printf 'Refusing to clean unexpected path: %s\n' "$scratch" >&2 ;;
  esac
}
trap cleanup EXIT

tar -xzf "$archive" --directory "$scratch" --no-same-owner
extracted_root="$scratch/$expected_root"
if find "$extracted_root" -type l -print -quit | rg -q .; then
  printf 'Artifact contains a symbolic link.\n' >&2
  exit 1
fi

rebuilt_dir="$scratch/rebuilt"
mkdir "$rebuilt_dir"
ASKDU_ARTIFACT_OUTPUT_DIR="$rebuilt_dir" \
  "$extracted_root/scripts/build_artifact_bundle.sh" "$rebuild_mode" >/dev/null
rebuilt_archive="$rebuilt_dir/$(basename "$archive")"
if ! cmp --silent "$archive" "$rebuilt_archive"; then
  printf 'Clean-room rebuild differs from the supplied artifact.\n' >&2
  exit 1
fi

printf 'PASS: verified %s members and reproduced the artifact byte-for-byte.\n' \
  "$(printf '%s\n' "$listing" | wc -l | tr -d ' ')"
