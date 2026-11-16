#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
courseware_ops.py — 希沃白板课件「调整/丰富」的高层操作集（复用 mcp_client.py）。

把希沃白板 MCP 中与「创建后调整课件」最常用的一批能力封装成
带子命令的命令行工具，供 agent 在已连接 MCP 后反复调用，避免每次现写 JSON-RPC。

使用前请先确保：
    1) 已按生命周期流程连接 MCP（脚本/lifecycle/*）；
    2) 已打开一份由 build_v2.py 创建或从云端打开的课件。
    脚本会自动通过 en_find_shells 取当前课件 Shell；若无打开的课件会给出提示。

用法示例：
    python courseware_ops.py --port 7916 info
    python courseware_ops.py --port 7916 add-text --text "Hello" --x 400 --y 300 --fontSize 36
    python courseware_ops.py --port 7916 add-image --source "C:/img/a.png" --width 600
    python courseware_ops.py --port 7916 add-table --markdown "| 姓名 | 分数 |"
    python courseware_ops.py --port 7916 add-mindmap --markdown "- 主题\n  - 分支1"
    python courseware_ops.py --port 7916 add-poem --title "静夜思" --author "李白"
    python courseware_ops.py --port 7916 add-wordcard --word "apple"
    python courseware_ops.py --port 7916 add-hanzi --characters "山水"
    python courseware_ops.py --port 7916 add-pinyin --pinyin "hàn zì"
    python courseware_ops.py --port 7916 add-ruled --content "Aa Bb"
    python courseware_ops.py --port 7916 add-plot --expression "x^2-2*x+1"
    python courseware_ops.py --port 7916 add-activity --type choice --json '[...]'
    python courseware_ops.py --port 7916 add-slide
    python courseware_ops.py --port 7916 edit-text --contains "明月" --fontSize 40 --color "#C00000"
    python courseware_ops.py --port 7916 goto --slide 2
    python courseware_ops.py --port 7916 gen-scripts
    python courseware_ops.py --port 7916 search --keyword "题西林壁" --max 10
    python courseware_ops.py --port 7916 open --name "题西林壁"
    python courseware_ops.py --port 7916 set-bg --source "C:/bg/cover.png"        # 设置原生页面背景
    python courseware_ops.py --port 7916 render-slideml --slide-id "SLIDE_ID" --xml-file "shape.xml"  # SlideML 画形状
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp"))

# Windows 默认控制台是 GBK，✓/✗ 等字符会触发 UnicodeEncodeError；统一改用 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
from mcp_client import McpHttpSession, parse_page_number
from courseware_runtime import (activity_payload_to_mcp_args, is_url,
                               normalize_mindmap_markdown, resolve_asset_path)


def resolve_shell(mcp):
    _, o = mcp.tools_call("en_find_shells", {"searchingMode": "all"}, rid=10)
    sid = McpHttpSession.find_shell(o)
    if not sid:
        sys.stderr.write("未找到已打开的课件 Shell。请先用 build_v2.py 创建"
                         "或从云端打开一份课件。\n")
        sys.exit(4)
    return sid


def call(mcp, name, args, rid=20):
    st, o = mcp.tools_call(name, args, rid=rid)
    txt = McpHttpSession.text_of(o)
    print("→ %s (HTTP %d):" % (name, st))
    print(txt if txt else "(无文本返回)")
    if McpHttpSession.is_error(o):
        sys.stderr.write("  ⚠ 该操作可能未成功，请检查返回。\n")
    return o


def set_native_slide_background(mcp, base, source, slide=None, rid=20):
    """Set and verify a native slide background; never fall back to an element."""
    arguments = {"imagePath": source, **base}
    if slide is not None:
        arguments["slideNumber"] = slide
    status, output = mcp.tools_call(
        "set_slide_background_image", arguments, rid=rid)
    output_text = McpHttpSession.text_of(output)
    failed = status not in (200, 202) or McpHttpSession.is_error(output)
    failed = failed or any(word in output_text.lower() for word in (
        "失败", "不存在", "无法", "无效", "error", "not found"))
    if failed:
        raise RuntimeError("设置页面背景失败：%s" % output_text[:240])

    info_args = dict(base)
    if slide is not None:
        info_args["slideNumber"] = slide
    info_status, info = mcp.tools_call("get_slide_info", info_args, rid=rid + 1)
    info_text = McpHttpSession.text_of(info)
    if info_status not in (200, 202) or McpHttpSession.is_error(info):
        raise RuntimeError("页面背景回读失败：%s" % info_text[:240])
    if "背景图片" not in info_text:
        raise RuntimeError("页面背景未落地：get_slide_info 未返回背景图片")
    return output, info


def current_slide_number(mcp, base, rid=30):
    _, output = mcp.tools_call("get_slide_info", base, rid=rid)
    return parse_page_number(McpHttpSession.text_of(output))


def goto_verified(mcp, base, target, rid=30):
    """绝对导航后立即回读；静默失败时用相对导航补救。"""
    mcp.tools_call("goto_slide", {"slideNumber": target, **base}, rid=rid)
    current = current_slide_number(mcp, base, rid + 1)
    if current is not None and current < target:
        for step in range(target - current):
            mcp.tools_call("goto_next_slide", base, rid=rid + 2 + step)
        current = current_slide_number(mcp, base, rid + 50)
    if current != target:
        raise RuntimeError("导航校验失败：当前页 %s，目标页 %s" % (current, target))
    return current


def main():
    ap = argparse.ArgumentParser(description="希沃白板课件调整操作集")
    ap.add_argument("--port", type=int, default=7916)
    ap.add_argument("--url", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p):
        p.add_argument("--slide", type=int, default=None, help="指定页号（默认当前页）")

    p = sub.add_parser("info"); add_common(p)
    p = sub.add_parser("add-slide"); add_common(p)
    p = sub.add_parser("add-text"); add_common(p)
    p.add_argument("--text", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p.add_argument("--fontSize", type=float); p.add_argument("--fontFamily"); p.add_argument("--color")
    p.add_argument("--bold", action="store_true"); p.add_argument("--italic", action="store_true")
    p = sub.add_parser("add-image"); add_common(p)
    p.add_argument("--source", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p.add_argument("--width", type=float); p.add_argument("--height", type=float)
    p = sub.add_parser("add-table"); add_common(p)
    p.add_argument("--markdown", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p.add_argument("--width", type=float); p.add_argument("--height", type=float)
    p = sub.add_parser("add-mindmap"); add_common(p)
    p.add_argument("--markdown", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p.add_argument("--width", type=float); p.add_argument("--height", type=float)
    p = sub.add_parser("add-poem"); add_common(p)
    p.add_argument("--title", required=True); p.add_argument("--author")
    p = sub.add_parser("add-wordcard"); add_common(p)
    p.add_argument("--word", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p = sub.add_parser("add-hanzi"); add_common(p)
    p.add_argument("--characters", required=True, help="汉字（本地 3500 字库范围内，可多个）")
    p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p = sub.add_parser("add-pinyin"); add_common(p)
    p.add_argument("--pinyin", required=True, help="带声调拼音，如 hàn zì")
    p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p = sub.add_parser("add-ruled"); add_common(p)
    p.add_argument("--content", required=True, help="四线三格内容（英文字母/单词）")
    p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p = sub.add_parser("add-plot"); add_common(p)
    p.add_argument("--expression", required=True); p.add_argument("--x", type=float); p.add_argument("--y", type=float)
    p = sub.add_parser("add-activity"); add_common(p)
    p.add_argument("--type", required=True, choices=["choice", "classify", "judge", "match"])
    p.add_argument("--json", required=True, help="活动参数 JSON 数组/对象字符串")
    p = sub.add_parser("edit-text"); add_common(p)
    p.add_argument("--contains", help="按文案模糊匹配要改的文本元素"); p.add_argument("--elementIds", help="逗号分隔的 elementId")
    p.add_argument("--fontSize", type=float); p.add_argument("--fontFamily"); p.add_argument("--color")
    p.add_argument("--bold", action="store_true"); p.add_argument("--italic", action="store_true")
    p.add_argument("--underline", action="store_true"); p.add_argument("--lineSpacing", type=float)
    p = sub.add_parser("goto"); p.add_argument("--slide", type=int, required=True)
    p = sub.add_parser("gen-scripts")
    p = sub.add_parser("sync"); p.add_argument("--wait", action="store_true")
    p = sub.add_parser("undo")
    p = sub.add_parser("redo")
    p = sub.add_parser("search"); p.add_argument("--keyword", required=True); p.add_argument("--max", type=int, default=10)
    p = sub.add_parser("open"); p.add_argument("--name", required=True)
    p = sub.add_parser("set-bg"); add_common(p)
    p.add_argument("--source", required=True, help="希沃客户端本机图片路径")
    p = sub.add_parser("render-slideml")
    p.add_argument("--slide-id", required=True, help="目标页 slideId（由 add_slide / get_slide_info 获取）")
    p.add_argument("--xml", help="SlideML XML 字符串")
    p.add_argument("--xml-file", help="SlideML XML 文件路径")

    args = ap.parse_args()

    # 图片路径快速失败：相对路径基于 CWD 转绝对路径，本地文件必须存在。
    # 希沃进程读不到相对路径会静默丢图（元素不创建也不报错），先在这里拦住。
    if args.cmd in ("add-image", "set-bg"):
        args.source = resolve_asset_path(args.source)
        if args.cmd == "set-bg" and is_url(args.source):
            sys.stderr.write("✗ 原生页面背景只接受希沃客户端本机图片路径。\n")
            sys.exit(3)
        if not is_url(args.source) and not os.path.isfile(args.source):
            sys.stderr.write("✗ 图片文件不存在：%s\n" % args.source)
            sys.exit(3)

    url = args.url or "http://127.0.0.1:%d/mcp" % args.port
    mcp = McpHttpSession(url)
    mcp.initialize()

    # search / open 不依赖已打开的课件，单独处理
    if args.cmd == "search":
        st, o = mcp.tools_call("search_cloud_courseware",
                               {"keyword": args.keyword, "maxResults": args.max}, rid=25)
        print("→ search_cloud_courseware (HTTP %d):" % st)
        print(McpHttpSession.text_of(o) or "(无文本返回)")
        return
    if args.cmd == "open":
        st, o = mcp.tools_call("open_cloud_courseware", {"coursewareName": args.name}, rid=26)
        print("→ open_cloud_courseware (HTTP %d):" % st)
        print(McpHttpSession.text_of(o) or "(无文本返回)")
        if McpHttpSession.is_error(o):
            sys.stderr.write("  ⚠ 打开可能失败，请检查返回。\n")
            sys.exit(5)
        return

    sid = resolve_shell(mcp)
    base = {"shellId": sid}
    requested_slide = getattr(args, "slide", None)
    if requested_slide is not None and args.cmd != "goto":
        goto_verified(mcp, base, requested_slide)

    if args.cmd == "info":
        call(mcp, "get_current_courseware_info", base, rid=21)
        call(mcp, "get_slide_info", base, rid=22)
    elif args.cmd == "add-slide":
        call(mcp, "add_slide", base, rid=21)
    elif args.cmd == "add-text":
        a = {"text": args.text, **base}
        for k in ("x", "y", "fontSize", "fontFamily", "color"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        a["bold"] = args.bold; a["italic"] = args.italic
        call(mcp, "add_text_element", a, rid=21)
    elif args.cmd == "add-image":
        source = resolve_asset_path(args.source)  # 相对路径基于 CWD；希沃进程读不到相对路径
        if not is_url(source) and not os.path.isfile(source):
            sys.stderr.write("✗ 图片文件不存在：%s（解析为 %s）\n" % (args.source, source))
            sys.exit(3)
        a = {"source": source, **base}
        for k in ("x", "y", "width", "height"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_image_element", a, rid=21)
    elif args.cmd == "add-table":
        a = {"markdownTable": args.markdown, **base}
        for k in ("x", "y", "width", "height"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_table_element", a, rid=21)
    elif args.cmd == "add-mindmap":
        # 思维导图以 (x,y) 为中心对称生长（width/height 被忽略），缺省给画布中心
        a = {"markdownList": normalize_mindmap_markdown(args.markdown), **base}
        a["x"] = args.x if args.x is not None else 640
        a["y"] = args.y if args.y is not None else 420
        call(mcp, "add_mind_map_element", a, rid=21)
    elif args.cmd == "add-poem":
        a = {"title": args.title, **base}
        if args.author: a["author"] = args.author
        call(mcp, "add_classical_poem_element", a, rid=21)
    elif args.cmd == "add-wordcard":
        a = {"word": args.word, **base}
        for k in ("x", "y"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_english_word_card_element", a, rid=21)
    elif args.cmd == "add-hanzi":
        a = {"characters": args.characters, **base}
        for k in ("x", "y"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_hanzi_card_element", a, rid=21)
    elif args.cmd == "add-pinyin":
        a = {"pinyin": args.pinyin, **base}
        for k in ("x", "y"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_pinyin_card_element", a, rid=21)
    elif args.cmd == "add-ruled":
        a = {"content": args.content, **base}
        for k in ("x", "y"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_ruled_paper_element", a, rid=21)
    elif args.cmd == "add-plot":
        a = {"expression": args.expression, **base}
        for k in ("x", "y"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        call(mcp, "add_function_plot_element", a, rid=21)
    elif args.cmd == "add-activity":
        payload = json.loads(args.json)
        tool = {
            "choice": "add_choice_activity_element",
            "classify": "add_classify_activity_element",
            "judge": "add_judge_activity_element",
            "match": "add_match_activity_element",
        }[args.type]
        a = {"shellId": sid}
        a.update(activity_payload_to_mcp_args(args.type, payload))
        call(mcp, tool, a, rid=21)
    elif args.cmd == "edit-text":
        a = {"shellId": sid}
        if args.contains: a["containsTextRegex"] = args.contains
        ids = args.elementIds
        if ids: a["elementIds"] = [x.strip() for x in ids.split(",")]
        for k in ("fontSize", "fontFamily", "color", "lineSpacing"):
            v = getattr(args, k, None)
            if v is not None: a[k] = v
        a["bold"] = args.bold; a["italic"] = args.italic; a["underline"] = args.underline
        call(mcp, "edit_text_element", a, rid=21)
    elif args.cmd == "goto":
        goto_verified(mcp, base, args.slide, rid=21)
        print("→ 已导航并校验当前页：%d" % args.slide)
    elif args.cmd == "gen-scripts":
        call(mcp, "generate_scripts_from_current_courseware", base, rid=21)
    elif args.cmd == "sync":
        a = {"shellId": sid}
        if args.wait: a["waitUntilSynced"] = True
        call(mcp, "sync_current_courseware", a, rid=21)
    elif args.cmd == "undo":
        call(mcp, "en_undo", base, rid=21)
    elif args.cmd == "redo":
        call(mcp, "en_redo", base, rid=21)
    elif args.cmd == "set-bg":
        output, info = set_native_slide_background(
            mcp, base, args.source, slide=args.slide, rid=21)
        print("→ set_slide_background_image (HTTP 200/202):")
        print(McpHttpSession.text_of(output) or "(无文本返回)")
        print("✓ 原生页面背景已回读：%s" %
              (McpHttpSession.text_of(info) or "")[:160])
    elif args.cmd == "render-slideml":
        # 用 SlideML 渲染矢量形状/复杂版式（MCP 无通用形状工具时的形状方案）
        xml = args.xml
        if not xml and args.xml_file:
            with open(args.xml_file, encoding="utf-8") as f:
                xml = f.read()
        if not xml:
            sys.stderr.write("需提供 --xml 或 --xml-file\n")
            sys.exit(3)
        call(mcp, "RenderSlideML",
             {"slideId": args.slide_id, "slideXml": xml, "shellId": sid}, rid=21)


if __name__ == "__main__":
    main()
