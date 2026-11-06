#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3.1｜混合结构（有框线成表、无框线成段落）—— 正式引擎
================================================================
依据 references/table-v31-spec.md。用户 2026-11-06 口径：
「其实我让你用表格排版，是为了方便看教学活动，现在不显示表格框线的地方，
可以不使用表格，你自己决定就行了」；随后确认预览效果「没什么问题了，保存下来吧」。

按「先出效果 → 用户确认 → 再固化」走完：临时脚本在 /tmp 排出 18 页预览，
用户确认后又补了「表格与标题色块左右对齐」的修正，再次确认后固化。

相对 V3.0（单一主表格）的唯一结构变化：
1. bd="none" 的行（标题／章节标题／通栏长文本）从主表摘出，改为文档级普通段落；
   只有真正画框线的行（字段行／环节分区／四列表头／活动行／辅助对照／图片）留表格。
2. 连续的有框线行合并为一张表，段落块天然充当表间分隔；不再要求「全文一张表」。
3. 每张表加 tblInd = tblCellMar.left（170 twips = 3mm），抵消 Word/LibreOffice
   把表格按单元格左内边距向左顶出的行为，使表格边框、段落色块、正文文字三者左边缘齐平。

版式参数（页面／字族字号／配色／边框／四列比例／图片宽度／行距）**不复制第二份**，
一律复用 table_v30.py 的常量与渲染构件，避免同一数字写两处打架。
改任何一项版式参数前，仍须遵守「先出效果 → 用户确认 → 再固化」。
"""
import argparse
import os
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)          # 复用同目录 V3.0 的常量与 OOXML 构件
import table_v30 as V
import xuexqingdan_typeset as X

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

FREE_IND = Mm(3)          # 与表格单元格 3mm 左右内边距对齐，保证文字块左右边缘齐平


def align_table_to_text(t, twips):
    """Word/LO 会把表格按 tblCellMar.left 向左顶出，边框落在版心外 3mm。
    给表加等量 tblInd，边框回到版心左边界，表格内文字也与正文段落齐平。"""
    tblPr = t._tbl.tblPr
    ind = tblPr.find(qn("w:tblInd"))
    if ind is None:
        ind = OxmlElement("w:tblInd")
        X._put(tblPr, ind, X._TBLPR_ORDER)
    ind.set(qn("w:type"), "dxa")
    ind.set(qn("w:w"), str(twips))


def render_free(doc, cells, opts):
    """把无框线行渲染成文档级普通段落。"""
    cs = cells[0][1]       # bd=none 的行都是 20 格通栏单单元格
    t = cs["t"]

    if t == "title":
        p = doc.add_paragraph()
        X.fmt_para(p, 2, 4, line=1.2, align=V.CENTER_A)
        X.add_run(p, cs["text"], size=V.FS_TITLE, color=V.TITLE,
                  bold=True, font=X.Ctx.head)
        return

    if t == "band":
        p = doc.add_paragraph()
        # 底纹铺满内容宽（与表格外框齐），文字首行内缩 3mm（与表格内文字齐）
        X.fmt_para(p, V.BAND_BEFORE, V.BAND_AFTER, line=1.2,
                   left=Cm(0), first=FREE_IND, align=V.LEFT_A,
                   keep_next=opts.get("keep", False))
        V.shade_paragraph(p, V.BAND)
        X.add_run(p, cs["text"], size=V.FS_H1, color=V.GREEN,
                  bold=True, font=X.Ctx.head)
        return

    if t == "group":
        for k, (kind, text) in enumerate(cs["parts"]):
            p = doc.add_paragraph()
            if kind == "sub":
                X.fmt_para(p, V.SUB_BEFORE if k else 0, V.SUB_AFTER, line=1.25,
                           left=Cm(0), first=FREE_IND, align=V.LEFT_A)
                V.shade_paragraph(p, V.BAND)
                X.add_run(p, text, size=V.FS_H2, color=V.GREEN,
                          bold=True, font=X.Ctx.head)
            elif kind == "item":
                p.paragraph_format.right_indent = FREE_IND
                X.fmt_para(p, 0, V.AFTER_BODY, line=V.LINE_ITEM,
                           left=FREE_IND + V.HANG, first=Mm(-6), align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_BODY, color=V.INK)
            elif kind == "tab":
                p.paragraph_format.right_indent = FREE_IND
                X.fmt_para(p, 0, V.AFTER_CELL, line=V.LINE_CELL,
                           left=FREE_IND, align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_CELL, color=V.INK)
            else:
                p.paragraph_format.right_indent = FREE_IND
                X.fmt_para(p, 0, V.AFTER_BODY, line=V.LINE_BODY,
                           left=FREE_IND, first=V.FIRST_INDENT, align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_BODY, color=V.INK)
        return

    raise ValueError("无框线行出现未处理的类型：%s" % t)


def split_blocks(rows):
    """连续同类（脱表 / 留表）合并成块。"""
    blocks = []
    for cells, opts in rows:
        free = opts.get("bd", "thin") == "none"
        if blocks and blocks[-1][0] == free:
            blocks[-1][1].append((cells, opts))
        else:
            blocks.append((free, [(cells, opts)]))
    return blocks


def build(md_path, out_path, header_text, font_head=None, font_body=None):
    X.Ctx.head = font_head or X.resolve_font(X.HEAD_CANDIDATES, "思源黑体")
    X.Ctx.body = font_body or X.resolve_font(X.BODY_CANDIDATES, "楷体")

    title, rows = V.parse_source(md_path)
    # 源稿一般放在课题的 .workbuddy/ 下，图片写作 assets/xxx.jpg（相对课题根）
    root = os.path.dirname(os.path.dirname(os.path.abspath(md_path)))
    for cells, _ in rows:
        for _, cs in cells:
            p = cs.get("path")
            if cs["t"] == "image" and p and not os.path.isabs(p) and not os.path.exists(p):
                cand = os.path.join(root, p)
                if os.path.exists(cand):
                    cs["path"] = cand

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = X.Ctx.body
    st.font.size = Pt(V.FS_BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), X.Ctx.body)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(V.PAGE_W), Cm(V.PAGE_H)
    sec.top_margin, sec.bottom_margin = Cm(V.M_TOP), Cm(V.M_BOTTOM)
    sec.left_margin, sec.right_margin = Cm(V.M_LEFT), Cm(V.M_RIGHT)
    sec.header_distance, sec.footer_distance = Cm(V.HDR_DIST), Cm(V.FTR_DIST)

    # 口径覆盖①：沿用四类共用的 build_header()，不加参数、不分叉
    X.build_header(sec, V.CONTENT_W, text=header_text or title,
                   logo=None, logo_mode="placeholder")
    for footer in (sec.footer, sec.first_page_footer):
        p = footer.paragraphs[0]
        X.fmt_para(p, 0, 0, line=None, align=V.CENTER_A)
        X.add_run(p, "第 ", size=V.FS_HF, color=V.FOOT)
        X.add_page_field(p, size=V.FS_HF, color=V.FOOT)
        X.add_run(p, " 页", size=V.FS_HF, color=V.FOOT)

    all_rows = ([V.title_row(title)] if title else []) + rows

    # 沿用 V3.0 的两处定向 keepNext：板书标题→板书图、「四、教学过程」→环节标题
    for k, (cells, opts) in enumerate(all_rows):
        cs = cells[0][1]
        if cs["t"] in ("band", "band2", "head"):
            nxt = all_rows[k + 1][0][0][1] if k + 1 < len(all_rows) else None
            opts["keep"] = bool(
                (nxt and nxt["t"] == "image")
                or "教学过程" in cs.get("text", ""))

    blocks = split_blocks(all_rows)
    for free, group in blocks:
        if free:
            for cells, opts in group:
                render_free(doc, cells, opts)
        else:
            t = V.build_table(doc, group)
            align_table_to_text(t, V.CELL_MAR[0])   # 170 twips = 3mm

    doc.save(out_path)
    return len(all_rows), len(blocks), sum(1 for f, _ in blocks if not f), title


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--header", default="", help="页眉右侧课题；留空则用源稿主标题")
    a = ap.parse_args()
    n, b, t, title = build(a.input, a.output, a.header)
    print("生成完成：%s | 逻辑行 %d | 块 %d（其中表格 %d 张）| 主标题 %s"
          % (a.output, n, b, t, title))
