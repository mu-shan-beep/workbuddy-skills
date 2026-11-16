#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp_client.py — 希沃白板 MCP 的轻量 streamable-http 客户端（仅标准库）。

供 tools/refresh_capabilities.py 与 scripts/courseware/* 复用，避免每个脚本
都重复手写 MCP 握手（initialize / tools/list / tools/call）与 SSE 解析逻辑。

用法（作为模块导入）：
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # mcp/
    from mcp_client import McpHttpSession, find_live_port

    s = McpHttpSession("http://127.0.0.1:7916/mcp")
    s.initialize()
    o = s.tools_call("get_current_courseware_info", {})
    print(McpHttpSession.text_of(o))
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_PORTS = [7916, 7917, 13247, 19463, 27733]
PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "seewo-assistant-pc"


class McpHttpSession:
    """一个到希沃白板 MCP 端点（streamable-http）的会话。"""

    def __init__(self, url, timeout=60):
        self.url = url
        self.timeout = timeout
        self.session = None

    def _post(self, payload):
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self.session:
            h["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                st = resp.status
                ns = resp.headers.get("Mcp-Session-Id") or self.session
                raw = resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            st = e.code
            ns = e.headers.get("Mcp-Session-Id") or self.session
            raw = e.read().decode("utf-8", "ignore")
        if ns:
            self.session = ns
        return st, raw

    @staticmethod
    def parse_sse(raw):
        """解析 MCP 的响应：可能是纯 JSON，也可能是 SSE（data: 行）。"""
        raw = (raw or "").strip()
        if raw.startswith("{"):
            try:
                return json.loads(raw)
            except ValueError:
                return None
        last = None
        for ln in raw.splitlines():
            ln = ln.strip()
            if ln.startswith("data:"):
                d = ln[5:].strip()
                if d:
                    try:
                        last = json.loads(d)
                    except ValueError:
                        pass
        return last

    def initialize(self):
        status, raw = self._post(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": CLIENT_NAME, "version": "1.0"}}}
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return status, raw

    def tools_list(self):
        st, raw = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                              "params": {}})
        return st, self.parse_sse(raw)

    def tools_call(self, name, arguments, rid=3):
        st, raw = self._post({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}})
        return st, self.parse_sse(raw)

    @staticmethod
    def text_of(o):
        """从 tools/call 的 result.content 中取出合并后的文本内容。"""
        if not isinstance(o, dict):
            return str(o)
        res = o.get("result")
        if not isinstance(res, dict):
            return json.dumps(o, ensure_ascii=False)
        out = []
        for c in res.get("content", []):
            if isinstance(c, dict) and c.get("type") == "text":
                out.append(c.get("text", ""))
        return "\n".join(out)

    @staticmethod
    def walk_find(o, keys):
        """在任意嵌套结构里找第一个命中 keys 的字符串值（用于提取 shellId 等）。"""
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys and isinstance(v, str):
                    return v
                hit = McpHttpSession.walk_find(v, keys)
                if hit:
                    return hit
        elif isinstance(o, list):
            for it in o:
                hit = McpHttpSession.walk_find(it, keys)
                if hit:
                    return hit
        return None

    @staticmethod
    def find_shell(o):
        """从 en_find_shells / new_cloud_courseware* 的返回里取出 shell id。"""
        return McpHttpSession.walk_find(o, ["id", "shellId"])

    @staticmethod
    def find_shell_named(o, name):
        """在 en_find_shells 返回的 shells 列表里按课件名匹配 shell id。

        多 Shell 并存时 walk_find 会拿到第一个 id（可能是别的课件），必须按名匹配。
        客户端存的课件名可能带书名号（如「《观沧海》」），两种写法都试。
        """
        matches = McpHttpSession.find_shells_named(o, name)
        return matches[0] if matches else None

    @staticmethod
    def find_shells_named(o, name):
        """Return every exact-name shell id so callers can reject ambiguity."""
        try:
            data = json.loads(McpHttpSession.text_of(o))
        except ValueError:
            return []
        shells = data.get("shells") if isinstance(data, dict) else None
        if not isinstance(shells, list) or not name:
            return []
        wanted = {name, "《%s》" % name.strip("《》")}
        return [shell["id"] for shell in shells
                if (isinstance(shell, dict) and shell.get("id")
                    and shell.get("coursewareName") in wanted)]

    @staticmethod
    def collect(o, keys):
        """递归收集任意嵌套结构里所有命中 keys 的字符串值（用于取全部元素 id 等）。

        注意：会把 shellContext.id 也收进来；取元素 id 请用 element_ids。
        """
        out = []
        if isinstance(o, dict):
            for k, v in o.items():
                if k in keys and isinstance(v, str):
                    out.append(v)
                out.extend(McpHttpSession.collect(v, keys))
        elif isinstance(o, list):
            for it in o:
                out.extend(McpHttpSession.collect(it, keys))
        return out

    @staticmethod
    def element_ids(o, types=None):
        """从 get_elements 返回中精确取 elements[].id（避免 shellContext.id 污染）。

        types 为可选的类型集合过滤（如 {"Picture"}）。本环境实测：图片元素类型是
        "Picture"，elementTypes 过滤值 "image"/"Image" 永远查不到。
        """
        try:
            data = json.loads(McpHttpSession.text_of(o))
        except ValueError:
            return []
        elements = data.get("elements") if isinstance(data, dict) else None
        if not isinstance(elements, list):
            return []
        out = []
        for e in elements:
            if not isinstance(e, dict) or not e.get("id"):
                continue
            if types and e.get("type") not in types:
                continue
            out.append(e["id"])
        return out

    @staticmethod
    def added_element_id(o):
        """从 add_*_element 返回中精确取新元素 id（顶层 id + type 字段，排除 shellContext）。"""
        try:
            data = json.loads(McpHttpSession.text_of(o))
        except ValueError:
            return None
        if isinstance(data, dict) and data.get("id") and data.get("type"):
            return data["id"]
        return None

    @staticmethod
    def is_error(o):
        """粗略判断 tools/call 是否返回错误（isError 或含错误文案）。"""
        if not isinstance(o, dict):
            return False
        res = o.get("result")
        if isinstance(res, dict) and res.get("isError"):
            return True
        txt = McpHttpSession.text_of(o)
        return ("未找到" in txt) or ("not implemented" in txt.lower()) \
            or ("error" in txt.lower() and "失败" in txt)


def parse_page_number(text):
    """从 get_slide_info 的返回文本中解析当前页码（1-base）。

    兼容三种返回形态：
      1) 纯 JSON：{"pageNumber": 3} / {"slideNumber": 3} / {"currentSlideNumber": 3}；
      2) 文本中嵌 JSON 片段："pageNumber": 3；
      3) 中文 Markdown（本环境实测）：`序号(1-base): 3`、`当前页码：3`、`第 3 页` 等。
    解析失败返回 None。
    """
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key in ("pageNumber", "slideNumber", "currentSlideNumber"):
                value = data.get(key)
                if value is not None:
                    return int(value)
    except (ValueError, TypeError):
        pass
    match = re.search(r'"(?:pageNumber|slideNumber|currentSlideNumber)"\s*:\s*(\d+)', text)
    if match:
        return int(match.group(1))
    for pattern in (r"序号\s*[（(]1-base[)）]\s*[:：]?\s*(\d+)",
                    r"(?:当前)?页码\s*[:：]?\s*(\d+)",
                    r"当前页\s*[:：]?\s*(\d+)",
                    r"第\s*(\d+)\s*页"):
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def probe_port(port, timeout=3):
    """Classify an MCP candidate as unreachable, endpoint-only, or ready."""
    url = "http://127.0.0.1:%d/mcp" % port
    session = McpHttpSession(url, timeout=timeout)
    try:
        initialize_status, initialize_raw = session.initialize()
        status, payload = session.tools_list()
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "state": "unreachable", "port": port, "url": url,
            "has_tools": False, "tool_count": 0, "detail": "连接失败：%s" % exc,
        }

    initialize_payload = McpHttpSession.parse_sse(initialize_raw)
    initialized_as_mcp = (
        bool(session.session)
        or (isinstance(initialize_payload, dict) and "jsonrpc" in initialize_payload)
        or "protocolVersion" in (initialize_raw or "")
    )
    if not initialized_as_mcp:
        return {
            "state": "unreachable", "port": port, "url": url,
            "has_tools": False, "tool_count": 0,
            "detail": "HTTP %s 响应不是 MCP initialize 握手" % initialize_status,
        }

    tools = ((payload or {}).get("result") or {}).get("tools") if isinstance(payload, dict) else None
    if status in (200, 202) and isinstance(tools, list) and tools:
        return {
            "state": "ready", "port": port, "url": url,
            "has_tools": True, "tool_count": len(tools), "detail": "tools/list 可用",
        }
    return {
        "state": "endpoint", "port": port, "url": url,
        "has_tools": False, "tool_count": len(tools) if isinstance(tools, list) else 0,
        "detail": "MCP 端点可达，但 tools/list 未返回可用工具",
    }


def find_live_port(ports=None, timeout=3):
    """依次探测候选端口，返回第一个 MCP 端点可达且带 tools 的端口。

    与 scripts/lifecycle/lifecycle.py 的 ``probe`` 子命令共用本模块的探测原语；
    主流程仍建议用 lifecycle.py probe / ensure_connected.py。
    """
    ports = ports or DEFAULT_PORTS
    for port in ports:
        if probe_port(port, timeout=timeout)["state"] == "ready":
            return port
    return None


if __name__ == "__main__":
    # 直接运行可做连通性自检：python mcp_client.py [port]
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7916
    s = McpHttpSession("http://127.0.0.1:%d/mcp" % port)
    try:
        s.initialize()
        st, o = s.tools_list()
        tools = (o or {}).get("result", {}).get("tools", []) if isinstance(o, dict) else []
        print(json.dumps({"port": port, "reachable": True,
                          "tool_count": len(tools)}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"port": port, "reachable": False, "error": str(e)},
                         ensure_ascii=False))
