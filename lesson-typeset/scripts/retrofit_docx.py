#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无源稿课题：直接在既有 Word 上就地改造为统一版式（不新建 md 源稿）。

2026-11-10 用户口径：「缺少源稿的全部在 word 文档上改」——这类课题以
`交付文件/` 里既有的 docx 为唯一权威载体，不再要求补写 `.workbuddy/*-源.md`。
本入口只调格式、不改文字，版式数值全部复用引擎，不另写第二份常量：
  · 页边距 / 配图宽度        → typeset.PROFILES
  · 字号 / 颜色 / 页眉页脚构件 → renderers/(xuexqingdan|zjg)_typeset.py
  · 交付落地（旧版进废纸篓）  → typeset.commit()
  · 字族                     → renderers 的 resolve_font 回落链
逐字稿按「第 N 页 ↔ pNN.jpg」补课件截图；已有配图的稿子不重复插图（幂等）。

用法：
    T=~/.workbuddy/skills/lesson-typeset/scripts/retrofit_docx.py
    python3 "$T" --root "<课题目录>" --header "19 秦兵马俑" --all --check
    python3 "$T" --root "<课题目录>" --header "19 秦兵马俑" --all
    python3 "$T" --root "<课题目录>" --header "17 长城" \
        --file "长城-教学设计.docx"          # 有源稿但旧版式、不宜重排的，单独指定
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "renderers"))
import typeset as TS                     # noqa: E402
import zjg_typeset as Z                  # noqa: E402
import xuexqingdan_typeset as X          # noqa: E402

PAGE_RE = re.compile(r"^第\s*(\d+)\s*页\s*·")
GREEN, INK, MUTED = X.GREEN, X.INK, X.MUTED

ZJG_STYLE = {
    "title":  (Z.FS_TITLE,  INK,   True,  "head"),
    "sub":    (Z.FS_SUB,    INK,   False, "head"),
    "page":   (Z.FS_PAGE,   GREEN, True,  "head"),
    "tea":    (Z.FS_TEA,    INK,   None,  "body"),
    "stu":    (Z.FS_STU,    INK,   None,  "body"),
    "preset": (Z.FS_PRESET, MUTED, None,  "body"),
    "op":     (Z.FS_OP,     MUTED, None,  "body"),
    "ch":     (Z.FS_CH,     INK,   True,  "head"),
    "body":   (Z.FS_BODY,   INK,   None,  "body"),
}


def type_of(fname):
    for t in ("教学设计", "逐字稿", "学习清单", "制作笔记"):
        if t in fname:
            return t
    return "制作笔记"                     # 过程文档套基础层，不按新类型另立参数


def fonts():
    head = X.resolve_font(X.HEAD_CANDIDATES, "思源黑体")
    body = X.resolve_font(X.BODY_CANDIDATES, "楷体")
    X.Ctx.head, X.Ctx.body = head, body
    Z.Ctx.head, Z.Ctx.body = head, body
    return head, body


def set_run(run, font, size, color=None, bold=None):
    run.font.name = font
    rf = run._element.get_or_add_rPr().get_or_add_rFonts()
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(a), font)
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold


def classify_zjg(text, idx):
    if idx == 0:
        return "title"
    if idx == 1:
        return "sub"
    if PAGE_RE.match(text):
        return "page"
    if re.match(r"^师\s*[:：]", text):
        return "tea"
    if re.match(r"^生[^：:]{0,6}\s*[:：]", text):
        return "stu"
    if text.startswith("〔学生可能说〕"):
        return "preset"
    if text.startswith("〔"):
        return "op"
    if re.match(r"^[一二三四五六七八九十]+、", text) or (text.startswith("第") and "课时" in text[:12]):
        return "ch"
    return "body"


def restyle(doc, typ, head, body, fs0, fs1):
    for idx, p in enumerate(doc.paragraphs):
        if not p.text.strip():
            continue
        if typ == "逐字稿":
            size, color, bold, fam = ZJG_STYLE[classify_zjg(p.text.strip(), idx)]
            font = head if fam == "head" else body
        else:
            st = (p.style.name or "") if p.style is not None else ""
            is_title = idx == 0 or "文档标题" in st or "Title" in st
            is_head = ("标题" in st or "Heading" in st or
                       all(r.bold for r in p.runs if r.text.strip()))
            if is_title:
                size, font, color, bold = fs0, head, INK, True
            elif is_head:
                size, font, color, bold = fs1, head, GREEN, True
            else:
                size, font, color, bold = X.FS_BODY, body, INK, None
        for r in p.runs:
            set_run(r, font, size, color, bold)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    for r in p.runs:
                        set_run(r, body, 10.5, INK)


def images_dir(root, fname, explicit=None):
    if explicit:
        return explicit if os.path.isdir(explicit) else None
    m = TS.KESHI.search(fname)
    cands = TS.KESHI_IMG_DIRS.get(m.group(0) if m else "", TS.GENERIC_IMG_DIRS)
    for rel in cands:
        d = os.path.join(root, rel)
        if os.path.isdir(d) and any(os.path.exists(os.path.join(d, "p01." + e))
                                    for e in ("jpg", "jpeg", "png")):
            return d
    return None


def insert_figures(doc, idir, img_w):
    """按页标题插图（标题→图→台词，与引擎 2.5 一致）。已有配图则跳过，保证幂等。"""
    anchors = [(p, int(PAGE_RE.match(p.text.strip()).group(1)))
               for p in doc.paragraphs if p.text.strip() and PAGE_RE.match(p.text.strip())]
    if not anchors or len(doc.inline_shapes) >= len(anchors):
        return 0
    made = 0
    for p, n in anchors:
        cand = next((os.path.join(idir, "p%02d.%s" % (n, e)) for e in ("jpg", "jpeg", "png")
                     if os.path.isfile(os.path.join(idir, "p%02d.%s" % (n, e)))), None)
        if not cand:
            continue
        newp = OxmlElement("w:p")
        p._p.addnext(newp)
        para = Paragraph(newp, p._parent)
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.space_before = Pt(4)
        para.paragraph_format.space_after = Pt(4)
        para.add_run().add_picture(cand, width=Cm(img_w))
        made += 1
    return made


def text_of(doc):
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                if c.text.strip():
                    parts.append(c.text)
    return parts


def process(root, fname, header, explicit_images, check):
    path = os.path.join(TS.output_folder(root, type_of(fname)), fname)
    if not os.path.isfile(path):
        return "SKIP 不存在: " + fname
    lock = os.path.join(os.path.dirname(path), "~$" + fname[1:])
    if os.path.exists(lock):
        return "SKIP 文件被编辑器占用: " + fname

    bak_dir = os.path.join("/tmp", "lesson-typeset-retrofit")
    os.makedirs(bak_dir, exist_ok=True)
    bak = os.path.join(bak_dir, fname)
    shutil.copy2(path, bak)
    before = text_of(Document(bak))

    head, body = fonts()
    typ = type_of(fname)
    prof = TS.PROFILES[typ]
    fs0, fs1 = prof["fs"]
    m = prof["m"]

    d = Document(bak)
    for sec in d.sections:
        sec.top_margin, sec.bottom_margin = Cm(m[0]), Cm(m[1])
        sec.left_margin, sec.right_margin = Cm(m[2]), Cm(m[3])
        sec.different_first_page_header_footer = False
        cw = X.PAGE_W - m[2] - m[3]
        X.build_header(sec, cw, text=header)
        Z.build_footer(sec, page_number=True)
    restyle(d, typ, head, body, fs0, fs1)

    added, missing = 0, None
    if typ == "逐字稿":
        idir = images_dir(root, fname, explicit_images)
        if idir:
            added = insert_figures(d, idir, prof["img_w"])
            if len(d.inline_shapes) < sum(1 for p in d.paragraphs
                                          if p.text.strip() and PAGE_RE.match(p.text.strip())):
                missing = "有页缺截图，请检查 " + idir
        else:
            missing = "⚠️ 未找到课件截图目录，逐字稿无配图（不得静默漏图）"

    out = os.path.join(bak_dir, "staging-" + fname)
    d.save(out)
    chk = Document(out)
    if text_of(chk) != before:
        return "FAIL 文字发生变化，已放弃: " + fname
    hdr = [t.text for t in chk.sections[0].header._element.iter(qn("w:t")) if t.text]
    if "木老师原创课件" not in hdr or header not in hdr:
        return "FAIL 页眉注入异常: %s → %r" % (fname, hdr)
    tag = "CHECK OK" if check else "OK"
    if not check:
        replaced = TS.commit(out, path)      # 旧成品进废纸篓 + 原子覆盖
        TS.sweep_copies(root, fname)
    else:
        replaced = False
    return "%s %-48s 页眉=%s 图=%d(+%d) 边距=%s %s%s" % (
        tag, fname, header, len(chk.inline_shapes), added, str(m),
        ("旧版已入废纸篓 " if replaced else ""), missing or "")


def main():
    ap = argparse.ArgumentParser(description="无源稿课题：就地改既有 Word 为统一版式")
    ap.add_argument("--root", required=True, help="课题根目录")
    ap.add_argument("--header", required=True, help="页眉课题名，如「19 秦兵马俑」")
    ap.add_argument("--all", action="store_true", help="处理交付包内所有无规范源稿的 docx")
    ap.add_argument("--file", action="append", default=[], help="显式指定文件（可重复）")
    ap.add_argument("--images", help="课件截图目录；省略则按课时自动探测")
    ap.add_argument("--check", action="store_true", help="只试改校验，不落地")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    folder = TS.output_folder(root, "教学设计")
    wb = os.path.join(root, ".workbuddy")
    names = [x for x in sorted(os.listdir(folder))
             if x.endswith(".docx") and not x.startswith("~$")]
    if a.all:
        names = [x for x in names
                 if not os.path.isfile(os.path.join(wb, x[:-5] + "-源.md"))]
    if a.file:
        names = [x for x in names if x in a.file]
    if not names:
        print("没有需要就地改造的文件")
        return
    print("【%s】待处理 %d 份%s" % (os.path.basename(root), len(names),
                                  "（试改校验）" if a.check else ""))
    for f in names:
        try:
            print("  " + process(root, f, a.header, a.images, a.check))
        except Exception as e:
            print("  ERROR %-44s %s: %s" % (f, type(e).__name__, str(e)[:180]))


if __name__ == "__main__":
    main()
