#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_v2.py — 新主流程：页面计划 → 校验 → ENBX 原生合成 → 打开 → MCP 叠加交互层。

流水线（对应 SKILL Workflow A 的 5–7 步）：
  1. validate_deck 计划级校验（errors 硬停，warnings 提示返修）
  2. 配图预检：所有声明的背景图和内容图必须存在且可解码，缺图硬停
  3. 合成整册课件：enbx_renderer 按 AI 逐页 visualPlan 原生直出 .enbx，
     不使用固定主题、候选构图或 PPTX 中间件
  4. 落稿打开：本地 ENBX 经 swenlauncher 打开 + en_find_shells 按名绑 shell
    （全部精确同名旧 shell 会先关闭并确认；--resume 则复用它续修）
  5. MCP 原生背景：逐页设置图片或纯色背景并回读确认
  6. MCP 叠加：tool_page 页叠加学科工具（思维导图/表格/汉字卡/拼音卡/田字格/
     单词卡/函数图像/古诗），activity_page 页叠加课堂活动（整页替换）
     ——响应含「失败/至少/不能为空」文案即判失败（客户端可能以 exit 0 返回错误文案）
  7. 云同步（Edit 门控）→ ensure_edit_mode 终态（始终保持在备课模式）

用法：
    python build_v2.py --spec pages.json [--outdir output/xxx] [--dry-run]
    python build_v2.py --spec pages.json --validate-only
    python build_v2.py --spec pages.json --slow-mode   # 慢机器：所有等待 ×2
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "design"))
sys.path.insert(0, os.path.join(HERE, "..", "mcp"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from mcp_client import McpHttpSession, find_live_port  # noqa: E402
from mcp_runtime import RobustMcp, ensure_edit_mode, sync_with_edit_gate  # noqa: E402
from courseware_runtime import (activity_payload_to_mcp_args,  # noqa: E402
                               normalize_mindmap_markdown, page_subject_tool)
from courseware_ops import set_native_slide_background  # noqa: E402
from subject_tools import (hanzi_character_rows, hanzi_characters, hanzi_layout,  # noqa: E402
                           native_tool_spec,
                           normalize_reported_bounds, tool_background_policy,
                           tool_interaction_slot, wordcard_layout, wordcard_words)

from visual_plan_renderer import is_authored_visual  # noqa: E402
from validate_deck import validate_deck  # noqa: E402

# 客户端以 exit 0 返回错误文案时的识别关键词。
ERROR_KEYWORDS = ("失败", "至少", "不能为空", "无效", "不支持")

# ── 等待节奏（集中管理，避免散落的 time.sleep 魔法数字）──────────────
# WAIT_SCALE 由 --slow-mode 置为 2.0，供慢机器整体放慢等待。
WAIT_SCALE = 1.0
SETTLE_SECONDS = 0.8          # 翻页/叠加后客户端 UI 稳定等待
IMPORT_STABILIZE_SECONDS = 3.0  # en_bind_shell 后导入稳定等待
IMPORT_POLL_INTERVAL = 3.0    # swenlauncher 打开后轮询 shell 的间隔


def settle(seconds=None):
    """按统一节奏等待；seconds 缺省时用 SETTLE_SECONDS。"""
    base = SETTLE_SECONDS if seconds is None else float(seconds)
    time.sleep(base * WAIT_SCALE)


# ── 阶段进度与耗时统计（#18：长流程可观测）──────────────────────────
_STAGE_TIMES = []            # [(阶段名, 秒)]
_RUN_STARTED = None          # main() 入口时间戳

TOTAL_STAGES = 7


def _fmt_seconds(seconds):
    seconds = float(seconds)
    if seconds < 60:
        return "%.1fs" % seconds
    return "%d分%02d秒" % (seconds // 60, seconds % 60)


def stage_start(number, name):
    """打印阶段横幅并返回计时起点。"""
    print("\n━━ [%d/%d] %s" % (number, TOTAL_STAGES, name))
    return (name, time.time())


def stage_end(started):
    """记录并打印阶段耗时。"""
    name, t0 = started
    seconds = time.time() - t0
    _STAGE_TIMES.append((name, seconds))
    print("✓ %s 完成（%s）" % (name, _fmt_seconds(seconds)))


def print_stage_summary():
    if _STAGE_TIMES:
        print("阶段耗时：%s" %
              "；".join("%s %s" % (name, _fmt_seconds(sec))
                        for name, sec in _STAGE_TIMES))
    if _RUN_STARTED is not None:
        print("总耗时：%s" % _fmt_seconds(time.time() - _RUN_STARTED))


def fail(code, message, hint=None):
    """统一失败出口：错误 + 下一步指引 + 已用时长，再退出。"""
    sys.stderr.write("✗ %s\n" % message)
    if hint:
        sys.stderr.write("▶ 下一步：%s\n" % hint)
    if _RUN_STARTED is not None:
        sys.stderr.write("（已用时 %s）\n" % _fmt_seconds(time.time() - _RUN_STARTED))
    sys.exit(code)


def _derive_deck_title(spec):
    """落稿标题：spec 根级 title > 课题 topic > 首个有标题页面 > 「未命名课件」。

    客户端 close_current_courseware 已支持，同名旧课件会在导入前全部自动关闭，
    但「未命名课件」天然易撞名；spec 缺 title 时按课题自动派生，尽量避开默认名。
    """
    title = str(spec.get("title") or "").strip()
    if title:
        return title, None
    topic = str(spec.get("topic") or "").strip()
    if topic:
        return topic, "spec 缺根级 title，已按课题名派生落稿标题"
    for page in spec.get("pages") or []:
        page_title = str((page or {}).get("title") or "").strip()
        if page_title:
            return page_title, "spec 缺根级 title，已按首页标题派生落稿标题"
    return "未命名课件", "spec 缺根级 title 且无课题/页面标题可派生，落稿将使用「未命名课件」"


# 工具留白区（tool_page 引导语带下方）：y 234–660，中心 (640, 447)
TOOL_ZONE = tuple(tool_interaction_slot({}).values())
POEM_ZONE = tuple(tool_interaction_slot({"type": "poem"}).values())


def _connect_mcp(port=0, url=None, courseware_name=None):
    """Require a working MCP tools endpoint before formal ENBX generation."""
    resolved_url = url
    if not resolved_url:
        resolved_port = port or find_live_port()
        resolved_url = "http://127.0.0.1:%d/mcp" % resolved_port
    session = McpHttpSession(resolved_url)
    session.initialize()
    status, payload = session.tools_list()
    tools = ((payload or {}).get("result") or {}).get("tools")
    if status not in (200, 202) or not isinstance(tools, list) or not tools:
        raise RuntimeError("MCP tools/list 未返回可用工具")
    runtime = RobustMcp(session, courseware_name=courseware_name)
    runtime.available_tools = {
        tool.get("name") for tool in tools
        if isinstance(tool, dict) and tool.get("name")
    }
    return runtime, resolved_url


def _slide_bounds(mcp, base, page, rid):
    """从 get_slide_info 的『元素简要信息』解析 {元素标签: (x, y, w, h)}。

    get_elements 不返回几何、get_element_properties 对工具元素查不到（实测），
    目前唯一可靠的几何回读通道是 get_slide_info 的 markdown 行：
    「- 思维导图.1: (-381, 192) 883×116」。
    """
    import re
    _, o = mcp.tools_call("get_slide_info", {"slideNumber": page, **base}, rid=rid)
    out = {}
    for m in re.finditer(r"-\s*([\w一-鿿]+\.\d+):\s*\((-?\d+),\s*(-?\d+)\)\s*(\d+)×(\d+)",
                         McpHttpSession.text_of(o)):
        out[m.group(1)] = tuple(int(m.group(i)) for i in range(2, 6))
    return out


def _courseware_slide_count(mcp, base, rid):
    """Read the stable deck page count used by import/overlay integrity gates."""
    _, output = mcp.tools_call("get_current_courseware_info", base, rid=rid)
    text = McpHttpSession.text_of(output)
    try:
        value = json.loads(text).get("slideCount")
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        match = re.search(r'"slideCount"\s*:\s*(\d+)', text or "")
        return int(match.group(1)) if match else None


def _deck_integrity_error(mcp, base, expected_pages, rid, stage):
    actual = _courseware_slide_count(mcp, base, rid)
    if actual == expected_pages:
        return None
    if actual is None:
        return "%s无法回读课件页数（预期 %d 页）" % (stage, expected_pages)
    return "%s课件页数由 %d 变为 %d；停止同步，避免保存破坏性叠加" % (
        stage, expected_pages, actual)


def _center_mindmap(mcp, base, page, rid, logs):
    """脑图叠加后重定位：MindMapTree 的 edit_element x/y 是**中心**语义（实测：
    x=640,y=430 → bounds (198,372) 883×116，中心恰为 (639.5,430)），且尺寸由
    自动布局决定、width/height 请求会被忽略——所以只能挪中心、不能缩放。
    超宽时居中至少让两侧对称溢出，并记告警。"""
    bounds = _slide_bounds(mcp, base, page, rid)
    mm = next((v for k, v in bounds.items() if k.startswith("思维导图")), None)
    if not mm:
        logs.append("⚠ 第%d页 脑图几何回读失败，跳过重定位" % page)
        return
    _, o = mcp.tools_call("get_elements", {"slideNumber": page,
                                           "elementTypes": ["MindMapTree"], **base}, rid=rid + 1)
    try:
        ids = [e["id"] for e in json.loads(McpHttpSession.text_of(o)).get("elements", [])]
    except ValueError:
        ids = []
    if ids:
        zx, zy, zw, zh = TOOL_ZONE
        mcp.tools_call("edit_element", {"slideNumber": page, "elementIds": ids,
                                        "x": zx + zw // 2, "y": zy + zh // 2, **base}, rid=rid + 2)
        # 脑图叠加/编辑后最后一个节点残留内部聚焦（绿框手柄，元素级选中已是空）。
        # 实测唯一清法：选中该脑图元素 → 再清空选中（节点聚焦随元素选中循环复位）。
        try:
            mcp.tools_call("select_elements", {"slideNumber": page, "elementIds": ids,
                                               "selectionType": "replace", **base}, rid=rid + 3)
            mcp.tools_call("select_elements", {"slideNumber": page, "elementIds": [],
                                               "selectionType": "replace", **base}, rid=rid + 4)
        except Exception:
            pass
    if mm[2] > zw:
        logs.append("⚠ 第%d页 脑图宽 %dpx 超出留白区 %dpx：节点文案过长，建议精简"
                    % (page, mm[2], zw))


def _deselect(mcp, base, page, rid):
    """清空页面选中态（终态策略：绝不遗留元素选中）。
    selectionType 枚举实测有效值为 replace；空 elementIds + replace = 全不选。"""
    try:
        mcp.tools_call("select_elements", {"slideNumber": page, "elementIds": [],
                                           "selectionType": "replace", **base}, rid=rid)
    except Exception:
        pass

# subjectTool.type → (MCP 工具名, 数据键别名列表, 参数构造函数)
def _tool_call(tool):
    """subjectTool → (tool_name, args)。数据键兼容 prompt 模板的各种写法。"""
    ttype = tool.get("type")
    data = tool.get("data") or {}

    def pick(*keys, default=None):
        for k in keys:
            if data.get(k) is not None:
                return data[k]
        return default

    if ttype == "mindmap":
        md = pick("mdStr", "markdown", "markdownList", default="")
        return "add_mind_map_element", {
            "markdownList": normalize_mindmap_markdown(md),
            "x": 640, "y": 400}  # 脑图以 (x,y) 为中心对称生长，给内容区中心
    if ttype == "table":
        return "add_table_element", {
            "markdownTable": pick("markdownTable", "markdown", "mdStr", default=""),
            "x": 80, "y": 240, "width": 1120, "height": 380}
    native = native_tool_spec(ttype)
    if ttype == "hanzi":
        return "add_hanzi_card_element", {"characters": pick("characters", "text", default="")}
    if ttype == "pinyin":
        return "add_pinyin_card_element", {"pinyin": pick("pinyin", "text", default="")}
    if ttype == "ruled":
        return "add_ruled_paper_element", {"content": pick("content", "text", default="")}
    if ttype == "wordcard":
        # 多词拆分与逐词叠加统一由 overlay_tools 的 wordcard 分支处理
        # （words[existing_count:] 循环），这里只返回工具名，避免两处逻辑分裂。
        return "add_english_word_card_element", {}
    if ttype == "poem":
        args = {"title": pick("title", default="")}
        if pick("author"):
            args["author"] = pick("author")
        return "add_classical_poem_element", args
    if ttype in ("plot", "function"):
        return native["mcpTool"], {"expression": pick("expression", "expr", default="")}
    return None, None


def _wordcard_words(tool):
    """wordcard 工具的词表：data.words 列表优先；data.word 单字符串按 , 、 ， 切分。
    单页词数由教学任务决定，最多三词；超过上限必须在计划阶段拆页。"""
    return wordcard_words(tool, truncate=True)


def _native_element_ids(mcp, base, page, tool_type, rid):
    spec = native_tool_spec(tool_type)
    if not spec:
        return []
    _, output = mcp.tools_call("get_elements", {
        "slideNumber": page, "elementTypes": spec["elementTypes"], **base}, rid=rid)
    try:
        return [element["id"] for element in json.loads(
            McpHttpSession.text_of(output)).get("elements", [])]
    except (ValueError, TypeError, KeyError):
        return []


def _page_elements(mcp, base, page, rid, element_types=None):
    """Read page elements for resume decisions; None means the read is unsafe."""
    arguments = {"slideNumber": page, **base}
    if element_types:
        arguments["elementTypes"] = element_types
    status, output = mcp.tools_call("get_elements", arguments, rid=rid)
    if status not in (200, 202) or McpHttpSession.is_error(output):
        return None
    try:
        data = json.loads(McpHttpSession.text_of(output))
    except (ValueError, TypeError):
        return None
    elements = data.get("elements") if isinstance(data, dict) else None
    return elements if isinstance(elements, list) else None


def _native_bounds_all(mcp, base, page, tool_type, rid):
    spec = native_tool_spec(tool_type)
    if not spec:
        return []
    bounds = _slide_bounds(mcp, base, page, rid)
    return [normalize_reported_bounds(tool_type, value)
            for name, value in bounds.items()
            if any(name.startswith(prefix) for prefix in spec["boundsPrefixes"])]


def _native_bounds(mcp, base, page, tool_type, rid):
    matches = _native_bounds_all(mcp, base, page, tool_type, rid)
    return matches[0] if matches else None


def _layout_intrinsic_tool(mcp, base, page, tool_type, rid, logs):
    """Center a native fixed-size component in its tool-specific safe slot."""
    spec = native_tool_spec(tool_type)
    ids = _native_element_ids(mcp, base, page, tool_type, rid)
    if not ids:
        logs.append("⚠ 第%d页 %s接口成功但元素回读失败" % (page, spec["label"]))
        return False
    settle_seconds = float(spec.get("settleSeconds", 0))
    if settle_seconds > 0:
        settle(settle_seconds)
    bounds = _native_bounds(mcp, base, page, tool_type, rid + 1)
    if not bounds:
        logs.append("⚠ 第%d页 %s已落地，但 get_slide_info 未返回可识别几何；"
                    "请在 Windows 记录元素标签并校准 boundsPrefixes" % (page, spec["label"]))
        return False
    slot = spec["slot"]
    _, _, width, height = bounds
    x = slot["x"] + max(0, (slot["w"] - width) // 2)
    y = slot["y"] + max(0, (slot["h"] - height) // 2)
    mcp.tools_call("edit_element", {"slideNumber": page, "elementIds": ids,
                                    "x": x, "y": y, **base}, rid=rid + 2)
    if settle_seconds > 0:
        settle(settle_seconds)
    actual = _native_bounds(mcp, base, page, tool_type, rid + 3)
    if not actual:
        logs.append("⚠ 第%d页 %s写入坐标后无法再次回读几何" % (page, spec["label"]))
        return False
    actual_x, actual_y, actual_w, actual_h = actual
    if (actual_x < 0 or actual_y < 0 or actual_x + actual_w > 1280
            or actual_y + actual_h > 720):
        logs.append("⚠ 第%d页 %s写回后越出画布：(%d,%d) %d×%d"
                    % (page, spec["label"], actual_x, actual_y, actual_w, actual_h))
        return False
    tolerance = 24
    if (actual_x < slot["x"] - tolerance or actual_y < slot["y"] - tolerance
            or actual_x + actual_w > slot["x"] + slot["w"] + tolerance
            or actual_y + actual_h > slot["y"] + slot["h"] + tolerance):
        logs.append("⚠ 第%d页 %s写回几何 (%d,%d) %d×%d 未完全落入安全槽；"
                    "请根据 Windows 截图校准坐标语义"
                    % (page, spec["label"], actual_x, actual_y, actual_w, actual_h))
    if width > slot["w"] or height > slot["h"]:
        logs.append("⚠ 第%d页 %s原生尺寸 %d×%d 超出安全槽 %d×%d；"
                    "已按画布居中，需在 Windows 调整页面壳或拆分内容"
                    % (page, spec["label"], width, height, slot["w"], slot["h"]))
    if spec["windowsStatus"] != "verified":
        logs.append("⚠ 第%d页 %s首版落位：原始 %d×%d，写回 (%d,%d) %d×%d；"
                    "请用客户端截图校准"
                    % (page, spec["label"], width, height,
                       actual_x, actual_y, actual_w, actual_h))
    return True


def _layout_hanzi_cards(mcp, base, page, tool, rid, logs):
    """Width-scale one/two intrinsic HanziCards, then place by actual heights."""
    spec = native_tool_spec("hanzi")
    chars = hanzi_characters(tool)
    target = hanzi_layout(len(chars))
    ids = _native_element_ids(mcp, base, page, "hanzi", rid)
    expected_rows = target["rows"] if target else 0
    if len(ids) != expected_rows or not target:
        logs.append("⚠ 第%d页 汉字卡无法布局：元素数 %d，预期行数 %d，字符数 %d"
                    % (page, len(ids), expected_rows, len(chars)))
        return False
    settle_seconds = float(spec.get("settleSeconds", 0))
    if settle_seconds > 0:
        settle(settle_seconds)
    initial = _native_bounds_all(mcp, base, page, "hanzi", rid + 1)
    if len(initial) != expected_rows:
        logs.append("⚠ 第%d页 汉字卡展开后仅回读到 %d/%d 行初始几何" %
                    (page, len(initial), expected_rows))
        return False
    slot = spec["slot"]
    gap = spec["rowGap"] if expected_rows > 1 else 0
    max_width = max(bound[2] for bound in initial)
    total_height = sum(bound[3] for bound in initial)
    usable_height = slot["h"] - gap * (expected_rows - 1)
    scale = min(1.0, slot["w"] / max_width, usable_height / total_height)
    target_widths = [max(1, int(round(bound[2] * scale))) for bound in initial]
    for index, (element_id, width) in enumerate(zip(ids, target_widths)):
        mcp.tools_call("edit_element", {
            "slideNumber": page, "elementIds": [element_id],
            "width": width, **base,
        }, rid=rid + 2 + index)
    if settle_seconds > 0:
        settle(settle_seconds)
    resized = _native_bounds_all(
        mcp, base, page, "hanzi", rid + 2 + expected_rows)
    if len(resized) != expected_rows:
        logs.append("⚠ 第%d页 汉字卡宽度写回后仅回读到 %d/%d 行几何" %
                    (page, len(resized), expected_rows))
        return False
    group_height = sum(bound[3] for bound in resized) + gap * (expected_rows - 1)
    if max(bound[2] for bound in resized) > slot["w"] or group_height > slot["h"]:
        logs.append("⚠ 第%d页 汉字卡宽度缩放后仍无法放入安全槽：最大宽 %dpx，"
                    "总高 %dpx，安全槽 %d×%dpx" %
                    (page, max(bound[2] for bound in resized), group_height,
                     slot["w"], slot["h"]))
        return False
    y = slot["y"] + (slot["h"] - group_height) // 2
    expected = []
    for index, (element_id, bound) in enumerate(zip(ids, resized)):
        width, height = bound[2], bound[3]
        x = slot["x"] + (slot["w"] - width) // 2
        mcp.tools_call("edit_element", {
            "slideNumber": page, "elementIds": [element_id],
            "x": x, "y": y, **base,
        }, rid=rid + 3 + expected_rows + index)
        expected.append((x, y, width, height))
        y += height + gap
    if settle_seconds > 0:
        settle(settle_seconds)
    actual = _native_bounds_all(
        mcp, base, page, "hanzi", rid + 3 + expected_rows * 2)
    if len(actual) != expected_rows:
        logs.append("⚠ 第%d页 汉字卡定位后仅回读到 %d/%d 行几何" %
                    (page, len(actual), expected_rows))
        return False
    tolerance = 24
    for row_index, (got, want) in enumerate(zip(actual, expected), 1):
        if any(abs(value - goal) > tolerance for value, goal in zip(got, want)):
            logs.append("⚠ 第%d页 汉字卡第%d行写回异常：期望 %s，实际 %s" %
                        (page, row_index, want, got))
            return False
        x, y, width, height = got
        if (x < slot["x"] - tolerance or y < slot["y"] - tolerance
                or x + width > slot["x"] + slot["w"] + tolerance
                or y + height > slot["y"] + slot["h"] + tolerance):
            logs.append("⚠ 第%d页 汉字卡第%d行未落入安全槽：%s" %
                        (page, row_index, got))
            return False
    row_summary = "+".join(str(count) for count in target["rowCounts"])
    logs.append("第%d页 汉字卡按 %s 字创建 %d 个原生行元素，实际尺寸 %s" %
                (page, row_summary, expected_rows,
                 "、".join("%d×%dpx" % (bound[2], bound[3]) for bound in actual)))
    return True


def _poll_native_bounds(mcp, base, page, tool_type, expected, rid,
                        timeout=None, interval=0.3):
    """轮询回读原生元素几何，直到凑齐 *expected* 个或超时。

    返回 ``(bounds, next_rid)``。相比固定 sleep：快机器上元素一旦出现立即
    继续，慢机器上最多等到超时（受 WAIT_SCALE 缩放），不再凭经验拍等待值。
    """
    if timeout is None:
        timeout = max(3.0, SETTLE_SECONDS * 5 * WAIT_SCALE)
    deadline = time.time() + timeout
    bounds = []
    while True:
        bounds = _native_bounds_all(mcp, base, page, tool_type, rid)
        rid += 1
        if len(bounds) >= expected or time.time() >= deadline:
            return bounds, rid
        time.sleep(interval * WAIT_SCALE)


def _layout_wordcards(mcp, base, page, rid, logs):
    """Place 1-3 cards in one row using settled native content dimensions."""
    ids = _native_element_ids(mcp, base, page, "wordcard", rid)
    if not ids:
        logs.append("⚠ 第%d页 单词卡元素回读失败，跳过重定位" % page)
        return False
    spec = native_tool_spec("wordcard")
    slot = spec["slot"]
    zx, zy, zw, zh = slot["x"], slot["y"], slot["w"], slot["h"]
    n = len(ids)
    # Word-card definitions load asynchronously and each word produces a
    # different intrinsic size. Read those sizes before calculating the row;
    # MCP width/height edits are currently unreliable. Poll until all cards
    # report geometry instead of a fixed sleep (fast machines continue early).
    initial, rid = _poll_native_bounds(
        mcp, base, page, "wordcard", n, rid + 1)
    if len(initial) != n:
        logs.append("⚠ 第%d页 单词卡仅回读到 %d/%d 张初始几何" % (page, len(initial), n))
        return False
    expected_layout = wordcard_layout(initial)
    if not expected_layout:
        logs.append("⚠ 第%d页 %d 张单词卡的原生总宽超出安全槽；请按教学内容拆页"
                    % (page, n))
        return False
    for i, (eid, target) in enumerate(zip(ids, expected_layout)):
        mcp.tools_call("edit_element", {"slideNumber": page, "elementIds": [eid],
                                        "x": target["x"], "y": target["y"],
                                        **base}, rid=rid + 2 + i)
    actual, rid = _poll_native_bounds(
        mcp, base, page, "wordcard", n, rid + 2 + n)
    expected = [tuple(target[key] for key in ("x", "y", "width", "height"))
                for target in expected_layout]
    if len(actual) != n:
        logs.append("⚠ 第%d页 单词卡写回后仅回读到 %d/%d 张几何" % (page, len(actual), n))
        return False
    tolerance = 4
    geometry_ok = True
    for index, (got, want) in enumerate(zip(actual, expected), 1):
        if any(abs(got[axis] - want[axis]) > tolerance for axis in (0, 1)):
            geometry_ok = False
            logs.append("⚠ 第%d页 单词卡%d写回位置 %s，目标 %s（容差 %dpx）"
                        % (page, index, got[:2], want[:2], tolerance))
        if any(abs(got[axis] - want[axis]) > tolerance for axis in (2, 3)):
            geometry_ok = False
            logs.append("⚠ 第%d页 单词卡%d异步加载后尺寸从 %s 变为 %s；需重新排版"
                        % (page, index, want[2:], got[2:]))
        ax, ay, aw, ah = got
        if (ax < zx - tolerance or ay < zy - tolerance
                or ax + aw > zx + zw + tolerance or ay + ah > zy + zh + tolerance):
            geometry_ok = False
            logs.append("⚠ 第%d页 单词卡%d写回后未落入安全槽：%s" % (page, index, got))
    gaps = [actual[i + 1][0] - actual[i][0] - actual[i][2]
            for i in range(n - 1)]
    if gaps and (max(gaps) - min(gaps) > tolerance
                 or any(abs(gap - spec["cardGap"]) > tolerance for gap in gaps)):
        geometry_ok = False
        logs.append("⚠ 第%d页 单词卡水平间距不一致：%s，目标 %dpx"
                    % (page, gaps, spec["cardGap"]))
    return geometry_ok


def _poem_text_fallback(mcp, base, tool, rid):
    """古诗库未收录时的兜底：data.lines 全文逐行叠加楷体大字文本（真元素，非静默降级）。

    返回 (元素 id 或 None, 新 rid)。引导语带位于 y128–224，诗行区 y248–656；
    带作者行共 6 行（行距 64）/ 无作者 5 行（行距 76），垂直居中于该区。
    """
    data = tool.get("data") or {}
    lines = [ln for ln in (data.get("lines") or []) if str(ln).strip()]
    title, author = data.get("title", ""), data.get("author", "")
    if not lines:
        return None, rid
    header = ("%s · %s" % (title, author)) if author else title
    step = 64 if author else 76
    total_h = step * (len(lines) + 1)
    y = 248 + max(0, (408 - total_h) // 2)
    _, o = mcp.tools_call("add_text_element", {
        "text": header, "x": 640, "y": y, "fontSize": 26,
        "fontFamily": "KaiTi", "color": "#8B8578", "bold": False, **base}, rid=rid)
    rid += 1
    eid = McpHttpSession.added_element_id(o)
    for i, ln in enumerate(lines):
        _, o = mcp.tools_call("add_text_element", {
            "text": str(ln), "x": 640, "y": y + step * (i + 1), "fontSize": 40,
            "fontFamily": "KaiTi", "color": "#1F3A5F", "bold": True, **base}, rid=rid)
        rid += 1
        eid = eid or McpHttpSession.added_element_id(o)
    return eid, rid


def _poem_lookup_issue(text):
    """Classify poem-library misses that authored full text can safely replace."""
    value = str(text or "")
    if any(token in value for token in ("未找到", "未收录", "无匹配")):
        return "本地诗词库未收录"
    multiple = re.search(
        r"(?:匹配|命中|找到).{0,40}(?:[2-9]\d*|多|多个)\s*(?:首|条)", value)
    if multiple or ("多首" in value and any(
            token in value for token in ("诗", "词", "匹配", "候选"))):
        return "标题或作者模糊匹配多首"
    return None


# 可解码校验支持的图片扩展名（PIL 不可用时的降级检查依据）。
RASTER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def preflight_images(spec, spec_dir):
    """Validate every foreground and background raster before MCP work.

    优先使用 PIL 做真实解码校验；PIL 缺失时降级为「文件存在 + 扩展名」
    检查并输出一次警告，而不是直接 ImportError 中断整个构建。
    """
    try:
        from PIL import Image
    except ImportError:
        Image = None
        sys.stderr.write("⚠ 未安装 Pillow（requirements.txt）：图片预检降级为"
                         "存在性 + 扩展名检查，未验证可解码性。\n")

    problems = []
    for i, page in enumerate(spec.get("pages", []), 1):
        sources = []
        if page.get("image"):
            sources.append(("image", page["image"]))
        plan = page.get("visualPlan") or {}
        background = plan.get("background") or {}
        if background.get("type") == "image" and background.get("source"):
            sources.append(("visualPlan.background.source", background["source"]))
        for j, element in enumerate(plan.get("elements") or []):
            if not isinstance(element, dict) or element.get("kind") != "image":
                continue
            source = element.get("source")
            if source in {"page.image", "image"}:
                source = page.get("image")
            if source:
                sources.append(("visualPlan.elements[%d].source" % j, source))
        for field, source in sources:
            resolved = source if os.path.isabs(source) else os.path.join(spec_dir, source)
            if not os.path.isfile(resolved):
                problems.append("pages[%d](%s).%s 不存在：%s（解析为 %s）"
                                % (i - 1, page.get("title", ""), field, source, resolved))
                continue
            if Image is None:
                if not str(source).lower().endswith(RASTER_EXTENSIONS):
                    problems.append("pages[%d](%s).%s 不是常见图片扩展名：%s"
                                    % (i - 1, page.get("title", ""), field, source))
                continue
            try:
                with Image.open(resolved) as image:
                    image.verify()
            except Exception as exc:
                problems.append("pages[%d](%s).%s 不是可解码图片：%s"
                                % (i - 1, page.get("title", ""), field, exc))
    return problems


def native_background_pages(spec):
    """Return authored backgrounds that must be applied by MCP."""
    result = []
    for slide_number, page in enumerate(spec.get("pages", []), 1):
        if tool_background_policy(page) == "none":
            continue
        background = ((page.get("visualPlan") or {}).get("background") or {})
        kind = background.get("type")
        if ((kind == "image" and background.get("source")) or
                (kind == "solid" and background.get("color"))):
            result.append((slide_number, background))
    return result


def image_background_pages(spec):
    """Compatibility alias for callers predating native solid backgrounds."""
    return native_background_pages(spec)


def missing_native_background_tools(spec, available_tools):
    if (native_background_pages(spec) and
            "set_slide_background_image" not in available_tools):
        return ["set_slide_background_image"]
    return []


def prepare_native_backgrounds(spec, outdir, deck_name):
    """Create client-readable 16:9 assets without embedding them in ENBX."""
    from enbx_backend import write_cover_image, write_solid_image

    prepared = []
    backgrounds = native_background_pages(spec)
    if not backgrounds:
        return prepared
    asset_dir = os.path.join(outdir, "%s.backgrounds" % deck_name)
    for slide_number, background in backgrounds:
        requested = os.path.join(asset_dir, "page-%03d.png" % slide_number)
        kind = background["type"]
        if kind == "image":
            source = background["source"]
            resolved = (source if os.path.isabs(source)
                        else os.path.join(spec["specDir"], source))
            image_path = write_cover_image(resolved, requested, 1280, 720)
            descriptor = "图片 %s" % source
        else:
            image_path = write_solid_image(background["color"], requested, 1280, 720)
            descriptor = "纯色 %s" % background["color"]
        item = {
            "slideNumber": slide_number,
            "type": kind,
            "description": descriptor,
            "imagePath": image_path,
        }
        if kind == "image":
            item["source"] = background["source"]
        else:
            item["color"] = background["color"]
        prepared.append(item)
    return prepared


def apply_native_backgrounds(mcp, base, prepared, rid_start=600):
    """Apply every native background and require page-info confirmation."""
    applied = []
    rid = rid_start
    for item in prepared:
        slide_number = item["slideNumber"]
        try:
            set_native_slide_background(
                mcp, base, item["imagePath"], slide=slide_number, rid=rid)
        except Exception as exc:
            raise RuntimeError(
                "第%d页原生背景设置失败（%s）：%s" %
                (slide_number,
                 item.get("description") or item.get("source") or item["imagePath"],
                 exc)) from exc
        kind_label = "图片" if item.get("type", "image") == "image" else "纯色"
        applied.append("第%d页 原生背景（%s）" % (slide_number, kind_label))
        rid += 2
    return applied


def _reposition_poem(mcp, base, page, rid, logs):
    """古诗卡叠加后重定位：客户端把 ClassicalWorkElement 默认落 (40,0)
    1240×650 几乎满页，压住引导语带；且 edit_element 对它 x/y 是 **2 倍语义**
    （传 (20,18) → 实际 (40,36)；width/height 不倍乘）。古诗组件需要接近原生
    650px 的高度才能完整显示八行诗，因此使用专属 POEM_ZONE，不压进通用工具槽。"""
    ids = _native_element_ids(mcp, base, page, "poem", rid)
    if not ids:
        logs.append("⚠ 第%d页 古诗卡接口返回成功但元素回读失败" % page)
        return False
    slot = native_tool_spec("poem")["slot"]
    zx, zy, zw, zh = slot["x"], slot["y"], slot["w"], slot["h"]
    mcp.tools_call("edit_element", {"slideNumber": page, "elementIds": ids,
                                    "x": zx // 2, "y": zy // 2,
                                    "width": zw, "height": zh, **base}, rid=rid + 1)
    return True


def _poem_fallback_present(elements, tool):
    """Recognize the explicit text fallback from its complete authored copy."""
    if elements is None:
        return False
    data = tool.get("data") or {}
    required = [str(data.get("title") or "").strip()]
    required.extend(str(line).strip() for line in data.get("lines") or [])
    required = [value for value in required if value]
    payload = json.dumps(elements, ensure_ascii=False)
    return bool(required) and all(value in payload for value in required)


def _expected_native_count(tool):
    if tool.get("type") == "wordcard":
        return len(_wordcard_words(tool))
    if tool.get("type") == "hanzi":
        return len(hanzi_character_rows(tool))
    return 1


def _verify_existing_tool(mcp, base, page, tool, rid, logs, fallback=False):
    """Re-run only deterministic layout/readback for an already present tool."""
    tool_type = tool.get("type")
    if tool_type == "wordcard":
        return _layout_wordcards(mcp, base, page, rid, logs)
    if tool_type == "mindmap":
        _center_mindmap(mcp, base, page, rid, logs)
        return True
    if tool_type == "poem":
        return True if fallback else _reposition_poem(mcp, base, page, rid, logs)
    if tool_type == "hanzi":
        return _layout_hanzi_cards(mcp, base, page, tool, rid, logs)
    if tool_type in {"pinyin", "ruled", "plot", "function"}:
        canonical = "plot" if tool_type == "function" else tool_type
        return _layout_intrinsic_tool(mcp, base, page, canonical, rid, logs)
    return False


def _resume_tool_state(mcp, base, page, tool, rid):
    """Return (state, existing_count), failing closed on ambiguous readback."""
    spec = native_tool_spec(tool.get("type"))
    if not spec:
        return "unknown", 0
    elements = _page_elements(mcp, base, page, rid, spec["elementTypes"])
    if elements is None:
        return "unreadable", 0
    ids = [element.get("id") for element in elements
           if isinstance(element, dict) and element.get("id")]
    expected = _expected_native_count(tool)
    if tool.get("type") == "poem" and not ids:
        all_elements = _page_elements(mcp, base, page, rid + 1)
        if all_elements is None:
            return "unreadable", 0
        if _poem_fallback_present(all_elements, tool):
            return "fallback", 1
    if len(ids) == expected:
        return "complete", len(ids)
    if len(ids) > expected:
        return "excess", len(ids)
    return "partial", len(ids)


def overlay_tools(mcp, base, pages, rid_start=1000, resume=False):
    """逐页叠加学科工具与课堂活动；返回 (failures, added, warnings)。绝不静默降级。"""
    failures, added, warnings = [], [], []
    rid = rid_start
    for idx, page in enumerate(pages, 1):
        tool = page_subject_tool(page)
        activity = page.get("activity") or {}
        if not tool and not activity.get("activityType"):
            continue
        label = "第%d页(%s)" % (idx, page.get("title", ""))
        mcp.tools_call("goto_slide", {"slideNumber": idx, **base}, rid=rid)
        rid += 1
        settle()
        if tool:
            name, args = _tool_call(tool)
            if not name:
                failures.append("%s 未知工具类型 %r" % (label, tool.get("type")))
                continue
            existing_count = 0
            tool_complete = False
            if resume:
                state, existing_count = _resume_tool_state(
                    mcp, base, idx, tool, rid)
                rid += 2
                if state in {"complete", "fallback"}:
                    if _verify_existing_tool(
                            mcp, base, idx, tool, rid, warnings,
                            fallback=state == "fallback"):
                        added.append("%s 工具 %s（续修回读：已存在）" %
                                     (label, tool.get("type")))
                        tool_complete = True
                        rid += 10
                    else:
                        failures.append("%s 工具 %s 已存在但布局复核失败" %
                                        (label, tool.get("type")))
                        continue
                elif state == "excess":
                    failures.append("%s 工具 %s 已有 %d 个原生元素，超过预期 %d 个；"
                                    "为避免重复叠加已停止续修" %
                                    (label, tool.get("type"), existing_count,
                                     _expected_native_count(tool)))
                    continue
                elif state in {"unreadable", "unknown"}:
                    failures.append("%s 工具 %s 无法可靠回读现有元素；"
                                    "为避免重复叠加已停止续修" %
                                    (label, tool.get("type")))
                    continue
                elif state == "partial" and existing_count:
                    failures.append("%s 工具 %s 仅回读到 %d/%d 个原生元素，"
                                    "无法证明缺失项身份；为避免补错内容已停止续修" %
                                    (label, tool.get("type"), existing_count,
                                     _expected_native_count(tool)))
                    continue
            if tool_complete:
                pass
            elif tool.get("type") == "wordcard":
                words = _wordcard_words(tool)
                if not words:
                    failures.append("%s 工具 wordcard 缺少 words/word 数据" % label)
                    continue
                ok, bad = existing_count, 0
                for w in words[existing_count:]:
                    st, o = mcp.tools_call(name, {"word": w, **base}, rid=rid)
                    rid += 1
                    t = McpHttpSession.text_of(o)
                    if McpHttpSession.is_error(o) or any(k in t for k in ERROR_KEYWORDS):
                        failures.append("%s 工具 wordcard 叠加失败（%r）：%s"
                                        % (label, w, t[:120]))
                        bad += 1
                    else:
                        ok += 1
                if ok:
                    if _layout_wordcards(mcp, base, idx, rid, warnings):
                        added.append("%s 工具 wordcard（%d 词：%s）"
                                     % (label, ok, "、".join(words)))
                    else:
                        failures.append("%s 工具 wordcard 已调用但元素未通过回读/布局校验" % label)
                    rid += 6
                if bad:
                    continue
            elif tool.get("type") == "hanzi":
                rows = hanzi_character_rows(tool)
                ok, bad = existing_count, 0
                for row in rows[existing_count:]:
                    st, o = mcp.tools_call(
                        name, {"characters": row, **base}, rid=rid)
                    rid += 1
                    text = McpHttpSession.text_of(o)
                    if McpHttpSession.is_error(o) or any(
                            keyword in text for keyword in ERROR_KEYWORDS):
                        failures.append("%s 工具 hanzi 第%d行叠加失败（%r）：%s" %
                                        (label, ok + bad + 1, row, text[:120]))
                        bad += 1
                    else:
                        ok += 1
                if not bad and ok == len(rows):
                    if _layout_hanzi_cards(mcp, base, idx, tool, rid, warnings):
                        added.append("%s 工具 hanzi（%d 行：%s）" %
                                     (label, len(rows), "+".join(rows)))
                    else:
                        failures.append("%s 工具 hanzi 已调用但未通过回读/布局校验" % label)
                    rid += 20
                if bad:
                    continue
            else:
                st, o = mcp.tools_call(name, {**args, **base}, rid=rid)
                rid += 1
                text = McpHttpSession.text_of(o)
                poem_issue = (_poem_lookup_issue(text)
                              if tool.get("type") == "poem" else None)
                if (McpHttpSession.is_error(o) or poem_issue
                        or any(k in text for k in ERROR_KEYWORDS)):
                    if poem_issue:
                        # 原生检索无法用全文消歧；用 authored lines 显式完整回退。
                        eid, rid = _poem_text_fallback(mcp, base, tool, rid)
                        if eid:
                            added.append("%s 工具 poem（%s，文本兜底，元素 %s）" %
                                         (label, poem_issue, eid))
                            warnings.append("%s %s「%s」：已按 spec 全文叠加，请人工核对" %
                                            (label, poem_issue,
                                             (tool.get("data") or {}).get("title", "")))
                        else:
                            failures.append("%s 工具 poem 叠加失败（%s + 文本兜底也未出元素）：%s"
                                            % (label, poem_issue, text[:120]))
                    else:
                        failures.append("%s 工具 %s 叠加失败：%s" % (label, tool.get("type"), text[:120]))
                else:
                    eid = McpHttpSession.added_element_id(o)
                    added.append("%s 工具 %s%s" % (label, tool.get("type"),
                                                   "（元素 %s）" % eid if eid else ""))
                    if tool.get("type") == "mindmap":
                        _center_mindmap(mcp, base, idx, rid, warnings)
                        rid += 10
                    elif tool.get("type") == "poem":
                        if _reposition_poem(mcp, base, idx, rid, warnings):
                            rid += 4
                        else:
                            added.pop()
                            fallback_id, rid = _poem_text_fallback(mcp, base, tool, rid + 2)
                            if fallback_id:
                                added.append("%s 工具 poem（原生组件未落地，文本兜底，元素 %s）"
                                             % (label, fallback_id))
                                warnings.append("%s 原生古诗组件未落地：已用楷体全文叠加，请人工核对"
                                                % label)
                            else:
                                failures.append("%s 工具 poem 接口成功但无元素，且 spec 未提供 lines 兜底"
                                                % label)
                    elif tool.get("type") in {"pinyin", "ruled", "plot", "function"}:
                        canonical = "plot" if tool.get("type") == "function" else tool.get("type")
                        if not _layout_intrinsic_tool(mcp, base, idx, canonical, rid, warnings):
                            added.pop()
                            failures.append("%s 工具 %s 已调用但元素未通过回读/布局校验"
                                            % (label, canonical))
                        rid += 4
        if activity.get("activityType"):
            atype = activity["activityType"]
            tool_name = {"choice": "add_choice_activity_element",
                         "classify": "add_classify_activity_element",
                         "judge": "add_judge_activity_element",
                         "match": "add_match_activity_element"}.get(atype)
            if not tool_name:
                failures.append("%s 未知活动类型 %r" % (label, atype))
                continue
            if resume:
                elements = _page_elements(mcp, base, idx, rid)
                rid += 1
                if elements is None:
                    failures.append("%s 活动页元素无法可靠回读；为避免重复替换已停止续修" % label)
                    continue
                if elements:
                    added.append("%s 活动 %s（续修回读：已存在）" % (label, atype))
                    _deselect(mcp, base, idx, rid)
                    rid += 1
                    continue
            args = activity_payload_to_mcp_args(atype, activity)
            st, o = mcp.tools_call(tool_name, {**args, **base}, rid=rid)
            rid += 1
            text = McpHttpSession.text_of(o)
            if McpHttpSession.is_error(o) or any(k in text for k in ERROR_KEYWORDS):
                failures.append("%s 活动 %s 叠加失败：%s" % (label, atype, text[:120]))
            else:
                settle()
                integrity_error = _deck_integrity_error(
                    mcp, base, len(pages), rid, "%s 活动 %s 后" % (label, atype))
                rid += 1
                if integrity_error:
                    failures.append(integrity_error)
                    break
                added.append("%s 活动 %s" % (label, atype))
        _deselect(mcp, base, idx, rid)
        rid += 1
    return failures, added, warnings


def _find_swenlauncher():
    """定位 swenlauncher.exe（.enbx 文件关联的打开入口）；从注册表读不到就走默认盘符。"""
    import re
    import subprocess
    try:
        out = subprocess.check_output(
            ["reg", "query", r"HKCR\iseewo.enbx\shell\open\command"],
            stderr=subprocess.DEVNULL).decode("mbcs", "ignore")
        m = re.search(r'([A-Za-z]:\\[^"]*swenlauncher\.exe)', out)
        if m and os.path.exists(m.group(1)):
            return m.group(1)
    except Exception:
        pass
    for cand in (r"D:\Seewo\EasiNote5\swenlauncher\swenlauncher.exe",
                 r"C:\Program Files\Seewo\EasiNote5\swenlauncher\swenlauncher.exe",
                 r"C:\Program Files (x86)\Seewo\EasiNote5\swenlauncher\swenlauncher.exe"):
        if os.path.exists(cand):
            return cand
    raise RuntimeError("找不到课件启动程序，请确认所需应用已安装。")


def _close_same_name_shells(raw, name, retries=10, interval=0.5):
    """Close every exact-name shell and prove they all disappeared before reimport.

    close_current_courseware 已获客户端支持：重导入前把所有精确同名 shell 全部
    关闭并回读确认消失。关闭只结束编辑会话，不删除云端课件；这避免 launcher
    聚焦旧窗口、把工具元素叠到旧文档（古诗卡/课堂活动组件可能不可删）。
    """
    _, output = raw.tools_call(
        "en_find_shells", {"searchingMode": "all", "coursewareName": name}, rid=30)
    shell_ids = McpHttpSession.find_shells_named(output, name)
    if not shell_ids:
        return []
    closed = []
    for offset, shell_id in enumerate(shell_ids):
        status, output = raw.tools_call(
            "close_current_courseware", {"shellId": shell_id},
            rid=31 + offset * 20)
        text = McpHttpSession.text_of(output)
        if status not in (200, 202) or McpHttpSession.is_error(output):
            raise RuntimeError(
                "关闭同名课件「%s」(shell %s) 失败：%s" % (name, shell_id, text[:240]))
        closed.append(shell_id)
    verify_rid = 31 + len(shell_ids) * 20
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(interval)
        _, output = raw.tools_call(
            "en_find_shells", {"searchingMode": "all", "coursewareName": name},
            rid=verify_rid + attempt)
        if not McpHttpSession.find_shells_named(output, name):
            return closed
    raise RuntimeError(
        "已请求关闭 %d 个同名课件「%s」，但 shell 仍然存在：%s" %
        (len(shell_ids), name, ", ".join(shell_ids)))


def _import_enbx(deck_path, name):
    """enbx 导入：swenlauncher 打开本地包 → 轮询 en_find_shells 按名取 shell。

    .enbx 已注册文件关联（iseewo.enbx → swenlauncher），打开即进 Edit；
    首次 sync_current_courseware 会把本地课件上传为云课件（版本 -1 → 1）。
    同名课件已在客户端打开时，launcher 只会聚焦旧窗口、不重读文件。导入前
    自动关闭全部精确同名 shell 并回读确认消失；关闭失败或 shell 残留时停止，
    防止把工具元素叠到旧文档（古诗卡/课堂活动组件可能不可删）。
    """
    import subprocess
    raw = McpHttpSession("http://127.0.0.1:%d/mcp" % find_live_port())
    raw.initialize()
    closed_shells = _close_same_name_shells(raw, name)
    if closed_shells:
        print("✓ 已关闭 %d 个同名旧课件并确认消失：%s" %
              (len(closed_shells), ", ".join(closed_shells)))
    launcher = _find_swenlauncher()
    subprocess.Popen([launcher, os.path.abspath(deck_path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(IMPORT_POLL_INTERVAL * WAIT_SCALE)
        _, o = raw.tools_call("en_find_shells",
                              {"searchingMode": "all", "coursewareName": name})
        sid = McpHttpSession.find_shell_named(o, name)
        if sid:
            return sid
    return None


def _find_unique_open_shell(mcp, name):
    """Resolve one exact-name shell for explicit repair/resume mode."""
    status, output = mcp.tools_call(
        "en_find_shells", {"searchingMode": "all", "coursewareName": name}, rid=30)
    if status not in (200, 202) or McpHttpSession.is_error(output):
        raise RuntimeError("查询续修课件失败：%s" % McpHttpSession.text_of(output)[:240])
    matches = McpHttpSession.find_shells_named(output, name)
    if not matches:
        raise RuntimeError("未找到已打开的同名课件「%s」" % name)
    if len(matches) > 1:
        raise RuntimeError("客户端存在 %d 个同名课件「%s」，无法唯一确定续修目标" %
                           (len(matches), name))
    return matches[0]


def _argument_parser():
    ap = argparse.ArgumentParser(description="页面计划 → ENBX 原生直出 → 希沃课件（v2 主流程）")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--outdir", default=None, help="ENBX 输出目录（默认 spec 同目录）")
    ap.add_argument("--port", type=int, default=0, help="MCP 端口；缺省 live 探测")
    ap.add_argument("--url", default=None)
    ap.add_argument("--dry-run", action="store_true", help="渲染后不连 MCP")
    ap.add_argument("--validate-only", action="store_true", help="只做计划级校验")
    ap.add_argument("--resume", action="store_true",
                    help="续修唯一同名的已打开课件，不重新生成或导入 ENBX")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--slow-mode", action="store_true",
                    help="慢机器模式：所有等待时长 ×2（settle/导入稳定/轮询超时）")
    ap.add_argument("--require-images", action="store_true",
                    help="严格配图门禁（默认行为；保留该参数便于显式声明）")
    return ap


def main():
    parser = _argument_parser()
    args = parser.parse_args()
    if args.slow_mode:
        global WAIT_SCALE
        WAIT_SCALE = 2.0
        print("✓ 慢机器模式：等待时长 ×2")
    if args.resume and (args.dry_run or args.validate_only):
        parser.error("--resume 不能与 --dry-run 或 --validate-only 同时使用")

    mcp = None
    global _RUN_STARTED
    _RUN_STARTED = time.time()
    if not args.dry_run and not args.validate_only:
        try:
            mcp, url = _connect_mcp(args.port, args.url)
        except Exception as exc:
            fail(6,
                 "希沃进程或 MCP 尚未就绪，未读取 spec、未生成 ENBX。详情：%s" % exc,
                 "先运行 scripts/lifecycle/ensure_connected.py 并完成信任后重试")
        print("✓ MCP 前置检查通过（%s）" % url)

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    spec_dir = os.path.dirname(os.path.abspath(args.spec))
    spec["specDir"] = spec_dir
    if not is_authored_visual(spec):
        fail(7, "新建课件必须由 AI 提供根级 visualPlanning 视觉计划；"
                "项目不再包含旧主题、固定布局或候选构图回退。",
             "在 spec 根级补齐 visualPlanning 后重跑")
    title, title_note = _derive_deck_title(spec)
    if title_note:
        print("⚠ %s" % title_note)
    if mcp is not None:
        mcp.courseware_name = title
    mode = ("续修" if args.resume else
            "仅校验" if args.validate_only else
            "试运行" if args.dry_run else "新建")
    print("构建开始：%s（%d 页，模式：%s，图片方案：%s）" %
          (title, len(spec.get("pages") or []),
           mode, spec.get("imageStrategy") or "generated"))

    # [1] 计划级校验
    st = stage_start(1, "计划级校验")
    errors, warnings = validate_deck(spec)
    for w in warnings:
        print("⚠ %s" % w)
    if errors:
        for e in errors:
            sys.stderr.write("✗ %s\n" % e)
        fail(7, "页面计划未通过校验，已停止。",
             "按上方报错逐条修正 spec 后重跑；可先加 --validate-only 只校验不落稿")
    print("✓ 页面计划校验通过（%d 页，%d 条告警）" % (len(spec.get("pages", [])), len(warnings)))
    stage_end(st)

    # [2] 配图预检：正式流程始终严格，缺失或损坏图片直接阻断。
    st = stage_start(2, "配图预检")
    problems = preflight_images(spec, spec_dir)
    for problem in problems:
        sys.stderr.write("✗ " + problem + "\n")
    if problems:
        fail(8, "配图预检未通过，已停止。",
             "补齐缺失图片或替换损坏图片后重跑；若确实无法出图，"
             "可改用无图方案（imageStrategy=none，见 visual_planning.md）")
    stage_end(st)

    missing_background_tools = (missing_native_background_tools(
        spec, mcp.available_tools) if mcp is not None else [])
    if missing_background_tools:
        fail(6, "当前 MCP 缺少 %s，未继续构建或续修；页面背景不允许回退为普通元素。"
             % ", ".join(missing_background_tools),
             "确认希沃客户端为支持原生背景的版本并重启后重试")

    if args.validate_only:
        print_stage_summary()
        return

    # Renderer outputs may live outside the spec directory. Keep relative image
    # paths anchored to the page plan, not to --outdir.
    spec["specDir"] = spec_dir

    print("✓ 落稿格式：enbx（原生直出，不生成或导入 PPTX）")

    # [3] 原生渲染 ENBX
    st = stage_start(3, "原生渲染 ENBX")
    outdir = args.outdir or spec_dir
    os.makedirs(outdir, exist_ok=True)
    safe = "".join(c if c not in '\\/:*?"<>|' else "_" for c in title)
    if mcp is not None:
        mcp.courseware_name = safe
    deck_path = os.path.join(outdir, "%s.enbx" % safe)
    native_backgrounds = prepare_native_backgrounds(spec, outdir, safe)
    if args.resume:
        print("✓ 续修模式：保留已打开课件，不重新合成或导入 ENBX")
    else:
        from enbx_renderer import render_deck_enbx
        render_deck_enbx(spec, deck_path)
        print("✓ enbx 已合成：%s" % deck_path)
    stage_end(st)

    if args.dry_run:
        plan = [(index, page.get("layout"),
                 (page_subject_tool(page) or {}).get("type"),
                 (page.get("activity") or {}).get("activityType"))
                for index, page in enumerate(spec.get("pages", []), 1)]
        print("(dry-run) 叠加计划：")
        for index, layout, tool, activity in plan:
            extras = []
            if any(item["slideNumber"] == index for item in native_backgrounds):
                extras.append("MCP 原生背景")
            if tool or activity:
                extras.append("MCP 叠加 %s" % (tool or activity))
            extra = "  ← " + "；".join(extras) if extras else ""
            print("  第%d页 %s%s" % (index, layout, extra))
        print_stage_summary()
        return

    # [4] 打开刚生成的 ENBX
    st = stage_start(4, "导入并绑定课件")
    print("✓ MCP 会话已建立（%s）" % url)

    try:
        sid = (_find_unique_open_shell(mcp, safe) if args.resume
               else _import_enbx(deck_path, safe))
    except RuntimeError as exc:
        stage = "续修目标定位" if args.resume else "ENBX 导入前置处理"
        fail(11, "%s失败：%s" % (stage, exc),
             "确认客户端可正常关闭同名课件后重跑；反复失败时先关闭希沃，"
             "运行 ensure_connected.py 重连后再试")
    if not sid:
        fail(9, "ENBX 打开失败",
             "重跑一次；仍失败时先关闭希沃客户端并运行 ensure_connected.py 重连")
    print("✓ %s，shell=%s" % ("已绑定续修课件" if args.resume else "已导入", sid))
    mcp.shell_id = sid
    base = {"shellId": sid}
    # Native subject tools operate on the globally bound editing shell even
    # when shellId is present. Bind explicitly so other open tabs cannot
    # redirect overlays to a stale current page.
    mcp.tools_call("en_bind_shell", base, rid=19)
    settle(IMPORT_STABILIZE_SECONDS)  # 等待导入完成并稳定客户端状态。
    ensure_edit_mode(mcp, base, rid=20)

    expected_pages = len(spec.get("pages", []))
    integrity_error = _deck_integrity_error(
        mcp, base, expected_pages, rid=900,
        stage="续修绑定后" if args.resume else "导入后")
    if integrity_error:
        fail(12, integrity_error,
             "页数不一致多为导入尚未完成或课件被手动改动；"
             "稍候重跑一次，仍失败时关闭同名课件后重建")
    stage_end(st)

    # [5] MCP 原生页面背景。失败时不叠加组件、不云同步，也不回退为普通元素。
    st = stage_start(5, "MCP 原生页面背景")
    try:
        applied_backgrounds = apply_native_backgrounds(mcp, base, native_backgrounds)
    except RuntimeError as exc:
        fail(13, "%s\n已在交互叠加和云同步前中止。" % exc,
             "重跑会先自动关闭同名旧课件并重新导入全新课件；"
             "若背景已部分设置，可检查客户端页面后重试")
    for message in applied_backgrounds:
        print("✓ %s" % message)

    background_integrity_error = _deck_integrity_error(
        mcp, base, expected_pages, rid=950, stage="原生背景设置后")
    if background_integrity_error:
        fail(13, "%s\n已在交互叠加和云同步前中止。" % background_integrity_error,
             "重跑会先自动关闭同名旧课件并重新导入全新课件")
    stage_end(st)

    # [6] MCP 叠加交互层
    st = stage_start(6, "MCP 叠加交互层")
    failures, added, overlay_warnings = overlay_tools(
        mcp, base, spec.get("pages", []), resume=args.resume)
    for a in added:
        print("✓ %s" % a)
    for w in overlay_warnings:
        print(w)

    final_integrity_error = _deck_integrity_error(
        mcp, base, expected_pages, rid=4900, stage="交互叠加后")
    if final_integrity_error:
        failures.append(final_integrity_error)
    stage_end(st)

    if failures:
        for fmsg in failures:
            sys.stderr.write("✗ %s\n" % fmsg)
        fail(10, "已在云同步前中止。",
             "修正 spec 后对当前课件使用 --resume 续修，避免重复叠加已成功的元素")

    # [7] 云同步 + Edit 终态
    st = stage_start(7, "云同步与终态")
    if not args.no_sync:
        sync_with_edit_gate(mcp, base, sid, rid=5000)
        print("✓ 云同步完成")
    ensure_edit_mode(mcp, base, rid=5100)
    stage_end(st)

    print("\n✓ 落稿完成：%s（%d 页，%d 个交互元素）" % (title, len(spec.get("pages", [])), len(added)))
    print_stage_summary()
    print("后续微调：对同一 spec 重跑可全量重建；对已打开课件局部返修用 --resume 续修。")


if __name__ == "__main__":
    main()
