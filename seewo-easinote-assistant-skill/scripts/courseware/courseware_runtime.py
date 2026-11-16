#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Formal runtime helpers shared by ENBX generation and MCP operations."""
import os
import re

from subject_tools import NATIVE_SUBJECT_TOOLS

TOOL_TYPES = set(NATIVE_SUBJECT_TOOLS) | {'function', 'mindmap', 'table'}


def is_url(source):
    """Return whether a resource is an HTTP(S) URL."""
    return bool(re.match(r"^https?://", source or "", re.I))


def resolve_asset_path(source, base_dir=None):
    """Resolve relative local resources before handing them to Seewo MCP."""
    if not source or is_url(source) or os.path.isabs(source):
        return source
    return os.path.abspath(os.path.join(base_dir or os.getcwd(), source))


def page_subject_tool(page):
    """Return a page tool, including the supported nested content form."""
    tool = page.get("subjectTool")
    if isinstance(tool, dict) and tool.get("type"):
        return tool
    content = page.get("content")
    if isinstance(content, dict):
        nested = content.get("subjectTool")
        if isinstance(nested, dict) and nested.get("type"):
            return nested
    return tool if isinstance(tool, dict) else None


def normalize_mindmap_markdown(markdown):
    """Convert Markdown headings and list items to the nested list Seewo MCP needs.

    The Seewo mindmap MCP expects a multi-level markdown list whose depth is
    expressed by leading spaces. Spec authors may write heading style
    ("# 主题 / ## 分支 / - 子项") or list style ("- 主题 /   - 分支").

    This normalizer converts headings to indented list items and, for list
    items WITHOUT explicit indentation, indents them one level below the most
    recent heading. Without this, a spec mixing headings and bare list items
    ("## 临海" then "- 东临碣石") collapses the list items to root level and
    the client renders only the root node and its first branch.
    """
    result = []
    heading_level = 0  # 最近的 # 标题层级（0 = 尚未出现标题）
    for raw in (markdown or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        heading = re.match(r"^(#{1,6})\s*(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            heading_level = level
            result.append("  " * (level - 1) + "- " + heading.group(2).strip())
            continue
        if stripped.startswith(("-", "*")):
            text = stripped.lstrip("-* ").strip()
            indent = len(raw) - len(raw.lstrip(" \t"))
            if indent == 0 and heading_level > 0:
                # 无缩进列表项：作为最近标题的下一级子项
                indent = 2 * heading_level
            result.append(" " * max(indent, 0) + "- " + text)
            continue
        result.append(raw)
    return "\n".join(result)


def _choice_question(item):
    if 'correctOption' in item and 'wrongOptions' in item:
        return item
    options = list(item.get("options") or [])
    answer = item.get("answer")
    if isinstance(answer, int) and not isinstance(answer, bool) and 0 <= answer < len(options):
        correct = options[answer]
    else:
        correct = answer
    wrong = [value for value in options if value != correct]
    return {
        "question": item.get("question", ""),
        "correctOption": correct,
        "wrongOptions": wrong,
    }


def activity_payload_to_mcp_args(activity_type, payload):
    """Convert authored activity data to the live MCP argument contract."""
    if activity_type == "choice":
        items = payload if isinstance(payload, list) else payload.get("questions", [])
        return {"questions": [_choice_question(item) for item in items]}
    if activity_type == "judge":
        if isinstance(payload, dict) and "statements" in payload and "answers" in payload:
            return {"statements": payload["statements"], "answers": payload["answers"]}
        items = payload if isinstance(payload, list) else payload.get("questions", [])

        def as_bool(value):
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "对", "正确"}
            return bool(value)

        return {
            "statements": [item.get("statement", item.get("question", "")) for item in items],
            "answers": [as_bool(item.get("answer")) for item in items],
        }
    if activity_type == "classify":
        items = payload if isinstance(payload, list) else payload.get("categories", [])
        return {"categories": [
            {"name": category.get("name", ""),
             "items": category.get("items") or category.get("words") or []}
            for category in items if isinstance(category, dict)
        ]}
    if activity_type == "match":
        items = payload if isinstance(payload, list) else payload.get("pairs", [])
        return {"pairs": [
            {"left": pair.get("left", pair.get("term", "")),
             "right": pair.get("right", pair.get("definition", ""))}
            for pair in items if isinstance(pair, dict)
        ]}
    return payload if isinstance(payload, dict) else {}
