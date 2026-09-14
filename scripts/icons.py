"""Render the apple-touch icon from the committed favicon.

    DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --with cairosvg python scripts/icons.py

(`DYLD_FALLBACK_LIBRARY_PATH` is for macOS with Homebrew's cairo.) cairosvg is
not a project dependency; the output is committed.

`static/favicon.svg` is rendered with its light-scheme colours, its `<style>`
block and corner radius removed, onto an opaque 180 px square at
`frontend/public/icons/apple-touch-icon-180.png`. The reader serves it at
`/app/icons/apple-touch-icon-180.png`. The glyph comes from whichever font the
machine resolves for the favicon's stack.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "static" / "favicon.svg"
OUTPUT = ROOT / "frontend" / "public" / "icons" / "apple-touch-icon-180.png"
SIZE = 180


def take(svg: str, pattern: str, what: str) -> str:
    match = re.search(pattern, svg)
    if not match:
        raise SystemExit(f"static/favicon.svg: cannot find {what} ({pattern})")
    return match.group(1)


def flat(svg: str) -> str:
    """The favicon with its classes replaced by the light-scheme fills."""
    bg = take(svg, r"\.bg\s*\{\s*fill:\s*(#[0-9a-fA-F]{3,8})", "the .bg fill")
    fg = take(svg, r"\.fg\s*\{\s*fill:\s*(#[0-9a-fA-F]{3,8})", "the .fg fill")
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
    svg = re.sub(r"<style>.*?</style>", "", svg, flags=re.S)
    svg = re.sub(r'\s+rx="[\d.]+"', "", svg)
    return svg.replace('class="bg"', f'fill="{bg}"').replace('class="fg"', f'fill="{fg}"')


def main() -> None:
    try:
        from cairosvg import svg2png
    except (ModuleNotFoundError, OSError) as error:
        raise SystemExit(
            "cairosvg is not importable. Run this as:\n"
            "  DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run --with cairosvg "
            f"python scripts/icons.py\n({error})"
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    svg2png(
        bytestring=flat(SOURCE.read_text()).encode(),
        write_to=str(OUTPUT),
        output_width=SIZE,
        output_height=SIZE,
    )
    print(f"{OUTPUT.stat().st_size:,} bytes -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
