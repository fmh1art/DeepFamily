#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
third_party_root="$project_root/third_party"
coda_data_root="$project_root/data/external/coda-bench"
coda_revision="63828a2b652e26a9770555a0cc41e6c8aafdb5d9"
zstd_bin=""

usage() {
  printf 'Usage: %s [--code] [--coda-pilots] [--coda-heldout] [--all]\n' "$0"
}

with_direct_network() {
  env \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    "$@"
}

resolve_zstd() {
  local candidate
  if [ -n "${ZSTD_BIN:-}" ]; then
    if [ ! -x "$ZSTD_BIN" ]; then
      printf 'ZSTD_BIN is not executable: %s\n' "$ZSTD_BIN" >&2
      return 1
    fi
    zstd_bin="$ZSTD_BIN"
    return 0
  fi
  if command -v zstd >/dev/null 2>&1; then
    zstd_bin=$(command -v zstd)
    return 0
  fi
  for candidate in \
    /usr/bin/zstd \
    /usr/local/bin/zstd \
    /opt/homebrew/bin/zstd \
    /opt/tiger/ss_bin/zstd; do
    if [ -x "$candidate" ]; then
      zstd_bin="$candidate"
      printf 'Using zstd outside PATH: %s\n' "$zstd_bin"
      return 0
    fi
  done
  printf 'zstd is required; install it or set ZSTD_BIN=/absolute/path/to/zstd.\n' >&2
  return 1
}

clone_at_revision() {
  local repo_url="$1"
  local target_dir="$2"
  local revision="$3"
  local actual_revision

  if [ -d "$target_dir/.git" ]; then
    if [ -n "$(git -C "$target_dir" status --porcelain)" ]; then
      printf 'Refusing to change dirty third-party clone: %s\n' "$target_dir" >&2
      return 1
    fi
  else
    mkdir -p "$(dirname "$target_dir")"
    if ! GIT_TERMINAL_PROMPT=0 git clone --filter=blob:none --no-checkout "$repo_url" "$target_dir"; then
      with_direct_network env GIT_TERMINAL_PROMPT=0 \
        git clone --filter=blob:none --no-checkout "$repo_url" "$target_dir"
    fi
  fi

  if ! git -C "$target_dir" cat-file -e "${revision}^{commit}" 2>/dev/null; then
    if ! GIT_TERMINAL_PROMPT=0 git -C "$target_dir" fetch --depth 1 origin "$revision"; then
      with_direct_network env GIT_TERMINAL_PROMPT=0 \
        git -C "$target_dir" fetch --depth 1 origin "$revision"
    fi
  fi
  git -C "$target_dir" checkout --detach "$revision"
  actual_revision=$(git -C "$target_dir" rev-parse HEAD)
  if [ "$actual_revision" != "$revision" ]; then
    printf 'Revision verification failed for %s\n' "$target_dir" >&2
    return 1
  fi
  printf '%s\t%s\n' "$target_dir" "$actual_revision"
}

fetch_code() {
  clone_at_revision \
    https://github.com/ruc-datalab/CoDA-Bench.git \
    "$third_party_root/CoDA-Bench" \
    24f2eee08c60d3a6826654ed39a621631b68a73a
  clone_at_revision \
    https://github.com/ruc-datalab/DeepPrep.git \
    "$third_party_root/DeepPrep" \
    0b6e4431def5364e9bf23a255c6e44a4034e2e8a
  clone_at_revision \
    https://github.com/ruc-datalab/DeepAnalyze.git \
    "$third_party_root/DeepAnalyze" \
    d14468b9ef91372359ddcd70da57e0e0f4eb0d1b
}

download_coda_files() {
  local -a download_args
  mkdir -p "$coda_data_root"
  download_args=(
    download RUC-DataLab/CoDA-Bench
    README.md
    coda_bench.json
    coda_bench_hard.json
    archives/community_43.tar.zst
    archives/community_52.tar.zst
    --repo-type dataset
    --revision "$coda_revision"
    --local-dir "$coda_data_root"
    --max-workers 2
  )
  if ! hf "${download_args[@]}"; then
    with_direct_network hf "${download_args[@]}"
  fi

  (
    cd "$coda_data_root"
    sha256sum -c "$project_root/data/manifests/coda-community-43.sha256"
    sha256sum -c "$project_root/data/manifests/coda-community-52.sha256"
  )
}

extract_coda_community() (
  local community_id="$1"
  local target_dir="$coda_data_root/communities/community_${community_id}"
  local archive member_list extraction_dir extracted
  if [ -d "$target_dir/full_community" ]; then
    printf 'CoDA community already extracted: %s\n' "$target_dir"
    return 0
  fi

  archive="$coda_data_root/archives/community_${community_id}.tar.zst"
  member_list=$(mktemp)
  extraction_dir=$(mktemp -d "$coda_data_root/.community${community_id}-extract.XXXXXX")
  cleanup() {
    rm -f -- "$member_list"
    rm -rf -- "$extraction_dir"
  }
  trap cleanup EXIT

  "$zstd_bin" -dc "$archive" | tar -tf - > "$member_list"
  python3 - "$member_list" <<'PY'
import pathlib
import sys

members = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
unsafe = [
    member
    for member in members
    if pathlib.PurePosixPath(member).is_absolute()
    or ".." in pathlib.PurePosixPath(member).parts
]
if unsafe:
    raise SystemExit("Unsafe archive members: " + ", ".join(unsafe[:5]))
PY
  "$zstd_bin" -dc "$archive" | tar -xf - -C "$extraction_dir"
  extracted="$extraction_dir/data/community_${community_id}"
  if [ ! -d "$extracted/full_community" ]; then
    printf 'Unexpected CoDA archive layout\n' >&2
    return 1
  fi
  mkdir -p "$(dirname "$target_dir")"
  mv "$extracted" "$target_dir"
  printf 'Extracted CoDA community: %s\n' "$target_dir"
)

verify_coda_csv_assets() (
  local community_id="$1"
  local manifest="$project_root/data/manifests/coda-community-${community_id}-csv.sha256"
  if [ ! -f "$manifest" ]; then
    printf 'Missing extracted-asset manifest: %s\n' "$manifest" >&2
    return 1
  fi
  cd "$coda_data_root"
  sha256sum -c "$manifest"
)

fetch_coda_pilots() {
  command -v hf >/dev/null || {
    printf 'The Hugging Face CLI (hf) is required.\n' >&2
    return 1
  }
  resolve_zstd
  download_coda_files
  extract_coda_community 43
  extract_coda_community 52
  verify_coda_csv_assets 43
  verify_coda_csv_assets 52
}

fetch_coda_heldout() {
  local -a download_args
  command -v hf >/dev/null || {
    printf 'The Hugging Face CLI (hf) is required.\n' >&2
    return 1
  }
  mkdir -p "$coda_data_root"
  download_args=(
    download RUC-DataLab/CoDA-Bench
    archives/community_45.tar.zst
    --repo-type dataset
    --revision "$coda_revision"
    --local-dir "$coda_data_root"
    --max-workers 2
  )
  if ! hf "${download_args[@]}"; then
    with_direct_network hf "${download_args[@]}"
  fi
  (
    cd "$coda_data_root"
    sha256sum -c "$project_root/data/manifests/coda-community-45.sha256"
  )
  printf 'Held-out archive verified but intentionally not listed or extracted.\n'
}

fetch_code_requested=false
fetch_pilot_requested=false
fetch_heldout_requested=false

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    --code)
      fetch_code_requested=true
      ;;
    --coda-pilot|--coda-pilots)
      fetch_pilot_requested=true
      ;;
    --coda-heldout)
      fetch_heldout_requested=true
      ;;
    --all)
      fetch_code_requested=true
      fetch_pilot_requested=true
      fetch_heldout_requested=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ "$fetch_code_requested" = true ]; then
  fetch_code
fi
if [ "$fetch_pilot_requested" = true ]; then
  fetch_coda_pilots
fi
if [ "$fetch_heldout_requested" = true ]; then
  fetch_coda_heldout
fi
