#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render an authored page plan directly to a native ENBX deck."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from enbx_backend import EnbxDeck  # noqa: E402
from visual_plan_renderer import (is_authored_visual, render_authored_page,  # noqa: E402
                                  validate_authored_visual,
                                  write_authored_manifest)


def render_deck_enbx(spec, out_path):
    """Render a validated authored plan; native activities keep a blank base."""
    if not is_authored_visual(spec):
        raise ValueError("新建课件必须提供根级 visualPlanning 视觉计划")
    errors, _warnings = validate_authored_visual(spec)
    if errors:
        raise ValueError("AI 视觉计划未通过校验：%s" % "; ".join(errors))

    deck = EnbxDeck(title=spec.get("title", "未命名课件"))
    for page in spec.get("pages", []):
        is_activity = page.get("layout") == "activity_page" or bool(page.get("activity"))
        slide = deck.new_slide(bg="#FFFFFFFF")
        if not is_activity:
            render_authored_page(slide, spec, page)

    deck.save(out_path)
    write_authored_manifest(spec, out_path)
    return out_path


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="页面计划 → ENBX")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with open(args.spec, encoding="utf-8") as handle:
        render_deck_enbx(json.load(handle), args.out)
    print("已生成 %s" % args.out)
