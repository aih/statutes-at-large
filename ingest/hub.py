"""Fetch volume USLM from the Hub dataset `dreamproit/us-statutes-at-large`."""

from __future__ import annotations

from pathlib import Path

import httpx

HUB_DATASET = "dreamproit/us-statutes-at-large"
HUB_FILE = "https://huggingface.co/datasets/{dataset}/resolve/main/xmls/STATUTE-{volume}.xml"
USER_AGENT = "statutes-linkedlegislation/0.1 (+https://statutes.linkedlegislation.org)"


def volume_url(volume: int) -> str:
    return HUB_FILE.format(dataset=HUB_DATASET, volume=volume)


def fetch_volume(volume: int, directory: Path, *, force: bool = False) -> Path:
    """Download `xmls/STATUTE-{n}.xml` into `directory`, skipping a file already there."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"STATUTE-{volume}.xml"
    if target.exists() and not force:
        return target
    partial = target.with_suffix(".xml.part")
    with httpx.stream(
        "GET", volume_url(volume), follow_redirects=True, timeout=120.0,
        headers={"User-Agent": USER_AGENT},
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    partial.replace(target)
    return target
