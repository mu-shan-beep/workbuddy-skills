#!/usr/bin/env python3
"""逐拍解析课件动画：输出每页初始可见文字 / 每一击出示的文字。

LL-009 复发加固：shape-id -> spTgt 精确归属，禁止用 split 粗切丢 target。
用法: python3 anim_beats.py <pptx> [--page N]
"""
import sys
import zipfile
import re
import argparse
import xml.etree.ElementTree as ET
from html import unescape

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def shape_text_map(root):
    """spid -> 形状文字（含组合形状内所有文字）。"""
    out = {}
    for sp in root.iter(P + "sp"):
        c = sp.find(".//" + P + "cNvPr")
        if c is None:
            continue
        sid = c.get("id")
        txt = "".join(t.text or "" for t in sp.iter(A + "t")).strip()
        if sid:
            out[sid] = txt
    # 图形框架（SmartArt/表格）
    for gf in root.iter(P + "graphicFrame"):
        c = gf.find(".//" + P + "cNvPr")
        if c is None:
            continue
        sid = c.get("id")
        txt = "".join(t.text or "" for t in gf.iter(A + "t")).strip()
        if sid:
            out[sid] = txt
    return out


def parse_beats(xml):
    root = ET.fromstring(xml)
    shapes = shape_text_map(root)
    beats = []          # [(kind, [sid...]), ...] kind in click/with/after
    animated = set()

    # 只解析 mainSeq 下的 par 组；每组一个 clickEffect 或自动效果
    timing = root.find(".//" + P + "timing")
    if timing is None:
        initial = [t for s, t in shapes.items() if t]
        return shapes, [], initial
    seq = timing.find(".//" + P + "seq")
    if seq is None:
        initial = [t for s, t in shapes.items() if t]
        return shapes, [], initial

    # 顺序遍历所有 p:cTn，找带 nodeType 的时序节点
    for ctn in seq.iter(P + "cTn"):
        ntype = ctn.get("nodeType")
        if ntype not in ("clickEffect", "withEffect", "afterEffect"):
            continue
        sids = []
        for st in ctn.iter(P + "spTgt"):
            sid = st.get("spid")
            if sid and sid not in sids:   # set/animEffect 会重复引用同一形状
                sids.append(sid)
                animated.add(sid)
        beats.append((ntype, sids))   # 空组也保留，保证单击组数不丢

    # 初始可见 = 有文字、且未被任何动画引用的形状
    initial = [t for s, t in shapes.items() if t and s not in animated]
    return shapes, beats, initial


def render(xml, page):
    shapes, beats, initial = parse_beats(xml)
    print(f"\n===== 第 {page} 页 =====")
    print("[初始可见]", " ｜ ".join(initial) if initial else "(无文字形状)")
    groups = []
    cur = []
    for kind, sids in beats:
        texts = []
        for s in sids:
            t = shapes.get(s, "")
            if t and t not in texts:      # 去重：背景框与文本框同文
                texts.append(t)
        if kind == "clickEffect":
            if cur:
                groups.append(cur)
            cur = texts
        else:
            for t in texts:
                if t not in cur:
                    cur.append(t)
    if cur:
        groups.append(cur)
    for i, g in enumerate(groups, 1):
        print(f"[第 {i} 击]", " ｜ ".join(g))
    if not groups:
        print("[动画] 无单击入组动画")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pptx")
    ap.add_argument("--page", type=int, help="只输出指定页（1-based）")
    args = ap.parse_args()
    z = zipfile.ZipFile(args.pptx)
    names = sorted(
        [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)],
        key=lambda s: int(re.search(r"slide(\d+)", s).group(1)),
    )
    for idx, n in enumerate(names, 1):
        if args.page and idx != args.page:
            continue
        render(z.read(n).decode("utf-8", "replace"), idx)


if __name__ == "__main__":
    main()
