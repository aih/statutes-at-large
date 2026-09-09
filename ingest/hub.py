"""Fetch volume USLM from the Hub dataset `dreamproit/us-statutes-at-large`,
and ask the Hub what changed (`fetch-statute --if-changed`)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

HUB_DATASET = "dreamproit/us-statutes-at-large"
HUB_FILE = "https://huggingface.co/datasets/{dataset}/resolve/main/xmls/STATUTE-{volume}.xml"
HUB_TREE = "https://huggingface.co/api/datasets/{dataset}/tree/main/xmls"
USER_AGENT = "statutes-linkedlegislation/0.1 (+https://statutes.linkedlegislation.org)"
VOLUME_NAME = re.compile(r"STATUTE-(\d+)\.xml$")


def volume_url(volume: int) -> str:
    return HUB_FILE.format(dataset=HUB_DATASET, volume=volume)


def tree_url(*, dataset: str = HUB_DATASET) -> str:
    return HUB_TREE.format(dataset=dataset)


def volume_of(path: Path | str) -> int | None:
    """`STATUTE-64.xml` → 64; None for any other name."""
    match = VOLUME_NAME.search(str(path))
    return int(match.group(1)) if match else None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    """The git object id of the file as a blob: what the Hub's tree listing
    reports as `oid` for a file that is not stored through LFS."""
    path = Path(path)
    digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


# ------------------------------------------------------ the tree listing


@dataclass(frozen=True, slots=True)
class HubFile:
    """One entry of the tree listing. A file stored through LFS carries the
    sha256 of its content (`lfs.oid`); any other file carries only the git
    blob id (`oid`)."""

    path: str
    size: int
    git_oid: str
    sha256: str | None

    @property
    def volume(self) -> int | None:
        return volume_of(self.path)

    def matches(self, local: Path) -> bool:
        """Whether the file on disk is byte-for-byte the listed one: the size
        first, then the sha256 when the Hub has one, else the git blob id."""
        local = Path(local)
        if not local.exists() or local.stat().st_size != self.size:
            return False
        if self.sha256:
            return sha256_of(local) == self.sha256
        return git_blob_sha1(local) == self.git_oid


def parse_tree(entries: list[dict]) -> list[HubFile]:
    files: list[HubFile] = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        lfs = entry.get("lfs") or {}
        files.append(
            HubFile(
                path=entry["path"],
                size=int(lfs.get("size", entry.get("size", 0)) or entry.get("size", 0)),
                git_oid=entry.get("oid", ""),
                sha256=lfs.get("oid"),
            )
        )
    return files


def list_volume_files(*, dataset: str = HUB_DATASET, client: httpx.Client | None = None) -> dict[int, HubFile]:
    """The volumes on the Hub, from `/api/datasets/{dataset}/tree/main/xmls`,
    following the `Link: <…>; rel="next"` pages. Keyed by volume number."""
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=60.0, headers={"User-Agent": USER_AGENT})
    found: dict[int, HubFile] = {}
    try:
        url: str | None = tree_url(dataset=dataset)
        while url:
            response = client.get(url)
            response.raise_for_status()
            for entry in parse_tree(response.json()):
                if entry.volume is not None:
                    found[entry.volume] = entry
            url = _next_link(response.headers.get("link"))
    finally:
        if own:
            client.close()
    return found


def _next_link(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel="?next"?', part)
        if match:
            return match.group(1)
    return None


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
                        dataset: str = USCODE_DATASET, info: dict | None = None) -> tuple[str, list[Path]]:
    """Download the parquet shards of one config (`current/train-*.parquet`)
    into `directory`, skipping files already there. Returns the dataset
    revision the listing came from and the local paths, in shard order.
    `info` is a dataset record already fetched (`uscode_dataset_info`), so a
    caller that asked the Hub once does not ask twice."""
    info = info if info is not None else uscode_dataset_info(dataset=dataset)
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
