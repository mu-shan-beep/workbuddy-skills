#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台 —— 统一 token 子系统（获取 / 校验 / 续期 / 持久化）

为什么需要它（替代原本散落的 3 条路径）：
  - edge_login_token.py   : Playwright 复用系统 Edge，抓 access_token + mac_key（但无续期）
  - token_helper.py       : 本地 HTTP 接收器，只抓裸 access_token（缺 mac_key，视频下载会失败）
  - get_token_from_edge_storage : 直读 Edge LevelDB（兜底，无续期）
  三者互不统一、无过期处理，token 一过期就 401。本模块把它们收口为一处。

解决用户提出的两点：
  1) 操作便捷：一个入口融合「已登录静默续期」「扫码/密码登录」「手动粘贴」
  2) 持续性：token 过期后优先用持久化 profile 的 Cookie 无感续期，无需重新扫码/输密码

用法（CLI）：
  python token_manager.py acquire  [--token-file ./smartedu_token.txt] [--profile .edge_profile] [--headless] [--timeout 300]
  python token_manager.py refresh  [--token-file ./smartedu_token.txt] [--profile .edge_profile]
  python token_manager.py status   [--token-file ./smartedu_token.txt]
  python token_manager.py check    [--token-file ./smartedu_token.txt]

编程接口（供 download_*.py 调用）：
  from token_manager import get_valid_token
  tok = get_valid_token(token_file)          # 返回 dict 或 None
  if tok:
      access_token = tok["access_token"]
      mac_key     = tok.get("mac_key") or ""

依赖：playwright（仅 acquire/refresh 需要；status/check/get_valid_token 的兜底不需要）
"""

import argparse
import json
import os
import re
import sys
import time

DEFAULT_PROFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".edge_profile")
DEFAULT_TOKEN_FILE = "./smartedu_token.txt"
UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)
HOME_URL = "https://basic.smartedu.cn/"
SESSION_URL = "https://basic.smartedu.cn/rest/api/user/session"

# token 有效期（秒）。平台真实 TTL 不透明，用保守的 2h 做本地乐观门禁；
# 真正以「下载遇到 401 → 自动续期 → 重试」为最终保障（见 download_*.py 的未来增强）。
DEFAULT_TTL = int(os.environ.get("SMARTEDU_TOKEN_TTL", "7200"))


# --------------------------------------------------------------------------- #
# 1. 持久化（写 / 读）
# --------------------------------------------------------------------------- #
def save_token(token_file, access_token, mac_key="", ttl=DEFAULT_TTL):
    """写入 JSON：access_token + mac_key + captured_at + expires_at。"""
    token_file = os.path.abspath(token_file)
    os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
    now = time.time()
    payload = {
        "access_token": access_token or "",
        "mac_key": mac_key or "",
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        "expires_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now + ttl)),
    }
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return token_file


def load_token(token_file):
    """读取 token。兼容两种历史格式：
       - JSON（含 access_token，可能带 mac_key / expires_at）
       - 裸 token 文本（旧 token_helper.py 写出）
       返回 dict 或 None。
    """
    token_file = os.path.abspath(token_file)
    if not os.path.isfile(token_file):
        return None
    try:
        with open(token_file, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict) and obj.get("access_token"):
            obj.setdefault("mac_key", "")
            obj.setdefault("captured_at", "")
            obj.setdefault("expires_at", "")
            return obj
    except Exception:
        pass
    # 裸 token 文本兜底（旧 token_helper.py 写出的原始 access_token，约 112 字符）
    try:
        raw = open(token_file, "r", encoding="utf-8").read().strip()
        if len(raw) >= 16 and " " not in raw and "{" not in raw:
            return {
                "access_token": raw,
                "mac_key": "",
                "captured_at": "",
                "expires_at": "",
            }
    except Exception:
        pass
    return None


def _parse_expires_at(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# 2. 实时有效性探测（最佳努力，仅用于 status/check，不阻塞下载流程）
# --------------------------------------------------------------------------- #
def probe_token(access_token):
    """用 Bearer 探测 session 端点，判断 token 是否仍被服务端接受。
    返回 True（有效）/ False（确定失效）/ None（无法判定，网络抖动等）。
    """
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            SESSION_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": HOME_URL,
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body)
        except Exception:
            return None
        # 服务端明确返回 code!=0 或 data 空 → 失效
        if not (data.get("code") == 0 and data.get("data")):
            return False
        return True
    except urllib.error.HTTPError as e:
        return False if e.code in (401, 403) else None
    except Exception:
        return None


def is_expired(token_dict, slack=0):
    """按本地 expires_at 判断（乐观门禁）。返回 True 表示已过期。"""
    exp = _parse_expires_at(token_dict.get("expires_at"))
    if exp is None:
        return False  # 无时间戳：乐观认为未过期，交给真实请求判定
    return time.time() > (exp - slack)


# --------------------------------------------------------------------------- #
# 3. 兜底：直读 Edge LevelDB（本机日常 Edge，非技能 profile）  —— 纯 stdlib
# --------------------------------------------------------------------------- #
def read_edge_leveldb():
    """从本机日常 Edge 的 Local Storage leveldb 提取 (access_token, mac_key)。
    返回 (token, mac_key) 或 (None, None)。不依赖 plyvel。
    """
    edge_profile = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft", "Edge", "User Data", "Default", "Local Storage", "leveldb"
    )
    if not os.path.exists(edge_profile):
        return None, None
    all_data = b""
    for f in sorted(os.listdir(edge_profile)):
        fp = os.path.join(edge_profile, f)
        if os.path.isfile(fp):
            try:
                with open(fp, "rb") as fh:
                    all_data += fh.read()
            except Exception:
                pass
    pattern = rb'ND_UC_AUTH-[\da-f-]+&ncet-xedu&token'
    matches = list(re.finditer(pattern, all_data))
    if not matches:
        return None, None
    for m in matches[:5]:
        start = max(0, m.start() - 20)
        end = min(len(all_data), m.end() + 3000)
        ctx = all_data[start:end]
        json_start = ctx.find(b'{')
        if json_start < 0:
            continue
        json_str = ctx[json_start:].decode("utf-8", errors="replace")
        brace = 0
        for i, c in enumerate(json_str):
            if c == '{':
                brace += 1
            elif c == '}':
                brace -= 1
                if brace == 0:
                    json_str = json_str[:i + 1]
                    break
        try:
            obj = json.loads(json_str)
            if 'value' in obj and isinstance(obj['value'], str):
                inner = json.loads(obj['value'])
                at = inner.get("access_token", "")
                mk = inner.get("mac_key", "")
                if at:
                    return at, mk
        except Exception:
            continue
    return None, None


# --------------------------------------------------------------------------- #
# 4. Playwright：复用系统 Edge 的持久化 profile，抓 token + mac_key
# --------------------------------------------------------------------------- #
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


def _grab_from_page(page):
    """轮询页面 LocalStorage，返回 (access_token, mac_key) 或 (None, None)。"""
    try:
        for item in page.evaluate(JS_DUMP_AUTH) or []:
            at = item.get("access_token")
            if at and len(at) > 10:
                return at, item.get("mac_key", "") or ""
    except Exception:
        pass
    return None, None


def _launch_pw(headless, profile_dir):
    """启动 Playwright（channel=msedge 复用系统 Edge，无需下载 Chromium）。
    返回 (playwright_ctx, page)。失败时抛异常。
    """
    from playwright.sync_api import sync_playwright
    import shutil
    profile = os.path.abspath(profile_dir)
    os.makedirs(profile, exist_ok=True)
    # Edge 正在运行时持久化上下文会冲突；提示用户但先尝试
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=profile,
        channel="msedge",
        headless=headless,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        no_viewport=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return pw, ctx, page


def refresh_from_profile(token_file, profile_dir=DEFAULT_PROFILE, timeout=120):
    """用持久化 profile 的 Cookie 无头抓取新 token（无需重新登录）。
    成功返回 True 并写入 token 文件；失败返回 False。
    """
    token_file = os.path.abspath(token_file)
    profile = os.path.abspath(profile_dir)
    if not os.path.isdir(profile):
        return False
    try:
        pw, ctx, page = _launch_pw(headless=True, profile_dir=profile)
    except Exception as e:
        print(f"[token_manager] 启动 Edge 失败（无头续期）：{e}")
        return False
    try:
        try:
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        at, mk = _grab_from_page(page)
        if at:
            save_token(token_file, at, mk)
            print(f"[token_manager] 已用持久化登录态续期 token -> {token_file}")
            return True
        # 可能还在登录页，轮询一小会儿
        deadline = time.time() + min(timeout, 60)
        while time.time() < deadline:
            at, mk = _grab_from_page(page)
            if at:
                save_token(token_file, at, mk)
                print(f"[token_manager] 已用持久化登录态续期 token -> {token_file}")
                return True
            time.sleep(2)
        return False
    finally:
        try:
            ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def _acquire_playwright(token_file, profile_dir=DEFAULT_PROFILE, headless=False, timeout=300):
    """兜底：Playwright 弹出真实 Edge 窗口登录（与旧实现一致）。"""
    token_file = os.path.abspath(token_file)
    profile = os.path.abspath(profile_dir)
    try:
        pw, ctx, page = _launch_pw(headless=headless, profile_dir=profile)
    except Exception as e:
        print(f"[token_manager] 启动 Edge 失败：{e}")
        return 2

    try:
        try:
            page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[token_manager] 打开首页失败：{e}")

        at, mk = _grab_from_page(page)
        if at:
            save_token(token_file, at, mk)
            print(f"[token_manager] 已存在登录态，token 直接就绪 -> {token_file}")
            return 0

        print()
        print("=" * 56)
        print("请在弹出的 Edge 窗口中完成登录（平台页支持 扫码 / 账号密码）")
        print(f"等待最多 {timeout} 秒……")
        print("=" * 56)
        print()
        try:
            page.goto(UC_LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[token_manager] 打开登录页失败：{e}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            at, mk = _grab_from_page(page)
            if at:
                break
            time.sleep(2)

        if not at:
            print("[token_manager] 超时未检测到 token，请重新运行并尽快完成登录。")
            return 1
        save_token(token_file, at, mk)
        print()
        print(f"[token_manager] 已获取 token -> {token_file}")
        print(f"[token_manager] access_token: {at[:16]}...（长度 {len(at)}）")
        print(f"[token_manager] mac_key: {'有' if mk else '无'}")
        return 0
    finally:
        try:
            ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def acquire_token(token_file, profile_dir=DEFAULT_PROFILE, headless=False, timeout=300):
    """统一登录入口（优先级）：
       1) 持久化 profile 仍有登录态 → 无头静默抓（零交互、不弹窗）
       2) 否则（非 headless）→ 工具自有的【内嵌登录窗口】（pywebview，扫码/密码合一）
       3) 内嵌窗口不可用/失败，或要求 headless → 兜底 Playwright 弹真实 Edge 窗口
       始终抓 access_token + mac_key，写入 token 文件。返回 0/1/2。
    """
    token_file = os.path.abspath(token_file)
    profile = os.path.abspath(profile_dir)

    # 1) 静默：若持久化 profile 仍有登录态，无头直接抓（零交互、不弹窗）
    if os.path.isdir(profile):
        try:
            if refresh_from_profile(token_file, profile, timeout=30):
                tok = load_token(token_file)
                if tok and tok.get("access_token"):
                    print(f"[token_manager] 已用持久化登录态静默取回 token -> {token_file}")
                    return 0
        except Exception as e:
            print(f"[token_manager] 静默续期跳过：{e}")

    # 2) 交互首选：内嵌窗口（仅在有界面时；headless 无意义）
    if not headless:
        try:
            from login_window import embedded_acquire
            print()
            print("=" * 56)
            print("请在弹出的内嵌登录窗口中完成登录（扫码 或 账号密码，二合一）")
            print(f"窗口关闭或等待最多 {timeout} 秒……")
            print("=" * 56)
            print()
            res = embedded_acquire(token_file, timeout=timeout)
            if res.get("ok"):
                save_token(token_file, res["access_token"], res.get("mac_key", ""))
                print()
                print(f"[token_manager] 已获取 token -> {token_file}")
                print(f"[token_manager] access_token: {res['access_token'][:16]}...（长度 {len(res['access_token'])}）")
                print(f"[token_manager] mac_key: {'有' if res['mac_key'] else '无'}（视频下载需要）")
                return 0
            if res.get("reason") == "cancelled":
                # 用户主动关窗未登录：不自动回退弹 Edge（避免打扰），直接返回
                print("[token_manager] 登录窗口已关闭，未获取到 token；可重新运行 acquire。")
                return 1
            # timeout 等情况：继续回退 Playwright
        except ImportError:
            print("[token_manager] 未安装 pywebview，回退到 Playwright 弹窗登录。")
        except Exception as e:
            print(f"[token_manager] 内嵌窗口登录失败（{e}），回退到 Playwright 弹窗登录。")

    # 3) 兜底：Playwright 弹出真实 Edge 窗口（或 headless 模式）
    return _acquire_playwright(token_file, profile, headless, timeout)


# --------------------------------------------------------------------------- #
# 5. 编排：取一个「有效」的 token（供下载脚本调用）
# --------------------------------------------------------------------------- #
def get_valid_token(token_file, auto_refresh=True, profile_dir=DEFAULT_PROFILE,
                    allow_edge_leveldb=True):
    """返回有效 token 的 dict，或 None（需要用户手动登录）。
    优先级：
       1) 文件里的 token 且未过期 → 直接返回（乐观，零交互）
       2) 已过期 + auto_refresh → 用持久化 profile 的 Cookie 无头续期（无需重新登录）
       3) 仍无效 → 兜底读本机日常 Edge 的 Local Storage leveldb
       4) 全部失败 → None（调用方提示用户运行 `token_manager.py acquire`）
    """
    token_file = os.path.abspath(token_file)
    tok = load_token(token_file)
    if tok and not is_expired(tok):
        return tok

    if auto_refresh and os.path.isdir(os.path.abspath(profile_dir)):
        if refresh_from_profile(token_file, profile_dir):
            tok = load_token(token_file)
            if tok:
                return tok

    if allow_edge_leveldb:
        at, mk = read_edge_leveldb()
        if at:
            save_token(token_file, at, mk)
            print(f"[token_manager] 已从本机 Edge 读取并保存 token -> {token_file}")
            return load_token(token_file)

    return None


# --------------------------------------------------------------------------- #
# 6. CLI
# --------------------------------------------------------------------------- #
def _fmt_status(token_file):
    tok = load_token(token_file)
    if not tok:
        print(f"[status] 未找到 token 文件：{os.path.abspath(token_file)}")
        return 2
    at = tok.get("access_token", "")
    exp = tok.get("expires_at", "")
    expired = is_expired(tok)
    live = probe_token(at)
    print(f"[status] token 文件：{os.path.abspath(token_file)}")
    print(f"[status] access_token: {at[:16]}...（长度 {len(at)}）")
    print(f"[status] mac_key: {'有' if tok.get('mac_key') else '无（视频下载会失败）'}")
    print(f"[status] captured_at: {tok.get('captured_at') or '未知'}")
    print(f"[status] expires_at : {exp or '未知'}")
    print(f"[status] 本地过期判定：{'已过期' if expired else '未过期'}")
    print(f"[status] 服务端探测：{('有效' if live is True else '已失效') if live is not None else '无法判定（网络/端点）'}")
    if expired or live is False:
        print("[status] 建议：运行 `python token_manager.py refresh` 或 `acquire` 续期。")
    return 0 if (not expired and live is not False) else 1


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台 统一 token 子系统")
    sub = ap.add_subparsers(dest="cmd")

    pa = sub.add_parser("acquire", help="登录并获取 token（扫码/密码，已登录则静默）")
    pa.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    pa.add_argument("--profile", default=DEFAULT_PROFILE)
    pa.add_argument("--headless", action="store_true", help="无头（仅 profile 已登录时可用）")
    pa.add_argument("--timeout", type=int, default=300)

    pr = sub.add_parser("refresh", help="用持久化 profile 无头续期（不重新登录）")
    pr.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    pr.add_argument("--profile", default=DEFAULT_PROFILE)
    pr.add_argument("--timeout", type=int, default=120)

    ps = sub.add_parser("status", help="查看当前 token 状态")
    ps.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)

    pc = sub.add_parser("check", help="同 status（别名）")
    pc.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return 0

    if args.cmd == "acquire":
        return acquire_token(args.token_file, args.profile, args.headless, args.timeout)
    if args.cmd == "refresh":
        return 0 if refresh_from_profile(args.token_file, args.profile, args.timeout) else 1
    if args.cmd in ("status", "check"):
        return _fmt_status(args.token_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
