#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified diagnostics and reusable primitives for the Seewo MCP lifecycle.

The module owns Windows-client discovery, process/window inspection, and
WorkBuddy configuration management.  Its ``main`` function exposes these
operations as stable diagnostic subcommands; the daily connection and exit
monitor remain separate entry points because they have distinct lifetimes.
"""
import argparse
import csv
import ctypes
import ctypes.wintypes
import io
import json
import os
import subprocess
import sys
import tempfile
import time


EXE_NAMES = ("EasiNote.exe", "EasiNote5.exe", "SeewoEasiNote.exe")
SERVER_KEY = "seewo-easinote-assistant-skill"
DEFAULT_CONFIG = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")
SEEWO_KEYWORDS = ("希沃", "seewo", "easinote", "easinote5")
COMMON_ROOTS = [
    r"C:\\Program Files (x86)\\Seewo",
    r"C:\\Program Files\\Seewo",
    r"C:\\Program Files\\Seewo\\EasiNote5",
    r"D:\\Program Files\\Seewo",
    r"D:\\Program Files (x86)\\Seewo",
]

try:
    import winreg
except ImportError:
    winreg = None

try:
    _USER32 = ctypes.windll.user32
except AttributeError:
    _USER32 = None

SW_RESTORE = 9


def no_window_creationflags():
    """Prevent Windows console helpers such as ``tasklist`` from flashing."""
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def parse_exe_names(value=None):
    """Return normalized executable names in their documented order."""
    if value is None:
        return list(EXE_NAMES)
    return [name.strip() for name in value.split(",") if name.strip()]


def parse_tasklist_csv(output, exe_names=EXE_NAMES):
    """Return matching PIDs from ``tasklist /FO CSV /NH`` output."""
    wanted = {name.strip().lower() for name in exe_names if name.strip()}
    pids = []
    for row in csv.reader(io.StringIO(output or "")):
        if not row or row[0].strip().lower() not in wanted:
            continue
        try:
            pids.append(int(row[1]))
        except (ValueError, IndexError):
            continue
    return pids


def get_process_pids(exe_names=EXE_NAMES):
    """Return ``(pids, error)`` without opening a visible console window."""
    try:
        output = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=no_window_creationflags(),
        ).stdout
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    return parse_tasklist_csv(output, exe_names), None


def is_process_running(exe_names=EXE_NAMES):
    """Return ``(running, pids, error)`` for the configured client names."""
    pids, error = get_process_pids(exe_names)
    return bool(pids), pids or [], error


def _enum_uninstall_roots():
    if winreg is None:
        return
    hkeys = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    base = r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"
    views = [0, winreg.KEY_WOW64_32KEY]
    for hkey in hkeys:
        for view in views:
            try:
                yield winreg.OpenKey(hkey, base, 0, winreg.KEY_READ | view)
            except OSError:
                continue


def _read_value(key, name):
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def scan_registry():
    """Return matching uninstall records from supported registry views."""
    results = []
    for root_key in _enum_uninstall_roots():
        try:
            count = winreg.QueryInfoKey(root_key)[0]
        except OSError:
            continue
        for index in range(count):
            try:
                sub_name = winreg.EnumKey(root_key, index)
                sub_key = winreg.OpenKey(root_key, sub_name)
            except OSError:
                continue
            display_name = _read_value(sub_key, "DisplayName") or ""
            if display_name and any(word in display_name.lower() for word in SEEWO_KEYWORDS):
                results.append({
                    "display_name": display_name,
                    "version": _read_value(sub_key, "DisplayVersion"),
                    "install_location": _read_value(sub_key, "InstallLocation"),
                })
            winreg.CloseKey(sub_key)
    return results


def _find_exe_under(root, max_depth=3):
    if not root or not os.path.isdir(root):
        return None
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = os.listdir(current)
        except (PermissionError, OSError):
            continue
        for entry in entries:
            full = os.path.join(current, entry)
            if os.path.isfile(full) and entry in EXE_NAMES:
                return full
        if depth < max_depth:
            stack.extend((os.path.join(current, entry), depth + 1)
                         for entry in entries if os.path.isdir(os.path.join(current, entry)))
    return None


def scan_filesystem(extra_roots=None):
    for root in list(extra_roots or []) + list(COMMON_ROOTS):
        executable = _find_exe_under(root)
        if executable:
            return executable
    return None


def detect_installation():
    """Return the legacy installation-detection JSON object."""
    result = {
        "installed": False, "exe_path": None, "version": None,
        "display_name": None, "install_location": None, "source": None,
    }
    registry_entries = scan_registry()
    registry_roots = [entry["install_location"] for entry in registry_entries
                      if entry.get("install_location")]
    executable = scan_filesystem(registry_roots) if registry_roots else None
    if executable is None:
        executable = scan_filesystem()
    if executable:
        result.update(installed=True, exe_path=executable,
                      source="registry" if registry_entries else "filesystem")
    elif registry_entries:
        result.update(installed=True, source="registry")
    if registry_entries:
        result.update(registry_entries[0])
    return result


def _configure_user32():
    if _USER32 is None:
        return None
    window_proc = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM,
    )
    _USER32.EnumWindows.argtypes = [window_proc, ctypes.wintypes.LPARAM]
    _USER32.EnumWindows.restype = ctypes.wintypes.BOOL
    _USER32.GetWindowThreadProcessId.argtypes = [
        ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.DWORD),
    ]
    _USER32.GetWindowThreadProcessId.restype = ctypes.wintypes.DWORD
    _USER32.IsWindowVisible.argtypes = [ctypes.wintypes.HWND]
    _USER32.IsWindowVisible.restype = ctypes.wintypes.BOOL
    _USER32.ShowWindowAsync.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
    _USER32.ShowWindowAsync.restype = ctypes.wintypes.BOOL
    _USER32.SetForegroundWindow.argtypes = [ctypes.wintypes.HWND]
    _USER32.SetForegroundWindow.restype = ctypes.wintypes.BOOL
    return window_proc


def bring_to_foreground(pid_set):
    """Best-effort window restore/foreground operation for the supplied PIDs."""
    window_proc = _configure_user32()
    if window_proc is None:
        return []
    found, seen = [], set()

    def callback(hwnd, _lparam):
        pid = ctypes.wintypes.DWORD()
        _USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pid_set and hwnd not in seen and _USER32.IsWindowVisible(hwnd):
            _USER32.ShowWindowAsync(hwnd, SW_RESTORE)
            _USER32.SetForegroundWindow(hwnd)
            seen.add(hwnd)
            found.append(pid.value)
        return True

    _USER32.EnumWindows(window_proc(callback), 0)
    return found


def show_windows(exe_names=EXE_NAMES):
    """Return the legacy result for foregrounding a freshly launched client."""
    pids, _ = get_process_pids(exe_names)
    if not pids:
        return {"ok": True, "found_pids": [],
                "detail": "未找到希沃白板进程，无法聚焦（请先启动客户端）"}
    if _USER32 is not None:
        try:
            _USER32.LockSetForegroundWindow(2)
            _USER32.AllowSetForegroundWindow(-1)
        except Exception:  # noqa: BLE001
            pass
    found = bring_to_foreground(set(pids))
    detail = (f"已聚焦 {len(found)} 个窗口（PID={found}）" if found else
              "找到进程但未能聚焦其窗口（可能被最小化到托盘或受系统前台锁限制，已在任务栏闪烁提示）")
    return {"ok": True, "found_pids": found, "detail": detail}


class ConfigError(ValueError):
    """The configured MCP file cannot be safely read or updated."""


def _load_config(path):
    if not os.path.exists(path):
        return {"mcpServers": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (ValueError, OSError) as exc:
        raise ConfigError("无法安全读取 MCP 配置：%s" % exc) from exc
    if not isinstance(data, dict):
        raise ConfigError("MCP 配置根节点必须是 JSON 对象")
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    if not isinstance(data["mcpServers"], dict):
        raise ConfigError("MCP 配置中的 mcpServers 必须是对象")
    return data


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    directory = os.path.dirname(path) or "."
    descriptor, temporary_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def add(config, url):
    data = _load_config(config)
    data["mcpServers"][SERVER_KEY] = {"type": "http", "url": url}
    _atomic_write(config, data)
    return data["mcpServers"][SERVER_KEY]


def remove(config, expected_url=None):
    data = _load_config(config)
    current = data["mcpServers"].get(SERVER_KEY)
    if expected_url and (not isinstance(current, dict) or current.get("url") != expected_url):
        return None
    removed = data["mcpServers"].pop(SERVER_KEY, None)
    _atomic_write(config, data)
    return removed


def status(config):
    return _load_config(config)["mcpServers"].get(SERVER_KEY)


def _probe_port(port, timeout=3):
    return _mcp_client().probe_port(port, timeout=timeout)


def probe_port(port, timeout=3):
    """Late MCP import keeps this shared module independent of HTTP transport."""
    return _probe_port(port, timeout=timeout)


def _default_ports():
    return _mcp_client().DEFAULT_PORTS


def _mcp_client():
    """Import the sibling MCP transport when this module runs as a script."""
    mcp_directory = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "mcp"))
    if mcp_directory not in sys.path:
        sys.path.insert(0, mcp_directory)
    import mcp_client
    return mcp_client


def _run_process(args):
    names = parse_exe_names(args.exe)
    pids, error = get_process_pids(names)
    if pids is None:
        return {"ok": False, "running": False, "pids": [], "exe_names": names, "error": error}
    return {"ok": True, "running": bool(pids), "pids": pids, "exe_names": names}


def _run_probe(args):
    ports = _default_ports()
    if args.ports:
        try:
            ports = [int(port) for port in args.ports.split(",") if port.strip()]
        except ValueError:
            pass
    deadline = time.time() + max(0.0, args.wait)
    last_detail = "未开始探测"
    while True:
        for port in ports:
            result = probe_port(port)
            last_detail = result["detail"]
            if result["state"] == "unreachable":
                continue
            if args.require_tools and result["state"] != "ready":
                last_detail = f"端口 {port} 有 MCP 响应，但 tools/list 未返回工具（可能未登录/未就绪）"
                continue
            return {
                "port": port, "url": result["url"], "transport": "streamable-http",
                "detail": result["detail"],
                "has_tools": result["has_tools"] if args.require_tools else None,
            }
        if time.time() >= deadline:
            break
        time.sleep(max(0.2, args.interval))
    return {"port": None, "url": None, "transport": None,
            "detail": last_detail, "has_tools": None}


def _run_config(args):
    if args.status:
        return {"config": args.config, "entry": status(args.config)}
    if args.remove:
        removed = remove(args.config, expected_url=args.expected_url)
        return {"removed": removed is not None, "entry": removed}
    entry = add(args.config, args.add)
    return {"added": True, "entry": entry}


def build_parser():
    parser = argparse.ArgumentParser(description="希沃白板 MCP 生命周期诊断工具")
    commands = parser.add_subparsers(dest="command", required=True)

    process = commands.add_parser("process", help="判断客户端进程是否运行")
    process.add_argument("--exe", default=",".join(EXE_NAMES), help="逗号分隔的进程名")

    commands.add_parser("detect", help="检测客户端安装位置")

    show = commands.add_parser("show", help="将客户端窗口带到前台")
    show.add_argument("--exe", default=",".join(EXE_NAMES), help="逗号分隔的进程名")

    probe = commands.add_parser("probe", help="探测 MCP 端口")
    probe.add_argument("ports", nargs="?", default=None, help="逗号分隔的端口覆盖")
    probe.add_argument("--wait", type=float, default=0.0, help="轮询等待总时长（秒）")
    probe.add_argument("--interval", type=float, default=1.0, help="轮询间隔（秒）")
    probe.add_argument("--require-tools", action="store_true", help="要求 tools/list 返回工具")

    config = commands.add_parser("config", help="管理 WorkBuddy MCP 配置")
    config.add_argument("--config", default=DEFAULT_CONFIG, help="mcp.json 路径")
    group = config.add_mutually_exclusive_group(required=True)
    group.add_argument("--add", metavar="URL", help="添加 MCP 服务")
    group.add_argument("--remove", action="store_true", help="移除 MCP 服务")
    group.add_argument("--status", action="store_true", help="打印当前 MCP 配置")
    config.add_argument("--expected-url", help="仅在当前 URL 匹配时移除")
    return parser


def main(argv=None):
    """Run a unified diagnostic command and emit its legacy JSON payload."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "process":
            payload = _run_process(args)
        elif args.command == "detect":
            payload = detect_installation()
        elif args.command == "show":
            payload = show_windows(parse_exe_names(args.exe))
        elif args.command == "probe":
            payload = _run_probe(args)
        else:
            payload = _run_config(args)
    except ConfigError as exc:
        print(json.dumps({"ok": False, "code": "config_invalid", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
