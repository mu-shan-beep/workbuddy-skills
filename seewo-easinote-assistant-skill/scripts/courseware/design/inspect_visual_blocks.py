#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""List the semantic content slots that an authored visual plan must place."""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 父目录 scripts/courseware 承载 rich_text 等共享模块，裸跑（不加 PYTHONPATH）时也要能解析
sys.path.insert(0, os.path.dirname(HERE))

from visual_plan_renderer import content_slots, text_contrast_report  # noqa: E402


def inspect_spec(spec):
    contrast_by_page = {item["page"]: item["contrast"]
                        for item in text_contrast_report(spec)}
    pages = []
    for index, page in enumerate(spec.get("pages") or [], 1):
        illustrations = []
        for element in (page.get("visualPlan") or {}).get("elements") or []:
            if isinstance(element, dict) and element.get("kind") == "image":
                illustrations.append({
                    "source": element.get("source") or "",
                    "role": element.get("role", "illustration"),
                    "caption": element.get("caption") or "",
                })
        entry = {
            "page": index,
            "title": page.get("title", ""),
            "interactive": bool(page.get("activity")),
            "nativeTool": (page.get("subjectTool") or {}).get("type"),
            "illustrations": illustrations,
            "slots": [
                {"source": source, "characters": len(text), "preview": text[:80]}
                for source, text in content_slots(page).items()
            ],
        }
        if index in contrast_by_page:
            entry["contrast"] = contrast_by_page[index]
        pages.append(entry)
    return {"pages": pages}


def main():
    parser = argparse.ArgumentParser(
        description="检查 AI 视觉计划可绑定的教学内容槽与文字对比度预检")
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()
    with open(args.spec, encoding="utf-8") as handle:
        result = inspect_spec(json.load(handle))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
