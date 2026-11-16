#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monitor_seewo.py - 后台监控希沃白板进程；完全退出后自动移除 MCP 配置。

由 agent 以后台任务方式拉起（长期运行）。仅使用 Python 标准库。
- 通过 tasklist 轮询判断进程是否存在；
- 连续缺失 --misses 次（默认 3 次）判定为“已完全退出”，调用共享配置管理函数；
- 日志同时写入 stdout 与 %TEMP%/seewo_mcp_monitor.log。

用法：
  monitor_seewo.py
  monitor_seewo.py --exe "<应用进程名>" --url URL --interval 5 --misses 3
"""
import argparse
import json
import os
import tempfile
import time

from lifecycle import (ConfigError, DEFAULT_CONFIG, EXE_NAMES, is_process_running,
                       parse_exe_names, remove)

LOG = os.path.join(tempfile.gettempdir(), "seewo_mcp_monitor.log")
LOCK = os.path.join(tempfile.gettempdir(), "seewo_mcp_monitor.lock")


def _pid_is_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read().strip()
    except OSError:
        return {}
    try:
        record = json.loads(raw)
        return record if isinstance(record, dict) else {}
    except ValueError:
        try:
            return {"pid": int(raw)}  # Compatibility with locks from earlier releases.
        except ValueError:
            return {}


def _write_lock(path, url=None, pid=None):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"pid": pid if pid is not None else os.getpid(), "url": url}, handle, ensure_ascii=False)


def monitor_url(path=LOCK):
    value = _read_lock(path).get("url")
    return value if isinstance(value, str) and value else None


def acquire_monitor_lock(path=LOCK, url=None):
    """Acquire a process-owned monitor lock, clearing stale lock files only."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        record = _read_lock(path)
        stale_pid = record.get("pid")
        if stale_pid and _pid_is_running(stale_pid):
            if url:
                _write_lock(path, url, pid=stale_pid)
            return False
        try:
            os.remove(path)
        except OSError:
            return False
        return acquire_monitor_lock(path, url)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "url": url}, handle, ensure_ascii=False)
        return True
    except OSError:
        try:
            os.close(fd)
            os.remove(path)
        except OSError:
            pass
        return False


def release_monitor_lock(path=LOCK):
    owner = _read_lock(path).get("pid")
    if owner not in (None, os.getpid()):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def process_running(names):
    running, _, error = is_process_running(names)
    if error:
        log(f"tasklist 调用失败: {error}")
        return True  # 无法判断时保守认为仍在运行，避免误删配置
    return running


def remove_config(config, expected_url=None):
    try:
        removed = remove(config, expected_url=expected_url)
        if removed is not None:
            log("已移除希沃白板 MCP 配置。")
        elif expected_url:
            log("当前 MCP 配置已由新连接接管，跳过移除。")
    except ConfigError as e:
        log(f"移除配置失败: {e}")


def main():
    p = argparse.ArgumentParser(description="监控希沃白板进程并清理 MCP 配置")
    p.add_argument("--exe", default=",".join(EXE_NAMES), help="逗号分隔的进程名")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--url", help="仅移除本监控器注册的 MCP URL")
    p.add_argument("--interval", type=int, default=5, help="轮询间隔（秒）")
    p.add_argument("--misses", type=int, default=3, help="连续缺失多少次判定为退出")
    args = p.parse_args()
    names = parse_exe_names(args.exe)
    if not acquire_monitor_lock(url=args.url):
        log("已有希沃白板退出监控在运行，跳过重复启动。")
        return
    try:
        log(f"监控启动：进程={names} 配置={args.config} 间隔={args.interval}s 连续缺失={args.misses}次判定退出")
        miss = 0
        while True:
            if process_running(names):
                if miss:
                    log("进程重新出现，重置缺失计数。")
                miss = 0
            else:
                miss += 1
                log(f"未检测到进程（第 {miss}/{args.misses} 次）")
                if miss >= args.misses:
                    log("判定希沃白板已完全退出，移除 MCP 配置。")
                    remove_config(args.config, expected_url=monitor_url() or args.url)
                    break
            time.sleep(args.interval)
        log("监控结束。")
    finally:
        release_monitor_lock()


if __name__ == "__main__":
    main()
