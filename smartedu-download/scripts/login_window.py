#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立内嵌登录窗口（pywebview 内嵌官方 UC 登录页，扫码 + 密码 合一；登录后自动取 token）

背景与动机
----------
之前 `token_manager.acquire` 用 Playwright 弹出「真实 Edge 窗口」（`channel="msedge"`）来登录，
对用户偏重、且强依赖系统 Edge 可用。用户希望改成「独立内嵌显示窗口」——
即由**工具自身拥有的窗口**承载登录界面，而不是弹出系统 Edge、也不是借用用户的默认浏览器。

实现思路
--------
  - 用 `pywebview` 在工具自有窗口里加载官方 UC 登录页
    （`uc.basic.smartedu.cn` 的 UC 登录页本身已内置「二维码扫码 + 用户名密码」两种入口，天然合一，
     无需我们重画 UI）。
  - 登录成功后页面会重定向到 `basic.smartedu.cn`，脚本通过 `webview.evaluate_js` 读取其
    LocalStorage 中的 NdAuth `access_token` + `mac_key`，写入 token 文件。
  - Windows 上 pywebview 自动复用系统内置的 **Edge WebView2 运行时**（Win10+ 预装），
    无需下载 Chromium，窗口轻量且归工具所有。

依赖
----
  pip install pywebview
  （Windows 自动使用内置 WebView2；macOS / Linux 需相应 WebView 后端）

注意
----
  沙箱无显示器 / 外网，本模块未实跑；请在已安装 WebView2 的本机 WorkBuddy 环境测试。
  若 pywebview 不可用，调用方（`token_manager.acquire`）会自动回退到 Playwright 弹窗。
"""

import os
import sys
import time

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)

# 与 token_manager.JS_DUMP_AUTH 同源：从「当前页面」LocalStorage 提取所有含 access_token 的内层对象。
# 之所以读「当前页面」而非固定 basic.smartedu.cn，是因为登录后页面会重定向到 basic.smartedu.cn，
# evaluate_js 自然跑在该页上下文里，正好能读到写入 basic 的 NdAuth token。
# 注意：这里写成「立即执行函数 (IIFE)」而非裸箭头函数 —— 因为 pywebview 的 evaluate_js 直接取值、
# 不会像 Playwright 那样自动调用传入的函数；裸 `() => {...}` 会被当成函数对象而非返回值。
JS_DUMP_AUTH = """
(() => {
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
})()
"""


def _extract_token(dump_list):
    """从 JS_DUMP_AUTH 返回的列表里挑第一个合法的 access_token + mac_key。"""
    if not isinstance(dump_list, list):
        return None, ""
    for item in dump_list:
        if isinstance(item, dict) and item.get("access_token"):
            at = item["access_token"]
            if len(at) > 10:
                return at, item.get("mac_key", "") or ""
    return None, ""


def embedded_acquire(token_file, timeout=300, width=440, height=720):
    """
    弹出工具自有的内嵌登录窗口，加载官方 UC 登录页（扫码 + 密码 合一）。
    登录成功后自动读取 token。

    返回 dict：
      {"ok": True,  "access_token": ..., "mac_key": ...}     成功
      {"ok": False, "reason": "cancelled"}                    用户关闭窗口未登录
      {"ok": False, "reason": "timeout"}                       超时

    若 pywebview 不可用，直接抛 ImportError（由调用方决定回退到 Playwright）。
    """
    import webview  # 延迟导入：未安装时由调用方捕获 ImportError

    token_file = os.path.abspath(token_file)
    result = {"ok": False, "access_token": None, "mac_key": "", "reason": ""}

    window = webview.create_window(
        "国家智慧教育平台 · 登录",
        url=UC_LOGIN_URL,
        width=width,
        height=height,
    )

    def watcher(win):
        deadline = time.time() + timeout
        errors = 0
        while time.time() < deadline:
            try:
                dump = win.evaluate_js(JS_DUMP_AUTH)
                errors = 0
            except Exception:
                # 窗口被用户关闭时 evaluate_js 会持续抛异常，连续多次即判定为取消
                errors += 1
                if errors >= 3:
                    result["reason"] = "cancelled"
                    return
                time.sleep(2)
                continue

            at, mk = _extract_token(dump)
            if at:
                result["ok"] = True
                result["access_token"] = at
                result["mac_key"] = mk
                try:
                    win.destroy()
                except Exception:
                    pass
                return
            time.sleep(2)
        # 自然超时
        result["reason"] = "timeout"
        try:
            win.destroy()
        except Exception:
            pass

    webview.start(watcher, window)
    return result


def main():
    import argparse
    ap = argparse.ArgumentParser(description="智慧教育平台 内嵌登录窗口（扫码/密码合一）")
    ap.add_argument("--token-file", default="./smartedu_token.txt", help="token 保存路径")
    ap.add_argument("--timeout", type=int, default=300, help="等待登录的秒数，默认 300")
    args = ap.parse_args()

    try:
        res = embedded_acquire(args.token_file, timeout=args.timeout)
    except ImportError:
        print("[login_window] 未安装 pywebview。请先执行：")
        print("  pip install pywebview")
        print("（Windows 上会自动使用内置 Edge WebView2，无需额外安装浏览器）")
        return 2

    if res.get("ok"):
        # 写入 token 文件（与 token_manager 格式一致：access_token + mac_key + 时间戳）
        from token_manager import save_token
        save_token(args.token_file, res["access_token"], res.get("mac_key", ""))
        print(f"[login_window] ✅ 已获取并保存 token -> {os.path.abspath(args.token_file)}")
        print(f"[login_window] access_token: {res['access_token'][:16]}...（长度 {len(res['access_token'])}）")
        print(f"[login_window] mac_key: {'有' if res['mac_key'] else '无'}（视频下载需要）")
        return 0
    else:
        reason = res.get("reason")
        if reason == "cancelled":
            print("[login_window] 登录窗口已关闭，未获取到 token。")
        else:
            print(f"[login_window] 超时未登录（{timeout_s(args.timeout)}），未获取到 token。")
        return 1


def timeout_s(t):
    return f"{t} 秒"


if __name__ == "__main__":
    sys.exit(main())
