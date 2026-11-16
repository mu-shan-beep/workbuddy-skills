#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台一键下载（自动登录 + 下载）

交互流程：
  1. 启动浏览器（调试模式，窗口可见）
  2. 自动检测是否已登录：
     - 已登录 → 直接从 LocalStorage 读 token
     - 未登录 → 自动跳转到官方登录页，显示二维码
  3. 用户在浏览器中扫码或输入密码（标准操作）
  4. 登录完成后，脚本自动从 LocalStorage 读取 access_token
  5. 调用 download_course.py 开始下载

用户只需：扫码或输入密码（标准登录操作），其余全自动。

用法：
  python smart_download.py --activity-id <activityId> [--out <output_dir>]
  python smart_download.py --experiment --course-id <courseId> [--class-hour-id lesson_1] [--out <output_dir>]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)

TOKEN_FILE_DEFAULT = "./smartedu_token.txt"


def extract_token_from_localstorage(page):
    """从浏览器 LocalStorage 中提取 access_token"""
    try:
        dump = page.evaluate("() => JSON.stringify(localStorage)")
        if not dump:
            return None
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
    except Exception as e:
        print(f"[token] 读取 LocalStorage 失败: {e}")
    return None


def login_and_get_token(token_file, timeout=300):
    """启动浏览器，等待用户登录，自动读取 token"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] 未安装 playwright，请先执行：")
        print("  pip install playwright")
        print("  playwright install chromium")
        return None

    token_path = Path(token_file).expanduser().resolve()
    print()
    print("=" * 50)
    print("正在启动浏览器……")
    print("=" * 50)
    print()

    with sync_playwright() as p:
        # 启动有头浏览器（调试模式，窗口可见）
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 打开登录页
        print("[browser] 打开登录页……")
        page.goto(UC_LOGIN_URL, wait_until="networkidle", timeout=60000)

        # 等待二维码出现
        print("[browser] 请用手机「智慧中小学」APP 扫码登录")
        print("[browser] 或使用用户名密码登录")
        print()

        # 轮询等待 token
        token = None
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 检查 URL 是否跳回主站
                current_url = page.url
                if "basic.smartedu.cn" in current_url and "uc.basic.smartedu.cn" not in current_url:
                    print(f"[browser] 检测到登录完成，正在读取 token……")
                    time.sleep(2)  # 等页面加载完成

                # 读取 LocalStorage
                token = extract_token_from_localstorage(page)
                if token:
                    print("[browser] ✅ 已获取 access_token")
                    break
            except Exception as e:
                print(f"[browser] 检查状态: {e}")

            time.sleep(1)

        browser.close()

    if not token:
        print("[browser] ❌ 超时未登录或未能获取 token")
        return None

    # 保存 token
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(token, encoding="utf-8")
    print(f"[browser] ✅ token 已保存到 {token_path}")
    print()

    return token


def run_download(activity_id=None, experiment=False, course_id=None, class_hour_id="lesson_1",
                 token_file=TOKEN_FILE_DEFAULT, out_dir=None):
    """调用 download_course.py 下载课程"""
    skill_base = Path(__file__).parent.parent
    download_script = skill_base / "scripts" / "download_course.py"

    cmd = [sys.executable, str(download_script)]

    if activity_id:
        cmd.extend(["--activity-id", activity_id])
    elif experiment:
        cmd.extend(["--experiment"])
        if course_id:
            cmd.extend(["--course-id", course_id])
        if class_hour_id:
            cmd.extend(["--class-hour-id", class_hour_id])

    cmd.extend(["--token-file", token_file])

    if out_dir:
        cmd.extend(["--out", out_dir])

    print("=" * 50)
    print("开始下载课程……")
    print("=" * 50)
    print()

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print()
        print("=" * 50)
        print("✅ 下载完成！")
        print(f"Token 文件：{token_file}")
        print("=" * 50)
    else:
        print()
        print(f"❌ 下载失败，退出码 {result.returncode}")

    return result.returncode


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台一键下载（自动登录）")
    ap.add_argument("--activity-id", help="课程 activityId")
    ap.add_argument("--experiment", action="store_true", help="实验课模式")
    ap.add_argument("--course-id", help="实验课 courseId")
    ap.add_argument("--class-hour-id", default="lesson_1", help="实验课课时 id")
    ap.add_argument("--token-file", default=TOKEN_FILE_DEFAULT, help="token 保存路径")
    ap.add_argument("--out", help="输出目录")
    args = ap.parse_args()

    # 第 1 步：登录并获取 token
    token = login_and_get_token(args.token_file)
    if not token:
        sys.exit(1)

    # 第 2 步：开始下载
    sys.exit(run_download(
        activity_id=args.activity_id,
        experiment=args.experiment,
        course_id=args.course_id,
        class_hour_id=args.class_hour_id,
        token_file=args.token_file,
        out_dir=args.out
    ))


if __name__ == "__main__":
    main()
