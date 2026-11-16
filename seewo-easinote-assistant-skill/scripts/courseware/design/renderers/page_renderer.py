# -*- coding: utf-8 -*-
"""页面渲染：把视觉计划的 visualPlan 绘制到 ENBX slide。

从原 visual_plan_renderer.py 拆分而来；只做绘制，不做校验——校验逻辑见
validators/visual_validator.py。渲染入口 render_authored_page 假定 spec
已通过 validate_authored_visual（含 bgTone 解析）。
"""
import json
import math
import os

import components as C
from rich_text import parse_rich
from subject_tools import tool_background_policy

from validators.content_validator import content_slots
from validators.visual_validator import (CAPTION_BAR_OPACITY,
                                         CAPTION_FONT_SIZE,
                                         CAPTION_LINE_SPACING,
                                         CAPTION_PAD_X, _box, _image_source,
                                         _resolve_path,
                                         illustration_caption_geometry,
                                         silhouette_tokens)


def _draw_background(slide, spec, page):
    if tool_background_policy(page) == "none":
        return
    background = page["visualPlan"]["background"]
    for scrim in background.get("scrims") or []:
        x, y, w, h = _box(scrim["box"])
        C.add_rect(slide, x, y, w, h, scrim["color"],
                   alpha=scrim["opacity"],
                   rounded=bool(scrim.get("rounded")),
                   radius=scrim.get("radius", 0.04))


def render_authored_page(slide, spec, page):
    _draw_background(slide, spec, page)
    slots = content_slots(page)
    elements = sorted(page["visualPlan"]["elements"], key=lambda item: item.get("z", 0))
    for element in elements:
        x, y, w, h = _box(element["box"])
        kind = element["kind"]
        style = element.get("style") or {}
        if kind == "shape":
            shape_kind = str(element.get("shape") or "rect").lower()
            fill = style.get("fill")
            line_color = style.get("line")
            opacity = style.get("opacity")
            if shape_kind == "line":
                C.add_line(slide, x, y, w, h, fill,
                           weight=style.get("weight", 1.0))
            elif shape_kind == "rounded":
                C.add_rect(slide, x, y, w, h, fill,
                           line=line_color, alpha=opacity,
                           rounded=True, radius=style.get("radius", 0.08))
            elif shape_kind == "oval":
                C.add_oval(slide, x, y, w, h, fill,
                           line=line_color, alpha=opacity)
            elif shape_kind == "triangle":
                C.add_triangle(slide, x, y, w, h, fill,
                               line=line_color, alpha=opacity)
            elif shape_kind == "arrow":
                C.add_arrow(slide, x, y, w, h, fill,
                            line=line_color, alpha=opacity)
            elif shape_kind == "callout":
                C.add_callout(slide, x, y, w, h, fill,
                              line=line_color, alpha=opacity,
                              tail_right=bool(element.get("tailRight")))
            else:
                C.add_rect(slide, x, y, w, h, fill,
                           line=line_color, alpha=opacity,
                           rounded=bool(style.get("rounded")),
                           radius=style.get("radius", 0.04))
            continue
        if kind == "image":
            raw = _image_source(page, element.get("source"))
            C.add_picture_cover(slide, _resolve_path(spec, raw), x, y, w, h)
            caption = str(element.get("caption") or "").strip()
            if caption:
                caption_box, _caption_lines = illustration_caption_geometry(element)
                cbx, cby, cbw, cbh = caption_box
                C.add_rect(slide, cbx, cby, cbw, cbh, "#000000",
                           alpha=CAPTION_BAR_OPACITY)
                C.add_rich_text(
                    slide, cbx, cby, cbw, cbh, caption, CAPTION_FONT_SIZE,
                    "#FFFFFF", "#FFFFFF", align="center", anchor="middle",
                    font="Microsoft YaHei", line_spacing=CAPTION_LINE_SPACING,
                    margin=(CAPTION_PAD_X, 4, CAPTION_PAD_X, 4), fit=False)
            continue
        fill = style.get("fill")
        source = element["source"]
        size = style["fontSize"]
        line_spacing = style.get("lineSpacing", 1.35)
        # 渲染前按客户端真实行高（1.42 系数）重新估算；若 spec box 高度不足，
        # 自动扩展容器高度，保证文本不溢出 fill 容器（fit=False 不缩号）。
        lines = parse_rich(slots.get(source, "")) or [[]]
        measured = C.measure_text_layout(
            lines, w, h, size, line_spacing, style.get("padding", 0),
            line_height_factor=C.REAL_LINE_HEIGHT_FACTOR)
        if measured["height_deficit"] > 0:
            grow = math.ceil(measured["height_deficit"]) + 4
            h += grow
        if fill:
            C.add_rect(slide, x, y, w, h, fill,
                       line=style.get("line"), alpha=style["fillOpacity"],
                       rounded=bool(style.get("rounded")),
                       radius=style.get("radius", 0.04))
        C.add_rich_text(
            slide, x, y, w, h, slots[source], size, style["color"],
            style.get("accentColor", style["color"]),
            align=style.get("align", "left"),
            anchor=style.get("verticalAlign", "top"),
            font=style.get("font", "Microsoft YaHei"),
            line_spacing=line_spacing,
            margin=style.get("padding", 0), fit=False)


def authored_manifest(spec):
    pages = []
    for index, page in enumerate(spec.get("pages") or [], 1):
        if page.get("visualPlan"):
            pages.append({
                "page": index,
                "background": page["visualPlan"].get("background"),
                "silhouette": sorted(silhouette_tokens(page)),
                "designRationale": page["visualPlan"].get("designRationale"),
            })
    return {"creativeDirection":
            (spec.get("visualPlanning") or {}).get("creativeDirection"), "pages": pages}


def write_authored_manifest(spec, out_path):
    root, _ = os.path.splitext(out_path)
    with open(root + ".visual-plan.json", "w", encoding="utf-8") as handle:
        json.dump(authored_manifest(spec), handle, ensure_ascii=False, indent=2)
