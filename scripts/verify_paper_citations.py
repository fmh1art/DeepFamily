from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEX_PATH = PROJECT_ROOT / "paper" / "main.tex"
BIB_PATH = PROJECT_ROOT / "paper" / "references.bib"
AUDIT_PATH = PROJECT_ROOT / "paper" / "citation-audit-v1.json"
USER_AGENT = "AskDU-Citation-Audit/0.4 (+https://www.vldb.org/2027/)"
ENTRY_START = re.compile(
    r"@(?P<entry_type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,",
    flags=re.MULTILINE,
)
CITATION = re.compile(
    r"\\cite[A-Za-z]*\s*(?:\[[^\]]*\]\s*){0,2}\{(?P<keys>[^}]*)\}",
    flags=re.MULTILINE,
)
ARXIV_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class BibEntry:
    entry_type: str
    fields: dict[str, str]


def strip_tex_comments(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        comment_at: int | None = None
        for index, character in enumerate(line):
            if character != "%":
                continue
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                comment_at = index
                break
        lines.append(line if comment_at is None else line[:comment_at])
    return "\n".join(lines)


def find_closing_brace(text: str, opening_index: int) -> int:
    depth = 0
    for index in range(opening_index, len(text)):
        character = text[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
    raise ValueError(f"unbalanced BibTeX entry beginning at byte {opening_index}")


def split_top_level(text: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    brace_depth = 0
    quoted = False
    escaped = False
    for index, character in enumerate(text):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"' and brace_depth == 0:
            quoted = not quoted
        elif not quoted:
            if character == "{":
                brace_depth += 1
            elif character == "}":
                brace_depth -= 1
                if brace_depth < 0:
                    raise ValueError("unbalanced braces in BibTeX field list")
            elif character == delimiter and brace_depth == 0:
                parts.append(text[start:index])
                start = index + 1
    if brace_depth != 0 or quoted:
        raise ValueError("unbalanced BibTeX field value")
    parts.append(text[start:])
    return parts


def unwrap_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and (
        (value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')
    ):
        return value[1:-1].strip()
    raise ValueError(f"BibTeX values must be braced or quoted: {value!r}")


def parse_fields(body: str, key: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for chunk in split_top_level(body, ","):
        if not chunk.strip():
            continue
        assignment = split_top_level(chunk, "=")
        if len(assignment) != 2:
            raise ValueError(f"invalid field assignment in {key}: {chunk.strip()!r}")
        name = assignment[0].strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise ValueError(f"invalid field name in {key}: {name!r}")
        if name in fields:
            raise ValueError(f"duplicate field in {key}: {name}")
        fields[name] = unwrap_value(assignment[1])
    if not fields:
        raise ValueError(f"BibTeX entry has no fields: {key}")
    return fields


def parse_bibliography(text: str) -> dict[str, BibEntry]:
    entries: dict[str, BibEntry] = {}
    cursor = 0
    while match := ENTRY_START.search(text, cursor):
        opening_index = text.find("{", match.start(), match.end())
        closing_index = find_closing_brace(text, opening_index)
        key = match.group("key")
        if key in entries:
            raise ValueError(f"duplicate BibTeX key: {key}")
        entries[key] = BibEntry(
            entry_type=match.group("entry_type").lower(),
            fields=parse_fields(text[match.end() : closing_index], key),
        )
        cursor = closing_index + 1
    return entries


def cited_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for match in CITATION.finditer(strip_tex_comments(text)):
        for key in match.group("keys").split(","):
            normalized = key.strip()
            if normalized:
                keys.add(normalized)
    return keys


def normalized_space(value: str) -> str:
    return " ".join(value.split())


def normalized_title(value: str) -> str:
    without_commands = re.sub(r"\\[A-Za-z]+", "", value)
    without_braces = without_commands.translate(str.maketrans("", "", "{}"))
    return "".join(
        character.lower() for character in without_braces if character.isalnum()
    )


def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    return value


def validate_record(
    key: str,
    entry: BibEntry,
    record_value: Any,
    seen_sources: set[tuple[str, str]],
) -> tuple[str, str, str]:
    record = require_mapping(record_value, f"records.{key}")
    expected_type = record.get("entry_type")
    if expected_type != entry.entry_type:
        raise ValueError(
            f"{key}: entry type drifted (expected {expected_type!r}, found {entry.entry_type!r})"
        )

    expected_fields_value = require_mapping(
        record.get("expected_fields"),
        f"records.{key}.expected_fields",
    )
    expected_fields = {
        str(name).lower(): normalized_space(str(value))
        for name, value in expected_fields_value.items()
    }
    actual_fields = {
        name: normalized_space(value) for name, value in entry.fields.items()
    }
    if actual_fields != expected_fields:
        missing = sorted(expected_fields.keys() - actual_fields.keys())
        extra = sorted(actual_fields.keys() - expected_fields.keys())
        changed = sorted(
            name
            for name in actual_fields.keys() & expected_fields.keys()
            if actual_fields[name] != expected_fields[name]
        )
        raise ValueError(
            f"{key}: audited BibTeX fields drifted; missing={missing}, extra={extra}, "
            f"changed={changed}"
        )

    source = require_mapping(record.get("source"), f"records.{key}.source")
    kind = source.get("kind")
    identifier = source.get("identifier")
    url = source.get("url")
    if kind not in {"arxiv", "doi", "official_pdf"}:
        raise ValueError(f"{key}: unsupported source kind {kind!r}")
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError(f"{key}: source identifier must be a non-empty string")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"{key}: source URL must use HTTPS")
    source_identity = (kind, identifier.lower())
    if source_identity in seen_sources:
        raise ValueError(f"{key}: duplicate audited source {kind}:{identifier}")
    seen_sources.add(source_identity)

    if kind == "arxiv":
        if entry.fields.get("eprint") != identifier:
            raise ValueError(f"{key}: arXiv identifier and eprint field differ")
        if url != f"https://arxiv.org/abs/{identifier}":
            raise ValueError(f"{key}: non-canonical arXiv source URL")
    else:
        if entry.fields.get("doi", "").lower() != identifier.lower():
            raise ValueError(f"{key}: source identifier and DOI field differ")
        if kind == "doi" and url != f"https://doi.org/{identifier}":
            raise ValueError(f"{key}: non-canonical DOI source URL")

    return kind, identifier, url


def fetch_bytes(url: str, *, headers: Mapping[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status not in {200, 206}:
            raise RuntimeError(f"unexpected HTTP {response.status} for {url}")
        return response.read()


def verify_doi_online(identifier: str, expected_title: str) -> None:
    encoded = urllib.parse.quote(identifier, safe="")
    payload = json.loads(
        fetch_bytes(f"https://api.crossref.org/works/{encoded}").decode("utf-8")
    )
    message = require_mapping(payload.get("message"), f"Crossref {identifier}")
    remote_doi = str(message.get("DOI", ""))
    titles = message.get("title")
    if remote_doi.lower() != identifier.lower():
        raise ValueError(f"Crossref returned a different DOI for {identifier}")
    if not isinstance(titles, list) or not titles:
        raise ValueError(f"Crossref returned no title for {identifier}")
    if normalized_title(str(titles[0])) != normalized_title(expected_title):
        raise ValueError(f"Crossref title differs for {identifier}")


def verify_arxiv_online(identifier: str, expected_title: str) -> None:
    encoded = urllib.parse.quote(identifier, safe="")
    payload = fetch_bytes(f"https://export.arxiv.org/api/query?id_list={encoded}")
    root = ET.fromstring(payload)
    entries = root.findall("atom:entry", ARXIV_NAMESPACE)
    if len(entries) != 1:
        raise ValueError(f"arXiv returned {len(entries)} entries for {identifier}")
    remote_id = entries[0].findtext("atom:id", default="", namespaces=ARXIV_NAMESPACE)
    remote_title = entries[0].findtext(
        "atom:title", default="", namespaces=ARXIV_NAMESPACE
    )
    unversioned_remote_id = re.sub(r"v\d+$", "", remote_id)
    if not unversioned_remote_id.endswith(f"/{identifier}"):
        raise ValueError(f"arXiv returned a different identifier for {identifier}")
    if normalized_title(remote_title) != normalized_title(expected_title):
        raise ValueError(f"arXiv title differs for {identifier}")


def verify_pdf_online(url: str) -> None:
    payload = fetch_bytes(url, headers={"Range": "bytes=0-4095"})
    if not payload.startswith(b"%PDF-"):
        raise ValueError(f"official paper URL did not return a PDF: {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that every paper citation matches its audited primary metadata."
    )
    parser.add_argument(
        "--online",
        action="store_true",
        help="also query Crossref, arXiv, and official PVLDB PDFs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = require_mapping(
        json.loads(AUDIT_PATH.read_text(encoding="utf-8")),
        "citation audit",
    )
    if audit.get("schema_version") != "citation-audit-v1":
        raise ValueError("unsupported citation audit schema")
    checked_at = audit.get("checked_at")
    if (
        not isinstance(checked_at, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_at) is None
    ):
        raise ValueError("citation audit checked_at must be an ISO date")

    entries = parse_bibliography(BIB_PATH.read_text(encoding="utf-8"))
    citations = cited_keys(TEX_PATH.read_text(encoding="utf-8"))
    records = require_mapping(audit.get("records"), "records")
    bibliography_keys = set(entries)
    record_keys = set(records)
    if citations != bibliography_keys or citations != record_keys:
        raise ValueError(
            "citation coverage mismatch: "
            f"uncited_bib={sorted(bibliography_keys - citations)}, "
            f"missing_bib={sorted(citations - bibliography_keys)}, "
            f"unaudited={sorted(citations - record_keys)}, "
            f"stale_audit={sorted(record_keys - citations)}"
        )

    seen_sources: set[tuple[str, str]] = set()
    online_sources: list[tuple[str, str, str, str]] = []
    for key in sorted(citations):
        kind, identifier, url = validate_record(
            key,
            entries[key],
            records[key],
            seen_sources,
        )
        online_sources.append((kind, identifier, url, entries[key].fields["title"]))

    if args.online:
        for kind, identifier, url, title in online_sources:
            if kind == "doi":
                verify_doi_online(identifier, title)
            elif kind == "arxiv":
                verify_arxiv_online(identifier, title)
            else:
                verify_pdf_online(url)
            print(f"ONLINE PASS: {kind}:{identifier}")

    mode = (
        "offline manifest and online primary sources"
        if args.online
        else "offline manifest"
    )
    print(
        f"PASS: {len(citations)} cited entries match the {mode} "
        f"(metadata checked {checked_at})."
    )


if __name__ == "__main__":
    main()
