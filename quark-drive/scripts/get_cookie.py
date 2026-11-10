#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
夸克网盘 Cookie 自动获取：打开浏览器 → 检测登录态 → 已登录直接抓 Cookie，
未登录则打开浏览器让用户扫码/手机登录，登录完成后自动抓取。

用法:
  python3 get_cookie.py                 # 检测+抓取，写入同目录 cookie.txt
  python3 get_cookie.py --out <path>    # 指定输出路径
  python3 get_cookie.py --check         # 只检测登录态，不写文件
  python3 get_cookie.py --timeout 300   # 等待扫码登录的超时秒数（默认 300）

原理:
  1. agent-browser 打开 pan.quark.cn
  2. 页面出现「全部文件」= 已登录；出现「扫码登录」= 未登录
  3. 未登录则等用户扫码，轮询页面直到登录成功（或超时）
  4. agent-browser cookies get 拉全量 Cookie -> 拼成 Cookie 头格式
  5. 调 drive-pc member 接口验证 Cookie 有效 -> 落盘

依赖: npm install -g agent-browser && agent-browser install
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAN_URL = "https://pan.quark.cn"
# 登录态判定: 抓到的 Cookie 里出现这些键 = 已登录
LOGIN_COOKIE_KEYS = {"__pus", "__puus", "__kp", "__kps"}
MEMBER_API = ("https://drive-pc.quark.cn/1/clouddrive/member?pr=ucpro&fr=pc"
              "&uc_param_str=&_ch=home&fetch_share=true&fetch_shop=true&fetch_subscribe=true")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def ab(*args, timeout=60):
    """执行 agent-browser 命令，返回 stdout。"""
    r = subprocess.run(["agent-browser", *args], capture_output=True, text=True,
                       timeout=timeout)
    return r.stdout.strip()


def browser_get(url, wait_seconds=3):
    """打开/复用浏览器访问页面。"""
    out = ab("open", url)
    time.sleep(wait_seconds)
    return out


def page_has_login_ui():
    """检测页面是否显示登录界面（扫码/手机登录）。"""
    try:
        snap = ab("snapshot", timeout=30)
    except Exception:
        return False
    return ("扫码登录" in snap) or ("手机登录" in snap) or ("微信登录" in snap)


def page_has_drive_ui():
    """检测页面是否已进入网盘主界面（已登录）。"""
    try:
        snap = ab("snapshot", timeout=30)
    except Exception:
        return False
    return ("全部文件" in snap) or ("最近" in snap and "回收站" in snap)


def grab_cookie_header():
    """从浏览器拉全量 Cookie，拼成 HTTP Cookie 头格式（domain=.quark.cn 全收）。"""
    raw = ab("cookies", "get", "--url", PAN_URL, "--json", timeout=30)
    data = json.loads(raw)
    cookies = data["data"]["cookies"]
    pairs = []
    seen = set()
    for c in cookies:
        name = c["name"]
        if name in seen:  # 同名取 .quark.cn 域的（后出现的通用域优先级高，这里保留第一个去重即可）
            continue
        seen.add(name)
        pairs.append(f"{name}={c['value']}")
    return "; ".join(pairs)


def verify_cookie(cookie_header):
    """用 member 接口验证 Cookie 是否有效（登录态）。"""
    req = urllib.request.Request(MEMBER_API, headers={
        "accept": "application/json, text/plain, */*",
        "user-agent": UA,
        "cookie": cookie_header,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d.get("code") == 0
    except Exception:
        return False


def ensure_logged_in(wait_timeout):
    """确保浏览器里已登录夸克。返回 True/False。"""
    browser_get(PAN_URL)
    if page_has_drive_ui():
        print("✅ 浏览器已有登录态")
        return True
    if not page_has_login_ui():
        # 可能是中转页，刷新一次再看
        browser_get(PAN_URL, wait_seconds=5)
        if page_has_drive_ui():
            print("✅ 浏览器已有登录态")
            return True
    print("⏳ 未登录。请在弹出的浏览器窗口扫码/手机登录夸克账号（完成自动继续）...")
    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        time.sleep(5)
        if page_has_drive_ui():
            print("✅ 检测到登录成功")
            return True
        remain = int(deadline - time.time())
        print(f"   等待登录中... 剩余 {remain}s", end="\r")
    print("\n❌ 等待登录超时")
    return False


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    out_path = HERE + "/cookie.txt"
    if "--out" in args:
        out_path = args[args.index("--out") + 1]
    wait_timeout = 300
    if "--timeout" in args:
        wait_timeout = int(args[args.index("--timeout") + 1])

    try:
        if not ensure_logged_in(wait_timeout):
            sys.exit(1)
        cookie = grab_cookie_header()
        if not any(f"{k}=" in cookie for k in LOGIN_COOKIE_KEYS):
            print("❌ 抓到的 Cookie 缺少登录关键字段（__pus/__puus 等），登录态不完整")
            sys.exit(1)
        if not verify_cookie(cookie):
            print("❌ Cookie 抓取成功但 member 接口验证失败")
            sys.exit(1)
        print(f"✅ Cookie 验证有效（{len(cookie)} 字符，含 {cookie.count('; ') + 1} 个字段）")
        if not check_only:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(cookie)
            print(f"✅ 已写入 {out_path}")
    finally:
        subprocess.run(["agent-browser", "close"], capture_output=True)


if __name__ == "__main__":
    main()
