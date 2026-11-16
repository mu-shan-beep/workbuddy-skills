# -*- coding: utf-8 -*-
"""内容槽校验：从页面提取 AI 视觉计划必须逐一绑定的语义内容槽。"""
from collections import OrderedDict

from rich_text import parse_rich

CANVAS_W = 1280
CANVAS_H = 720


def is_authored_visual(spec):
    """本路径 spec 必须提供根级 visualPlanning 视觉计划。"""
    return isinstance(spec.get("visualPlanning"), dict)


def _content_dict(page):
    value = page.get("content") or {}
    return value if isinstance(value, dict) else {}


def content_slots(page):
    """Return stable semantic slots that an authored plan must place once."""
    content = _content_dict(page)
    result = OrderedDict()
    tool = page.get("subjectTool") or {}
    if isinstance(tool, dict) and tool.get("type") == "poem":
        return result

    def add(name, value):
        lines = parse_rich(value or "")
        plain = "\n".join("".join(run["text"] for run in line) for line in lines).strip()
        if plain and name not in result:
            result[name] = plain

    add("title", page.get("title") or content.get("title"))
    add("kicker", page.get("kicker") or content.get("kicker"))
    add("lead", page.get("lead") or content.get("lead"))
    add("body", page.get("body") or content.get("paragraph") or content.get("body"))

    items = page.get("items")
    if not isinstance(items, list):
        items = content.get("list") or content.get("items") or []
    for index, item in enumerate(items if isinstance(items, list) else []):
        if isinstance(item, dict):
            title = item.get("title") or item.get("heading") or ""
            body = item.get("text") or item.get("body") or item.get("paragraph") or ""
            value = (str(title).strip() + ("\n" if title and body else "")
                     + str(body).strip())
        else:
            value = str(item)
        add("item.%d" % index, value)

    for key in ("question", "answer", "summary"):
        add(key, page.get(key) or content.get(key))

    big = page.get("bigNumber") or {}
    if isinstance(big, dict):
        value = str(big.get("value") or "").strip()
        unit = str(big.get("unit") or "").strip()
        add("bigNumber", value + ((" " + unit) if unit else ""))
    return result
