from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = PROJECT_ROOT / "docs/vldb2027-status.json"
USER_AGENT = "AskDU-CFP-Monitor/0.4 (+https://www.vldb.org/2027/)"
VENDOR_FILES = ("acmart.cls", "pvldb.sty", "ACM-Reference-Format.bst")


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []
        self.text: list[str] = []
        self.table_text: list[str] = []
        self._table_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag == "table":
            self._table_depth += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urljoin(self.base_url, href))

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._table_depth > 0:
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if not normalized:
            return
        self.text.append(normalized)
        if self._table_depth:
            self.table_text.append(normalized)


def parse_page(html: str, base_url: str) -> tuple[list[str], str, str]:
    parser = _PageParser(base_url)
    parser.feed(html)
    return parser.links, " ".join(parser.text), " ".join(parser.table_text)


def is_demo_link(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc in {"vldb.org", "www.vldb.org"}
        and (
            "demonstration" in parsed.path.lower()
            or "call-for-demo" in parsed.path.lower()
        )
    )


def table_has_demo_track(table_text: str) -> bool:
    return (
        re.search(r"\bdemonstrations?\b", table_text, flags=re.IGNORECASE) is not None
    )


def equivalent_vendor_bytes(local: bytes, upstream: bytes) -> bool:
    return local == upstream or local == upstream + b"\n" or upstream == local + b"\n"


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP status {response.status} for {url}")
        return response.read()


def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8")


def remote_head(repository: str) -> str:
    process = subprocess.run(
        ["git", "ls-remote", repository, "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    match = re.fullmatch(r"([0-9a-f]{40})\s+refs/heads/main\s*", process.stdout)
    if match is None:
        raise RuntimeError("could not parse the official template HEAD")
    return match.group(1)


def main() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    urls = snapshot["official_urls"]
    expected = snapshot["expected"]

    homepage_links, _, _ = parse_page(fetch_text(urls["homepage"]), urls["homepage"])
    _, _, dates_table = parse_page(
        fetch_text(urls["important_dates"]),
        urls["important_dates"],
    )
    _, formatting_text, _ = parse_page(
        fetch_text(urls["formatting_guidelines"]),
        urls["formatting_guidelines"],
    )

    demo_links = sorted({link for link in homepage_links if is_demo_link(link)})
    demo_cfp_present = bool(demo_links)
    demo_dates_present = table_has_demo_track(dates_table)
    formatting_signature_present = all(
        phrase in formatting_text
        for phrase in ("PVLDB template", "mandatory blocks", "desk rejection")
    )

    head = remote_head(urls["template_repository"])
    vendor_matches: dict[str, bool] = {}
    for name in VENDOR_FILES:
        upstream_url = (
            "https://raw.githubusercontent.com/vldbproceedings/"
            f"VLDB-Template/{head}/{name}"
        )
        vendor_matches[name] = equivalent_vendor_bytes(
            (PROJECT_ROOT / "paper" / name).read_bytes(),
            fetch_bytes(upstream_url),
        )

    print(f"Demo CFP link present: {str(demo_cfp_present).lower()}")
    print(f"Demo row in Important Dates: {str(demo_dates_present).lower()}")
    print(
        f"Formatting warning signature present: {str(formatting_signature_present).lower()}"
    )
    print(f"Official template HEAD: {head}")
    print(
        "Vendor files match HEAD: "
        + ", ".join(
            f"{name}={str(matches).lower()}" for name, matches in vendor_matches.items()
        )
    )

    problems: list[str] = []
    if demo_cfp_present != expected["demo_cfp_link_present"]:
        problems.append("the official Demo CFP-link state changed")
    if demo_dates_present != expected["demo_dates_row_present"]:
        problems.append("the official Demo deadline-row state changed")
    if not formatting_signature_present:
        problems.append("the formatting-guideline warning changed or disappeared")
    if head != expected["template_head"]:
        problems.append("the official template HEAD changed")
    if not all(vendor_matches.values()):
        problems.append("one or more local vendor templates differ from official HEAD")

    if problems:
        for problem in problems:
            print(f"ACTION REQUIRED: {problem}.", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"PASS: official status matches snapshot checked on {snapshot['checked_at']}."
    )


if __name__ == "__main__":
    main()
