"""The tab mark at /favicon.svg and the two API docs pages that name it."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = "{http://www.w3.org/2000/svg}"


def test_the_favicon_is_served_from_the_root(client):
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["cache-control"] == "public, max-age=86400"
    root = ET.fromstring(response.content)
    assert root.tag == f"{SVG}svg"
    assert root.find(f"{SVG}text").text == "§"


def test_the_favicon_carries_the_us_code_sites_colours():
    svg = (ROOT / "static" / "favicon.svg").read_text()
    assert ".bg { fill: #1a4480; }" in svg
    assert ".fg { fill: #ffffff; }" in svg
    assert ".bg { fill: #2670c4; }" in svg


def test_favicon_ico_redirects_to_the_svg(client):
    response = client.get("/favicon.ico", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/favicon.svg"


def test_the_docs_pages_name_the_favicon(client):
    for path in ("/docs", "/redoc"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'href="/favicon.svg"' in response.text
        assert "fastapi.tiangolo.com" not in response.text


def test_the_apple_touch_icon_is_180_pixels_square():
    data = (ROOT / "frontend" / "public" / "icons" / "apple-touch-icon-180.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 180
    assert int.from_bytes(data[20:24], "big") == 180
