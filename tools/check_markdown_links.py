"""Check repository-local targets in Markdown links.

The checker intentionally validates file existence only. Heading anchors are renderer-
specific (especially for Chinese headings), so fragment validation is left to browser
or repository-renderer checks.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)")
IGNORED_SCHEMES = {"app", "data", "file", "http", "https", "mailto", "vscode"}


def iter_markdown_files(paths: list[Path]) -> list[Path]:
    """Expand file and directory arguments into a stable Markdown file list."""

    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(
                candidate
                for candidate in path.rglob("*.md")
                if candidate.is_file() and "node_modules" not in candidate.parts
            )
        elif path.is_file():
            files.add(path)
        else:
            raise FileNotFoundError(path)
    return sorted(files, key=lambda item: item.as_posix().casefold())


def local_target(markdown_file: Path, raw_target: str) -> Path | None:
    """Resolve a local Markdown link target, ignoring URLs and pure anchors."""

    target = raw_target.removeprefix("<").removesuffix(">")
    if not target or target.startswith("#"):
        return None

    parsed = urlsplit(target)
    if parsed.scheme.casefold() in IGNORED_SCHEMES:
        return None
    if parsed.scheme:
        return None

    decoded_path = unquote(parsed.path)
    if not decoded_path:
        return None

    app_file_link = re.fullmatch(r"/?([A-Za-z]:[\\/].*):\d+", decoded_path)
    if app_file_link:
        return Path(app_file_link.group(1))

    candidate = Path(decoded_path)
    if candidate.is_absolute():
        return candidate
    return (markdown_file.parent / candidate).resolve()


def check_file(markdown_file: Path) -> list[tuple[int, str, Path]]:
    """Return missing local link targets as line, raw target, resolved path tuples."""

    missing: list[tuple[int, str, Path]] = []
    text = markdown_file.read_text(encoding="utf-8")
    fence_marker: str | None = None
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence_marker is None:
                fence_marker = marker
            elif fence_marker == marker:
                fence_marker = None
            continue
        if fence_marker is not None:
            continue
        for match in LINK_PATTERN.finditer(line):
            raw_target = match.group("target")
            resolved = local_target(markdown_file, raw_target)
            if resolved is not None and not resolved.exists():
                missing.append((line_number, raw_target, resolved))
    return missing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check that repository-local Markdown link targets exist."
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files or directories")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        markdown_files = iter_markdown_files(args.paths)
    except FileNotFoundError as exc:
        print(f"input path does not exist: {exc}", file=sys.stderr)
        return 2

    missing_count = 0
    for markdown_file in markdown_files:
        for line_number, raw_target, resolved in check_file(markdown_file):
            missing_count += 1
            print(
                f"{markdown_file}:{line_number}: missing {raw_target} -> {resolved}",
                file=sys.stderr,
            )

    print(f"checked_files={len(markdown_files)} missing_links={missing_count}")
    return 1 if missing_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
