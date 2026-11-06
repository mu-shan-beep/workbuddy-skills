#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐字稿时间轴与归属校验
======================

查四件事（依据 lesson-script/references/script-spec.md 十一、十九 E）：

1. 页号 1…N 连续、无跳号；
2. 时间轴首尾相接、无断点／倒退，首页 0:00，末页止 ＝ 课时长；
3. 每页落在教学设计的某个活动区间内（跨相邻活动标注 WARN，跨环节记 ERROR）；
4. 正文自述“约 N 分钟／N 分半”与页区间是否明显不符（偏差 ≥ 0.75 分钟告警）。

可选：配图张数 ＝ 稿页数。

用法：
    python3 audit_script.py 逐字稿-源.md
    python3 audit_script.py 逐字稿-源.md --total 40
    python3 audit_script.py 逐字稿-源.md --acts acts.json --images assets/ppt-第一课时

acts.json：
    [{"name": "二·自主阅读", "start": "0:03:00", "end": "0:08:00"}]
    时间可写 分:秒 或 时:分:秒。

退出码：0 全部通过（可含 WARN）；1 存在 ERROR。
"""

import argparse
import glob
import json
import os
import re
import sys

PAGE_RE = re.compile(r"^##\s*第\s*(\d+)\s*页\s*·\s*(.+?)｜(\d+):(\d+)—(\d+):(\d+)\s*$", re.M)
DUR_RE = re.compile(r"约\s*(\d+)\s*(分钟|分半)")


def to_sec(h, m):
    return int(h) * 60 + int(m)


def parse_clock(s):
    parts = [int(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def fmt(sec):
    return "%d:%02d" % (sec // 60, sec % 60)


def load_acts(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    acts = []
    for a in raw:
        acts.append((a["name"], parse_clock(a["start"]), parse_clock(a["end"])))
    return acts


def page_mentions(body):
    """页内自述时长（分钟）。"""
    out = []
    for n, unit in DUR_RE.findall(body):
        out.append(int(n) + (0.5 if unit == "分半" else 0))
    return out


def main():
    ap = argparse.ArgumentParser(description="逐字稿时间轴与活动归属校验")
    ap.add_argument("script", help="逐字稿源稿（.md）")
    ap.add_argument("--acts", help="活动区间 JSON")
    ap.add_argument("--total", type=int, default=40, help="课时总长（分钟），默认 40")
    ap.add_argument("--images", help="课件截图目录，检查张数是否等于页数")
    ap.add_argument("--quiet", action="store_true", help="只打印结论")
    a = ap.parse_args()

    if not os.path.isfile(a.script):
        sys.exit("找不到源稿：%s" % a.script)
    text = open(a.script, encoding="utf-8").read()

    hits = PAGE_RE.findall(text)
    if not hits:
        sys.exit("未解析到页标题。格式应为：## 第 1 页 · 页面主题｜0:00—0:20")

    # 每页正文：从本页标题到下一个页标题之前
    bounds = [m.start() for m in PAGE_RE.finditer(text)] + [len(text)]
    pages = []
    for i, m in enumerate(PAGE_RE.finditer(text)):
        p, title = int(m.group(1)), m.group(2).strip()
        s, e = to_sec(m.group(3), m.group(4)), to_sec(m.group(5), m.group(6))
        body = text[m.end():bounds[i + 1]]
        pages.append({"page": p, "title": title, "start": s, "end": e, "body": body})

    errors, warns = [], []

    nums = [p["page"] for p in pages]
    if nums != list(range(1, len(pages) + 1)):
        errors.append("页号不连续：%s（应为 1…%d）" % (nums, len(pages)))

    prev = 0
    for p in pages:
        if p["start"] != prev:
            errors.append("第 %d 页起始 %s 与上页结束 %s 不相接" % (p["page"], fmt(p["start"]), fmt(prev)))
        if p["end"] <= p["start"]:
            errors.append("第 %d 页时长 ≤ 0（%s—%s）" % (p["page"], fmt(p["start"]), fmt(p["end"])))
        prev = p["end"]

    total = a.total * 60
    if pages[0]["start"] != 0:
        errors.append("首页不是 0:00（实为 %s）" % fmt(pages[0]["start"]))
    if prev != total:
        errors.append("末页止于 %s，与课时长 %s 不符" % (fmt(prev), fmt(total)))

    acts = load_acts(a.acts)
    for p in pages:
        p["act"] = "-"
        if not acts:
            continue
        inside = [n for n, s, e in acts if p["start"] >= s and p["end"] <= e]
        if inside:
            p["act"] = inside[0]
            continue
        spanning = [n for n, s, e in acts if p["start"] < e and p["end"] > s]
        if len(spanning) == 2:
            p["act"] = "%s + %s" % (spanning[0], spanning[1])
            warns.append("第 %d 页跨同环节两个相邻活动：%s" % (p["page"], " / ".join(spanning)))
        elif len(spanning) > 2:
            p["act"] = "跨 %d 个活动" % len(spanning)
            errors.append("第 %d 页跨 %d 个活动（%s），超出单页容量的合理范围"
                          % (p["page"], len(spanning), " / ".join(spanning)))
        else:
            errors.append("第 %d 页（%s—%s）不落在任何活动区间内"
                          % (p["page"], fmt(p["start"]), fmt(p["end"])))

    # 自述时长只查“说的时间比给的还多”这一种（例：页给 3.5 分钟，正文写“这五分钟里”）；
    # 页内某个小活动短于整页时长属正常，不告警。
    for p in pages:
        ms = page_mentions(p["body"])
        p["mentions"] = ms
        dur = (p["end"] - p["start"]) / 60.0
        if ms and max(ms) - dur >= 0.5:
            warns.append("第 %d 页：区间只有 %.1f 分钟，正文却写“约 %g 分钟”，时间不够用"
                         % (p["page"], dur, max(ms)))

    img_note = ""
    if a.images:
        files = [f for f in glob.glob(os.path.join(a.images, "p*.*"))
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if len(files) != len(pages):
            errors.append("配图 %d 张 ≠ 稿页 %d 页（%s）" % (len(files), len(pages), a.images))
        img_note = "｜配图 %d 张" % len(files)

    if not a.quiet:
        print("源稿：%s" % os.path.basename(a.script))
        print("页数：%d ｜ 总时长：%s%s" % (len(pages), fmt(prev), img_note))
        print("")
        print("%-4s %-14s %-13s %-7s %-6s %s" % ("页", "起—止", "时长(分)", "自述", "配图?", "归属活动"))
        for p in pages:
            dur = (p["end"] - p["start"]) / 60.0
            mention = ",".join("%g" % m for m in p["mentions"]) or "-"
            print("%-4d %-14s %-13.1f %-7s %-6s %s"
                  % (p["page"], "%s—%s" % (fmt(p["start"]), fmt(p["end"])), dur,
                     mention, "p%02d" % p["page"], p["act"]))
        print("")

    for e in errors:
        print("ERROR  " + e)
    for w in warns:
        print("WARN   " + w)
    if not errors:
        print("通过：时间轴连续、总长 %s、每页均落在设计活动区间内%s"
              % (fmt(total), "，配图张数正确" if a.images else ""))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
