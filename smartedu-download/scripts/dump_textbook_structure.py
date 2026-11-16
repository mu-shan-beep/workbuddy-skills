#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国家中小学智慧教育平台 - 教材资源结构 DUMP 工具（只 dump，不下载）

适用对象：teachingmaterials 类教材（如「道德与法治二年级上册」08c775e6...）。
          注意：national_lesson 类清单接口公开可直连，但 teachingmaterials 类
          资源接口必须带浏览器会话态（裸 API 一律 403），所以本工具用已登录
          浏览器会话捕获应用自身的 200 响应，再解析出结构。

两种模式：
  --capture  启动已登录浏览器，监听 teachingmaterials/**/resources/** 响应，
             保存原始 JSON 到 captures/ 目录。用户手动点完 16 课（或 --auto 自动点）
             后按 Enter 结束。不下载任何文件。
  --parse    读取 captures/*.json，递归提取每课的 5 类资源（微课/课件/教学设计/
             任务单/练习）及其直链，输出 structure_report.json + structure_report.md。
             纯本地解析，无需联网、无需浏览器。

用法：
  # 1) 捕获（需已登录会话；默认扫码登录，或用 --user-data-dir 复用本机 Edge 会话）
  python dump_textbook_structure.py --capture \
      --teachingmaterial-id 08c775e6-83eb-7f05-ef45-3a8d03a0ceda \
      --url "https://basic.smartedu.cn/syncClassroom/teachingmaterial?teachingmaterialId=08c775e6-83eb-7f05-ef45-3a8d03a0ceda" \
      --user-data-dir "C:/Users/User/AppData/Local/Microsoft/Edge/User Data"

  # 2) 解析（任何时候都能跑，离线）
  python dump_textbook_structure.py --parse --out ./structure_report
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

SKILL_BASE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.path.join(SKILL_BASE, "..")  # 技能根
CAPTURES_DIR = os.path.join(WORKDIR, "captures")
REPORT_JSON = os.path.join(WORKDIR, "structure_report.json")
REPORT_MD = os.path.join(WORKDIR, "structure_report.md")

# resource_type_code -> (中文名, 目标格式, 目录)
RTYPE_MAP = {
    "micro_lesson_video": ("微课视频", "mp4", "视频课程"),
    "coursewares": ("课件", "pptx", "课件"),
    "lesson_plandesign": ("教学设计", "docx", "教学设计"),
    "learning_task": ("学习任务单", "docx", "学习任务单"),
    "after_class_exercise": ("作业练习", "docx", "课后练习"),
}
KNOWN_RTYPES = set(RTYPE_MAP.keys())

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)


# ---------------------------------------------------------------------------
# 解析：从捕获的 JSON 中递归提取资源结构
# ---------------------------------------------------------------------------
def _make_entry(obj):
    """从单个资源条目对象构造扁平资源记录。"""
    rtc = obj.get("resource_type_code") or obj.get("resourceTypeCode")
    title = (obj.get("global_title") or {}).get("zh-CN") or obj.get("title") or ""
    storages, m3u8s = [], []
    for ti in (obj.get("ti_items") or []):
        for s in (ti.get("ti_storages") or []):
            if s:
                storages.append(s)
                if ".m3u8" in s:
                    m3u8s.append(s)
    for s in (obj.get("ti_storages") or []):
        if s:
            storages.append(s)
            if ".m3u8" in s:
                m3u8s.append(s)
    return {
        "resource_type_code": rtc,
        "name": RTYPE_MAP.get(rtc, (rtc, "", ""))[0],
        "title": title,
        "format": RTYPE_MAP.get(rtc, ("", "", ""))[1] or ("m3u8" if m3u8s else "pdf"),
        "storages": storages,
        "m3u8": m3u8s,
    }


def _is_resource_entry(obj):
    rtc = obj.get("resource_type_code") or obj.get("resourceTypeCode")
    return bool(rtc and (obj.get("ti_items") is not None or obj.get("ti_storages") is not None))


def _is_lesson_node(obj):
    nid = obj.get("id")
    ntitle = obj.get("title") or (obj.get("global_title") or {}).get("zh-CN")
    return bool(nid and ntitle and isinstance(ntitle, str))


def _add_entry(lesson_info, entry):
    key = (entry["title"], entry["resource_type_code"])
    if key not in lesson_info["_seen"]:
        lesson_info["_seen"].add(key)
        lesson_info["resources"].append(entry)


def _walk(obj, current_lesson, lessons):
    """
    单趟遍历：遇到资源条目则归属到「最近的叶子课时节点」；
    遇到课时节点（id+title）则更新当前课时上下文（叶子节点=无 child_nodes）。
    不回传自身，杜绝无限递归。
    """
    if isinstance(obj, dict):
        if _is_resource_entry(obj):
            entry = _make_entry(obj)
            if current_lesson:
                lid = current_lesson[0]
                lessons.setdefault(lid, {"id": lid, "title": current_lesson[1],
                                        "resources": [], "_seen": set()})
                _add_entry(lessons[lid], entry)
            else:
                lessons.setdefault("__UNCATEGORIZED__", {"id": "__UNCATEGORIZED__",
                                                         "title": "未归类资源", "resources": [], "_seen": set()})
                _add_entry(lessons["__UNCATEGORIZED__"], entry)
            return
        if _is_lesson_node(obj):
            # 叶子课时（无 child_nodes）成为新的归属上下文；单元（有 child_nodes）不改变上下文
            new_lesson = (obj["id"], (obj.get("title") or (obj.get("global_title") or {}).get("zh-CN")))
            if obj.get("child_nodes") is None:
                current_lesson = new_lesson
            for k, v in obj.items():
                _walk(v, current_lesson, lessons)
            return
        for k, v in obj.items():
            _walk(v, current_lesson, lessons)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, current_lesson, lessons)


def collect_resources(obj):
    """从单个接口响应提取 (resources_flat, lessons_dict)。"""
    lessons = {}
    _walk(obj, None, lessons)
    # 去掉内部去重辅助字段
    for info in lessons.values():
        info.pop("_seen", None)
    # 汇总扁平资源列表
    flat = []
    for info in lessons.values():
        for r in info["resources"]:
            if r not in flat:
                flat.append(r)
    return flat, lessons


def parse_captures(captures_dir):
    """读取 captures 下所有 json，汇总资源与课时。"""
    cap_dir = Path(captures_dir)
    if not cap_dir.exists():
        print(f"[parse] 捕获目录不存在：{captures_dir}")
        return None
    files = sorted(cap_dir.glob("*.json"))
    if not files:
        print(f"[parse] 捕获目录为空：{captures_dir}")
        return None

    all_resources = []
    all_lessons = {}
    for f in files:
        try:
            obj = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[parse] 跳过无法解析的文件 {f.name}: {e}")
            continue
        res, lessons = collect_resources(obj)
        all_resources.extend(res)
        for lid, linfo in lessons.items():
            if lid == "__UNCATEGORIZED__":
                # 未归类：并入总资源表，不单独建课时
                continue
            cur = all_lessons.get(lid)
            if cur is None:
                all_lessons[lid] = linfo
            else:
                seen = {(r["title"], r["resource_type_code"]) for r in cur["resources"]}
                for r in linfo["resources"]:
                    if (r["title"], r["resource_type_code"]) not in seen:
                        cur["resources"].append(r)
                        seen.add((r["title"], r["resource_type_code"]))
        print(f"[parse] {f.name}: 提取资源 {len(res)} 项，课时 {len(lessons)} 个")
    # 把未归类资源并入（若有）
    return {"resources": all_resources, "lessons": all_lessons}


def build_report(parsed):
    lessons = parsed["lessons"]
    lines = []
    lines.append("# 教材资源结构报告（teachingmaterials 类）\n")
    lines.append(f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"> 课时节点数（含资源的）：{len(lessons)}\n")

    # 资源类型统计
    type_count = {}
    for l in lessons.values():
        for r in l["resources"]:
            type_count[r["resource_type_code"]] = type_count.get(r["resource_type_code"], 0) + 1
    lines.append("## 资源类型概览\n")
    lines.append("| 类型 code | 中文名 | 出现课时数 |")
    lines.append("|---|---|---|")
    for code, (cn, _, _) in RTYPE_MAP.items():
        lines.append(f"| {code} | {cn} | {type_count.get(code, 0)} |")
    lines.append("")

    lines.append("## 逐课资源清单\n")
    for idx, (lid, l) in enumerate(sorted(lessons.items(), key=lambda x: x[1]["title"]), 1):
        lines.append(f"### {idx}. {l['title']}  `{lid}`\n")
        if not l["resources"]:
            lines.append("_（该节点下未捕获到资源条目，可能尚未点开）_\n")
            continue
        lines.append("| 类型 | 名称 | 格式 | 直链数 | 链接预览 |")
        lines.append("|---|---|---|---|---|")
        for r in l["resources"]:
            n = len(r["storages"])
            preview = r["storages"][0][:70] + ("…" if len(r["storages"][0]) > 70 else "") if r["storages"] else "—"
            lines.append(f"| {r['resource_type_code']} | {r['title'] or r['name']} | {r['format']} | {n} | {preview} |")
        lines.append("")
    return "\n".join(lines)


def cmd_parse(args):
    parsed = parse_captures(args.captures or CAPTURES_DIR)
    if not parsed:
        return 2
    # 写 JSON
    out_json = args.out or REPORT_JSON
    out_md = (args.out or REPORT_MD)
    if out_json.endswith(".md"):
        out_md = out_json
        out_json = out_json[:-3] + ".json"
    else:
        out_md = out_json[:-5] + ".md" if out_json.endswith(".json") else out_json + ".md"
    Path(out_json).write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    md = build_report(parsed)
    Path(out_md).write_text(md, encoding="utf-8")
    print(f"\n[parse] 共提取资源条目 {len(parsed['resources'])} 条，课时 {len(parsed['lessons'])} 个")
    print(f"[parse] JSON -> {out_json}")
    print(f"[parse] MD   -> {out_md}")
    return 0


# ---------------------------------------------------------------------------
# 捕获：用已登录浏览器监听 responses
# ---------------------------------------------------------------------------
def try_import_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("[capture] 未安装 Playwright。请先执行：")
        print("  pip install playwright && playwright install chromium")
        sys.exit(2)


def is_logged_in(page):
    try:
        dump = page.evaluate("() => JSON.stringify(localStorage)")
        if dump and "access_token" in dump:
            return True
    except Exception:
        pass
    return False


def wait_qr_login(page, timeout=300):
    print("[capture] 等待扫码登录（默认 300s）……")
    start = time.time()
    while time.time() - start < timeout:
        if is_logged_in(page):
            print("[capture] ✅ 检测到登录态")
            return True
        try:
            if "basic.smartedu.cn" in page.url and "uc.basic" not in page.url:
                time.sleep(1)
                if is_logged_in(page):
                    print("[capture] ✅ 已登录主站")
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def cmd_capture(args):
    sync_playwright = try_import_playwright()
    cap_dir = Path(args.captures or CAPTURES_DIR)
    cap_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        launch_kwargs = {"headless": False}
        if args.user_data_dir:
            launch_kwargs["user_data_dir"] = args.user_data_dir
            print(f"[capture] 使用持久化会话目录：{args.user_data_dir}")
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context()
        page = context.new_page()

        captured = []

        def on_response(response):
            url = response.url
            # 只捕 teachingmaterials 且含 resources 的 JSON 响应
            if "teachingmaterials" in url and "resources" in url:
                ct = response.headers.get("content-type", "")
                if "json" in ct or url.endswith(".json"):
                    try:
                        body = response.body()
                        text = body.decode("utf-8", "replace")
                        obj = json.loads(text)
                        fname = f"{int(time.time()*1000)}_{abs(hash(url))%100000:05d}.json"
                        (cap_dir / fname).write_text(text, encoding="utf-8")
                        captured.append(fname)
                        print(f"[capture] 已保存 {fname}  <- {url[:90]}")
                    except Exception as e:
                        pass

        page.on("response", on_response)

        if args.url:
            print(f"[capture] 打开：{args.url}")
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        else:
            print(f"[capture] 打开登录页（无 --url，请手动进入教材页）")
            page.goto("https://basic.smartedu.cn/", wait_until="domcontentloaded", timeout=60000)

        # 若无持久化会话，确保登录
        if not args.user_data_dir:
            if not is_logged_in(page):
                page.goto(UC_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                if not wait_qr_login(page):
                    print("[capture] ❌ 登录超时")
                    browser.close()
                    return 2
            # 若给了 url 但还没进，重新进入
            if args.url and "teachingmaterials" not in page.url:
                page.goto(args.url, wait_until="domcontentloaded", timeout=60000)

        print("\n" + "=" * 60)
        print("[capture] 开始监听 teachingmaterials 资源接口。")
        print("  - 请在页面中：切换教材 → 小学(五四制) → 道德与法治 → 二年级 → 上册 → 统编版")
        print("  - 点开教材卡片，逐课点击展开（每课 5 类资源）")
        print("  - 捕获到的响应会自动保存到 captures/")
        if args.auto:
            print("  - 你选择了 --auto（自动点选，实验性），脚本将尝试自动导航")
        print("  - 全部点完后，回到本终端按 Enter 结束捕获")
        print("=" * 60 + "\n")

        if args.auto:
            auto_navigate(page)

        input("按 Enter 结束捕获并保存……")
        browser.close()

    print(f"\n[capture] 共捕获 {len(captured)} 个资源响应，保存于 {cap_dir}")
    print(f"[capture] 下一步运行：python dump_textbook_structure.py --parse")
    return 0


def auto_navigate(page):
    """实验性：按文本点击选择器完成教材定位 + 逐课展开。"""
    print("[auto] 尝试自动导航（如失败请改为手动）……")
    steps = [
        ("切换教材", "button, .switch, [class*='switch']"),
        ("小学（五•四学制）", "*"),
        ("道德与法治", "*"),
        ("二年级", "*"),
        ("上册", "*"),
        ("统编版", "*"),
    ]
    for label, sel in steps:
        try:
            # 文本匹配点击
            page.click(f"text={label}", timeout=8000)
            print(f"[auto] 点击：{label}")
            time.sleep(1.5)
        except Exception as e:
            print(f"[auto] 点击失败：{label} -> {e}")
    # 点教材卡片（含二年级上册）
    try:
        page.click("text=二年级上册", timeout=8000)
        print("[auto] 点开教材卡片")
        time.sleep(2)
    except Exception as e:
        print(f"[auto] 点教材卡片失败：{e}")
    # 逐课点击
    lessons = ["假期有收获", "周末巧安排", "欢欢喜喜庆国庆", "团团圆圆过中秋",
               "我爱我们班", "班级生活有规则", "我是班级值日生", "装扮我们的教室",
               "这些是大家的", "我们不乱扔", "大家排好队", "我们小点儿声",
               "我爱家乡山和水", "家乡物产养育我", "可亲可敬的家乡人", "家乡新变化"]
    for ln in lessons:
        try:
            page.click(f"text={ln}", timeout=6000)
            print(f"[auto] 展开课时：{ln}")
            time.sleep(1.2)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="教材资源结构 DUMP（只 dump 不下载）")
    ap.add_argument("--capture", action="store_true", help="捕获模式：浏览器监听 teachingmaterials 资源接口")
    ap.add_argument("--parse", action="store_true", help="解析模式：把 captures/ 汇总成结构报告")
    ap.add_argument("--teachingmaterial-id", help="教材 ID（仅用于提示/命名）")
    ap.add_argument("--url", help="教材页 URL（捕获模式；省略则手动进入）")
    ap.add_argument("--user-data-dir", help="持久化浏览器会话目录（复用本机已登录 Edge，跳过扫码）")
    ap.add_argument("--auto", action="store_true", help="捕获时尝试自动点选（实验性）")
    ap.add_argument("--captures", help="捕获目录（默认 <skill>/captures）")
    ap.add_argument("--out", help="解析报告输出路径（默认 <skill>/structure_report.json/.md）")
    args = ap.parse_args()

    if args.parse:
        return cmd_parse(args)
    if args.capture:
        return cmd_capture(args)
    print("请指定 --capture 或 --parse。详见文件头注释。")
    return 2


if __name__ == "__main__":
    sys.exit(main())
