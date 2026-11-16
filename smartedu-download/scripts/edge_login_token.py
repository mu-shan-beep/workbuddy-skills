#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台 —— 用本机已安装的 Edge 完成登录并自动抓取 token。

与 smart_download.py 的区别：
  - channel="msedge" 直接复用系统已安装的 Edge，**无需下载 Chromium**（省 ~150MB）
  - 使用 persistent context，登录态落在 --user-data-dir 指定目录，下次可复用
  - 同时抓取 access_token 与 mac_key，写成 JSON（视频下载可用）
  - 全程只需用户在弹出的浏览器里扫码 / 输密码登录，脚本自动轮询 LocalStorage

用法：
  python edge_login_token.py --token-file ./smartedu_token.txt [--timeout 300] [--headless]
  python edge_login_token.py --token-file ./smartedu_token.txt --check   # 只检查现有登录态

依赖：pip install playwright   （不需要 playwright install chromium）
"""

import argparse
import json
import os
import sys
import time

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)
HOME_URL = "https://basic.smartedu.cn/"
DEFAULT_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".edge_profile")

JS_DUMP_AUTH = """
() => {
  const out = [];
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      const v = localStorage.getItem(k) || '';
      if (!v || v.indexOf('access_token') === -1) continue;
      let inner = null;
      try {
        const raw = JSON.parse(v);
        inner = (raw && typeof raw.value === 'string') ? JSON.parse(raw.value) : raw;
      } catch (e) { continue; }
      if (inner && inner.access_token) out.push(inner);
    }
  } catch (e) {}
  return out;
}
"""


def save_token(inner, token_file):
    token_file = os.path.abspath(token_file)
    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
    payload = {
        "access_token": inner.get("access_token", ""),
        "mac_key": inner.get("mac_key", ""),
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return token_file


def main():
    ap = argparse.ArgumentParser(description="Edge 登录并自动抓取智慧教育平台 token")
    ap.add_argument("--token-file", default="./smartedu_token.txt")
    ap.add_argument("--user-data-dir", default=DEFAULT_PROFILE,
                    help="Edge 持久化 profile 目录（默认技能目录下 .edge_profile，独立于用户日常 Edge，不冲突）")
    ap.add_argument("--timeout", type=int, default=300, help="等待登录的秒数，默认 300")
    ap.add_argument("--headless", action="store_true", help="无头模式（仅当已有登录态时可用）")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright。请执行：")
        print(f"  {sys.executable} -m pip install playwright")
        print("  （使用 channel='msedge' 复用系统 Edge，无需 playwright install chromium）")
        return 2

    profile = os.path.abspath(args.user_data_dir)
    os.makedirs(profile, exist_ok=True)

    with sync_playwright() as p:
        print(f"[browser] 启动 Edge（profile: {profile}）...")
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=profile,
            channel="msedge",
            headless=args.headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            no_viewport=True,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def grab():
            try:
                for item in page.evaluate(JS_DUMP_AUTH) or []:
                    at = item.get("access_token")
                    if at and len(at) > 10:
                        return item
            except Exception:
                pass
            return None

        # 先看是否已有登录态
        try:
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[browser] 打开首页失败：{e}")

        inner = grab()
        if inner:
            path = save_token(inner, args.token_file)
            print(f"[browser] 已存在登录态，token 直接就绪 -> {path}")
            ctx.close()
            return 0

        print()
        print("=" * 56)
        print("请在弹出的 Edge 窗口中完成登录（扫码 或 账号密码）")
        print(f"等待最多 {args.timeout} 秒……")
        print("=" * 56)
        print()
        try:
            page.goto(UC_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[browser] 打开登录页失败：{e}")

        deadline = time.time() + args.timeout
        inner = None
        while time.time() < deadline:
            inner = grab()
            if inner:
                break
            # 登录成功后页面会跳回主站，若停在登录页则保持等待
            time.sleep(2)

        if not inner:
            print("[browser] 超时未检测到 token，请重新运行本脚本并尽快完成登录。")
            ctx.close()
            return 1

        path = save_token(inner, args.token_file)
        print()
        print(f"[browser] 已获取 token -> {path}")
        print(f"[browser] access_token: {inner.get('access_token', '')[:16]}...（长度 {len(inner.get('access_token', ''))}）")
        print(f"[browser] mac_key: {'有' if inner.get('mac_key') else '无'}")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
