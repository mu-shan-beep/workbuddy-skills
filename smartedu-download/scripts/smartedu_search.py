#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smartedu_search.py —— 用已登录的 Edge profile 在国家中小学智慧教育平台站内搜索，
并把命中的课程/资源 ID 打印出来（解决站内搜索 API 无法直接调用、无法按关键词定位 courseId 的问题）。

用法：
  python smartedu_search.py "以工匠精神雕琢时代品质" [--json-out hits.json]

依赖：playwright（channel=msedge 复用系统 Edge，无需下载 Chromium）
"""
import argparse
import json
import os
import re
import sys
import time

HOME_URL = "https://basic.smartedu.cn/"
DEFAULT_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".edge_profile")

ID_PAT = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")

# 常见课程/资源详情页路由
ROUTE_PAT = re.compile(
    r"(qualityCourse|classActivity|experimentLesson|prepare|tchMaterial|tresource|"
    r"syncClassroom|eliteLesson|lesson|course)", re.I)


def extract_hits(text, keyword):
    """从一段 JSON/HTML 文本里抽取与 keyword 同现的 uuid 及附近标题。"""
    hits = []
    if not text:
        return hits
    for m in re.finditer(re.escape(keyword), text):
        s = max(0, m.start() - 400)
        e = min(len(text), m.end() + 400)
        chunk = text[s:e]
        for uid in ID_PAT.findall(chunk):
            hits.append(uid)
    return hits


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台站内搜索并抓取资源 ID")
    ap.add_argument("keyword")
    ap.add_argument("--user-data-dir", default=DEFAULT_PROFILE)
    ap.add_argument("--json-out", default=None, help="把抓到的响应元数据写成 JSON 便于排查")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--wait", type=int, default=12, help="搜索结果等待秒数")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright：pip install playwright")
        return 2

    profile = os.path.abspath(args.user_data_dir)
    captured = []          # [(url, body)]
    id_buckets = {}        # uuid -> set(来源)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile,
            channel="msedge",
            headless=args.headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(resp):
            try:
                u = resp.url
                if not (".json" in u or "/api/" in u or "search" in u.lower()):
                    return
                body = resp.text()
            except Exception:
                return
            captured.append((u, body[:200000]))
            for uid in extract_hits(body, args.keyword):
                id_buckets.setdefault(uid, set()).add(u.split("?")[0])

        page.on("response", on_response)

        print(f"[search] 打开首页 {HOME_URL}")
        page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # 找搜索框：优先 placeholder 含“搜索”，其次 input[type=search]，最后任意可见 input
        box = None
        for sel in ['input[placeholder*="搜索"]', 'input[type="search"]',
                    'input[placeholder*="Search"]', 'input.ant-input', 'input']:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    box = loc
                    print(f"[search] 命中搜索框选择器：{sel}")
                    break
            except Exception:
                continue
        if box is None:
            print("[search] 未在首页找到搜索框，尝试直接访问搜索路由……")
            for u in ("https://basic.smartedu.cn/search",
                      "https://basic.smartedu.cn/searchResult"):
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3000)
                    for sel in ['input[placeholder*="搜索"]', 'input[type="search"]', 'input']:
                        try:
                            loc = page.locator(sel).first
                            if loc.count() and loc.is_visible():
                                box = loc
                                print(f"[search] 在 {u} 命中搜索框：{sel}")
                                break
                        except Exception:
                            continue
                    if box is not None:
                        break
                except Exception as e:
                    print(f"[search] 打开 {u} 失败：{e}")

        if box is not None:
            try:
                box.click()
                box.fill(args.keyword)
                page.keyboard.press("Enter")
                print(f"[search] 已提交关键词：{args.keyword}")
            except Exception as e:
                print("[search] 输入失败：", e)
        else:
            print("[search] 仍然没有搜索框；改为直接抓当前页面网络（可能已被重定向）。")

        for _ in range(args.wait):
            page.wait_for_timeout(1000)

        # 把页面上所有含 courseId / contentId 的链接也记下来
        try:
            hrefs = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href)") or []
        except Exception:
            hrefs = []
        for h in hrefs:
            if ("courseId=" in h or "contentId=" in h) and ROUTE_PAT.search(h):
                for uid in ID_PAT.findall(h):
                    id_buckets.setdefault(uid, set()).add("link:" + h.split("?")[0])
                captured.append((h, ""))

        # 打印当前页面里出现的、和关键词同一行的链接文字，帮助人工确认
        try:
            txt = page.inner_text("body")
        except Exception:
            txt = ""
        for line in txt.splitlines():
            if args.keyword in line and len(line.strip()) < 120:
                print("[page]", line.strip())

        ctx.close()

    print(f"\n[search] 捕获 {len(captured)} 条响应/链接")
    if id_buckets:
        print(f"[search] 与关键词同现的 ID（{len(id_buckets)} 个）：")
        for uid, srcs in id_buckets.items():
            print(f"  {uid}   <- {'; '.join(sorted(srcs))[:120]}")
    else:
        print("[search] 未在响应中直接命中关键词。打印部分响应 URL 供排查：")
        for u, _ in captured[:40]:
            print("   ", u[:160])

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump([{"url": u, "len": len(b), "body": b[:60000]} for u, b in captured], f,
                      ensure_ascii=False, indent=2)
        print("[search] 响应清单(含 body) ->", args.json_out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
