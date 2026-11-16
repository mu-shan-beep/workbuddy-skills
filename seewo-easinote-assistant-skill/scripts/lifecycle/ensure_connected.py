#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensure_connected.py - 一次性、幂等地完成「希沃白板 MCP 连接」全生命周期。

把原来的 8 个独立步骤合并为 1 个进程，输出一段精简 JSON，从而：
  * 减少工具调用轮次（从最多 8 次 Bash 调用降为 1 次）；
  * 当客户端已打开且已配置时走「快速通道」，跳过安装检测 / 探测 / 写配置；
  * 仅在确实需要时才启动客户端、写配置、拉起退出监控。

逻辑直接复用同目录模块与共享 MCP 客户端，不重复启动子 Python 进程。
退出码：
  0 = 已就绪（connected=true；need_trust=true 时还需用户在 UI 点「信任」）
  2 = 未安装（已给出下载链接，需安装后重试）
  3 = 端口探测失败（可能未启动 / 未登录，需用户确认登录后重试）
  1 = 其它错误
"""
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit

from lifecycle import (ConfigError, DEFAULT_CONFIG, EXE_NAMES, add as add_config,
                       detect_installation, is_process_running, show_windows,
                       status as config_status)

MCP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mcp")
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

from mcp_client import DEFAULT_PORTS, probe_port  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DOWNLOAD = "https://easinote.seewo.com"
EXES = ",".join(EXE_NAMES)
DETACHED = 0x00000008  # Windows DETACHED_PROCESS


def registered_connection_ready(entry, timeout=2):
    """Return a ready probe result for a registered local endpoint, else ``None``."""
    if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
        return None
    try:
        parsed = urlsplit(entry["url"])
        if not parsed.port:
            return None
    except ValueError:
        return None
    canonical_url = "http://127.0.0.1:%s/mcp" % parsed.port
    if entry["url"] != canonical_url:
        return None
    result = probe_port(parsed.port, timeout=timeout)
    return result if result["state"] == "ready" else None


def wait_for_ready_mcp(ports=DEFAULT_PORTS, wait_seconds=30, interval=2):
    """Return the first tools-ready MCP probe result, or the last failure."""
    deadline = time.time() + max(0, wait_seconds)
    last = {
        "state": "unreachable", "port": None, "url": None,
        "has_tools": False, "tool_count": 0, "detail": "未开始探测",
    }
    while True:
        for port in ports:
            last = probe_port(port)
            if last["state"] == "ready":
                return last
        if time.time() >= deadline:
            return last
        time.sleep(max(0.2, interval))


def result(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(code)


def launch_detached(path, *args):
    try:
        subprocess.Popen(
            [PY, path, *args],
            creationflags=DETACHED, close_fds=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    # ===== 快速通道：配置存在且 tools/list 可用 -> 直接就绪 =====
    try:
        entry = config_status(DEFAULT_CONFIG)
    except ConfigError as exc:
        result({"connected": False, "code": "config_invalid", "detail": str(exc)}, 1)
    registered = isinstance(entry, dict) and bool(entry.get("url"))
    ready = registered_connection_ready(entry) if registered else None
    if ready:
        result({
            "connected": True, "port": ready["port"], "url": ready["url"],
            "already_registered": True, "need_trust": False,
            "skipped": True,
            "detail": "配置已存在且 tools/list 可用，跳过安装/探测/写配置（快速通道）",
        })

    # ===== 完整生命周期（仅快速通道未命中时才执行） =====
    running, _, process_error = is_process_running(EXE_NAMES)
    if process_error:
        result({"connected": False, "code": "process_check_failed", "detail": process_error}, 1)

    if not running:
        det = detect_installation()
        if not (det and det.get("installed") and det.get("exe_path")):
            result({
                "connected": False, "code": "not_installed",
                "detail": "未检测到希沃白板，请先安装后重试。",
                "download": DOWNLOAD,
            }, 2)
        # 启动客户端（分离进程，避免阻塞）
        exe = det["exe_path"]
        try:
            subprocess.Popen([exe], creationflags=DETACHED, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:  # noqa: BLE001
            result({"connected": False, "code": "launch_failed", "detail": str(e)}, 1)
        # 轮询进程出现（最多 ~20s）
        for _ in range(20):
            running, _, process_error = is_process_running(EXE_NAMES)
            if process_error:
                break
            if running:
                running = True
                break
            time.sleep(1)
        if not running:
            result({
                "connected": False, "code": "launch_timeout",
                "detail": "启动客户端超时，请手动打开希沃白板后重试。",
            }, 1)
        # 显示窗口到前台
        show_windows(EXE_NAMES)

    # ===== 探测 MCP 端口（含 tools 验证，确认 MCP 真在提供能力） =====
    probe = wait_for_ready_mcp()
    if probe["state"] != "ready":
        result({
            "connected": False, "code": "port_unavailable",
            "detail": "未探测到可用 MCP 端口。若客户端已打开但仍失败，请在客户端完成登录后重试；"
                      "并确认客户端设置中已开启 MCP 服务。",
            "hint": "login_required",
        }, 3)

    url = probe["url"]
    port = probe["port"]

    # ===== 写配置（幂等：已存在则不强加 need_trust） =====
    just_added = not registered
    needs_write = not registered or entry.get("url") != url
    if needs_write:
        try:
            add_config(DEFAULT_CONFIG, url)
        except ConfigError as exc:
            result({"connected": False, "code": "config_invalid", "detail": str(exc)}, 1)

    # ===== 启动退出监控（后台分离，客户端退出后自动移除配置） =====
    launch_detached(os.path.join(HERE, "monitor_seewo.py"), "--exe", EXES,
                    "--interval", "15", "--url", url)

    result({
        "connected": True, "port": port, "url": url,
        "already_registered": registered,
        # 仅「本次新写入配置」时才需要用户点「信任」；已注册复用时默认可用
        "need_trust": just_added,
        "skipped": False,
        "detail": "已写入 MCP 配置" if just_added else
                  ("已更新 MCP 配置" if needs_write else "配置已存在，已复用"),
    })


if __name__ == "__main__":
    main()
