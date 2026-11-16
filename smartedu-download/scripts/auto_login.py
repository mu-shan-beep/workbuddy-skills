#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台自动登录取 token（极简版）

交互流程：
  1. 脚本启动 Playwright 浏览器，显示二维码
  2. 用户用手机「智慧中小学」APP 扫码确认
  3. 脚本自动等待登录完成
  4. 脚本自动从 LocalStorage 读取 access_token
  5. 写入 token 文件

用户操作：只扫码，无需其他动作。

用法：
  python auto_login.py --token-file ./smartedu_token.txt [--timeout 300]
"""

import argparse
import json
import sys
import time
from pathlib import Path

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)

TOKEN_FILE_DEFAULT = "./smartedu_token.txt"


def extract_access_token_from_localstorage(dump):
    """从 localStorage JSON dump 中提取 access_token。"""
    if not dump:
        return None
    try:
        obj = json.loads(dump)
        if isinstance(obj, dict):
            for _k, v in obj.items():
                if isinstance(v, str) and "access_token" in v:
                    try:
                        inner = json.loads(v)
                        if isinstance(inner, dict) and inner.get("access_token"):
                            return inner["access_token"]
                    except Exception:
                        pass
        if isinstance(obj, list):
            for item in obj:
                v = item.get("value") if isinstance(item, dict) else None
                if isinstance(v, str) and "access_token" in v:
                    try:
                        inner = json.loads(v)
                        if isinstance(inner, dict) and inner.get("access_token"):
                            return inner["access_token"]
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def is_logged_in(page):
    """检查当前页面是否已登录。"""
    try:
        # 检查是否有 access_token
        dump = page.evaluate("() => JSON.stringify(localStorage)")
        token = extract_access_token_from_localstorage(dump)
        if token:
            return True, token
    except Exception:
        pass
    return False, None


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台自动登录取 token")
    ap.add_argument("--token-file", default=TOKEN_FILE_DEFAULT, help="token 保存路径")
    ap.add_argument("--timeout", type=int, default=300, help="等待扫码超时秒数")
    args = ap.parse_args()

    # 导入 playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright。请先执行：")
        print("  pip install playwright")
        print("  playwright install chromium")
        return 2

    token_file = Path(args.token_file).expanduser().resolve()

    print("[auto_login] 正在启动浏览器……")
    print(f"[auto_login] token 将保存到：{token_file}")
    print()

    with sync_playwright() as p:
        # 启动有头浏览器
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 打开登录页
        print("[auto_login] 正在打开登录页……")
        page.goto(UC_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        # 等待二维码出现
        print("[auto_login] 等待二维码出现……")
        try:
            page.wait_for_selector("img[src*='qrcode']", timeout=30000)
        except Exception:
            # 可能选择器不同，尝试其他方式
            pass

        print()
        print("[auto_login] ============================================")
        print("[auto_login] 请用「智慧中小学」APP 扫描页面上的二维码")
        print("[auto_login] 扫码确认后，脚本会自动取 token")
        print("[auto_login] 如果 5 分钟未扫码，将自动超时")
        print("[auto_login] ============================================\n")

        # 轮询等待登录
        start_time = time.time()
        token = None

        while time.time() - start_time < args.timeout:
            # 检查是否已登录
            logged_in, token = is_logged_in(page)
            if logged_in:
                break
            # 检查页面是否跳转到 basic.smartedu.cn
            try:
                current_url = page.url
                if "basic.smartedu.cn" in current_url and "uc.basic.smartedu.cn" not in current_url:
                    # 已跳转回主站，再等一会儿让页面加载完成
                    time.sleep(1)
                    logged_in, token = is_logged_in(page)
                    if logged_in:
                        break
            except Exception:
                pass
            time.sleep(1)

        browser.close()

        if not token:
            print("[auto_login] ❌ 超时未登录或未能获取 token")
            return 2

        # 写入 token 文件
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token, encoding="utf-8")

        print(f"[auto_login] ✅ 已获取 access_token")
        print(f"[auto_login] ✅ 已保存到：{token_file}")
        print()
        print("[auto_login] 现在可以运行 download_course.py 下载课程了。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
