from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE: dict[str, Any] = runpy.run_path(str(PROJECT_ROOT / "scripts/check_vldb2027_status.py"))


def test_parser_distinguishes_body_copy_from_an_official_demo_link() -> None:
    parse_page = MODULE["parse_page"]
    is_demo_link = MODULE["is_demo_link"]
    html = """
      <html><body>
        <p>The conference will feature demonstrations.</p>
        <a href="call-for-research-track.html">Research Track</a>
      </body></html>
    """
    links, text, table_text = parse_page(html, "https://www.vldb.org/2027/")

    assert "demonstrations" in text
    assert table_text == ""
    assert not any(is_demo_link(link) for link in links)


def test_parser_detects_demo_link_and_dates_row() -> None:
    parse_page = MODULE["parse_page"]
    is_demo_link = MODULE["is_demo_link"]
    table_has_demo_track = MODULE["table_has_demo_track"]
    html = """
      <html><body>
        <a href="call-for-demonstrations.html">Demonstrations</a>
        <table><tr><td>Demonstration Track</td><td>March 30</td></tr></table>
      </body></html>
    """
    links, _, table_text = parse_page(html, "https://www.vldb.org/2027/")

    assert any(is_demo_link(link) for link in links)
    assert table_has_demo_track(table_text)


def test_vendor_comparison_allows_only_a_trailing_newline_difference() -> None:
    equivalent_vendor_bytes = MODULE["equivalent_vendor_bytes"]

    assert equivalent_vendor_bytes(b"content\n", b"content")
    assert equivalent_vendor_bytes(b"content", b"content\n")
    assert not equivalent_vendor_bytes(b"content\n\n", b"content")
    assert not equivalent_vendor_bytes(b"changed\n", b"content\n")
