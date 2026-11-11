#!/usr/bin/env python3
"""Compare structural invariants between an original PPTX and an edited copy."""

import argparse
import hashlib
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile


SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
TIMING_TAG = "{http://schemas.openxmlformats.org/presentationml/2006/main}timing"
TEXT_TAG = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
SLIDE_ID_LIST_TAG = "{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst"
RELATIONSHIP_ID_ATTR = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def element_signature(element):
    if element is None:
        return None
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        tuple(element_signature(child) for child in element),
    )


def digest_entry(archive, name):
    digest = hashlib.sha256()
    with archive.open(name) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xml_digest(archive, name):
    # Ignore harmless XML declaration and namespace-prefix rewrites by editors.
    normalized = ET.tostring(ET.fromstring(archive.read(name)))
    return hashlib.sha256(normalized).hexdigest()


def relationships(archive, names):
    result = {}
    for name in names:
        if not name.startswith("ppt/") or not name.endswith(".rels"):
            continue
        root = ET.fromstring(archive.read(name))
        result[name] = tuple(
            sorted(
                (
                    item.get("Id", ""),
                    item.get("Type", ""),
                    item.get("Target", ""),
                    item.get("TargetMode", ""),
                )
                for item in root
            )
        )
    return result


def slide_order(archive, package_relationships):
    root = ET.fromstring(archive.read("ppt/presentation.xml"))
    slide_ids = root.find(SLIDE_ID_LIST_TAG)
    targets = {
        relationship_id: target
        for relationship_id, _type, target, _mode in package_relationships.get(
            "ppt/_rels/presentation.xml.rels", ()
        )
    }
    if slide_ids is None:
        return ()
    order = []
    for slide_id in slide_ids:
        target = targets.get(slide_id.get(RELATIONSHIP_ID_ATTR, ""), "")
        if target.startswith("/"):
            order.append(target.lstrip("/"))
        else:
            order.append(posixpath.normpath(posixpath.join("ppt", target)))
    return tuple(order)


def inspect(path):
    with ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        slide_names = {
            int(match.group(1)): name
            for name in names
            if (match := SLIDE_RE.fullmatch(name))
        }
        timing = {}
        slide_text = {}
        for slide, name in slide_names.items():
            root = ET.fromstring(archive.read(name))
            timing[slide] = element_signature(root.find(TIMING_TAG))
            slide_text[slide] = tuple(
                node.text or "" for node in root.iter(TEXT_TAG)
            )
        media_names = [
            name for name in names if "media" in PurePosixPath(name).parts
        ]
        media_hashes = {name: digest_entry(archive, name) for name in media_names}
        package_relationships = relationships(archive, names)
        template_hashes = {
            name: xml_digest(archive, name)
            for name in names
            if name.startswith(("ppt/slideMasters/", "ppt/slideLayouts/", "ppt/theme/"))
            and not name.endswith(".rels")
        }
        return (
            slide_names,
            slide_order(archive, package_relationships),
            slide_text,
            timing,
            media_hashes,
            package_relationships,
            template_hashes,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", help="Original PPTX")
    parser.add_argument("edited", help="Edited PPTX copy")
    parser.add_argument(
        "--allow-text-slides",
        default="",
        help="Comma-separated slide numbers whose text was intentionally changed",
    )
    parser.add_argument(
        "--allow-slide-structure-change",
        action="store_true",
        help="Accept intentional slide insertion, deletion, or reordering",
    )
    parser.add_argument(
        "--allow-timing-slides",
        default="",
        help="Comma-separated slide numbers whose animation was intentionally changed",
    )
    parser.add_argument(
        "--allow-media-change",
        action="store_true",
        help="Accept intentional embedded-media changes",
    )
    parser.add_argument(
        "--allow-relationship-change",
        action="store_true",
        help="Accept intentional package relationship changes",
    )
    parser.add_argument(
        "--allow-template-change",
        action="store_true",
        help="Accept intentional master, layout, or theme changes",
    )
    args = parser.parse_args()
    try:
        allowed_text = {
            int(value.strip())
            for value in args.allow_text_slides.split(",")
            if value.strip()
        }
        allowed_timing = {
            int(value.strip())
            for value in args.allow_timing_slides.split(",")
            if value.strip()
        }
        (
            before_slides, before_order, before_text, before_timing,
            before_media, before_relationships, before_template,
        ) = inspect(args.original)
        (
            after_slides, after_order, after_text, after_timing,
            after_media, after_relationships, after_template,
        ) = inspect(args.edited)
    except (ValueError, OSError, BadZipFile, ET.ParseError, KeyError) as exc:
        parser.error(str(exc))

    text_changed = sorted(
        slide
        for slide in before_slides.keys() | after_slides.keys()
        if before_text.get(slide) != after_text.get(slide)
    )
    timing_changed = sorted(
        slide
        for slide in before_slides.keys() | after_slides.keys()
        if before_timing.get(slide) != after_timing.get(slide)
    )
    media_content_preserved = Counter(before_media.values()) == Counter(
        after_media.values()
    )
    media_paths_preserved = before_media.keys() == after_media.keys()
    problems = []
    if before_slides.keys() != after_slides.keys() and not args.allow_slide_structure_change:
        problems.append("slide_set_changed")
    if before_order != after_order and not args.allow_slide_structure_change:
        problems.append("slide_order_changed")
    if not media_content_preserved and not args.allow_media_change:
        problems.append("unexpected_media_change")
    if not media_paths_preserved and not args.allow_media_change:
        problems.append("unexpected_media_path_change")
    if before_relationships != after_relationships and not args.allow_relationship_change:
        problems.append("unexpected_relationship_change")
    if before_template != after_template and not args.allow_template_change:
        problems.append("unexpected_template_change")
    if set(text_changed) - allowed_text:
        problems.append("unexpected_text_change")
    if set(timing_changed) - allowed_timing:
        problems.append("unexpected_timing_change")

    result = {
        "slides_before": len(before_slides),
        "slides_after": len(after_slides),
        "slide_set_preserved": before_slides.keys() == after_slides.keys(),
        "slide_order_preserved": before_order == after_order,
        "media_before": len(before_media),
        "media_after": len(after_media),
        "media_content_preserved": media_content_preserved,
        "media_paths_preserved": media_paths_preserved,
        "relationships_preserved": before_relationships == after_relationships,
        "template_preserved": before_template == after_template,
        "text_changed_slides": text_changed,
        "timing_changed_slides": timing_changed,
        "unexpected": problems,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
