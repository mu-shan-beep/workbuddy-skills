#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP runtime guards shared by ENBX creation and image backfill."""
import json
import re
import time

from mcp_client import McpHttpSession


def current_working_mode(mcp, base, rid):
    """Read the active courseware mode, or None when it cannot be parsed."""
    _, info = mcp.tools_call("get_current_courseware_info", base, rid=rid)
    text = McpHttpSession.text_of(info)
    try:
        return json.loads(text).get("shellContext", {}).get("workingMode")
    except ValueError:
        match = re.search(r'"workingMode"\s*:\s*"(\w+)"', text or "")
        return match.group(1) if match else None


def ensure_edit_mode(mcp, base, rid, retries=4, stable_reads=2,
                     settle_seconds=1.2):
    """Require consecutive Edit-mode reads before returning control."""
    tip = ""
    stable = 0
    last_mode = None
    for attempt in range(retries + 1):
        try:
            last_mode = current_working_mode(mcp, base, rid + 200 + attempt)
            if last_mode == "Edit":
                stable += 1
                if stable >= max(1, stable_reads):
                    return tip
            else:
                stable = 0
                _, output = mcp.tools_call(
                    "en_goto_app_ui", {"ui": "Edit", **base},
                    rid=rid + attempt,
                )
                tip = McpHttpSession.text_of(output)
            time.sleep(settle_seconds)
        except Exception as exc:
            stable = 0
            tip = "(en_goto_app_ui skipped: %s)" % exc
            time.sleep(settle_seconds)
    raise RuntimeError(
        "Courseware did not remain in Edit mode (last=%s): %s"
        % (last_mode or "unknown", tip or "no client response")
    )


def sync_with_edit_gate(mcp, base, shell, rid):
    """Synchronize only from Edit mode and fail if the retry is rejected."""
    ensure_edit_mode(mcp, base, rid)
    args = {"waitUntilSynced": True}
    if shell:
        args["shellId"] = shell
    _, output = mcp.tools_call("sync_current_courseware", args, rid=rid + 1)
    if McpHttpSession.is_error(output):
        ensure_edit_mode(mcp, base, rid + 2)
        _, output = mcp.tools_call(
            "sync_current_courseware", args, rid=rid + 3
        )
    if McpHttpSession.is_error(output):
        raise RuntimeError(
            "Courseware sync failed: %s"
            % McpHttpSession.text_of(output)[:120]
        )
    return McpHttpSession.text_of(output)


class RobustMcp:
    """Retry an MCP call once after rebinding a stale courseware shell."""

    def __init__(self, mcp, courseware_name=None):
        self.mcp = mcp
        self.courseware_name = courseware_name
        self.shell_id = None

    def __getattr__(self, item):
        return getattr(self.mcp, item)

    def tools_call(self, name, arguments, rid=3):
        if name in ("en_find_shells", "en_bind_shell",
                    "open_cloud_courseware"):
            return self.mcp.tools_call(name, arguments, rid=rid)
        if (self.shell_id and isinstance(arguments, dict)
                and arguments.get("shellId")
                and arguments["shellId"] != self.shell_id):
            arguments = {**arguments, "shellId": self.shell_id}
        try:
            status, output = self.mcp.tools_call(name, arguments, rid=rid)
        except Exception:
            return self._retry(name, arguments, rid)
        if McpHttpSession.is_error(output) and self._looks_shell_dead(output):
            return self._retry(name, arguments, rid)
        return status, output

    @staticmethod
    def _looks_shell_dead(output):
        text = McpHttpSession.text_of(output)
        shell_words = ("shell", "Shell", "\u7ed1\u5b9a", "\u5931\u6548")
        error_words = (
            "\u5931\u8d25", "\u65e0\u6548", "\u672a\u627e\u5230",
            "\u4e0d\u5b58\u5728", "error",
        )
        return (any(word in text for word in shell_words)
                and any(word in text for word in error_words))

    def _retry(self, name, arguments, rid):
        self._rebind()
        if (self.shell_id and isinstance(arguments, dict)
                and arguments.get("shellId")):
            arguments = {**arguments, "shellId": self.shell_id}
        return self.mcp.tools_call(name, arguments, rid=rid)

    def _rebind(self):
        args = {"searchingMode": "all"}
        if self.courseware_name:
            args["coursewareName"] = self.courseware_name
        _, output = self.mcp.tools_call("en_find_shells", args, rid=990)
        shell = (
            McpHttpSession.find_shell_named(output, self.courseware_name)
            or McpHttpSession.find_shell(output)
        )
        if not shell and self.courseware_name:
            _, opened = self.mcp.tools_call(
                "open_cloud_courseware",
                {"coursewareName": self.courseware_name}, rid=992,
            )
            shell = McpHttpSession.find_shell(opened)
        if not shell:
            raise RuntimeError("Shell rebind failed: no available shell")
        self.mcp.tools_call("en_bind_shell", {"shellId": shell}, rid=991)
        if shell != self.shell_id:
            print("   Shell rebound: %s -> %s" % (self.shell_id, shell))
        self.shell_id = shell
