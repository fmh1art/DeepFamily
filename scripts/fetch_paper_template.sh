#!/usr/bin/env bash
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
paper_dir="${ASKDU_PAPER_DIR:-$project_root/paper}"
template_revision="39c95f5c6fcbe652a83be24e4eff8f2134cd3fbc"
template_base_url="https://raw.githubusercontent.com/vldbproceedings/VLDB-Template/$template_revision"

acmart_sha256="2f949e6e3f2a79f2cdc218b9dcdbaa7dd451adb4ee0be1af6dc7ebe00b318ea7"
pvldb_upstream_sha256="52ad3948f3231b31d2ac90f470c1759e7f96add7b577ec4e267dfbdc87fc4eb2"
pvldb_local_sha256="bbf67313dfc26c82c71160e073ed23f826cb4f85a1359dc6eebcb276dbeb5354"
bibliography_sha256="0590db3b8d255a3af91982ab710f3ace5fcaa52434020c9af8a4f141b00b68f3"

with_direct_network() {
  env \
    -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    "$@"
}

has_digest() {
  local path="$1"
  local expected="$2"
  [ -f "$path" ] && [ "$(sha256sum "$path" | awk '{print $1}')" = "$expected" ]
}

refuse_drift() {
  local path="$1"
  local expected="$2"
  if [ -e "$path" ] && ! has_digest "$path" "$expected"; then
    printf 'Refusing to overwrite a modified template file: %s\n' "$path" >&2
    return 1
  fi
}

download() {
  local url="$1"
  local output="$2"
  local -a curl_args=(
    --fail
    --location
    --silent
    --show-error
    --retry 2
    --connect-timeout 20
    --max-time 120
    --output "$output"
    "$url"
  )
  if ! curl "${curl_args[@]}"; then
    with_direct_network curl "${curl_args[@]}"
  fi
}

verify_digest() {
  local path="$1"
  local expected="$2"
  local actual
  actual=$(sha256sum "$path" | awk '{print $1}')
  if [ "$actual" != "$expected" ]; then
    printf 'Template checksum mismatch for %s: expected %s, got %s\n' \
      "$path" "$expected" "$actual" >&2
    return 1
  fi
}

mkdir -p "$paper_dir"
refuse_drift "$paper_dir/acmart.cls" "$acmart_sha256"
refuse_drift "$paper_dir/pvldb.sty" "$pvldb_local_sha256"
refuse_drift "$paper_dir/ACM-Reference-Format.bst" "$bibliography_sha256"

if has_digest "$paper_dir/acmart.cls" "$acmart_sha256" \
  && has_digest "$paper_dir/pvldb.sty" "$pvldb_local_sha256" \
  && has_digest "$paper_dir/ACM-Reference-Format.bst" "$bibliography_sha256"; then
  printf 'Paper template is already present at pinned revision %s.\n' \
    "$template_revision"
  exit 0
fi

temporary_dir=$(mktemp -d /tmp/askdu-paper-template.XXXXXX)
cleanup() {
  case "$temporary_dir" in
    /tmp/askdu-paper-template.*) find "$temporary_dir" -depth -delete ;;
    *) printf 'Refusing to clean unexpected temporary path: %s\n' "$temporary_dir" >&2 ;;
  esac
}
trap cleanup EXIT

download "$template_base_url/acmart.cls" "$temporary_dir/acmart.cls"
download "$template_base_url/pvldb.sty" "$temporary_dir/pvldb.sty.upstream"
download \
  "$template_base_url/ACM-Reference-Format.bst" \
  "$temporary_dir/ACM-Reference-Format.bst"

verify_digest "$temporary_dir/acmart.cls" "$acmart_sha256"
verify_digest "$temporary_dir/pvldb.sty.upstream" "$pvldb_upstream_sha256"
verify_digest "$temporary_dir/ACM-Reference-Format.bst" "$bibliography_sha256"

# The pinned upstream pvldb.sty omits its final POSIX newline. Normalize only
# that byte, matching the checksum guarded by check_submission.sh.
cp "$temporary_dir/pvldb.sty.upstream" "$temporary_dir/pvldb.sty"
printf '\n' >> "$temporary_dir/pvldb.sty"
verify_digest "$temporary_dir/pvldb.sty" "$pvldb_local_sha256"

if [ ! -e "$paper_dir/acmart.cls" ]; then
  install -m 0644 "$temporary_dir/acmart.cls" "$paper_dir/acmart.cls"
fi
if [ ! -e "$paper_dir/pvldb.sty" ]; then
  install -m 0644 "$temporary_dir/pvldb.sty" "$paper_dir/pvldb.sty"
fi
if [ ! -e "$paper_dir/ACM-Reference-Format.bst" ]; then
  install -m 0644 \
    "$temporary_dir/ACM-Reference-Format.bst" \
    "$paper_dir/ACM-Reference-Format.bst"
fi

verify_digest "$paper_dir/acmart.cls" "$acmart_sha256"
verify_digest "$paper_dir/pvldb.sty" "$pvldb_local_sha256"
verify_digest "$paper_dir/ACM-Reference-Format.bst" "$bibliography_sha256"
printf 'Fetched checksum-pinned paper template revision %s.\n' "$template_revision"
