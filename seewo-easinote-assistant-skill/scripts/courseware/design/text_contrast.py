#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文字配色工具：按背景色自动推荐高对比度文字色，或校验指定文字/背景组合。

用途
----
视觉规划阶段，AI 必须在把文字色写进 spec 前，以该文字所在
textSafeRegion 的**实测 bgTone**（或纯色背景 / scrim 混合色）为背景完成
对比度预检。本工具与渲染器使用同一套 WCAG 2.1 相对亮度算法，避免「凭直觉
选色 → 校验器事后拦截」的返工。

用法
----
    # 推荐模式：输出深色系与浅色系两组达标文字色（默认目标 ≥4.5:1）
    python text_contrast.py --bg #A87F45
    python text_contrast.py --bg #A87F45 --target 7

    # 校验模式：输出指定组合的对比度与达标状态；<4.5:1 时退出码为 2
    python text_contrast.py --bg #A87F45 --fg #2A1500
    python text_contrast.py --bg #A87F45 --fg #2A1500 --json

    # 批量：可传多个 --bg，一次为多页/多区域选色
    python text_contrast.py --bg #EDDBB1 --bg #7A5F3A --bg #C8A05E

退出码
------
    0 全部达标（推荐模式始终 0）
    2 校验模式存在对比度 <4.5:1 的组合（或输入非法）
"""
import argparse
import math
import sys

# 与 visual_plan_renderer._contrast_ratio 同一套 WCAG 2.1 算法。
DEEP_BLACK = "#000000"
WHITE = "#FFFFFF"


def _srgb_to_linear(channel):
    channel = channel / 255.0
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color):
    r = _srgb_to_linear(int(hex_color[1:3], 16))
    g = _srgb_to_linear(int(hex_color[3:5], 16))
    b = _srgb_to_linear(int(hex_color[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color1, color2):
    l1 = relative_luminance(color1)
    l2 = relative_luminance(color2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def is_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


# 候选文字色池：深色系（浅底优先）与浅色系（深底优先）。
# 覆盖课件常用墨青、暖褐、金褐等色系，均与浅米/深褐背景体系搭配。
DARK_CANDIDATES = [
    "#2A1500", "#241505", "#1A1A2E", "#2A2116", "#14302E",
    "#1E3A36", "#3A2A14", "#2E4B4F", "#4A3A22", DEEP_BLACK,
]
LIGHT_CANDIDATES = [
    WHITE, "#F4F0E4", "#F0F4F8", "#FFF8EC", "#FDF6E3",
    "#EAF0F0", "#EFF3F5", "#F7F3E9", "#E8ECEF", "#FFFDF7",
]


def _matches(candidates, bg, target):
    return [(color, contrast_ratio(color, bg))
            for color in candidates
            if contrast_ratio(color, bg) >= target]


def recommend(bg, target=4.5):
    darks = sorted(_matches(DARK_CANDIDATES, bg, target),
                   key=lambda item: item[1], reverse=True)
    lights = sorted(_matches(LIGHT_CANDIDATES, bg, target),
                    key=lambda item: item[1], reverse=True)
    return darks, lights


def _fmt(color, ratio, target):
    mark = "✓" if ratio >= target else "✗"
    return "%s  %6.2f:1  %s≥%.1f" % (color, ratio, mark, target)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按背景色推荐高对比度文字色，或校验指定文字/背景组合")
    parser.add_argument("--bg", action="append", required=True,
                        help="背景色 #RRGGBB（可重复传入批量选色）")
    parser.add_argument("--fg", help="文字色 #RRGGBB；提供时进入校验模式")
    parser.add_argument("--target", type=float, default=4.5,
                        help="推荐/校验目标对比度，默认 4.5（WCAG AA 正文）")
    parser.add_argument("--json", action="store_true",
                        help="输出 JSON 便于程序解析")
    args = parser.parse_args(argv)

    backgrounds = [bg.strip() for bg in args.bg]
    invalid = [bg for bg in backgrounds if not is_color(bg)]
    if args.fg and not is_color(args.fg):
        invalid.append(args.fg)
    if invalid:
        print("✗ 非法颜色值：%s（应为 #RRGGBB）" % "、".join(invalid))
        return 2

    failed = False
    if args.fg:
        # ── 校验模式 ──
        rows = []
        for bg in backgrounds:
            ratio = contrast_ratio(args.fg, bg)
            ok = ratio >= args.target
            if not ok:
                failed = True
            row = {"bg": bg, "fg": args.fg, "ratio": round(ratio, 2),
                   "target": args.target, "pass": ok}
            rows.append(row)
        if args.json:
            import json
            print(json.dumps(rows, ensure_ascii=False))
        else:
            for row in rows:
                mark = "✓" if row["pass"] else "✗"
                print("%s 文字 %s 于背景 %s：%.2f:1 %s（目标 ≥%.1f:1）"
                      % (mark, row["fg"], row["bg"], row["ratio"],
                         "达标" if row["pass"] else "不达标", args.target))
            if failed:
                print("\n修复指引：运行 python text_contrast.py --bg <背景色> "
                      "获取达标文字色；或改用 fill 容器 / scrim 垫底后重选。")
        return 2 if failed else 0

    # ── 推荐模式 ──
    output = []
    for bg in backgrounds:
        darks, lights = recommend(bg, args.target)
        entry = {
            "bg": bg,
            "luminance": round(relative_luminance(bg), 3),
            "target": args.target,
            "darks": [{"fg": c, "ratio": round(r, 2)} for c, r in darks[:5]],
            "lights": [{"fg": c, "ratio": round(r, 2)} for c, r in lights[:5]],
        }
        output.append(entry)
        if not args.json:
            print("背景 %s（亮度 %.2f，目标 ≥%.1f:1）" % (bg, entry["luminance"], args.target))
            print("  深色文字（浅底优先）：")
            for color, ratio in darks[:5]:
                print("    " + _fmt(color, ratio, args.target))
            print("  浅色文字（深底优先）：")
            for color, ratio in lights[:5]:
                print("    " + _fmt(color, ratio, args.target))
            print()
    if args.json:
        import json
        print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
