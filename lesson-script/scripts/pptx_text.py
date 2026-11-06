#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐页抽取课件文字（对读底稿）
============================

只读 pptx 包内的 XML，不改动课件，也不需要 python-pptx。

用法：
    python3 pptx_text.py 牛和鹅-第一课时-课件.pptx
    python3 pptx_text.py 课件.pptx --notes          # 附带备注页文字
    python3 pptx_text.py 课件.pptx --json           # 机器可读，供比对脚本消费

输出：第 N 页：文字1 ｜ 文字2 ｜ …（页码即播放顺序，从 1 起）
备注页按 ppt/slides/_rels/slideN.xml.rels 里的 notesSlide 关系解析。
"""

import argparse
import json
import os
import re
import sys
import zipfile

SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
TEXT_RE = re.compile(r"<a:t>(.*?)</a:t>", re.S)


def _slide_index(name):
    m = SLIDE_RE.match(name)
    return int(m.group(1)) if m else -1


def _texts(xml):
    out = []
    for raw in TEXT_RE.findall(xml):
        s = (raw.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&quot;", '"')
                .replace("&apos;", "'"))
        s = s.strip()
        if s:
            out.append(s)
    return out


def _notes_for(z, slide_file):
    """按 rels 找该页备注，找不到返回空表。"""
    rel = "ppt/slides/_rels/%s.rels" % os.path.basename(slide_file)
    if rel not in z.namelist():
        return []
    xml = z.read(rel).decode("utf-8", "replace")
    m = re.search(r'Target="([^"]*notesSlide\d+\.xml)"', xml)
    if not m:
        return []
    target = m.group(1).lstrip("/")
    path = target if target.startswith("ppt/") else "ppt/" + target.lstrip("../")
    if path not in z.namelist():
        return []
    return _texts(z.read(path).decode("utf-8", "replace"))


def extract(pptx, with_notes=False):
    z = zipfile.ZipFile(pptx)
    slides = sorted([n for n in z.namelist() if SLIDE_RE.match(n)], key=_slide_index)
    rows = []
    for i, name in enumerate(slides, 1):
        item = {"page": i, "texts": _texts(z.read(name).decode("utf-8", "replace"))}
        if with_notes:
            item["notes"] = _notes_for(z, name)
        rows.append(item)
    return rows


def main():
    ap = argparse.ArgumentParser(description="逐页抽取 pptx 文字，作为逐字稿对读底稿")
    ap.add_argument("pptx", help="课件路径")
    ap.add_argument("--notes", action="store_true", help="一并输出备注页文字")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    if not os.path.isfile(a.pptx):
        sys.exit("找不到课件：%s" % a.pptx)

    rows = extract(a.pptx, a.notes)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    print("课件：%s" % os.path.basename(a.pptx))
    print("页数：%d" % len(rows))
    for r in rows:
        print("第 %d 页：%s" % (r["page"], " ｜ ".join(r["texts"]) or "（无文字）"))
        if a.notes and r.get("notes"):
            print("        备注：%s" % " ｜ ".join(r["notes"]))


if __name__ == "__main__":
    main()
