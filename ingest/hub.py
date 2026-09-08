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


# ------------------------------------------------- dreamproit/uscode (stage 3)

USCODE_DATASET = "dreamproit/uscode"
HUB_API = "https://huggingface.co/api/datasets/{dataset}"
HUB_RESOLVE = "https://huggingface.co/datasets/{dataset}/resolve/{revision}/{path}"


def uscode_dataset_info(*, dataset: str = USCODE_DATASET) -> dict:
    """The Hub's record of the dataset: `sha` (the revision), `lastModified`,
    and `siblings` (every file)."""
    response = httpx.get(
        HUB_API.format(dataset=dataset), follow_redirects=True, timeout=60.0,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    return response.json()


def fetch_uscode_shards(directory: Path, *, config: str = "current", force: bool = False,
                        dataset: str = USCODE_DATASET) -> tuple[str, list[Path]]:
    """Download the parquet shards of one config (`current/train-*.parquet`)
    into `directory`, skipping files already there. Returns the dataset
    revision the listing came from and the local paths, in shard order."""
    info = uscode_dataset_info(dataset=dataset)
    revision = info.get("sha") or "main"
    names = sorted(
        s["rfilename"] for s in info.get("siblings", [])
        if s["rfilename"].startswith(f"{config}/") and s["rfilename"].endswith(".parquet")
    )
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name in names:
        target = directory / Path(name).name
        paths.append(target)
        if target.exists() and not force:
            continue
        partial = target.with_suffix(".parquet.part")
        with httpx.stream(
            "GET", HUB_RESOLVE.format(dataset=dataset, revision=revision, path=name),
            follow_redirects=True, timeout=300.0, headers={"User-Agent": USER_AGENT},
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
        partial.replace(target)
    (directory / "REVISION").write_text(revision + "\n")
    return revision, paths
