#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENBX-only drawing helpers used by the authored visual renderer."""
import math
import sys

# 客户端中文字体（Microsoft YaHei 等）的实际行高 ≈ 字号 × 1.32 × lineSpacing，
# 再加上 \r\n 段距余量，会比 字号×行距 的直接估算高 30%+。
# 渲染层兜底扩展容器时用该系数（实测 22px×1.5×3 行估算 99px，客户端渲染约 142px）；
# 校验器保持 line_height_factor=1.0 的宽松估算，避免对单行短文本误报。
REAL_LINE_HEIGHT_FACTOR = 1.42


def _text_units(text):
    """Estimate width units: CJK about 1em, ASCII about 0.55em."""
    return sum(1.0 if ord(char) > 0x2E7F else 0.55 for char in text)


def measure_text_layout(lines_of_runs, width, height, size, line_spacing=1.4,
                        margin=(0, 0, 0, 0), line_height_factor=1.0):
    """Measure wrapped text without changing the declared font size.

    The estimate matches the ENBX line segmenter: CJK uses about 1em, ASCII
    uses about 0.55em, and 2% of each line is reserved against edge overflow.
    """
    left, top, right, bottom = normalize_margin(margin)
    available_width = max(0.0, float(width) - left - right)
    available_height = max(0.0, float(height) - top - bottom)
    wrap_width = max(available_width * 0.98, 1.0)
    line_count = 0
    for runs in lines_of_runs:
        units = sum(_text_units(run.get("text", "")) for run in runs) if runs else 0.0
        line_count += max(1, math.ceil(units * float(size) / wrap_width - 1e-6))
    if not lines_of_runs:
        line_count = 1
    required_height = (line_count * float(size) * float(line_spacing)
                       * line_height_factor)
    return {
        "estimated_line_count": line_count,
        "required_height": required_height,
        "available_height": available_height,
        "available_width": available_width,
        "height_deficit": max(0.0, required_height - available_height),
        "fits": available_width > 0 and required_height <= available_height + 1e-6,
    }


def fit_font_size(lines_of_runs, width, height, size, line_spacing=1.4, floor=20):
    """Return ``(font_size, still_overflowing)`` for the ENBX text box."""
    for candidate in range(int(size), int(floor) - 1, -1):
        measurement = measure_text_layout(
            lines_of_runs, width, height, candidate, line_spacing)
        if measurement["fits"]:
            return candidate, False
    return int(floor), True


def normalize_margin(margin):
    """Return ``(left, top, right, bottom)`` non-negative pixel margins."""
    if margin is None:
        return 0, 0, 0, 0
    if isinstance(margin, (int, float)):
        value = max(0, margin)
        return value, value, value, value
    if not isinstance(margin, (list, tuple)) or len(margin) != 4:
        raise ValueError("margin 必须是非负数或 (left, top, right, bottom)")
    return tuple(max(0, value) for value in margin)


def _log_shrink(what, size, new_size, overflow, text=''):
    excerpt = str(text).replace("\n", " / ")[:36]
    suffix = "：%s" % excerpt if excerpt else ""
    if new_size < size:
        sys.stderr.write("⚠ 文本框自动缩号 %s：%d→%dpx%s（建议精简文案）%s\n" %
                         (what, size, new_size, "，仍溢出" if overflow else "", suffix))
    elif overflow:
        sys.stderr.write("⚠ 文本框溢出 %s：%dpx 已到下限仍装不下（必须精简文案）%s\n" %
                         (what, new_size, suffix))


def add_rect(slide, x, y, width, height, fill, line=None, rounded=False,
             radius=0.08, alpha=None):
    import enbx_backend as backend
    return backend.add_rect(slide, x, y, width, height, fill, line=line,
                            rounded=rounded, radius=radius, alpha=alpha)


def add_line(slide, x, y, width, height, color, weight=1.0):
    import enbx_backend as backend
    return backend.add_line(slide, x, y, width, height, color, weight=weight)


def add_oval(slide, x, y, width, height, fill, line=None, alpha=None):
    """椭圆/圆形：结构锚点、序号圆点、图标底座。"""
    import enbx_backend as backend
    return backend.add_shape(slide, "OVAL", x, y, width, height, fill,
                             alpha=alpha, line=line)


def add_triangle(slide, x, y, width, height, fill, line=None, alpha=None):
    """等腰三角：方向指示、装饰角标。"""
    import enbx_backend as backend
    return backend.add_shape(slide, "ISOSCELES_TRIANGLE", x, y, width, height,
                             fill, alpha=alpha, line=line)


def add_arrow(slide, x, y, width, height, fill, line=None, alpha=None):
    """右箭头：流程引导、指向强调。"""
    import enbx_backend as backend
    return backend.add_shape(slide, "RIGHT_ARROW", x, y, width, height,
                             fill, alpha=alpha, line=line)


def add_callout(slide, x, y, width, height, fill, line=None, alpha=None,
                tail_right=False):
    """对话气泡：引用、提示、角色话语（tail_right 控制尾巴方向）。"""
    import enbx_backend as backend
    return backend.add_shape(
        slide, "ROUNDED_RECTANGULAR_CALLOUT", x, y, width, height,
        fill, alpha=alpha, line=line,
        adjusts={1: 1 if tail_right else 0})


def add_rich_text(slide, x, y, width, height, markup, size, color, accent,
                  align='left', anchor='top', font='Microsoft YaHei',
                  line_spacing=1.4, margin=(0, 0, 0, 0), min_size=None,
                  fit=True):
    import enbx_backend as backend
    return backend.add_rich_text(
        slide, x, y, width, height, markup, size, color, accent,
        align=align, anchor=anchor, font=font, line_spacing=line_spacing,
        margin=margin, min_size=min_size, fit=fit)


def add_picture_cover(slide, path, x, y, width, height):
    import enbx_backend as backend
    return backend.add_picture_cover(slide, path, x, y, width, height)
