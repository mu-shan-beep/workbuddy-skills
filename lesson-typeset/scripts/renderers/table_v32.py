#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3.2｜按功能判断表格（正式引擎，2026-11-06 固化）
====================================================
用户 2026-11-06 反馈：「课时主题这些内容不应该使用表格吧，skill 只是辅助我们提效，
你也应该思考哪些使用表格合适，哪些不用合适」。

统一判据（不再按「有没有框线」机械分块，而是问「表格在这里提供了什么」）：

    用表格  ⇔ ① 二维数据需要列与列横向对齐（四列教学活动、对照表、评价量表）
             ② 格子 / 横线本身是作答载体（作答线、填写线、田字格）
             ③ 页眉左右分区（Logo 预留区 + 品牌文字，共用 build_header）
             ④ 「图版」——板书设计这类要与上方表格同框同宽、作为版式
                一部分的教学图，用单行通栏表格（20 格网格 / tblInd=170 /
                0.5pt 同色框线），和四列活动表属于同一套结构
    用段落  ⇔ ① 单行「标签＋一行值」（课题 / 作者 / 课时主题 …）
             ② 只给单块文字加底纹或边框的装饰性 1×1 表
             ③ 主标题、章节标题、环节分区标题、长段落
             ④ 「插图」——课件截图、配图等独立图片，用专门的插图样式
                （居中、独立上下留白、图注 9.5pt），不套表格的缩进 /
                框线 / 行距，也不用表格的段前段后

段落侧的视觉替代：字段行用制表位对齐（无竖线）、强调块用段落底纹、
分区标题用底纹＋上下边线。四列活动表保持 V3.1 的 20 格网格 /
4:7:5:4 / tblInd=170 不变，保证教学活动看起来完全一样。
图版与插图是两类不同构件，不再一律「有框线才成表」。
"""
import argparse
import os
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)          # 优先用本目录的引擎副本
import table_v30 as V
import xuexqingdan_typeset as X

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

FREE_IND = Mm(3)          # 与表格单元格 3mm 左右内边距对齐
TAB_STOPS = (Mm(38), Mm(79), Mm(120))   # 相对 left_indent：对应 5/10/15 格


def align_table_to_text(t, twips):
    tblPr = t._tbl.tblPr
    ind = tblPr.find(qn("w:tblInd"))
    if ind is None:
        ind = OxmlElement("w:tblInd")
        X._put(tblPr, ind, X._TBLPR_ORDER)
    ind.set(qn("w:type"), "dxa")
    ind.set(qn("w:w"), str(twips))


def para_border(p, edges, sz=V.BORDER_THICK, color=V.LINE):
    """段落边框：替代「只是想画个框」的 1×1 表格。"""
    pPr = p._p.get_or_add_pPr()
    bdr = pPr.find(qn("w:pBdr"))
    if bdr is None:
        bdr = OxmlElement("w:pBdr")
        pPr.insert_element_before(
            bdr, "w:shd", "w:tabs", "w:spacing", "w:ind", "w:jc",
            "w:rPr", "w:sectPr", "w:pPrChange")
    for edge in ("top", "left", "bottom", "right"):
        if edge not in edges:
            continue
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), color)
        bdr.append(e)


def render_free(doc, cells, opts):
    """把「不需要表格」的行渲染成文档级普通段落。"""
    cs = cells[0][1]
    t = cs["t"]

    if t == "title":
        p = doc.add_paragraph()
        X.fmt_para(p, 2, 4, line=1.2, align=V.CENTER_A)
        X.add_run(p, cs["text"], size=V.FS_TITLE, color=V.TITLE,
                  bold=True, font=X.Ctx.head)
        return

    if t == "band":                       # 一级章节标题：底纹段落
        p = doc.add_paragraph()
        # 脱表后标题与正文是两个独立段落，必须绑定，否则标题会孤悬页底
        X.fmt_para(p, V.BAND_BEFORE, V.BAND_AFTER, line=1.2,
                   left=Cm(0), first=FREE_IND, align=V.LEFT_A,
                   keep_next=True)
        V.shade_paragraph(p, V.BAND)
        X.add_run(p, cs["text"], size=V.FS_H1, color=V.GREEN,
                  bold=True, font=X.Ctx.head)
        return

    if t == "band2":                      # 环节分区：底纹段落 + 上下边线（不建 1×1 表）
        p = doc.add_paragraph()
        # 下接图版表格时压紧段前段后：图版行本身较高，多留 6mm 会把标题＋图
        # 整组挤到下一页，出现「末页只剩一张图」。
        compact = opts.get("drop_bottom", False)
        X.fmt_para(p, 0 if compact else V.SUB_BEFORE,
                   0 if compact else V.SUB_AFTER, line=1.2,
                   left=Cm(0), first=FREE_IND, align=V.LEFT_A,
                   keep_next=True)
        V.shade_paragraph(p, V.BAND)
        # 下接图版表格时，表格自身的上框线就是分隔线，不再画一条重复的下边线
        edges = ("top",) if opts.get("drop_bottom") else ("top", "bottom")
        para_border(p, edges)
        X.add_run(p, cs["text"], size=V.FS_H2, color=V.GREEN,
                  bold=True, font=X.Ctx.head)
        return

    if t == "flabel":                    # 单行「标签＋值」：制表位对齐，无框线无竖线
        p = doc.add_paragraph()
        p.paragraph_format.right_indent = FREE_IND
        X.fmt_para(p, 0, Pt(4), line=V.LINE_CELL,
                   left=FREE_IND, align=V.LEFT_A, keep_next=True)
        for stop in TAB_STOPS:
            p.paragraph_format.tab_stops.add_tab_stop(stop)
        parts = [c for _, c in cells]
        for k, item in enumerate(parts):
            if item["t"] == "flabel":
                X.add_run(p, item["text"], size=V.FS_TH, color=V.GREEN,
                          font=X.Ctx.head)
                if k < len(parts) - 1:
                    p.add_run("\t")
            else:
                X.add_rich(p, item["text"], size=V.FS_CELL, color=V.INK)
                if k < len(parts) - 2:
                    p.add_run("\t")
        return

    if t == "image":                      # 「插图」：独立版式，不模仿表格
        # 与表格脱钩：无缩进、无边框、不用 band2 的段前段后；
        # 图片上下各留 6pt，图注另起一段 9.5pt 居中灰字。
        p = doc.add_paragraph()
        X.fmt_para(p, Pt(6), Pt(6), line=1.0, align=V.CENTER_A, keep_next=True)
        if os.path.exists(cs["path"]):
            p.add_run().add_picture(cs["path"], width=Cm(V.IMG_W_CM))
        cap = cs.get("alt", "").strip()
        if cap:
            pc = doc.add_paragraph()
            X.fmt_para(pc, 0, Pt(4), line=1.2, align=V.CENTER_A)
            X.add_run(pc, cap, size=V.FS_CAP, color=V.MUTED, font=X.Ctx.body)
        return

    if t == "group":
        parts = cs["parts"]
        framed = opts.get("bd") == "thin"      # 辅助对照容器：整块一个框，但不是表格
        for k, (kind, text) in enumerate(parts):
            p = doc.add_paragraph()
            p.paragraph_format.right_indent = FREE_IND
            if kind == "sub":
                X.fmt_para(p, V.SUB_BEFORE if k else 0, V.SUB_AFTER, line=1.25,
                           left=Cm(0), first=FREE_IND, align=V.LEFT_A,
                           keep_next=True)
                V.shade_paragraph(p, V.BAND)
                X.add_run(p, text, size=V.FS_H2, color=V.GREEN,
                          bold=True, font=X.Ctx.head)
            elif kind == "item":
                X.fmt_para(p, 0, V.AFTER_BODY, line=V.LINE_ITEM,
                           left=FREE_IND + V.HANG, first=Mm(-6), align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_BODY, color=V.INK)
            elif kind == "tab":
                X.fmt_para(p, 0, V.AFTER_CELL, line=V.LINE_CELL,
                           left=FREE_IND, align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_CELL, color=V.INK)
            else:
                X.fmt_para(p, 0, V.AFTER_BODY, line=V.LINE_BODY,
                           left=FREE_IND, first=V.FIRST_INDENT, align=V.LEFT_A)
                X.add_rich(p, text, size=V.FS_BODY, color=V.INK)
            if framed:
                edges = ["left", "right"]
                if k == 0:
                    edges.append("top")
                if k == len(parts) - 1:
                    edges.append("bottom")
                para_border(p, tuple(edges), sz=V.BORDER_THIN)
        return

    raise ValueError("脱表行出现未处理的类型：%s" % t)


def needs_table(cells, opts):
    """进表的两类：二维列对齐的行、需要与表格同构的「图版」行。"""
    if any(cs["t"] in ("head", "actname", "lines", "ghead", "gcell")
           for _, cs in cells):
        return True
    return opts.get("figure_panel", False)


def split_blocks(rows):
    blocks = []
    for cells, opts in rows:
        free = not needs_table(cells, opts)
        if blocks and blocks[-1][0] == free:
            blocks[-1][1].append((cells, opts))
        else:
            blocks.append((free, [(cells, opts)]))
    return blocks


def build(md_path, out_path, header_text, font_head=None, font_body=None):
    X.Ctx.head = font_head or X.resolve_font(X.HEAD_CANDIDATES, "思源黑体")
    X.Ctx.body = font_body or X.resolve_font(X.BODY_CANDIDATES, "楷体")

    title, rows = V.parse_source(md_path)
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

    X.build_header(sec, V.CONTENT_W, text=header_text or title,
                   logo=None, logo_mode="placeholder")
    for footer in (sec.footer, sec.first_page_footer):
        p = footer.paragraphs[0]
        X.fmt_para(p, 0, 0, line=None, align=V.CENTER_A)
        X.add_run(p, "第 ", size=V.FS_HF, color=V.FOOT)
        X.add_page_field(p, size=V.FS_HF, color=V.FOOT)
        X.add_run(p, " 页", size=V.FS_HF, color=V.FOOT)

    all_rows = ([V.title_row(title)] if title else []) + rows

    # 「板书设计」下的图属于图版：与上方四列活动表同框同宽，进表格。
    # 其他图片（课件截图等）是插图，仍走独立的段落版式。
    last_heading = ""
    for k, (cells, opts) in enumerate(all_rows):
        cs = cells[0][1]
        if cs["t"] in ("band", "band2"):
            last_heading = cs.get("text", "")
        if cs["t"] == "image" and "板书设计" in last_heading:
            opts["figure_panel"] = True
            prev = all_rows[k - 1][1] if k else None
            if prev is not None:
                prev["drop_bottom"] = True

    for k, (cells, opts) in enumerate(all_rows):
        cs = cells[0][1]
        if cs["t"] in ("band", "band2"):
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
            align_table_to_text(t, V.CELL_MAR[0])
    doc.save(out_path)
    return len(all_rows), len(blocks), sum(1 for f, _ in blocks if not f), title


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--header", default="")
    a = ap.parse_args()
    n, b, t, title = build(a.input, a.output, a.header)
    print("生成完成：%s | 逻辑行 %d | 块 %d（其中表格 %d 张）| 主标题 %s"
          % (a.output, n, b, t, title))
