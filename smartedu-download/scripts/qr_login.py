#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台 扫码登录 / 取 token 的三种交互接口

背景（逆向结论，详见 references/api_notes.md）：
  平台统一登录域 uc.basic.smartedu.cn 支持扫码登录，但下载所需的 NdAuth
  access_token 是在 basic.smartedu.cn 的「浏览器会话」里、经 UC 重定向
  （send_uckey=true）后由前端写进 LocalStorage 的。纯 Python 无法在沙箱里
  拿到该 token；扫码只是把浏览器会话登录了，最终仍需从浏览器读 LocalStorage。

本脚本提供三种可独立测试的接口：

  [B] 扫码登录引导（最小、零重依赖）
      python qr_login.py --mode guide
      -> 用系统默认浏览器打开官方 UC 扫码登录页，用户用「智慧中小学」APP 扫码登录；
         登录后回到 WorkBuddy 说「已登录」，再用 token_helper.py 书签取 token。

  [C] Playwright 全自动扫码（对齐「扫码后进入解析」目标；需本机测试）
      python qr_login.py --mode playwright --token-file ./smartedu_token.txt
      -> 启动真实浏览器打开 UC 扫码登录页（窗口可见，方便手机扫码）；
         用户扫码确认后，脚本自动等待登录完成并读取 LocalStorage 的 access_token 写入文件。
         依赖：pip install playwright && playwright install chromium
         注意：当前沙箱无浏览器，本接口未经验证，请在本机 WorkBuddy 环境测试。

  [A] 书签增强 + token 过期自检 见 token_helper.py：
      python token_helper.py            # 启动接收器 + 书签小工具
      python token_helper.py --check    # 校验已有 token 是否有效（200/401）

用法示例：
  python qr_login.py --mode guide
  python qr_login.py --mode playwright --token-file ./smartedu_token.txt
"""

import argparse
import json
import sys
import webbrowser
from pathlib import Path

# 由 basic.smartedu.cn 的 ucLoginUrl 还原（sdp-app-id + redirect_uri + send_uckey）
UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)

TOKEN_FILE_DEFAULT = "./smartedu_token.txt"


def extract_access_token_from_text(text):
    """兼容裸 token / JSON 包装 value / 内层 JSON 三种输入。"""
    text = (text or "").strip()
    if not text:
        return None
    if len(text.split()) == 1 and text.startswith(("eyJ", "A", "B", "C", "D", "E", "F")):
        return text
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "value" in obj and isinstance(obj["value"], str):
            try:
                inner = json.loads(obj["value"])
                if isinstance(inner, dict) and inner.get("access_token"):
                    return inner["access_token"]
            except Exception:
                pass
    except Exception:
        pass
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get("access_token"):
            return obj["access_token"]
    except Exception:
        pass
    return None


def extract_token_from_localstorage_dump(dump):
    """从浏览器导出的 localStorage 字符串（JSON 或 key=value 列表）中提 access_token。"""
    if not dump:
        return None
    try:
        obj = json.loads(dump)
        # 可能直接是 {key: value} 字典
        for _k, v in obj.items():
            if isinstance(v, str) and "access_token" in v:
                t = extract_access_token_from_text(v)
                if t:
                    return t
        # 也可能是 [{key, value}, ...]
        if isinstance(obj, list):
            for item in obj:
                v = item.get("value") if isinstance(item, dict) else None
                if isinstance(v, str) and "access_token" in v:
                    t = extract_access_token_from_text(v)
                    if t:
                        return t
    except Exception:
        # 回退：按行扫描
        for line in dump.splitlines():
            if "access_token" in line:
                t = extract_access_token_from_text(line)
                if t:
                    return t
    return None


# ---------------------------------------------------------------------------
# 接口 B：扫码登录引导
# ---------------------------------------------------------------------------
def mode_guide():
    print("[qr_login] 正在打开官方扫码登录页……")
    print(f"  登录页：{UC_LOGIN_URL}")
    ok = webbrowser.open(UC_LOGIN_URL)
    if not ok:
        print("[qr_login] 无法自动打开浏览器，请手动复制上面的链接到浏览器打开。")
    print()
    print("[qr_login] 步骤：")
    print("  1. 用「智慧中小学」APP 扫描页面上的二维码登录。")
    print("  2. 登录成功后，回到 WorkBuddy 对话说「已登录」。")
    print("  3. 我会启动 token_helper.py 的书签小工具，你点击书签即可把 token 自动回传。")
    print("     （或直接按 references/api_notes.md 第 3 节手动复制 token。）")


# ---------------------------------------------------------------------------
# 接口 C：Playwright 全自动扫码（未经沙箱验证，需本机测试）
# ---------------------------------------------------------------------------
def mode_playwright(token_file):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[qr_login] 未安装 Playwright。请先执行：")
        print("  pip install playwright && playwright install chromium")
        print("然后在本机（有浏览器的环境）重新运行本命令。")
        return 2

    out_path = Path(token_file).expanduser().resolve()
    print("[qr_login] 启动浏览器（窗口可见，请用手机扫描页面上的二维码）……")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 打开 UC 扫码登录页
        page.goto(UC_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        print("[qr_login] 请在弹出的浏览器窗口中用「智慧中小学」APP 扫码登录。")
        print("[qr_login] 登录完成（自动跳转回 basic.smartedu.cn）后脚本会读取 token。")

        # 等待登录完成：跳回 basic.smartedu.cn 且 LocalStorage 出现 access_token
        try:
            page.wait_for_url("**://basic.smartedu.cn/**", timeout=300000)
        except Exception as e:
            print(f"[qr_login] 等待跳转超时：{e}；将继续尝试读取 LocalStorage。")

        # 轮询 basic.smartedu.cn 的 LocalStorage 找 token
        token = None
        for _ in range(60):  # 最多等 ~60s
            try:
                dump = page.evaluate("() => JSON.stringify(localStorage)")
            except Exception:
                dump = None
            token = extract_token_from_localstorage_dump(dump)
            if token:
                break
            page.wait_for_timeout(1000)

        browser.close()

        if not token:
            print("[qr_login] 未能从 LocalStorage 读取到 access_token。请确认扫码登录成功。")
            return 2

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(token, encoding="utf-8")
        print(f"[qr_login] ✅ 已获取并保存 access_token -> {out_path}")
        print("[qr_login] 现在可以运行 download_course.py 继续下载。")
        return 0


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台 扫码登录 / 取 token 接口")
    ap.add_argument(
        "--mode",
        choices=["guide", "playwright"],
        required=True,
        help="guide=打开官方扫码登录页（B）；playwright=自动驱动浏览器扫码取 token（C，需本机测）",
    )
    ap.add_argument("--token-file", default=TOKEN_FILE_DEFAULT, help="C 模式保存 token 的路径")
    args = ap.parse_args()

    if args.mode == "guide":
        mode_guide()
        return 0
    elif args.mode == "playwright":
        return mode_playwright(args.token_file)


if __name__ == "__main__":
    sys.exit(main())
