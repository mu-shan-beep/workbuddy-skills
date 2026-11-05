#!/usr/bin/env python3
"""Print the next versioned PPT path without changing any files."""

import argparse
import re
from pathlib import Path


VERSION = re.compile(r"^(?P<base>.+)_V(?P<number>\d+)$")
PPT_SUFFIXES = {".pptx", ".pptm", ".ppsx", ".potx"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path, help="Current canonical PPT file")
    args = parser.parse_args()
    current = args.current.expanduser()
    if not current.is_file():
        parser.error(f"Current file does not exist: {current}")
    if current.suffix.lower() not in PPT_SUFFIXES:
        parser.error(f"Not a supported PowerPoint file: {current}")

    match = VERSION.fullmatch(current.stem)
    base = match.group("base") if match else current.stem
    number = int(match.group("number")) if match else 0
    if VERSION.fullmatch(base):
        parser.error(f"Stacked version suffix in current filename: {current.name}")
    versioned_name = re.compile(rf"^{re.escape(base)}_V(\d+)$")
    for sibling in current.parent.iterdir():
        if not sibling.is_file() or sibling.suffix.lower() != current.suffix.lower():
            continue
        other = versioned_name.fullmatch(sibling.stem)
        if other and int(other.group(1)) > number:
            parser.error(f"Newer version already exists; confirm the canonical file: {sibling}")

    target = current.with_name(f"{base}_V{number + 1}{current.suffix}")
    if target.exists():
        parser.error(f"Target already exists: {target}")
    print(target)


if __name__ == "__main__":
    main()
