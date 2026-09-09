#!/usr/bin/env bash
set -u

mode="${1:---submission}"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tex_file="$root_dir/paper/main.tex"
pdf_file="$root_dir/paper/main.pdf"
log_file="$root_dir/paper/main.log"
error_count=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  error_count=$((error_count + 1))
}

note() {
  printf 'INFO: %s\n' "$1"
}

if [[ "$mode" != "--draft" && "$mode" != "--submission" ]]; then
  printf 'Usage: %s [--draft|--submission]\n' "$0" >&2
  exit 2
fi

if [[ ! -f "$tex_file" ]]; then
  fail "missing paper/main.tex"
else
  rg -qF '\documentclass[sigconf, nonacm]{acmart}' "$tex_file" || \
    fail "official acmart document class declaration is missing or changed"
  rg -qF '\usepackage{pvldb}' "$tex_file" || \
    fail "mandatory \\usepackage{pvldb} block is missing"
  rg -qF '\vldbtopmatter' "$tex_file" || \
    fail "mandatory \\vldbtopmatter block is missing"

  if rg -qF '\renewcommand\vldbavailabilityurl{}' "$tex_file"; then
    if [[ "$mode" == "--submission" ]]; then
      fail "artifact availability URL is empty"
    else
      note "artifact availability URL remains empty in the draft"
    fi
  fi

  marker_pattern='TODO|TBD|PLACEHOLDER|SystemName|Author Name|author@example\.com'
  markers="$(rg -n "$marker_pattern" "$tex_file")"
  if [[ -n "$markers" ]]; then
    if [[ "$mode" == "--submission" ]]; then
      fail "unresolved draft markers remain in paper/main.tex"
    else
      note "draft markers remain, as expected in an unfinished draft"
    fi
    printf '%s\n' "$markers" | sed -n '1,30p'
  else
    note "no unresolved draft markers found"
  fi
fi

template_hash_specs=(
  "2f949e6e3f2a79f2cdc218b9dcdbaa7dd451adb4ee0be1af6dc7ebe00b318ea7:acmart.cls"
  "bbf67313dfc26c82c71160e073ed23f826cb4f85a1359dc6eebcb276dbeb5354:pvldb.sty"
  "0590db3b8d255a3af91982ab710f3ace5fcaa52434020c9af8a4f141b00b68f3:ACM-Reference-Format.bst"
)

for template_spec in "${template_hash_specs[@]}"; do
  expected_hash="${template_spec%%:*}"
  template_file="${template_spec#*:}"
  if [[ ! -s "$root_dir/paper/$template_file" ]]; then
    fail "missing official template file: paper/$template_file"
  elif command -v sha256sum >/dev/null 2>&1; then
    actual_hash="$(sha256sum "$root_dir/paper/$template_file" | awk '{print $1}')"
    if [[ "$actual_hash" != "$expected_hash" ]]; then
      fail "official template file changed: paper/$template_file"
    fi
  else
    fail "sha256sum is unavailable; official template files were not verified"
  fi
done

if [[ -f "$pdf_file" ]]; then
  if command -v pdfinfo >/dev/null 2>&1; then
    pages="$(pdfinfo "$pdf_file" | awk '/^Pages:/ {print $2}')"
    if [[ -z "$pages" ]]; then
      fail "could not determine PDF page count"
    elif (( pages > 4 )); then
      fail "PDF has $pages pages; the provisional VLDB demo limit is 4"
    else
      note "PDF page count: $pages (within provisional 4-page limit)"
    fi

    page_size="$(pdfinfo "$pdf_file" | awk -F: '/^Page size:/ {sub(/^[[:space:]]+/, "", $2); print $2}')"
    if [[ "$page_size" != *"612 x 792 pts"* ]]; then
      fail "PDF page size is not US Letter: ${page_size:-unknown}"
    fi
  else
    note "pdfinfo is unavailable; page count was not checked"
  fi


  if command -v pdffonts >/dev/null 2>&1; then
    unembedded_fonts="$(pdffonts "$pdf_file" | awk 'NR > 2 && $(NF-4) != "yes" {print}')"
    if [[ -n "$unembedded_fonts" ]]; then
      fail "PDF contains unembedded fonts"
      printf '%s\n' "$unembedded_fonts" | sed -n '1,20p'
    else
      note "all PDF fonts are embedded"
    fi
  else
    note "pdffonts is unavailable; font embedding was not checked"
  fi
else
  if [[ "$mode" == "--submission" ]]; then
    fail "paper/main.pdf is missing; build the paper before submission check"
  else
    note "paper/main.pdf is not built yet"
  fi
fi

if [[ -f "$log_file" ]] && rg -q \
  'Overfull|Undefined control sequence|undefined citations|Warning: Citation|LaTeX Warning|Fatal error' \
  "$log_file"; then
  fail "paper/main.log contains a blocking LaTeX warning or error"
fi

if (( error_count > 0 )); then
  printf 'FAILED: %d issue(s) found.\n' "$error_count" >&2
  exit 1
fi

printf 'PASS: %s checks completed.\n' "${mode#--}"
