#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for native Seewo subject-tool semantics and geometry.

The six tools below are native application components. They are not decorative
layouts: each one has a bounded teaching intent, data contract, interaction
slot, client element type, and post-overlay layout policy.
"""
import re


GENERIC_TOOL_SLOT = {"x": 60, "y": 234, "w": 1160, "h": 426}

NATIVE_SUBJECT_TOOLS = {
    "poem": {
        "label": "古诗词卡",
        "mcpTool": "add_classical_poem_element",
        "elementTypes": ["ClassicalWorkElement"],
        "boundsPrefixes": ["古诗词", "古诗卡", "古诗", "ClassicalWork"],
        "subjects": ["语文", "chinese"],
        "teachingIntents": ["whole-poem-reading"],
        "requiredData": ["title", "lines"],
        "layoutPolicy": "full-canvas",
        "backgroundPolicy": "none",
        "slot": {"x": 40, "y": 36, "w": 1200, "h": 630},
        "xyScale": 0.5,
        "windowsStatus": "verified",
    },
    "hanzi": {
        "label": "汉字卡",
        "mcpTool": "add_hanzi_card_element",
        "elementTypes": ["HanziCard"],
        "boundsPrefixes": ["汉字卡片", "汉字卡", "HanziCard"],
        "subjects": ["语文", "chinese"],
        "teachingIntents": ["character-formation"],
        "requiredData": ["characters"],
        "layoutPolicy": "multi-element-card-rows",
        # A single MCP call always creates one expanded row. Eight or more
        # characters therefore require two HanziCard elements; width edits
        # scale each row proportionally while direct height edits are ignored.
        "slot": {"x": 70, "y": 234, "w": 1140, "h": 435},
        "maxItems": 20,
        "maxColumns": 10,
        "maxRows": 2,
        "singleRowMaxItems": 7,
        "rowGap": 18,
        "baseCardWidth": 300,
        "baseRowHeight": 435,
        "resizeAxis": "width",
        "settleSeconds": 0.8,
        "windowsStatus": "needs-verification",
    },
    "pinyin": {
        "label": "拼音卡",
        "mcpTool": "add_pinyin_card_element",
        "elementTypes": ["PinyinCard"],
        "boundsPrefixes": ["拼音卡片", "拼音卡", "PinyinCard"],
        "subjects": ["语文", "chinese"],
        "teachingIntents": ["pronunciation"],
        "requiredData": ["pinyin"],
        "layoutPolicy": "intrinsic-centered",
        "slot": {"x": 150, "y": 270, "w": 980, "h": 330},
        "windowsStatus": "verified",
    },
    "wordcard": {
        "label": "英语单词卡",
        "mcpTool": "add_english_word_card_element",
        "elementTypes": ["EnglishWordCard"],
        "boundsPrefixes": ["英语单词卡", "单词卡片", "单词卡", "EnglishWordCard"],
        "subjects": ["英语", "english"],
        "teachingIntents": ["vocabulary-acquisition"],
        "requiredData": ["words"],
        "layoutPolicy": "intrinsic-card-row",
        "slot": {"x": 10, "y": 258, "w": 1260, "h": 330},
        "cardGap": 24,
        "maxItems": 3,
        # edit_element currently acknowledges width/height without reliably
        # applying them. Layout must therefore use settled intrinsic bounds.
        "resizeStatus": "mcp-fix-pending",
        "boundsReadScale": 0.5,
        "windowsStatus": "verified",
    },
    "ruled": {
        "label": "英语四线三格",
        "mcpTool": "add_ruled_paper_element",
        "elementTypes": ["RuledPaper"],
        "boundsPrefixes": ["四线三格", "英语书写", "RuledPaper"],
        "subjects": ["英语", "english"],
        "teachingIntents": ["english-handwriting"],
        "requiredData": ["content"],
        "layoutPolicy": "intrinsic-centered",
        "slot": {"x": 110, "y": 274, "w": 1060, "h": 300},
        "boundsReadScale": 0.5,
        "windowsStatus": "verified",
    },
    "plot": {
        "label": "函数图像",
        "mcpTool": "add_function_plot_element",
        "elementTypes": ["MathFunctionElement"],
        "boundsPrefixes": ["函数图像", "数学函数", "MathFunction"],
        "subjects": ["数学", "物理", "math", "physics"],
        "teachingIntents": ["function-inquiry"],
        "requiredData": ["expression", "observations"],
        "layoutPolicy": "split-analysis-right",
        "analysisSlot": {"x": 40, "y": 232, "w": 620, "h": 410},
        "slot": {"x": 720, "y": 246, "w": 520, "h": 360},
        "boundsReadScale": 0.5,
        "windowsStatus": "verified",
    },
}


LEGACY_ALIASES = {"function": "plot"}


def canonical_tool_type(tool_type):
    value = str(tool_type or "").strip()
    return LEGACY_ALIASES.get(value, value)


def native_tool_spec(tool_type):
    return NATIVE_SUBJECT_TOOLS.get(canonical_tool_type(tool_type))


def normalize_reported_bounds(tool_type, bounds):
    """Convert get_slide_info geometry to logical 1280x720 coordinates.

    Several native components report x/y at twice their visual value:
    components while width/height remain logical pixels.  Keep that client
    quirk in the tool contract instead of scattering divisions through the
    overlay code.
    """
    if not bounds:
        return bounds
    spec = native_tool_spec(tool_type) or {}
    scale = float(spec.get("boundsReadScale", 1.0))
    x, y, width, height = bounds
    return (int(round(x * scale)), int(round(y * scale)), width, height)


def tool_data(tool):
    """Return nested data while accepting the historical flat tool contract."""
    nested = tool.get("data") if isinstance(tool, dict) else None
    merged = dict(tool) if isinstance(tool, dict) else {}
    if isinstance(nested, dict):
        merged.update(nested)
    merged.pop("data", None)
    return merged


def wordcard_words(tool, truncate=False):
    data = tool_data(tool)
    words = data.get("words")
    if not isinstance(words, list):
        words = re.split(r"[,，、;；]", str(data.get("word") or data.get("text") or ""))
    result = [str(word).strip() for word in words if str(word).strip()]
    limit = NATIVE_SUBJECT_TOOLS["wordcard"]["maxItems"]
    return result[:limit] if truncate else result


def hanzi_characters(tool):
    """Return the compact character sequence consumed by the native HanziCard."""
    return re.sub(r"\s+", "", str(tool_data(tool).get("characters") or ""))


def hanzi_layout(character_count):
    """Plan one or two separate HanziCard rows with proportional width scaling."""
    spec = NATIVE_SUBJECT_TOOLS["hanzi"]
    if character_count < 1 or character_count > spec["maxItems"]:
        return None
    rows = 1 if character_count <= spec["singleRowMaxItems"] else 2
    columns = (character_count + rows - 1) // rows
    row_counts = ([character_count] if rows == 1
                  else [columns, character_count - columns])
    slot = spec["slot"]
    base_width = spec["baseCardWidth"]
    base_row_height = spec["baseRowHeight"]
    gap = spec["rowGap"] if rows > 1 else 0
    natural_widths = [count * base_width for count in row_counts]
    usable_height = slot["h"] - gap * (rows - 1)
    scale = min(1.0, slot["w"] / max(natural_widths),
                usable_height / (rows * base_row_height))
    row_widths = [int(round(width * scale)) for width in natural_widths]
    row_height = min(int(round(base_row_height * scale)), usable_height // rows)
    width = max(row_widths)
    height = rows * row_height + gap * (rows - 1)
    return {
        "x": slot["x"] + (slot["w"] - width) // 2,
        "y": slot["y"] + (slot["h"] - height) // 2,
        "width": width,
        "height": height,
        "columns": columns,
        "rows": rows,
        "rowCounts": row_counts,
        "rowWidths": row_widths,
        "rowGap": gap,
        "cardWidth": int(round(base_width * scale)),
        "rowHeight": row_height,
        "scale": scale,
    }


def hanzi_character_rows(tool):
    """Split authored characters into the exact per-call HanziCard rows."""
    characters = hanzi_characters(tool)
    layout = hanzi_layout(len(characters))
    if not layout:
        return []
    rows = []
    offset = 0
    for count in layout["rowCounts"]:
        rows.append(characters[offset:offset + count])
        offset += count
    return rows


def wordcard_layout(card_bounds):
    """Lay out 1-3 settled native cards using their actual intrinsic sizes."""
    spec = NATIVE_SUBJECT_TOOLS["wordcard"]
    bounds = list(card_bounds or [])
    count = len(bounds)
    if count < 1 or count > spec["maxItems"]:
        return []
    slot = spec["slot"]
    gap = spec["cardGap"]
    widths = [int(round(bound[2])) for bound in bounds]
    heights = [int(round(bound[3])) for bound in bounds]
    row_width = sum(widths) + gap * (count - 1)
    if row_width > slot["w"]:
        return []
    x0 = slot["x"] + (slot["w"] - row_width) // 2
    y = slot["y"] + max(0, (slot["h"] - max(heights)) // 2)
    layout = []
    x = x0
    for width, height in zip(widths, heights):
        layout.append({"x": x, "y": y, "width": width, "height": height})
        x += width + gap
    return layout


def plot_observations(tool):
    """Return the structured observation dimensions for a function inquiry."""
    values = tool_data(tool).get("observations") or []
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def tool_interaction_slot(page_or_tool):
    tool = page_or_tool.get("subjectTool") if isinstance(page_or_tool, dict) else None
    if not isinstance(tool, dict):
        tool = page_or_tool if isinstance(page_or_tool, dict) else {}
    spec = native_tool_spec(tool.get("type"))
    return dict(spec["slot"]) if spec else dict(GENERIC_TOOL_SLOT)


def tool_background_policy(page_or_tool):
    """Return whether a native tool page accepts an authored background.

    ``"none"`` means the page must keep the client default blank background:
    ``poem`` (full-canvas classical poem component) and classroom activity
    pages (choice/judge/match/classify, which own the whole page).  Any other
    page type is ``"authored"`` and may declare ``visualPlan.background``.
    """
    if isinstance(page_or_tool, dict):
        activity = page_or_tool.get("activity") or {}
        if (page_or_tool.get("layout") == "activity_page" or
                activity.get("activityType")):
            return "none"
    tool = page_or_tool.get("subjectTool") if isinstance(page_or_tool, dict) else None
    if not isinstance(tool, dict):
        tool = page_or_tool if isinstance(page_or_tool, dict) else {}
    spec = native_tool_spec(tool.get("type"))
    return spec.get("backgroundPolicy", "authored") if spec else "authored"


def _subject_matches(subject, allowed):
    if not subject:
        return True
    lowered = str(subject).lower()
    return any(token.lower() in lowered for token in allowed)


def validate_native_tool(tool, subject="", grade="", require_intent=False):
    """Validate a native tool and return ``(errors, warnings)``.

    The first Windows pass keeps unknown client geometry as warnings, but data
    loss and subject misuse are hard errors before ENBX generation.
    """
    errors, warnings = [], []
    tool_type = canonical_tool_type((tool or {}).get("type"))
    spec = native_tool_spec(tool_type)
    if not spec:
        return errors, warnings
    data = tool_data(tool or {})
    if not _subject_matches(subject, spec["subjects"]):
        errors.append("%s 仅适用于%s，当前学科为 %s" %
                      (spec["label"], "/".join(spec["subjects"][:2]), subject or "未声明"))
    intent = str((tool or {}).get("teachingIntent") or "").strip()
    if require_intent and not intent:
        errors.append("%s 缺少 teachingIntent（允许值：%s）" %
                      (spec["label"], "/".join(spec["teachingIntents"])))
    elif intent and intent not in spec["teachingIntents"]:
        errors.append("%s.teachingIntent=%r 非法（允许值：%s）" %
                      (spec["label"], intent, "/".join(spec["teachingIntents"])))

    if tool_type == "poem":
        if not str(data.get("title") or "").strip():
            errors.append("古诗词卡缺少 title")
        lines = [str(line).strip() for line in data.get("lines") or [] if str(line).strip()]
        if not lines:
            errors.append("古诗词卡必须提供 lines，供本地诗词库未收录时完整降级")
        elif len(lines) > 12:
            warnings.append("古诗词卡共 %d 行，原生卡可能需要 Windows 实机检查末行" % len(lines))
    elif tool_type == "hanzi":
        chars = hanzi_characters(tool)
        if not chars:
            errors.append("汉字卡缺少 characters")
        elif len(chars) > spec["maxItems"]:
            errors.append("汉字卡每页最多 %d 字（最多 %d 排、每排 %d 字），当前 %d 字"
                          % (spec["maxItems"], spec["maxRows"],
                             spec["maxColumns"], len(chars)))
    elif tool_type == "pinyin":
        value = str(data.get("pinyin") or "").strip()
        if not value:
            errors.append("拼音卡缺少 pinyin")
        elif not re.search(r"[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ1-5]", value, re.I):
            warnings.append("拼音卡未检测到声调符号或声调数字，请确认不是无调拼音")
        if grade and not any(token in str(grade) for token in ("一", "二", "1", "2", "低")):
            warnings.append("拼音卡主要用于小学低段；当前年级 %s 仅应服务易错音/多音字" % grade)
    elif tool_type == "wordcard":
        words = wordcard_words(tool)
        if not words:
            errors.append("英语单词卡缺少 words/word")
        elif len(words) > spec["maxItems"]:
            errors.append("英语单词卡单页最多 %d 词，当前 %d 词；必须拆页，禁止截断"
                          % (spec["maxItems"], len(words)))
    elif tool_type == "ruled":
        value = str(data.get("content") or "").strip()
        if not value:
            errors.append("英语四线三格缺少 content")
        elif not re.search(r"[A-Za-z]", value):
            errors.append("英语四线三格 content 必须包含英文字母或单词，不能当语文田字格使用")
        elif len(value) > 40:
            warnings.append("英语四线三格 content 超过 40 字符，建议拆分书写目标")
    elif tool_type == "plot":
        expression = str(data.get("expression") or data.get("expr") or "").strip()
        if not expression:
            errors.append("函数图像缺少 expression")
        elif "x" not in expression.lower():
            errors.append("函数图像 expression 必须包含自变量 x")
        observations = plot_observations(tool)
        if not observations:
            errors.append("函数工具左右布局缺少 observations（需 2-3 条观察任务）")
        elif not 2 <= len(observations) <= 3:
            errors.append("函数工具 observations 必须为 2-3 条，当前 %d 条" % len(observations))

    if spec["windowsStatus"] != "verified":
        warnings.append("%s 的客户端尺寸/坐标仍需本轮 Windows 截图校准" % spec["label"])
    return errors, warnings


HIGHER_STAGE_TOKENS = (
    "初中", "高中",
    "初一", "初二", "初三", "高一", "高二", "高三",
    "七年级", "八年级", "九年级", "七", "八", "九",
)


def is_higher_stage(grade):
    """Return whether ``grade`` indicates secondary school (初中及以上).

    Higher-stage courseware should focus on teaching, structuring and
    comparison tools; classroom activities are reserved for necessary
    checkpoints and must not be padded in to inflate interactivity.
    """
    text = str(grade or "").strip()
    return any(token in text for token in HIGHER_STAGE_TOKENS)


def validate_activity_usage(grade, activity_count, content_page_count):
    """Check classroom-activity density against the student stage.

    Lower primary may use activities liberally as game-based learning; no
    warning is raised there.  Secondary school (初中及以上) keeps activities
    to necessary checkpoints only (usually 1-2, possibly zero).
    """
    errors, warnings = [], []
    if not is_higher_stage(grade) or activity_count <= 0 or content_page_count <= 0:
        return errors, warnings
    ratio = activity_count * 100 // content_page_count
    if activity_count >= 3:
        warnings.append(
            "高年级（初中及以上）课堂活动 %d 个、占内容页约 %d%%，超过建议上限："
            "以讲授/梳理/对比类原生工具（poem/hanzi/mindmap/table/plot）为主，"
            "课堂活动只保留必要检测环节，通常不超过 1-2 个，可为 0" %
            (activity_count, ratio))
    elif activity_count == 2 and ratio >= 30:
        warnings.append(
            "高年级（初中及以上）课堂活动 2 个且占内容页约 %d%%：确认每个活动"
            "都完成讲授/梳理/对比无法达成的检测目标（即时全员反馈、易错点甄别、"
            "术语配对），否则用普通练习页或 judge 判断页替代" % ratio)
    return errors, warnings
