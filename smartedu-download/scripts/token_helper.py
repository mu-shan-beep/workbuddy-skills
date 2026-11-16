#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智慧教育平台 access_token 自动获取助手

功能：
  - 在本地启动一个临时 HTTP 接收器（默认 127.0.0.1:17777，端口被占用自动顺延）
  - 生成一段 bookmarklet，用户在已登录 basic.smartedu.cn 的页面上点击后，
    自动从 Local Storage 提取 access_token 并通过 fetch(keepalive) 回传到本地
  - 收到 token 后自动写入文件，供 download_course.py 使用
  - 新增 --login-page 模式：一键开启统一登录入口（含已登录检测）

用法：
  python token_helper.py --token-file ./smartedu_token.txt [--port 17777] [--timeout 300]
  python token_helper.py --token-file ./smartedu_token.txt --login-page
  python token_helper.py --check --token-file ./smartedu_token.txt
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

DEFAULT_PORTS = list(range(17777, 17788))  # 17777-17787
TOKEN_FILE_DEFAULT = "./smartedu_token.txt"
AUTH_CHECK_URL = "https://basic.smartedu.cn/rest/api/user/session"


def find_free_port(preferred=DEFAULT_PORTS):
    """从候选列表找一个可绑定的端口。"""
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


def extract_access_token_from_text(text):
    """兼容用户可能复制整个 Local Storage value 或只复制 access_token 的情况。"""
    text = text.strip()
    if not text:
        return None
    if len(text.split()) == 1 and text.startswith(("eyJ", "A", "B", "C", "D", "E", "F")):
        return text
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "value" in obj and isinstance(obj["value"], str):
            inner = json.loads(obj["value"])
            if isinstance(inner, dict) and "access_token" in inner:
                return inner["access_token"]
    except Exception:
        pass
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "access_token" in obj:
            return obj["access_token"]
    except Exception:
        pass
    return None


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


def make_nd_auth_header(token):
    """平台文件鉴权弱 MAC 头：服务端仅校验 id 中的 token 是否有效。"""
    return {
        "X-ND-AUTH": f'MAC id="{token}",nonce="0",mac="0"',
        "Referer": "https://basic.smartedu.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }


def check_token_file(token_file, activity_id):
    """校验 token 是否有效。"""
    import urllib.request
    import urllib.error

    p = Path(token_file).expanduser()
    if not p.exists():
        print(f"[check] token 文件不存在：{p}")
        return False
    token = p.read_text(encoding="utf-8").strip()
    if not token or len(token) < 10:
        print("[check] token 文件为空或太短。")
        return False

    details_url = (
        "https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/national_lesson/resources/details/"
        f"{activity_id}.json"
    )
    storage_urls = []
    try:
        req = urllib.request.Request(
            details_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://basic.smartedu.cn/"},
        )
        data = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", errors="replace")
        obj = json.loads(data)
        rels = obj.get("relations", {})
        for _k, items in rels.items():
            if isinstance(items, list):
                for it in items:
                    for ti in (it.get("ti_items") or []):
                        storage_urls.extend(ti.get("ti_storages") or [])
    except Exception as e:
        print(f"[check] 拉取资源详情失败：{e}")
        return False

    if not storage_urls:
        print("[check] 未能从详情中提取文件 URL（该 activityId 可能无资源）。")
        return False

    invalid_hdr = make_nd_auth_header("__INVALID_TOKEN_FOR_PROBE__")
    real_hdr = make_nd_auth_header(token)

    for url in storage_urls[:60]:
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers=invalid_hdr), timeout=20).read(1)
            continue
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403):
                continue
        except Exception:
            continue
        try:
            urllib.request.urlopen(urllib.request.Request(url, headers=real_hdr), timeout=20).read(1)
            print("[check] �� token 有效（文件鉴权通过）。")
            return True
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print("[check] ��� token 失效/过期（HTTP 401/403）。请重新获取。")
                return False
            print(f"[check] ⚠ 探测返回 HTTP {e.code}。")
            return False
        except Exception as e:
            print(f"[check] ⚠ 探测异常：{e}")
            return False

    print("[check] ⚠ 候选 URL 均为公开资源，建议直接发起下载验证。")
    return False


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
    """生成统一登录入口页面（含页内按钮取 token，无需书签）。"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>智慧教育平台 TOKEN 自动获取</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; }}
  h1 {{ color: #1a73e8; font-size: 22px; }}
  .card {{ background: #f8f9fa; border-radius: 8px; padding: 16px; margin: 16px 0; }}
  .btn {{ display: inline-block; background: #1a73e8; color: #fff; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-size: 15px; cursor: pointer; border: none; }}
  .btn-green {{ background: #34a853; }}
  .btn:hover {{ opacity: 0.9; }}
  .code {{ background: #e8eaed; padding: 12px; border-radius: 6px; font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap; word-break: break-all; }}
  ol {{ padding-left: 20px; }}
  ol li {{ margin: 8px 0; }}
  textarea {{ width: 100%; height: 80px; margin-top: 8px; }}
  button {{ margin-top: 8px; }}
  .status {{ color: #34a853; font-weight: bold; }}
  .error {{ color: #ea4335; }}
</style>
</head>
<body>
<h1>国家智慧教育平台 TOKEN 自动获取</h1>
<div class="card">
  <h3>步骤 1：登录</h3>
  <p>点击下方按钮，跳转到官方登录页（支持扫码登录 / 用户名密码登录）：</p>
  <a class="btn btn-green" href="https://uc.basic.smartedu.cn/?sdp-app-id=95dda6f5-3b56-45da-af90-d204993b7538#/login?re_login=true&redirect_uri=https://basic.smartedu.cn/&send_uckey=true" target="_blank">前往登录</a>
</div>
<div class="card">
  <h3>步骤 2：获取 TOKEN</h3>
  <p>登录成功后，点击下方按钮自动读取 LocalStorage 中的 access_token 并发送：</p>
  <button class="btn" onclick="getToken()">获取 TOKEN</button>
  <p id="result" style="margin-top:12px; color:#666;"></p>
</div>
<div class="card">
  <h3>手动兜底</h3>
  <p>若自动读取失败，请从 DevTools → Application → Local Storage → access_token 复制值粘贴到这里：</p>
  <form action="/token" method="POST">
    <textarea name="token" placeholder="粘贴含 access_token 的 Local Storage value 或裸 token"></textarea>
    <button type="submit">提交 TOKEN</button>
  </form>
</div>
<div class="card">
  <h3>接收状态</h3>
  <p id="status">等待回传……</p>
  <p class="hint">本地接收端口：{port}</p>
</div>
<script>
function getToken(){{
  var token = null;
  var keys = Object.keys(localStorage);
  for (var i = 0; i < keys.length; i++) {{
    var k = keys[i];
    var v = localStorage.getItem(k) || '';
    if (!v || v.indexOf('access_token') === -1) continue;
    try {{
      var raw = JSON.parse(v);
      var inner = (raw && raw.value) ? JSON.parse(raw.value) : raw;
      if (inner && inner.access_token && inner.access_token.length > 10) {{
        token = inner.access_token;
        break;
      }}
    }} catch (e) {{}}
  }}
  var resultEl = document.getElementById('result');
  var statusEl = document.getElementById('status');
  if (!token) {{
    resultEl.innerHTML = '<span class="error">未在 Local Storage 找到 access_token，请确认已登录 basic.smartedu.cn</span>';
    return;
  }}
  fetch('http://127.0.0.1:{port}/token', {{
    method: 'POST',
    mode: 'no-cors',
    keepalive: true,
    body: new Blob([token], {{type: 'text/plain'}})
  }});
  resultEl.innerHTML = '<span class="status">✅ TOKEN 已发送，请回到 WorkBuddy 继续下载。</span>';
  statusEl.textContent = '已收到 TOKEN，已写入文件';
}}
function checkStatus(){{
  fetch('/status',{{method:'GET'}}).then(r=>r.text()).then(t=>{{
    document.getElementById('status').textContent = t;
    if (t.indexOf('已收到') === -1) setTimeout(checkStatus, 1000);
  }}).catch(()=>{{ document.getElementById('status').textContent = '等待回传……'; setTimeout(checkStatus, 1000); }});
}}
checkStatus();
</script>
</body>
</html>"""
    return html


class TokenHandler(BaseHTTPRequestHandler):
    token_received = False
    token_value = None
    token_file = None
    shutdown_event = threading.Event()

    def log_message(self, fmt, *args):
        print(f"[token_helper] {fmt % args}")

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
            if TokenHandler.token_received:
                self.wfile.write(f"已收到 TOKEN，已写入 {TokenHandler.token_file}".encode("utf-8"))
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

        extracted = extract_access_token_from_text(token) if token else None
        if not extracted:
            self._set_headers(400, content_type="text/plain; charset=utf-8")
            self.wfile.write(b"Bad Request: cannot extract access_token")
            return

        TokenHandler.token_value = extracted
        TokenHandler.token_received = True

        out_path = Path(TokenHandler.token_file).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(extracted, encoding="utf-8")
        print(f"[token_helper] 已收到并保存 access_token -> {out_path}")

        self._set_headers(200, content_type="text/plain; charset=utf-8")
        self.wfile.write(b"OK")

        TokenHandler.shutdown_event.set()
        threading.Timer(1.0, self.server.shutdown).start()


def mode_login_page(token_file, port, open_browser):
    """启动统一登录入口（含已登录检测 + 三种取 token 方式）。"""
    logged_in = is_logged_in()
    print(f"[token_helper] 登录状态检测：{'已登录' if logged_in else '未登录'}")

    actual_port = port if port else find_free_port()
    TokenHandler.token_file = token_file

    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{actual_port}/")

    server = HTTPServer(("127.0.0.1", actual_port), TokenHandler)
    print(f"\n[token_helper] 登录入口已启动：http://127.0.0.1:{actual_port}/")
    print("[token_helper] 请在浏览器中完成登录，然后使用书签或手动粘贴取 token。\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    ap = argparse.ArgumentParser(description="智慧教育平台 access_token 自动获取助手")
    ap.add_argument("--token-file", default=TOKEN_FILE_DEFAULT, help="token 保存路径")
    ap.add_argument("--port", type=int, default=0, help="接收端口，0 表示自动选择（默认 17777 起）")
    ap.add_argument("--timeout", type=int, default=300, help="无 token 时自动关闭秒数，默认 300")
    ap.add_argument("--check", action="store_true",
                    help="仅校验已有 token 文件是否有效（不启动接收器）；配合 --check-activity-id")
    ap.add_argument("--check-activity-id", default="713d4809-e590-4f80-bc11-270dc87d01f5",
                    help="--check 时用于探测的 activityId（默认取一个公开课程）")
    ap.add_argument("--login-page", action="store_true",
                    help="启动统一登录入口（含已登录检测 + 二维码/密码登录 + 书签取 token）")
    ap.add_argument("--open-browser", action="store_true", help="自动在浏览器打开本地登录页")
    args = ap.parse_args()

    if args.check:
        ok = check_token_file(args.token_file, args.check_activity_id)
        sys.exit(0 if ok else 2)

    if args.login_page:
        mode_login_page(args.token_file, args.port, args.open_browser)
        return

    port = args.port if args.port else find_free_port()
    TokenHandler.token_file = args.token_file

    server = HTTPServer(("127.0.0.1", port), TokenHandler)

    def timeout_shutdown():
        if not TokenHandler.token_received:
            print(f"[token_helper] {args.timeout} 秒内未收到 token，自动关闭。")
            server.shutdown()

    if args.timeout > 0:
        threading.Timer(args.timeout, timeout_shutdown).start()

    print(f"\n[token_helper] 接收器已启动：http://127.0.0.1:{port}/")
    print(f"[token_helper] 请在已登录 basic.smartedu.cn 的浏览器中打开上述地址，按页面提示使用书签小工具。\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

    if TokenHandler.token_received:
        print("\n[token_helper] token 已就绪，可继续运行 download_course.py。")
        print(f"[token_helper] token 文件：{args.token_file}")
    else:
        print("\n[token_helper] 未能获取 token，请重试或使用 DevTools 手动获取。")
        sys.exit(1)


if __name__ == "__main__":
    main()
