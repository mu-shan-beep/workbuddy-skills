# -*- coding: utf-8 -*-
"""视觉校验：几何、背景池、相似度、对比度与 imageStrategy 契约。

从原 visual_plan_renderer.py 拆分而来；渲染逻辑见 renderers/page_renderer.py。
本模块不包含学科、课型、主题或版式目录——模型逐页自主设计，校验器只负责
生产安全（几何越界、内容槽绑定、主体遮挡、对比度、复用上限等）。
"""
from collections import Counter
import math
import os
import re

import components as C
from rich_text import parse_rich
from subject_tools import tool_background_policy, tool_interaction_slot

from .content_validator import CANVAS_H, CANVAS_W, content_slots

MIN_BODY_SIZE = 22
MIN_TITLE_SIZE = 42
SUBJECT_OVERLAP_THRESHOLD = 0.02
CONTRAST_ERROR = 3.0      # WCAG AA large-text minimum
CONTRAST_WARN = 4.5       # WCAG AA normal-text recommendation
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ── 页面配图（kind:"image" 前景元素）契约 ─────────────────────────
# 配图区别于背景图：背景图铺满整页表达氛围/场景，配图是承载教学信息的
# 局部插图（示意、示例、对比、数据可视化等）。配图可带一句图注 caption，
# 渲染器在配图底部绘制半透明图注条；图注文字计入页面内容密度。
ILLUSTRATION_ROLES = ("illustration", "photo", "diagram", "data")
CAPTION_MIN_CHARS = 10
CAPTION_MAX_CHARS = 80
CAPTION_FONT_SIZE = 22
CAPTION_LINE_SPACING = 1.3
CAPTION_MAX_LINES = 2
CAPTION_PAD_X = 8
CAPTION_BAR_OPACITY = 55
MAX_ILLUSTRATION_AREA = 0.8  # 配图面积上限（占画布比例），禁止把配图当背景
MIN_ILLUSTRATION_W = 200     # 带图注时配图最小宽度
MIN_ILLUSTRATION_H = 60      # 带图注时配图最小高度（图注条可放置）

# ── 装饰形状（kind:"shape"）契约 ─────────────────────────────
# 形状是页面视觉语言的一部分：结构分区、视觉锚点、装饰语言（序号圆点、
# 引导箭头、角标、气泡图形等）。红线不变——shape 不做文字底板（文字垫底
# 只允许 text.fill 容器或 background.scrims）、不覆盖全画布。
SHAPE_KINDS = ("rect", "rounded", "oval", "line", "arrow", "triangle", "callout")
MAX_DECORATIVE_SHAPES = 8     # 每页装饰 shape 硬上限（防滥用）
WARN_DECORATIVE_SHAPES = 5    # 超过后软提醒，鼓励克制

# ── 背景图中心安静带（中心留白）──────────────────────────────
# 主体应置于页面边缘/单侧，中心区域保持安静以承载前景内容；primary 主主体
# 侵入中部安静带过多时软告警（不报错，不破坏既有课件）。
CENTRAL_QUIET_ZONE = (240, 140, 800, 440)
CENTRAL_CLUTTER_WARN = 0.15

# ── 背景池分档复用（按留白方向）──────────────────────────────
# 中间留白（主体置边缘/四角、中心安静）是内容页首选，支持自由布局，建议多
# 复用；侧边（左/右）留白压缩对侧可用空间、影响内容最大化展示，尽量少用
# 少复用；底部留白维持既有上限。取值为 (复用上限页数, 警告阈值页数)。
WHITESPACE_KINDS = ("center", "left", "right", "bottom")
WHITESPACE_LABELS = {"center": "中间", "left": "左侧", "right": "右侧", "bottom": "底部"}
BACKGROUND_REUSE_LIMITS = {
    "center": (6, 5),
    "left": (2, 2),
    "right": (2, 2),
    "bottom": (4, 3),
}

# ── 图片方案（spec 根级 imageStrategy）────────────────────────────
IMAGE_STRATEGIES = ("generated", "provided", "none")


# ── WCAG luminance & contrast ──────────────────────────────────────

def _srgb_to_linear(channel):
    channel = channel / 255.0
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color):
    r = _srgb_to_linear(int(hex_color[1:3], 16))
    g = _srgb_to_linear(int(hex_color[3:5], 16))
    b = _srgb_to_linear(int(hex_color[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(color1, color2):
    l1 = _relative_luminance(color1)
    l2 = _relative_luminance(color2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _blend_hex(fg_hex, bg_hex, opacity_pct):
    """Alpha-composite *fg_hex* over *bg_hex*; *opacity_pct* is 0–100."""
    alpha = opacity_pct / 100.0
    fr, fc, fb = (int(fg_hex[1:3], 16), int(fg_hex[3:5], 16), int(fg_hex[5:7], 16))
    br, bc, bb = (int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16))
    r = round(fr * alpha + br * (1 - alpha))
    g = round(fc * alpha + bc * (1 - alpha))
    b = round(fb * alpha + bb * (1 - alpha))
    return "#%02X%02X%02X" % (r, g, b)


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _box(value):
    if not isinstance(value, dict):
        return None
    try:
        box = tuple(float(value[key]) for key in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    return box


def _inside(box):
    x, y, w, h = box
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= CANVAS_W and y + h <= CANVAS_H


def _intersection_ratio(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    iw = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    ih = max(0, min(ay + ah, by + bh) - max(ay, by))
    intersection = iw * ih
    return intersection / max(1.0, min(aw * ah, bw * bh))


def _contains(container, item):
    cx, cy, cw, ch = container
    ix, iy, iw, ih = item
    return (ix >= cx and iy >= cy and ix + iw <= cx + cw
            and iy + ih <= cy + ch)


def _resolve_path(spec, source):
    if not source:
        return None
    base = spec.get("specDir") or os.getcwd()
    return source if os.path.isabs(source) else os.path.join(base, source)


def _image_source(page, raw):
    if raw in {"page.image", "image"}:
        return page.get("image")
    return raw


def _color(value):
    return isinstance(value, str) and bool(_COLOR.match(value))


def _opacity(value):
    return _number(value) and 0 <= value <= 100


def _radius(value):
    return _number(value) and 0 < value <= 0.5


def _padding(value, require_positive=False):
    if _number(value):
        values = (float(value),) * 4
    elif isinstance(value, (list, tuple)) and len(value) == 4:
        if not all(_number(item) for item in value):
            return None
        values = tuple(float(item) for item in value)
    else:
        return None
    floor = 0 if not require_positive else 1e-9
    return values if all(item >= floor for item in values) else None


def _validate_rounding(value, label, errors):
    if "rounded" in value and not isinstance(value["rounded"], bool):
        errors.append("%s.rounded 必须是布尔值" % label)
    if "radius" in value and not _radius(value["radius"]):
        errors.append("%s.radius 必须在 (0, 0.5] 之间" % label)


def _valid_labeled_box(value):
    if not isinstance(value, dict) or not str(value.get("label") or "").strip():
        return None
    box = _box(value.get("box"))
    return box if box and _inside(box) else None


def _validate_image_layout(background, label, errors):
    image_layout = background.get("imageLayout")
    layout_label = "%s.imageLayout" % label
    if not isinstance(image_layout, dict):
        errors.append("%s 必须由 AI 在出图后显式声明" % layout_label)
        return

    has_subject = image_layout.get("hasRecognizableSubject")
    if not isinstance(has_subject, bool):
        errors.append("%s.hasRecognizableSubject 必须是布尔值" % layout_label)

    whitespace = image_layout.get("whitespace")
    if whitespace is not None and whitespace not in WHITESPACE_KINDS:
        errors.append(
            "%s.whitespace 只接受 center / left / right / bottom（留白方向）"
            % layout_label)

    subjects = image_layout.get("subjects")
    if not isinstance(subjects, list):
        errors.append("%s.subjects 必须显式声明为数组" % layout_label)
        subjects = []
    valid_importance = []
    for subject_index, subject in enumerate(subjects):
        subject_label = "%s.subjects[%d]" % (layout_label, subject_index)
        if not isinstance(subject, dict):
            errors.append("%s 必须是对象" % subject_label)
            continue
        if not str(subject.get("label") or "").strip():
            errors.append("%s.label 缺失" % subject_label)
        importance = subject.get("importance")
        if importance not in {"primary", "secondary"}:
            errors.append("%s.importance 必须是 primary 或 secondary" % subject_label)
        else:
            valid_importance.append(importance)
        box = _box(subject.get("box"))
        if not box or not _inside(box):
            errors.append("%s.box 越界或无效" % subject_label)

    if has_subject is True:
        if not subjects:
            errors.append("%s 声明存在可识别主体时 subjects 不得为空" % layout_label)
        elif "primary" not in valid_importance:
            errors.append("%s.subjects 至少需要一个 primary 主体" % layout_label)
    elif has_subject is False and subjects:
        errors.append("%s 声明无可识别主体时 subjects 必须为空" % layout_label)

    safe_regions = image_layout.get("textSafeRegions")
    if not isinstance(safe_regions, list) or not safe_regions:
        errors.append("%s.textSafeRegions 必须是非空数组" % layout_label)
        safe_regions = []
    for region_index, region in enumerate(safe_regions):
        region_label = "%s.textSafeRegions[%d]" % (layout_label, region_index)
        if not isinstance(region, dict):
            errors.append("%s 必须是对象" % region_label)
            continue
        if not str(region.get("label") or "").strip():
            errors.append("%s.label 缺失" % region_label)
        box = _box(region.get("box"))
        if not box or not _inside(box):
            errors.append("%s.box 越界或无效" % region_label)
        bg_tone = region.get("bgTone")
        if bg_tone == "auto":
            errors.append(
                "%s.bgTone 声明为 auto 但无法从背景图提取实测色调："
                "请人工实测填写 #RRGGBB，或为该组文字改用 fill 容器 / scrim 垫底"
                % region_label)
        elif bg_tone is not None and not _color(bg_tone):
            errors.append("%s.bgTone 必须是 #RRGGBB" % region_label)


def _image_layout_geometry(background):
    """Return only validated-looking geometry; structural errors are reported elsewhere."""
    image_layout = background.get("imageLayout")
    if not isinstance(image_layout, dict):
        return [], []
    raw_subjects = image_layout.get("subjects") or []
    raw_subjects = raw_subjects if isinstance(raw_subjects, list) else []
    subjects = []
    for subject_index, subject in enumerate(raw_subjects):
        box = _valid_labeled_box(subject)
        if box and subject.get("importance") in {"primary", "secondary"}:
            subjects.append((subject_index, str(subject["label"]).strip(),
                             subject["importance"], box))
    raw_regions = image_layout.get("textSafeRegions") or []
    raw_regions = raw_regions if isinstance(raw_regions, list) else []
    safe_regions = []
    for region_index, region in enumerate(raw_regions):
        box = _valid_labeled_box(region)
        if box:
            bg_tone = region.get("bgTone") if isinstance(region, dict) else None
            if bg_tone and not _color(bg_tone):
                bg_tone = None
            safe_regions.append((region_index, str(region["label"]).strip(), box, bg_tone))
    return subjects, safe_regions


def _report_subject_overlap(index, owner, box, subjects, errors, warnings):
    for _subject_index, subject_label, importance, subject_box in subjects:
        ratio = _intersection_ratio(box, subject_box)
        if ratio <= SUBJECT_OVERLAP_THRESHOLD:
            continue
        message = ("pages[%d] %s 与%s主体「%s」重叠 %.1f%%" %
                   (index, owner, "主" if importance == "primary" else "次",
                    subject_label, ratio * 100))
        if importance == "primary":
            errors.append(message + "，必须调整图片或前景几何")
        else:
            warnings.append(message + "，请确认不会影响主体辨识")


def _background_whitespace_kind(background):
    """Classify a background image by its whitespace direction.

    返回 "center"（主体置边缘/四角、中心安静——内容页首选）/ "left" / "right"
    （单侧留白）/ "bottom"。优先读取 ``imageLayout.whitespace`` 的显式声明；
    缺省时按 primary 主体几何推断：primary 主体窄高、完整落在画布左/右半区
    时判为对侧留白，其余（含顶部/底部/四角主体与无主体画面）判为中间留白。
    """
    if not isinstance(background, dict):
        return "center"
    layout = background.get("imageLayout")
    if isinstance(layout, dict):
        declared = str(layout.get("whitespace") or "").strip().lower()
        if declared in WHITESPACE_KINDS:
            return declared
    subjects, _safe = _image_layout_geometry(background)
    primary_boxes = [box for _idx, _label, importance, box in subjects
                     if importance == "primary" and _inside(box)]
    if not primary_boxes:
        return "center"
    x0 = min(box[0] for box in primary_boxes)
    y0 = min(box[1] for box in primary_boxes)
    x1 = max(box[0] + box[2] for box in primary_boxes)
    y1 = max(box[1] + box[3] for box in primary_boxes)
    width, height = x1 - x0, y1 - y0
    if width <= CANVAS_W * 0.5 and height >= CANVAS_H * 0.35:
        if x1 <= CANVAS_W * 0.55:
            return "right"   # 主体在左侧 → 右侧留白
        if x0 >= CANVAS_W * 0.45:
            return "left"    # 主体在右侧 → 左侧留白
    return "center"


def _warn_background_center_clutter(index, background, errors, warnings):
    """Soft-warn when a primary subject intrudes into the central quiet zone.

    背景图主体应置于页面边缘/单侧，中心区域（CENTRAL_QUIET_ZONE）保持安静以
    承载前景文字与布局；primary 主主体侵入中部安静带过多时软告警。这是「中心
    大部分留白、主体置边缘」优化的强制兜底——只告警不报错，不破坏既有课件。
    """
    if not isinstance(background, dict) or background.get("type") != "image":
        return
    subjects, _safe = _image_layout_geometry(background)
    for _sidx, label, importance, box in subjects:
        if importance != "primary":
            continue
        ratio = _intersection_ratio(box, CENTRAL_QUIET_ZONE)
        if ratio > CENTRAL_CLUTTER_WARN:
            warnings.append(
                "pages[%d] 背景主主体「%s」侵入中部安静带 %.0f%%，中心留白被占用："
                "请将其移至页面边缘或单侧，保持中心区域承载前景内容"
                % (index, label, ratio * 100))


def illustration_caption_geometry(element):
    """Return ``(caption_box, line_count)`` for an image element with caption.

    The caption bar sits along the image's bottom edge (inside the image box).
    ``line_count`` is the wrapped estimate, capped at CAPTION_MAX_LINES + 1 so
    callers can report overflow instead of hiding it.

    The bar height accounts for the client's real line height
    (``components.REAL_LINE_HEIGHT_FACTOR``): a plain size*spacing estimate is
    ~30% short of what the client renders (22px×1.3 measures ≈ 40.6px per
    line), so the caption text visibly spills past the bar and the image's
    bottom edge.  The bar is also clamped to the image height so it never
    extends below the box.
    """
    box = _box(element.get("box"))
    caption = str(element.get("caption") or "").strip()
    if not box or not caption:
        return None, 0
    x, y, w, h = box
    lines = C.measure_text_layout(
        [[{"text": caption}]], w, h, CAPTION_FONT_SIZE,
        line_spacing=CAPTION_LINE_SPACING,
        margin=(CAPTION_PAD_X, 4, CAPTION_PAD_X, 4))["estimated_line_count"]
    lines = min(lines, CAPTION_MAX_LINES + 1)
    bar_height = (lines * CAPTION_FONT_SIZE * CAPTION_LINE_SPACING
                  * C.REAL_LINE_HEIGHT_FACTOR + 8)
    bar_height = min(bar_height, h)   # 条带绝不低于图片下缘，防止文字溢出画面
    return (x, y + h - bar_height, w, bar_height), lines


def _element_tokens(element):
    box = _box(element.get("box"))
    if not box:
        return set()
    x, y, w, h = box
    role = str(element.get("role") or element.get("kind") or "layer")
    tokens = set()
    for row in range(3):
        for col in range(4):
            cell = (col * 320, row * 240, 320, 240)
            if _intersection_ratio(box, cell) >= 0.18:
                tokens.add("%s:%d:%d" % (role, col, row))
    tokens.add("%s:size:%d:%d" % (role, round(w / 160), round(h / 120)))
    tokens.add("%s:anchor:%d:%d" % (role, round(x / 160), round(y / 120)))
    return tokens


def silhouette_tokens(page):
    plan = page.get("visualPlan") or {}
    tokens = set()
    for element in plan.get("elements") or []:
        if isinstance(element, dict) and element.get("kind") != "shape":
            tokens.update(_element_tokens(element))
    background = plan.get("background") or {}
    tokens.add("background:%s" % background.get("type"))
    for scrim in background.get("scrims") or []:
        if isinstance(scrim, dict):
            tokens.update(_element_tokens({"kind": "scrim", "role": "scrim",
                                           "box": scrim.get("box")}))
    return tokens


def silhouette_similarity(page_a, page_b):
    left, right = silhouette_tokens(page_a), silhouette_tokens(page_b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _validate_background(spec, page, index, errors, warnings):
    plan = page.get("visualPlan") or {}
    background = plan.get("background")
    label = "pages[%d].visualPlan.background" % index
    if tool_background_policy(page) == "none":
        if background is not None:
            errors.append("%s 古诗词原生工具页不得声明 background；保留客户端默认页面底色" % label)
        return None
    if not isinstance(background, dict):
        errors.append("%s 必须由 AI 明确设计" % label)
        return None
    kind = background.get("type")
    if kind not in {"image", "solid"}:
        errors.append("%s.type 必须是 image 或 solid" % label)
        return None
    if kind == "image":
        source = background.get("source")
        path = _resolve_path(spec, source)
        if not source:
            errors.append("%s.source 缺失" % label)
        elif not path or not os.path.isfile(path):
            errors.append("%s.source 不存在：%s" % (label, source))
        if background.get("fit", "cover") != "cover":
            errors.append("%s.fit 当前仅支持 cover" % label)
        _validate_image_layout(background, label, errors)
    else:
        if not _color(background.get("color")):
            errors.append("%s.color 必须是 #RRGGBB" % label)
        if "imageLayout" in background:
            errors.append("%s.imageLayout 仅用于 image 背景" % label)

    if "overlay" in background:
        errors.append("%s.overlay 已废止；请直接排文字，确需对比度时使用局部 scrims" % label)
    scrims = background.get("scrims") or []
    if not isinstance(scrims, list):
        errors.append("%s.scrims 必须是数组" % label)
        scrims = []
    for scrim_index, scrim in enumerate(scrims):
        scrim_label = "%s.scrims[%d]" % (label, scrim_index)
        box = _box(scrim.get("box") if isinstance(scrim, dict) else None)
        if not box or not _inside(box):
            errors.append("%s.box 越界或无效" % scrim_label)
        if not isinstance(scrim, dict) or not _color(scrim.get("color")):
            errors.append("%s.color 无效" % scrim_label)
            continue
        if "opacity" not in scrim:
            errors.append("%s.opacity 必须显式声明" % scrim_label)
        elif not _opacity(scrim["opacity"]):
            errors.append("%s.opacity 必须在 0-100" % scrim_label)
        _validate_rounding(scrim, scrim_label, errors)
    return kind


def _effective_text_bg(element, box, background, scrims, raw_scrims, safe_regions):
    """Return ``(effective_bg_hex_or_None, is_known_bool)`` for a text element.

    Determines the effective background colour behind a text box so that a
    WCAG contrast ratio can be computed.  The logic covers four scenarios:

    1. Solid background      → base = solid colour
    2. Image background      → base = bgTone of the containing textSafeRegion
    3. Text with ``fill``    → blend(fill, base, fillOpacity)
    4. Text on a ``scrim``   → blend(scrim.colour, base, scrim.opacity)
    """
    style = element.get("style") or {}
    bg_type = background.get("type")

    # ── 1. base background colour ──
    if bg_type == "solid":
        base = background.get("color") if _color(background.get("color")) else None
    elif bg_type == "image":
        base = None
        for _ri, _rl, sbox, tone in safe_regions:
            if tone and _contains(sbox, box):
                base = tone
                break
    else:
        base = None

    # ── 2. fill (container) takes precedence over scrim ──
    fill = style.get("fill")
    fill_opacity = style.get("fillOpacity", 100)
    if fill and _color(fill):
        op = fill_opacity if _opacity(fill_opacity) else 100
        if base and _color(base):
            return _blend_hex(fill, base, op), True
        if op >= 85:
            return fill, True
        return None, False

    # ── 3. scrim ──
    for scrim_index, scrim_box in scrims:
        if _contains(scrim_box, box):
            if scrim_index < len(raw_scrims) and isinstance(raw_scrims[scrim_index], dict):
                scrim = raw_scrims[scrim_index]
                scrim_color = scrim.get("color")
                scrim_opacity = scrim.get("opacity", 100)
                if _color(scrim_color):
                    op = scrim_opacity if _opacity(scrim_opacity) else 100
                    if base and _color(base):
                        return _blend_hex(scrim_color, base, op), True
                    if op >= 60:
                        return scrim_color, True
            break

    # ── 4. direct text on background ──
    if base and _color(base):
        return base, True
    return None, False


def _validate_elements(spec, page, index, errors, warnings):
    plan = page.get("visualPlan") or {}
    elements = plan.get("elements")
    label = "pages[%d].visualPlan.elements" % index
    full_canvas_tool = ((page.get("subjectTool") or {}).get("type") == "poem")
    content = page.get("content") if isinstance(page.get("content"), dict) else {}
    authored_copy = (page.get("body") or page.get("lead") or page.get("items")
                     or content.get("paragraph") or content.get("body")
                     or content.get("list") or content.get("items"))
    if full_canvas_tool and authored_copy:
        errors.append("pages[%d] 全画布古诗工具页不得夹带普通正文，请拆到相邻教学页" % index)
    if not isinstance(elements, list) or (not elements and not full_canvas_tool):
        errors.append("%s 必须是非空数组" % label)
        return
    shape_count = sum(1 for element in elements
                      if isinstance(element, dict)
                      and element.get("kind") == "shape")
    if shape_count > MAX_DECORATIVE_SHAPES:
        errors.append(
            "pages[%d] 装饰 shape %d 个，超过上限 %d：形状服务于结构分区与"
            "视觉强调，不是填充手段，请精简到必要范围" %
            (index, shape_count, MAX_DECORATIVE_SHAPES))
    elif shape_count >= WARN_DECORATIVE_SHAPES:
        warnings.append(
            "pages[%d] 装饰 shape %d 个，接近上限：请确认每个形状都承担"
            "结构分区或视觉强调作用，避免堆叠装饰" % (index, shape_count))
    slots = content_slots(page)
    used = Counter()
    foreground = []
    tool_slot = tool_interaction_slot(page) if page.get("subjectTool") else None
    tool_box = ((tool_slot["x"], tool_slot["y"], tool_slot["w"], tool_slot["h"])
                if tool_slot else None)
    background = plan.get("background") or {}
    background = background if isinstance(background, dict) else {}
    subjects, safe_regions = _image_layout_geometry(background)
    raw_scrims = background.get("scrims") or []
    raw_scrims = raw_scrims if isinstance(raw_scrims, list) else []
    scrims = [
        (scrim_index, _box(scrim.get("box")))
        for scrim_index, scrim in enumerate(raw_scrims)
        if isinstance(scrim, dict) and _box(scrim.get("box"))
    ]
    for scrim_index, scrim_box in scrims:
        if _contains(scrim_box, (0, 0, CANVAS_W, CANVAS_H)):
            errors.append("pages[%d] background.scrims[%d] 不得覆盖全画布" %
                          (index, scrim_index))
        if background.get("type") == "image" and safe_regions:
            if not any(_contains(safe_box, scrim_box)
                       for _region_index, _region_label, safe_box, _tone in safe_regions):
                errors.append(
                    "pages[%d] background.scrims[%d] 未完整落入任何 textSafeRegion" %
                    (index, scrim_index))
    if background.get("type") == "image":
        for scrim_index, scrim_box in scrims:
            _report_subject_overlap(
                index, "background.scrims[%d]" % scrim_index, scrim_box,
                subjects, errors, warnings)

    for element_index, element in enumerate(elements):
        item_label = "%s[%d]" % (label, element_index)
        if not isinstance(element, dict):
            errors.append("%s 必须是对象" % item_label)
            continue
        kind = element.get("kind")
        if kind not in {"text", "image", "shape"}:
            errors.append("%s.kind 必须是 text/image/shape" % item_label)
            continue
        box = _box(element.get("box"))
        if not box or not _inside(box):
            errors.append("%s.box 越界或无效" % item_label)
            continue
        if tool_box and _intersection_ratio(box, tool_box) > 0.02:
            errors.append("%s 与希沃原生工具安全区重叠" % item_label)

        if kind == "text":
            source = element.get("source")
            if source not in slots:
                errors.append("%s.source 未绑定可见内容槽：%r" % (item_label, source))
            else:
                used[source] += 1
            if background.get("type") == "image" and safe_regions:
                if not any(_contains(safe_box, box)
                           for _region_index, _region_label, safe_box, _tone in safe_regions):
                    errors.append(
                        "pages[%d] 内容槽 %s 的文字框未完整落入任何 textSafeRegion" %
                        (index, source))
            if background.get("type") == "image":
                _report_subject_overlap(
                    index, "内容槽 %s" % source, box, subjects, errors, warnings)
            style = element.get("style")
            if not isinstance(style, dict):
                errors.append("%s.style 必须是对象" % item_label)
                style = {}
            size = style.get("fontSize")
            floor = MIN_TITLE_SIZE if source == "title" else MIN_BODY_SIZE
            size_valid = _number(size) and size >= floor
            if not size_valid:
                errors.append("%s.style.fontSize 必须 ≥ %dpx" % (item_label, floor))
            if not _color(style.get("color")):
                errors.append("%s.style.color 必须是 #RRGGBB" % item_label)
            fill = style.get("fill")
            if fill is not None and not _color(fill):
                errors.append("%s.style.fill 必须是 #RRGGBB" % item_label)
            if "fillOpacity" in style and not _opacity(style["fillOpacity"]):
                errors.append("%s.style.fillOpacity 必须在 0-100" % item_label)
            padding = style.get("padding", 0)
            padding_values = _padding(padding, require_positive=fill is not None)
            if "padding" in style and padding_values is None:
                errors.append("%s.style.padding 必须是非负数或四个非负数" % item_label)
            if fill is not None:
                if "fillOpacity" not in style:
                    errors.append("%s.style.fill 使用时必须显式提供 fillOpacity" % item_label)
                if "padding" not in style or padding_values is None:
                    errors.append("%s.style.fill 使用时必须提供四侧均为正数的 padding" % item_label)
                for scrim_index, scrim_box in scrims:
                    if _intersection_ratio(box, scrim_box) > 0.5:
                        errors.append(
                            "%s 内容槽 %s 不得同时使用自身 fill 与 background.scrims[%d]" %
                            (item_label, source, scrim_index))
            if "line" in style and not _color(style["line"]):
                errors.append("%s.style.line 必须是 #RRGGBB" % item_label)
            _validate_rounding(style, "%s.style" % item_label, errors)
            # ── WCAG text-background contrast ──
            text_color = style.get("color")
            if _color(text_color):
                eff_bg, eff_known = _effective_text_bg(
                    element, box, background, scrims, raw_scrims, safe_regions)
                if eff_known and _color(eff_bg):
                    ratio = _contrast_ratio(text_color, eff_bg)
                    if ratio < CONTRAST_ERROR:
                        errors.append(
                            "pages[%d] 内容槽 %s 文字色 %s 与背景色 %s "
                            "对比度 %.1f:1 < %.1f:1，文字不可读；"
                            "请更换文字色或添加 scrim/fill 容器" %
                            (index, source, text_color, eff_bg,
                             ratio, CONTRAST_ERROR))
                    elif ratio < CONTRAST_WARN:
                        warnings.append(
                            "pages[%d] 内容槽 %s 文字色 %s 与背景色 %s "
                            "对比度 %.1f:1 < %.1f:1，建议提高对比度；"
                            "运行 scripts/courseware/design/text_contrast.py "
                            "--bg %s 重选达标文字色" %
                            (index, source, text_color, eff_bg,
                             ratio, CONTRAST_WARN, eff_bg))
                elif background.get("type") == "image" and not fill:
                    errors.append(
                        "pages[%d] 内容槽 %s 在图片背景上直接排布但无法验证对比度："
                        "其文字框必须完整落入一个声明了实测 bgTone（或 bgTone:\"auto\""
                        "自动提取）的 textSafeRegion；无法实测时改用 fill 容器或 "
                        "scrim 垫底后再排文字" %
                        (index, source))
            line_spacing = style.get("lineSpacing", 1.35)
            line_spacing_valid = _number(line_spacing) and line_spacing > 0
            if not line_spacing_valid:
                errors.append("%s.style.lineSpacing 必须是正数" % item_label)
            if (source in slots and size_valid and padding_values is not None
                    and line_spacing_valid):
                lines = parse_rich(slots[source]) or [[]]
                measurement = C.measure_text_layout(
                    lines, box[2], box[3], size, line_spacing, padding_values)
                if not measurement["fits"]:
                    errors.append(
                        "pages[%d] 内容槽 %s 文本框容纳不足：预计 %d 行，"
                        "需要 %.1fpx，可用 %.1fpx，差 %.1fpx（可用宽度 %.1fpx）；"
                        "请扩大文本框或精简文案，不得降低字号" %
                        (index, source, measurement["estimated_line_count"],
                         measurement["required_height"], measurement["available_height"],
                         measurement["height_deficit"], measurement["available_width"]))
            foreground.append((item_label, box, element))
        elif kind == "image":
            raw = _image_source(page, element.get("source"))
            path = _resolve_path(spec, raw)
            if not raw:
                errors.append("%s.source 缺失" % item_label)
            elif not path or not os.path.isfile(path):
                errors.append("%s.source 不存在：%s" % (item_label, raw))
            if element.get("fit", "cover") not in {"cover"}:
                errors.append("%s.fit 当前仅支持 cover" % item_label)
            if element.get("role", "illustration") not in ILLUSTRATION_ROLES:
                errors.append(
                    "%s.role 必须是 illustration/photo/diagram/data 之一" %
                    item_label)
            caption = str(element.get("caption") or "").strip()
            if "caption" in element:
                if not caption:
                    errors.append("%s.caption 不得为空" % item_label)
                elif len(caption) < CAPTION_MIN_CHARS:
                    errors.append(
                        "%s.caption 过短（%d 字 < %d）：图注应说明图中内容与"
                        "教学作用" % (item_label, len(caption), CAPTION_MIN_CHARS))
                elif len(caption) > CAPTION_MAX_CHARS:
                    errors.append(
                        "%s.caption 过长（%d 字 > %d）：一句话说明即可，"
                        "细节放正文" % (item_label, len(caption), CAPTION_MAX_CHARS))
            ix, iy, iw, ih = box
            if iw * ih > MAX_ILLUSTRATION_AREA * CANVAS_W * CANVAS_H:
                errors.append(
                    "%s 配图面积 %.0f%% 超过上限 %d%%：配图不是背景，全画布"
                    "图片必须走 visualPlan.background" %
                    (item_label, iw * ih / (CANVAS_W * CANVAS_H) * 100,
                     MAX_ILLUSTRATION_AREA * 100))
            if background.get("type") == "image":
                _report_subject_overlap(
                    index, "配图 %s" % (raw or element.get("source") or ""),
                    box, subjects, errors, warnings)
            if caption:
                if ih < MIN_ILLUSTRATION_H:
                    errors.append(
                        "%s 配图高度 %dpx 过小，底部图注条至少需要 %dpx" %
                        (item_label, round(ih), MIN_ILLUSTRATION_H))
                elif iw < MIN_ILLUSTRATION_W:
                    errors.append(
                        "%s 配图宽度 %dpx 过小，图注文字无法排布（至少 %dpx）" %
                        (item_label, round(iw), MIN_ILLUSTRATION_W))
                _caption_box, _lines = illustration_caption_geometry(element)
                if _lines > CAPTION_MAX_LINES:
                    errors.append(
                        "%s.caption 按 %dpx 字号需 %d 行，超过 %d 行上限："
                        "精简图注或加宽配图" %
                        (item_label, CAPTION_FONT_SIZE, _lines,
                         CAPTION_MAX_LINES))
                # 图注条高度必须能容纳客户端真实行高（REAL_LINE_HEIGHT_FACTOR）：
                # 估算过短时文字会从条带和图片下缘溢出，这里在设计期拦截。
                _bar_need = (_lines * CAPTION_FONT_SIZE * CAPTION_LINE_SPACING
                             * C.REAL_LINE_HEIGHT_FACTOR + 8)
                if _bar_need > ih:
                    errors.append(
                        "%s 配图高度 %dpx 不足以容纳 %d 行图注（按客户端行高"
                        "需 %dpx 条带）：文字会溢出图片，请加大配图高度或"
                        "精简图注" %
                        (item_label, round(ih), _lines, round(_bar_need)))
            foreground.append((item_label, box, element))
        else:
            shape = str(element.get("shape", "rect")).strip().lower()
            if shape not in SHAPE_KINDS:
                errors.append("%s.shape 必须是 %s 之一" %
                              (item_label, "/".join(SHAPE_KINDS)))
            style = element.get("style") or {}
            if not _color(style.get("fill")):
                errors.append("%s.style.fill 必须是 #RRGGBB" % item_label)
            if _contains(box, (0, 0, CANVAS_W, CANVAS_H)):
                errors.append("%s 不得绘制全画布 shape 遮罩" % item_label)
            foreground.append((item_label, box, element))

    for source in slots:
        if used[source] == 0:
            errors.append("pages[%d] 内容槽 %s 未出现在视觉计划中" % (index, source))
        elif used[source] > 1:
            errors.append("pages[%d] 内容槽 %s 被重复放置 %d 次" %
                          (index, source, used[source]))

    text_boxes = [box for _item_label, box, element in foreground
                  if element.get("kind") == "text"]
    for scrim_index, scrim_box in scrims:
        if not any(_contains(scrim_box, text_box) for text_box in text_boxes):
            errors.append("pages[%d] background.scrims[%d] 必须完整承载至少一个文字框" %
                          (index, scrim_index))

    for left_index, (left_label, left_box, left) in enumerate(foreground):
        for right_label, right_box, right in foreground[left_index + 1:]:
            if left.get("allowOverlap") or right.get("allowOverlap"):
                continue
            if _intersection_ratio(left_box, right_box) <= 0.04:
                continue
            left_kind, right_kind = left.get("kind"), right.get("kind")
            if left_kind == "shape" or right_kind == "shape":
                # 形状承担背景分区或装饰层：允许被文字/图片覆盖（z 低于对方），
                # 允许与其它形状组合创作；但形状不得盖住文字（z 高于文字）。
                shape_el = left if left_kind == "shape" else right
                other_el = right if left_kind == "shape" else left
                if other_el.get("kind") == "text" and shape_el.get("z", 0) > other_el.get("z", 0):
                    errors.append(
                        "%s 形状盖住%s：形状作为背景层时 z 必须低于被覆盖的"
                        "文字（当前 shape.z=%s > text.z=%s）" %
                        (left_label if left_kind == "shape" else right_label,
                         right_label if left_kind == "shape" else left_label,
                         shape_el.get("z", 0), other_el.get("z", 0)))
                continue
            errors.append("%s 与 %s 前景重叠" % (left_label, right_label))


# ── bgTone 自动提取（声明 bgTone:"auto" 时触发）───────────────────

def extract_bg_tone(image_path, box, canvas_w=CANVAS_W, canvas_h=CANVAS_H):
    """按 16:9 cover 裁切后取 *box*（画布坐标）区域的平均色。

    返回 ``#RRGGBB``；PIL 不可用、图片不可读或区域退化时返回 None。
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(image_path) as handle:
            image = handle.convert("RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            return None
        scale = max(canvas_w / float(width), canvas_h / float(height))
        crop_w, crop_h = canvas_w / scale, canvas_h / scale
        left = (width - crop_w) / 2.0
        top = (height - crop_h) / 2.0
        bx, by, bw, bh = box
        sx = left + bx / scale
        sy = top + by / scale
        sw = bw / scale
        sh = bh / scale
        x0 = int(max(0, min(width - 1, sx)))
        y0 = int(max(0, min(height - 1, sy)))
        x1 = int(max(x0 + 1, min(width, sx + sw)))
        y1 = int(max(y0 + 1, min(height, sy + sh)))
        crop = image.crop((x0, y0, x1, y1))
        if crop.size[0] < 1 or crop.size[1] < 1:
            return None
        small = crop.resize((16, 16))
        pixels = list(small.getdata())
        count = len(pixels)
        r = sum(pixel[0] for pixel in pixels) // count
        g = sum(pixel[1] for pixel in pixels) // count
        b = sum(pixel[2] for pixel in pixels) // count
        return "#%02X%02X%02X" % (r, g, b)
    except Exception:
        return None


def resolve_auto_bg_tones(spec):
    """把 textSafeRegion 中声明为 ``"auto"`` 的 bgTone 替换为实测平均色。

    就地修改 spec（validate 与 render 共享同一 spec 对象，回填结果直接
    参与对比度校验和渲染）。返回 ``(filled, failed)`` 计数；提取失败的
    区域保持 ``"auto"``，由 `_validate_image_layout` 给出明确报错。
    """
    filled, failed = 0, 0
    for page in spec.get("pages") or []:
        background = (page.get("visualPlan") or {}).get("background") or {}
        if not isinstance(background, dict) or background.get("type") != "image":
            continue
        regions = (background.get("imageLayout") or {}).get("textSafeRegions") or []
        if not isinstance(regions, list):
            continue
        for region in regions:
            if not isinstance(region, dict) or region.get("bgTone") != "auto":
                continue
            box = _box(region.get("box"))
            path = _resolve_path(spec, background.get("source"))
            tone = extract_bg_tone(path, box) if (box and path) else None
            if tone:
                region["bgTone"] = tone
                filled += 1
            else:
                failed += 1
    return filled, failed


# ── 整册校验 ──────────────────────────────────────────────────────

def validate_authored_visual(spec):
    errors, warnings = [], []
    planning = spec.get("visualPlanning")
    if not isinstance(planning, dict):
        return ["新建课件必须提供根级 visualPlanning 视觉计划"], warnings
    direction = planning.get("creativeDirection") or {}
    for key in ("concept", "visualMetaphor", "backgroundStrategy"):
        if not str(direction.get(key) or "").strip():
            errors.append("visualPlanning.creativeDirection.%s 缺失" % key)

    # bgTone:"auto" 自动提取须先于结构校验执行（就地回填实测色调）。
    resolve_auto_bg_tones(spec)

    strategy = str(spec.get("imageStrategy") or "").strip().lower() or None
    if strategy is not None and strategy not in IMAGE_STRATEGIES:
        errors.append("imageStrategy 非法 %r：仅支持 generated / provided / none"
                      % spec.get("imageStrategy"))
        strategy = None
    no_image = strategy == "none"

    pages = spec.get("pages") or []
    ordinary = []
    background_eligible = []
    image_backgrounds = []
    background_by_source = {}
    illustration_pages = []
    for index, page in enumerate(pages):
        is_activity = page.get("layout") == "activity_page" or bool(page.get("activity"))
        if is_activity:
            if page.get("visualPlan"):
                errors.append("pages[%d] 课堂活动页必须保持空白，不得声明 visualPlan" % index)
            continue
        plan = page.get("visualPlan")
        if not isinstance(plan, dict):
            errors.append("pages[%d] 缺少 AI 逐页 visualPlan" % index)
            continue
        if not str(plan.get("designRationale") or "").strip():
            errors.append("pages[%d].visualPlan.designRationale 缺失" % index)
        background_kind = _validate_background(spec, page, index, errors, warnings)
        if tool_background_policy(page) != "none":
            background_eligible.append((index, page))
        if background_kind == "image":
            background = plan.get("background") or {}
            image_backgrounds.append((index, background.get("source")))
            if background.get("source") and background.get("source") not in background_by_source:
                background_by_source[background.get("source")] = background
            _warn_background_center_clutter(
                index, background, errors, warnings)
        illustration_count = 0
        for element in plan.get("elements") or []:
            if isinstance(element, dict) and element.get("kind") == "image":
                illustration_pages.append(index)
                illustration_count += 1
        if illustration_count > 3:
            warnings.append(
                "pages[%d] 配图 %d 张，超过 1–3 张的推荐上限：避免堆叠多图，"
                "保持页面清爽" % (index, illustration_count))
        _validate_elements(spec, page, index, errors, warnings)
        ordinary.append((index, page))

    ratio = planning.get("backgroundImageMinRatio", 0.5)
    if not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        errors.append("visualPlanning.backgroundImageMinRatio 必须在 0-1")
        ratio = 0.5

    if no_image:
        if ratio > 0:
            errors.append(
                "imageStrategy=none（无外部图片方案）必须同时声明 "
                "visualPlanning.backgroundImageMinRatio=0，并按纯色背景方案重新设计页面")
        if image_backgrounds:
            errors.append(
                "imageStrategy=none 下不得声明图片背景：pages[%s]；"
                "请改为 solid 纯色背景" %
                "、".join(str(index) for index, _ in image_backgrounds))
        if illustration_pages:
            errors.append(
                "imageStrategy=none 下不得声明前景配图：pages[%s]；"
                "以色彩、留白、字体层级和必要图形完成设计，不保留空图位"
                % "、".join(str(index) for index in illustration_pages))
    else:
        required = math.ceil(len(background_eligible) * ratio)
        if len(image_backgrounds) < required:
            errors.append("AI 背景图覆盖不足：%d/%d，至少需要 %d 页" %
                          (len(image_backgrounds), len(background_eligible), required))
        if background_eligible and ratio > 0:
            first_index, first_page = background_eligible[0]
            first_bg = ((first_page.get("visualPlan") or {}).get("background") or {})
            if first_bg.get("type") != "image":
                errors.append("首个可使用背景的非活动页必须使用本课生成的背景图")

    sources = [source for _, source in image_backgrounds if source]
    counts = Counter(sources)
    for source, count in counts.items():
        kind = _background_whitespace_kind(background_by_source.get(source))
        limit, warn_at = BACKGROUND_REUSE_LIMITS.get(kind, (4, 3))
        label = WHITESPACE_LABELS.get(kind, "未知")
        if count > limit:
            errors.append(
                "背景图 %s（%s留白）重复使用 %d 页，超过该留白方向的复用上限 %d 页"
                % (source, label, count, limit))
        elif count >= warn_at:
            warnings.append(
                "背景图 %s（%s留白）复用 %d 页，请确认各页前景布局、文字排版与视觉"
                "重心有明显差异，并优先通过更换配图制造差异"
                % (source, label, count))
    if len(image_backgrounds) >= 4:
        center_pages = sum(
            1 for _index, source in image_backgrounds
            if source and _background_whitespace_kind(background_by_source.get(source)) == "center")
        if center_pages * 2 < len(image_backgrounds):
            warnings.append(
                "图片背景页 %d 页中仅 %d 页使用中间留白背景：内容页背景应大部分选用"
                "主体置边缘、中心安静的中间留白图，侧边留白图尽量少用"
                % (len(image_backgrounds), center_pages))

    for (_, left), (right_index, right) in zip(ordinary, ordinary[1:]):
        similarity = silhouette_similarity(left, right)
        if similarity >= 0.82:
            errors.append("pages[%d] 与前一教学页版面轮廓相似度 %.0f%%，必须重新设计视觉重心" %
                          (right_index, similarity * 100))
    if len(ordinary) >= 6:
        signatures = {
            tuple(sorted(silhouette_tokens(page))) for _, page in ordinary
        }
        minimum = 4
        if len(signatures) < minimum:
            errors.append("全册只有 %d 种实际版面轮廓，至少需要 %d 种" %
                          (len(signatures), minimum))
    return errors, warnings


def text_contrast_report(spec):
    """逐页输出文字对比度预检结果（供 inspect_visual_blocks 集成展示）。

    只读不改 spec；与 `_validate_elements` 使用同一套有效背景与对比度算法。
    ``status``：``pass``（≥4.5）、``warn``（3–4.5）、``fail``（<3）、
    ``unknown``（背景未知，无法计算）。
    """
    report = []
    for index, page in enumerate(spec.get("pages") or [], 1):
        plan = page.get("visualPlan") or {}
        elements = plan.get("elements") or []
        if not elements:
            continue
        background = plan.get("background") or {}
        background = background if isinstance(background, dict) else {}
        _subjects, safe_regions = _image_layout_geometry(background)
        raw_scrims = background.get("scrims") or []
        raw_scrims = raw_scrims if isinstance(raw_scrims, list) else []
        scrims = [
            (scrim_index, _box(scrim.get("box")))
            for scrim_index, scrim in enumerate(raw_scrims)
            if isinstance(scrim, dict) and _box(scrim.get("box"))
        ]
        entries = []
        for element in elements:
            if not isinstance(element, dict) or element.get("kind") != "text":
                continue
            style = element.get("style") or {}
            color = style.get("color")
            box = _box(element.get("box"))
            if not _color(color) or not box:
                continue
            eff_bg, known = _effective_text_bg(
                element, box, background, scrims, raw_scrims, safe_regions)
            entry = {"source": element.get("source"), "fg": color}
            if not known or not _color(eff_bg):
                entry.update({"status": "unknown",
                              "hint": "文字框须落入声明了实测 bgTone 的 textSafeRegion，"
                                      "或使用 fill/scrim 垫底"})
            else:
                ratio = _contrast_ratio(color, eff_bg)
                entry.update({"bg": eff_bg, "ratio": round(ratio, 2),
                              "status": ("pass" if ratio >= CONTRAST_WARN
                                         else "warn" if ratio >= CONTRAST_ERROR
                                         else "fail")})
            entries.append(entry)
        if entries:
            report.append({"page": index, "contrast": entries})
    return report
