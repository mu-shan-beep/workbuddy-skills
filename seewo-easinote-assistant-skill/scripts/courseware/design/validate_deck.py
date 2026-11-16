#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate courseware content, visuals, and native tool contracts."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from courseware_runtime import TOOL_TYPES  # noqa: E402
from rich_text import to_plain  # noqa: E402
from subject_tools import (native_tool_spec, validate_activity_usage,  # noqa: E402
                           validate_native_tool)
from visual_plan_renderer import content_slots, validate_authored_visual  # noqa: E402

GENERIC_ANTI = {"避免单调", "不要单调", "注意排版", "无", ""}
ACTIVITY_IMAGE_FIELDS = ("image", "background", "imagePrompt", "imageLabel")
# 结构页不计入页数区间，且豁免内容密度检查
STRUCTURAL_ROLES = ("cover", "toc", "section")
INTENT_DENSITY = {
    "moment": (80, 120),
    "evidence": (100, 150),
    "sequence": (120, 180),
    "compare": (120, 180),
    "practice": (100, 150),
    "summary": (80, 120),
}
MIN_ITEM_TEXT = 24
MINDMAP_NOTES_FLOOR = 60


def _mindmap_hierarchy(markdown):
    """Return ``(has_nested, top_level_count)`` for a mindmap markdown body.

    A real mind map needs parent-child hierarchy.  If there are several
    top-level nodes but no nested branches, the content is likely a flat list
    better served by ``items`` or ``table``.
    """
    has_nested = False
    top_level = 0
    for raw in (markdown or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level == 1:
                top_level += 1
            elif level >= 2:
                has_nested = True
        elif stripped.startswith(("-", "*")):
            indent = len(raw) - len(raw.lstrip(" \t"))
            if indent == 0:
                top_level += 1
            else:
                has_nested = True
    return has_nested, top_level


def _page_role(page):
    """Return normalized structural role (cover/toc/section) or None."""
    return str(page.get("role") or "").strip().lower() or None


def _page_chars(page):
    chars = len(to_plain(page.get("body") or ""))
    chars += len(to_plain(page.get("lead") or ""))
    chars += len(to_plain(page.get("question") or ""))
    chars += len(to_plain(page.get("answer") or ""))
    chars += len(to_plain(page.get("summary") or ""))
    for item in page.get("items") or []:
        if isinstance(item, dict):
            text = item.get("text") or item.get("body") or ""
            chars += len(to_plain((item.get("title") or "") + text))
        else:
            chars += len(to_plain(str(item)))
    for element in ((page.get("visualPlan") or {}).get("elements") or []):
        if isinstance(element, dict) and element.get("kind") == "image":
            chars += len(to_plain(element.get("caption") or ""))
    return chars


def validate_deck(spec):
    errors, warnings = [], []
    pages = spec.get("pages", [])
    if not pages:
        return ["pages 为空"], warnings

    activity_count = sum(
        1 for page in pages
        if page.get("layout") == "activity_page"
        or (page.get("activity") or {}).get("activityType"))
    content_page_count = sum(1 for page in pages if _page_role(page) is None)

    visual_errors, visual_warnings = validate_authored_visual(spec)
    errors.extend(visual_errors)
    warnings.extend(visual_warnings)
    if visual_errors:
        return errors, warnings

    plan = spec.get("pagePlan") or {}
    rng = plan.get("range")
    if not rng:
        warnings.append("spec 缺少 pagePlan.range：新建课件必须写入用户确认的"
                        "页数区间（如 [5, 10]），封面/目录/章节页不计入")
    else:
        try:
            low, high = int(rng[0]), int(rng[1])
        except (TypeError, ValueError, IndexError):
            errors.append("pagePlan.range 非法 %r：应为 [最小页数, 最大页数]，"
                          "如 [5, 10]" % (rng,))
        else:
            content_count = sum(1 for page in pages if _page_role(page) is None)
            if content_count < low:
                errors.append(
                    "有效内容页 %d 页 < 用户确认区间下限 %d（封面/目录/章节页"
                    "不计入）：扩充教学环节，或与用户确认下调区间" %
                    (content_count, low))
            elif content_count > high:
                errors.append(
                    "有效内容页 %d 页 > 用户确认区间上限 %d（封面/目录/章节页"
                    "不计入）：合并页面，或与用户确认上调区间" %
                    (content_count, high))

    for index, page in enumerate(pages):
        label = "pages[%d](%s)" % (index, page.get("title", ""))
        layout = page.get("layout")
        if not page.get("title") and layout != "activity_page":
            errors.append("%s 缺少 title" % label)

        role = _page_role(page)
        if role is not None and role not in STRUCTURAL_ROLES:
            errors.append("%s role 非法 %r：仅支持 cover/toc/section，"
                          "内容页应省略 role" % (label, page.get("role")))
            continue
        if role is not None:
            # 结构页（封面/目录/章节）不计入页数区间，豁免内容密度与分层检查
            continue

        if layout == "tool_page":
            tool = page.get("subjectTool") or {}
            if tool.get("type") not in TOOL_TYPES:
                errors.append("%s tool_page 缺少合法 subjectTool.type" % label)
            elif native_tool_spec(tool.get("type")):
                tool_errors, tool_warnings = validate_native_tool(
                    tool, subject=spec.get("subject", ""),
                    grade=spec.get("grade", ""), require_intent=False)
                errors.extend("%s %s" % (label, item) for item in tool_errors)
                warnings.extend("%s %s" % (label, item) for item in tool_warnings)
            elif tool.get("type") == "mindmap":
                data = tool.get("data") or {}
                markdown = str(data.get("mdStr") or data.get("markdown") or "")
                long_nodes = [line.strip(" #*-") for line in markdown.splitlines()
                              if line.strip() and len(line.strip(" #*-")) > 4]
                if long_nodes:
                    warnings.append("%s 脑图节点超 4 字会被定宽节点挤压：%s" %
                                    (label, "、".join(long_nodes[:3])))
                has_nested, top_level = _mindmap_hierarchy(markdown)
                if top_level >= 2 and not has_nested:
                    warnings.append(
                        "%s 脑图有 %d 个一级节点但无子分支：若内容不存在父子层级"
                        "关系，建议改用 items 列表或 table 呈现" %
                        (label, top_level))
                background = (page.get("visualPlan") or {}).get("background") or {}
                planning = spec.get("visualPlanning") or {}
                no_image_mode = (planning.get("backgroundImageMinRatio") == 0
                                 or spec.get("imageStrategy") == "none")
                if background.get("type") != "image":
                    message = ("%s 思维导图页必须使用与本课视觉世界和谐的背景图，"
                               "组件安全区内保持安静低细节，不得退化为纯色底" % label)
                    (warnings if no_image_mode else errors).append(message)
                slots = content_slots(page)
                note_names = [name for name in slots
                              if name not in ("title", "kicker")]
                note_chars = sum(len(slots[name]) for name in note_names)
                if not note_names:
                    errors.append(
                        "%s 思维导图页缺少文字说明：除标题外至少提供 lead 任务引导"
                        "或 body 结构说明，建议补充 1-3 条 items" % label)
                elif note_chars < MINDMAP_NOTES_FLOOR:
                    warnings.append(
                        "%s 思维导图页说明文字 %d 字 < 建议 %d：补充任务引导与层级"
                        "划分依据，使页面翔实可读" % (label, note_chars,
                                                        MINDMAP_NOTES_FLOOR))

        if layout == "activity_page":
            if not (page.get("activity") or {}).get("activityType"):
                errors.append("%s activity_page 缺少 activity.activityType" % label)
            declared = [field for field in ACTIVITY_IMAGE_FIELDS if page.get(field)]
            if declared:
                errors.append("%s 课堂活动页不得声明背景图或配图字段：%s" %
                              (label, "/".join(declared)))
            continue

        if layout != "tool_page":
            chars = _page_chars(page)
            intent = ((page.get("visualPlan") or {}).get("teachingIntent")
                      or page.get("visualIntent") or "evidence")
            hard_floor, recommended_floor = INTENT_DENSITY.get(
                intent, INTENT_DENSITY["evidence"])
            if chars < hard_floor:
                errors.append(
                    "%s 内容严重不足：%d 字 < 硬下限 %d。至少补齐核心结论、"
                    "具体解释或证据、学生任务或评价中的三层信息，或与相邻页合并" %
                    (label, chars, hard_floor))
            elif chars < recommended_floor:
                warnings.append(
                    "%s 内容 %d 字 < 建议 %d：补充解释、证据、例子、"
                    "辨析或成功标准，避免页面只剩一句结论" %
                    (label, chars, recommended_floor))
            short_items = [
                item_index + 1 for item_index, item in enumerate(page.get("items") or [])
                if (isinstance(item, dict)
                    and len(to_plain(item.get("text") or item.get("body") or ""))
                    < MIN_ITEM_TEXT)
            ]
            if short_items:
                warnings.append(
                    "%s 第%s项正文不足 %d 字：每项应包含要点及解释或依据" %
                    (label, "/".join(map(str, short_items)), MIN_ITEM_TEXT))

            content_layers = sum(1 for field in ("lead", "body", "question",
                                                 "answer", "summary")
                                 if to_plain(page.get(field) or ""))
            items_count = len(page.get("items") or [])
            if items_count:
                content_layers += 1
            if content_layers < 3:
                warnings.append(
                    "%s 信息分层不足（%d层 < 3）：authored_canvas 页至少使用 "
                    "lead/body/items/question/answer/summary 中的 3 种，"
                    "形成「核心结论→证据→任务」或「问题→答案→拓展」等多层结构" %
                    (label, content_layers))

        anti_pattern = str(page.get("anti_pattern") or "").strip()
        if anti_pattern in GENERIC_ANTI:
            warnings.append("%s.anti_pattern 空泛（%r）：必须写本页具体禁止项" %
                            (label, anti_pattern))

    activity_errors, activity_warnings = validate_activity_usage(
        spec.get("grade", ""), activity_count, content_page_count)
    errors.extend(activity_errors)
    warnings.extend(activity_warnings)

    return errors, warnings


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="页面计划校验")
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()
    with open(args.spec, encoding="utf-8") as handle:
        found_errors, found_warnings = validate_deck(json.load(handle))
    for warning in found_warnings:
        print("⚠ %s" % warning)
    for error in found_errors:
        print("✗ %s" % error)
    sys.exit(1 if found_errors else 0)
