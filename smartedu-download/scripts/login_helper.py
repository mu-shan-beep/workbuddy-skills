#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台统一登录入口助手（v1.1.1 新增）

功能：
  - 登录前自动检测 basic.smartedu.cn 是否已登录（用保护接口探活）
  - 已登录：直接输出提示，由上层流程继续下载
  - 未登录：启动本地 HTTP 服务，提供统一登录页（支持三种方式）
      1. 二维码扫码登录（跳转 uc.basic.smartedu.cn）
      2. 用户名密码登录（跳转 uc.basic.smartedu.cn）
      3. 书签一键取 token（bookmarklet，需浏览器已登录）

用法：
  python login_helper.py --token-file ./smartedu_token.txt --open-browser
  python login_helper.py --token-file ./smartedu_token.txt --check-only
  python login_helper.py --token-file ./smartedu_token.txt --auto-token-after-login
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DEFAULT_PORTS = list(range(17778, 17789))  # 17778-17788
TOKEN_FILE_DEFAULT = "./smartedu_token.txt"
AUTH_CHECK_URL = "https://basic.smartedu.cn/rest/api/user/session"

UC_LOGIN_URL = (
    "https://uc.basic.smartedu.cn/"
    "?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538"
    "#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true"
)


def is_logged_in():
    """探测 basic.smartedu.cn 是否已登录（静默，无副作用）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            AUTH_CHECK_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://basic.smartedu.cn/",
            },
        )
        resp = urllib.request.urlopen(req, timeout=8)
        body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        return bool(data.get("code") == 0 and data.get("data"))
    except Exception:
        return False


def find_free_port(preferred=DEFAULT_PORTS):
    for port in preferred:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_bookmarklet_js(port):
    js = """
(function(){
  var token=null, keys=Object.keys(localStorage);
  for(var i=0;i<keys.length;i++){
    var k=keys[i], v=localStorage.getItem(k)||'';
    if(!v||v.indexOf('access_token')===-1) continue;
    try{
      var raw=JSON.parse(v), inner=(raw&&raw.value)?JSON.parse(raw.value):raw;
      if(inner&&inner.access_token&&inner.access_token.length>10){token=inner.access_token;break;}
    }catch(e){}
  }
  if(!token){alert('未在 Local Storage 找到 access_token，请确认已登录 basic.smartedu.cn');return;}
  fetch('http://127.0.0.1:"""+str(port)+"""/token',{method:'POST',mode:'no-cors',keepalive:true,body:new Blob([token],{type:'text/plain'})});
  alert('TOKEN 已发送，请回到 WorkBuddy 继续下载。');
})();"""
    return js.strip().replace('\n', ' ').replace('  ', ' ').strip()


def build_html(port):
    bookmarklet = build_bookmarklet_js(port)
    bm_url = "javascript:" + bookmarklet
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>智慧教育平台登录</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Microsoft YaHei",sans-serif;max-width:680px;margin:32px auto;padding:0 20px;line-height:1.6;background:#f5f7fa;color:#222;}}
  h1{{color:#1a73e8;font-size:20px;margin-bottom:4px;}}
  .subtitle{{color:#666;font-size:13px;margin-bottom:24px;}}
  .card{{background:#fff;border-radius:10px;padding:20px;margin:0 0 16px;box-shadow:0 1px 4px rgba(0,0,0,.08);}}
  .card h3{{margin:0 0 12px;font-size:15px;color:#333;}}
  .btn{{display:inline-block;background:#1a73e8;color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none;font-size:14px;margin:4px 6px 4px 0;}}
  .btn-secondary{{background:#fff;color:#1a73e8;border:1px solid #1a73e8;}}
  .btn-green{{background:#34a853;}}
  .hint{{font-size:12px;color:#888;margin-top:6px;}}
  ol{{padding-left:20px;margin:0;}}
  li{{margin:6px 0;}}
  #status{{margin-top:16px;padding:12px;border-radius:6px;font-size:14px;background:#e8f5e9;color:#2e7d32;display:none;}}
  .status-wait{{background:#fff3cd;color:#856404;display:block;}}
  .status-ok{{background:#d4edda;color:#155724;display:block;}}
  .spinner{{display:inline-block;width:14px;height:14px;border:2px solid #856404;border-top-color:transparent;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px;}}
  @keyframes spin{{to{{transform:rotate(360deg)}}}}
</style>
</head>
<body>
<h1>国家智慧教育平台登录</h1>
<p class="subtitle">选择一种方式完成登录并获取 access_token</p>

<div class="card">
  <h3>&#x1F512; 方式一：扫码登录（推荐）</h3>
  <ol>
    <li>点击下方按钮，跳转到官方 UC 登录页。</li>
    <li>用「智慧中小学」APP 扫描二维码完成登录。</li>
    <li>登录成功后，页面会显示「方式二」的书签按钮，点击即可取 token。</li>
  </ol>
  <p style="margin-top:12px;">
    <a class="btn btn-green" href="{UC_LOGIN_URL}" target="_blank">打开扫码登录页</a>
  </p>
  <p class="hint">二维码登录页同时支持用户名密码切换，任选其一。</p>
</div>

<div class="card" id="token-card" style="display:none;">
  <h3>&#x1F517; 方式二：书签一键取 token</h3>
  <ol>
    <li>把下方「获取TOKEN」按钮拖到浏览器书签栏。</li>
    <li>在已登录的 basic.smartedu.cn 页面点击该书签。</li>
    <li>token 会自动回传并写入本地文件。</li>
  </ol>
  <p style="margin-top:12px;">
    <a class="btn" href="{bm_url}">获取TOKEN</a>
  </p>
  <p class="hint">若书签不便使用，可手动粘贴 token（见下方）。</p>
</div>

<div class="card">
  <h3>&#x1F4CB; 方式三：手动粘贴 token</h3>
  <p>若以上均不方便，可从 DevTools → Application → Local Storage 复制整个 value 粘贴：</p>
  <form action="/token" method="POST">
    <textarea name="token" placeholder="粘贴含 access_token 的 Local Storage value 或裸 token" style="width:100%;height:90px;margin-top:8px;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:12px;font-family:monospace;"></textarea>
    <button type="submit" class="btn" style="margin-top:8px;">提交 TOKEN</button>
  </form>
</div>

<div class="card">
  <h3>&#x1F4E1; 接收状态</h3>
  <p id="status" class="status-wait"><span class="spinner"></span>等待登录 &amp; 回传 token……</p>
  <p class="hint">本地接收端口：<strong>{port}</strong></p>
</div>

<script>
function checkStatus(){{
  fetch('/status').then(r=>r.text()).then(t=>{{
    var el=document.getElementById('status');
    if(t.indexOf('已收到')!==-1){{
      el.className='status-ok'; el.innerHTML='\u2705 TOKEN 已收到，请回到 WorkBuddy 继续下载。';
      document.getElementById('token-card').style.display='block';
    }} else {{
      el.innerHTML='<span class="spinner"></span>等待登录 &amp; 回传 token……';
      setTimeout(checkStatus, 1500);
    }}
  }}).catch(()=>{{setTimeout(checkStatus,1500);}});
}}
checkStatus();
</script>
</body>
</html>"""


class LoginHandler(BaseHTTPRequestHandler):
    token_received = False
    token_value = None
    token_file = None
    shutdown_event = threading.Event()

    def log_message(self, fmt, *args):
        print(f"[login_helper] {fmt % args}")

    def _set_headers(self, status=200, content_type="text/html; charset=utf-8", allow_cors=True):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if allow_cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._set_headers()
            self.wfile.write(build_html(self.server.server_port).encode("utf-8"))
        elif path == "/status":
            self._set_headers(content_type="text/plain; charset=utf-8")
            if LoginHandler.token_received:
                self.wfile.write(f"已收到 TOKEN，已写入 {LoginHandler.token_file}".encode("utf-8"))
            else:
                self.wfile.write("等待回传……".encode("utf-8"))
        else:
            self._set_headers(404)
            self.wfile.write(b"Not Found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/token":
            self._set_headers(404)
            self.wfile.write(b"Not Found")
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)
        body_text = raw_body.decode("utf-8", errors="replace").strip()
        token = None
        if body_text.startswith("token="):
            from urllib.parse import unquote_plus
            token = unquote_plus(body_text[len("token="):])
        else:
            token = body_text

        # 提取 access_token（兼容裸 token / JSON value / 内层 JSON）
        token = (token or "").strip()
        if not token:
            self._set_headers(400, content_type="text/plain; charset=utf-8")
            self.wfile.write(b"Bad Request: empty token")
            return

        def extract(tok):
            tok = tok.strip()
            if not tok:
                return None
            if len(tok.split()) == 1 and tok.startswith(("eyJ", "A", "B", "C", "D", "E", "F")):
                return tok
            try:
                obj = json.loads(tok)
                if isinstance(obj, dict):
                    if "access_token" in obj:
                        return obj["access_token"]
                    if "value" in obj and isinstance(obj["value"], str):
                        try:
                            inner = json.loads(obj["value"])
                            if isinstance(inner, dict) and "access_token" in inner:
                                return inner["access_token"]
                        except Exception:
                            pass
            except Exception:
                pass
            return None

        extracted = extract(token)
        if not extracted or len(extracted) < 10:
            self._set_headers(400, content_type="text/plain; charset=utf-8")
            self.wfile.write(b"Bad Request: cannot extract access_token")
            return

        LoginHandler.token_value = extracted
        LoginHandler.token_received = True

        out_path = Path(LoginHandler.token_file).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(extracted, encoding="utf-8")
        print(f"[login_helper] 已收到并保存 access_token -> {out_path}")

        self._set_headers(200, content_type="text/plain; charset=utf-8")
        self.wfile.write(b"OK")

        LoginHandler.shutdown_event.set()
        threading.Timer(1.0, self.server.shutdown).start()


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台统一登录入口助手")
    ap.add_argument("--token-file", default=TOKEN_FILE_DEFAULT, help="token 保存路径")
    ap.add_argument("--port", type=int, default=0, help="本地服务端口，0 表示自动选择")
    ap.add_argument("--check-only", action="store_true", help="仅检测登录状态，不启动服务")
    ap.add_argument("--open-browser", action="store_true", help="自动在浏览器打开本地登录页")
    ap.add_argument("--auto-token-after-login", action="store_true",
                    help="登录成功后自动尝试从 LocalStorage 取 token 写入文件（需浏览器配合）")
    args = ap.parse_args()

    # 1) 检测是否已登录
    logged_in = is_logged_in()
    print(f"[login_helper] 登录状态检测：{'已登录' if logged_in else '未登录'}")

    if args.check_only:
        sys.exit(0 if logged_in else 1)

    if logged_in and args.auto_token_after_login:
        # 已登录，但 token 还没写入文件——提示用户手动点书签或用其他方式
        print("[login_helper] 浏览器已登录，但本机尚无 token 文件。")
        print("  请在已登录的浏览器中打开 http://127.0.0.1:{port}/ 并使用书签取 token。")
        # 仍起接收器供书签使用
        port = args.port if args.port else find_free_port()
        LoginHandler.token_file = args.token_file
        server = HTTPServer(("127.0.0.1", port), LoginHandler)
        print(f"\n[login_helper] 接收器已启动：http://127.0.0.1:{port}/")
        print("[login_helper] 请在浏览器中打开上述地址，使用书签一键取 token。\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return

    if not logged_in:
        print("[login_helper] 未检测到登录态，启动统一登录入口……")
        port = args.port if args.port else find_free_port()
        LoginHandler.token_file = args.token_file

        if args.open_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")

        server = HTTPServer(("127.0.0.1", port), LoginHandler)
        print(f"\n[login_helper] 登录入口已启动：http://127.0.0.1:{port}/")
        print("[login_helper] 请在此页面完成登录，然后使用书签或手动粘贴取 token。\n")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return

    # 兜底：已登录但没要求自动取 token
    print("[login_helper] 已登录，可直接继续下载流程。")
    if not Path(args.token_file).exists():
        print("[login_helper] 但 token 文件不存在，请从浏览器书签取 token 后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
