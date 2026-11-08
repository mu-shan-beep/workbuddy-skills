#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学生学习清单「统一排版标准 V2.1」排版引擎
========================================

A4 练习纸：绿色标题栏 + 思源黑体标题 + 楷体正文 + 真线段作答区 + 田字格 + 三星自评。
版式常量以 references/unified-spec.md 第 1 章为唯一权威；改动前先出预览、经用户确认。

用法：
    python3 xuexqingdan_typeset.py --input 学习清单_第一课时.md \
        --header "23 王戎不取道旁李" \
        --output 23王戎不取道旁李-第一课时-学习清单.docx

    # 双面装订（奇偶页镜像：内侧 20mm / 外侧 18mm）
    python3 xuexqingdan_typeset.py --input ... --mirror
"""

import argparse
import math
import os
import re
import subprocess
import tempfile

from docx import Document
from docx.enum.table import (WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT,
                             WD_ROW_HEIGHT_RULE)
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

# ─────────────────── 版式常量（V2.1） ───────────────────

PAGE_W, PAGE_H = 21.0, 29.7            # A4 纵向
M_TOP = M_BOTTOM = 1.6                 # 上下 16mm
M_LEFT = M_RIGHT = 1.8                 # 左右 18mm（单面）
M_INNER, M_OUTER = 2.0, 1.8            # 双面装订：内侧 20 / 外侧 18
HDR_DIST = 0.9
FTR_DIST = 0.8

CONTENT_W = PAGE_W - M_LEFT - M_RIGHT          # 17.4cm
MIRROR_CONTENT_W = PAGE_W - M_INNER - M_OUTER  # 17.2cm

# 颜色
GREEN = "315A4B"     # 主标题 / 一级标题
INK = "2B302C"       # 正文
MUTED = "596960"     # 辅助文字
BAND = "EDF3EE"      # 标题栏 / 表头底色
LINE = "9BA9A0"      # 表格边框 / 填写横线
GRID_IN = "B5C7B9"   # 田字格内部虚线
WHITE = "FFFFFF"

# 页眉 Logo 区（四类文档统一复用，与教学设计 / 逐字稿同一套）
LOGO_W_MM = 30.0     # 预留区 30 × 12mm
LOGO_H_MM = 12.0
LOGO_MAX_H_MM = 10.0  # 实际最大显示高度
PH_TEXT = "999999"    # Logo 占位文字色
PH_BORDER = "B8B8B8"  # Logo 占位框虚线
SEP = "CBD5CD"        # 页眉分隔线

# 字号
FS_TITLE = 17.0      # 主标题
FS_H1 = 12.5         # 一级标题（标题栏）
FS_H2 = 11.5         # 二级标题
FS_BODY = 11.0       # 正文
FS_TH = 11.0         # 表格表头
FS_AUX = 10.5        # 辅助文字
FS_HF = 9.0          # 页眉页脚
FS_PH = 8.0          # Logo 占位文字

LINE_BODY = 1.4      # 正文行距
LINE_TITLE = 1.2

# 间距（mm）
GAP_GAP = 3.5        # 段落之间 3—5
GAP_ITEM = 4.5       # 同级项目 4—6
GAP_MODULE = 7.0     # 模块之间 6—8
GAP_TITLE = 6.0      # 主标题下方 5—7
GAP_H1_TEXT = 4.0    # 标题与正文 4—5

# 构件尺寸
BAND_H = 12.0        # 标题栏高 11—13mm
BAND_PAD_X = 4.0     # 标题栏左右内边距 4mm
ROW_H = 12.0         # 表格单行最小高 12mm
WRITE_H = 10.0       # 填写横线间距（三四年级 9—11mm）
CELL_MAR = (170, 170, 142, 142)   # 左/右 3mm、上/下 2.5mm（twips）

GRID_CELL_MM = 18.0  # 田字格 18—20mm
GRID_GAP_MM = 3.5    # 相邻格 3—4mm
GRID_PER_CHAR = 4    # 每字 1 范字 + 3 练习格

BORDER_OUT = 6       # 0.75pt
BORDER_IN = 4        # 0.5pt

MM2PT = 72 / 25.4


def mm2pt(mm):
    return Pt(mm * MM2PT)


# ─────────────────── 字体解析 ───────────────────

def _zh_families():
    try:
        out = subprocess.run(["fc-list", ":lang=zh", "family"],
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return set()
    fams = set()
    for line in out.splitlines():
        for f in line.split(","):
            fams.add(f.strip())
    return fams


HEAD_CANDIDATES = ["思源黑体", "思源黑体 CN", "Source Han Sans SC", "Source Han Sans CN",
                   "Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "微软雅黑",
                   "Microsoft YaHei", "Heiti SC", "黑体", "SimHei"]
BODY_CANDIDATES = ["楷体", "KaiTi", "Kaiti SC", "STKaiti", "楷体_GB2312"]


def resolve_font(candidates, fallback):
    """按候选顺序取本机真实存在的字族，保证全篇统一替换、不局部混用。"""
    fams = _zh_families()
    err = []
    for name in candidates:
        if name in fams:
            return name
        err.append(name)
    # 中文名在部分系统上以本地化名注册，退回首选名让 Word 自行替换
    return fallback


# ─────────────────── OOXML 有序插入 ───────────────────
# Word 对 pPr / tblPr / tcPr / trPr 的子元素顺序是严格的，顺序错了会静默丢格式
# （LibreOffice 较宽容，所以预览看不出来）。所有自定义属性一律按 schema 顺序插入。

_PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
              "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
              "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
              "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi",
              "adjustRightInd", "snapToGrid", "spacing", "ind", "contextualSpacing",
              "mirrorIndents", "suppressOverlap", "jc", "textDirection",
              "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle",
              "rPr", "sectPr", "pPrChange"]

_TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual",
                "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
                "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout",
                "tblCellMar", "tblLook", "tblCaption", "tblDescription"]

_TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
               "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark"]

_TRPR_ORDER = ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
               "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden"]


def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _put(parent, elem, order):
    """按 schema 顺序把 elem 插入 parent，替换同名旧节点。"""
    name = _local(elem.tag)
    for old in parent.findall(elem.tag):
        parent.remove(old)
    idx = order.index(name) if name in order else len(order)
    for child in list(parent):
        c = _local(child.tag)
        if c in order and order.index(c) > idx:
            child.addprevious(elem)
            return elem
    parent.append(elem)
    return elem


# ─────────────────── 底层工具 ───────────────────

def set_run(run, size=None, color=None, bold=False, font=None):
    f = font
    run.font.name = f
    rPr = run._r.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(attr), f)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    run.font.bold = bold
    return run


class Ctx:
    """渲染上下文：持有实际使用的字族名。"""
    head = "思源黑体"
    body = "楷体"


def add_run(p, text, size=None, color=None, bold=False, font=None):
    return set_run(p.add_run(text), size=size, color=color, bold=bold,
                   font=font or Ctx.body)


def add_rich(p, text, size, color, font=None, bold=False):
    """支持行内 **加粗**。"""
    for seg in re.split(r"(\*\*.+?\*\*)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            add_run(p, seg[2:-2], size=size, color=color, font=font, bold=True)
        else:
            add_run(p, seg, size=size, color=color, font=font, bold=bold)


def fmt_para(p, before=0.0, after=0.0, line=LINE_BODY, left=None, first=None,
             align=None, keep_next=False, exact_pt=None):
    pf = p.paragraph_format
    pf.space_before = Pt(before) if not isinstance(before, Pt) else before
    pf.space_after = Pt(after) if not isinstance(after, Pt) else after
    if exact_pt is not None:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(exact_pt)
    elif line is None:
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    else:
        pf.line_spacing = line
    pf.left_indent = Cm(0) if left is None else left
    pf.first_line_indent = Cm(0) if first is None else first
    if align is not None:
        p.alignment = align
    pf.keep_with_next = keep_next
    pf.widow_control = True


def para_bottom_border(p, sz=BORDER_OUT, color=LINE, space=0):
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(sz))
    bottom.set(qn("w:space"), str(space))
    bottom.set(qn("w:color"), color)
    bdr.append(bottom)
    _put(pPr, bdr, _PPR_ORDER)


def gap(doc, mm, keep_next=False):
    """表格类构件之间的透气段（表格前后不能用段距）。"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(max(1.0, mm * MM2PT))
    pf.keep_with_next = keep_next
    r = p.add_run("")
    r.font.size = Pt(1)
    return p


def add_page_field(p, size=FS_HF, color=MUTED):
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), " PAGE ")
    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    rf = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia"):
        rf.set(qn(attr), Ctx.body)
    rPr.append(rf)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    rPr.append(sz)
    col = OxmlElement("w:color")
    col.set(qn("w:val"), color)
    rPr.append(col)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.text = "1"
    r.append(t)
    fld.append(r)
    p._p.append(fld)


# ─────────────────── 表格 ───────────────────

def _tbl_borders(table, outer=BORDER_OUT, inner=BORDER_IN, color=LINE):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge, sz in (("top", outer), ("left", outer), ("bottom", outer), ("right", outer),
                     ("insideH", inner), ("insideV", inner)):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), str(sz))
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), color)
        b.append(e)
    _put(tblPr, b, _TBLPR_ORDER)


def _set_row_h(row, mm):
    """显式写 hRule=atLeast —— 只给 val 时 Word/LO 按内容自适应，行高会塌。"""
    row.height = Mm(mm)
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


def _no_borders(table):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "none")
        e.set(qn("w:sz"), "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), "auto")
        b.append(e)
    _put(tblPr, b, _TBLPR_ORDER)


def _tbl_margins(table, left=170, right=170, top=142, bottom=142):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for name, val in (("left", left), ("right", right), ("top", top), ("bottom", bottom)):
        e = OxmlElement("w:" + name)
        e.set(qn("w:w"), str(val))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    _put(tblPr, mar, _TBLPR_ORDER)


def _tbl_width(table, cm_width):
    """同时写 tblW / tblGrid / tcW —— 三者不一致时 Word 会把列拉平。"""
    tblPr = table._tbl.tblPr
    w = OxmlElement("w:tblW")
    w.set(qn("w:type"), "dxa")
    w.set(qn("w:w"), str(int(cm_width * 567)))
    _put(tblPr, w, _TBLPR_ORDER)
    table.autofit = False
    tblPr_lay = OxmlElement("w:tblLayout")
    tblPr_lay.set(qn("w:type"), "fixed")
    _put(tblPr, tblPr_lay, _TBLPR_ORDER)


def set_col_widths(table, widths_cm):
    total = sum(widths_cm)
    for i, w in enumerate(widths_cm):
        table.columns[i].width = Cm(w)
        for row in table.rows:
            row.cells[i].width = Cm(w)
    _tbl_width(table, total)
    # tblGrid 与 tcW 逐列对齐
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for gc, w in zip(grid.findall(qn("w:gridCol")), widths_cm):
            gc.set(qn("w:w"), str(int(w * 567)))


def _cell_shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    _put(tcPr, shd, _TCPR_ORDER)


def _cell_bottom_border(cell, sz=BORDER_OUT, color=LINE):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    e = OxmlElement("w:bottom")
    e.set(qn("w:val"), "single")
    e.set(qn("w:sz"), str(sz))
    e.set(qn("w:space"), "0")
    e.set(qn("w:color"), color)
    b.append(e)
    _put(tcPr, b, _TCPR_ORDER)


def _row_cant_split(row):
    trPr = row._tr.get_or_add_trPr()
    _put(trPr, OxmlElement("w:cantSplit"), _TRPR_ORDER)


def _row_header(row):
    trPr = row._tr.get_or_add_trPr()
    _put(trPr, OxmlElement("w:tblHeader"), _TRPR_ORDER)


def _first_para(cell, align=WD_ALIGN_PARAGRAPH.LEFT, line=1.3):
    p = cell.paragraphs[0]
    fmt_para(p, before=0, after=0, line=line, align=align)
    return p


def _cell_para(cell, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = cell.add_paragraph()
    fmt_para(p, before=0, after=0, line=1.3, align=align)
    return p


def content_width(mirror=False):
    return MIRROR_CONTENT_W if mirror else CONTENT_W


def shade_paragraph(p, fill):
    """段落底纹：替代「只是想给一块文字上色」的 1×1 表格。"""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr = p._p.get_or_add_pPr()
    pPr.insert_element_before(
        shd, "w:spacing", "w:ind", "w:jc", "w:rPr", "w:sectPr", "w:pPrChange")


def band(doc, text, width_cm):
    """一级标题栏：段落底纹（纯装饰的 1×1 表，按统一判据不再使用表格）。"""
    p = doc.add_paragraph()
    # 固定行高替代原 1×1 表格的 BAND_H，底纹高度与改前一致
    fmt_para(p, before=0, after=0, line=None, exact_pt=BAND_H * MM2PT,
             align=WD_ALIGN_PARAGRAPH.LEFT, keep_next=True)
    p.paragraph_format.first_line_indent = Cm(BAND_PAD_X / 10.0)
    shade_paragraph(p, BAND)
    add_run(p, text, size=FS_H1, color=GREEN, bold=True, font=Ctx.head)
    return p


def blank_table(doc, labels, width_cm):
    """「标签：____」行：标签格无边框，作答格画下边框，横线不穿文字。"""
    n = max(1, len(labels))
    lab_w = [min(6.4, 0.40 * len(lab) + 0.25) for lab in labels]
    line_w = max(2.0, (width_cm - sum(lab_w)) / n)
    widths = []
    for w in lab_w:
        widths += [w, line_w]

    t = doc.add_table(rows=1, cols=2 * n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(t)
    _tbl_margins(t, 0, 0, 0, 0)
    row = t.rows[0]
    _set_row_h(row, WRITE_H)
    for i, lab in enumerate(labels):
        c_lab = row.cells[i * 2]
        c_line = row.cells[i * 2 + 1]
        # 标签与作答线同基线：两格都底端对齐，标签加 1.2pt 下留白避免压线
        for c in (c_lab, c_line):
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
        p0 = _first_para(c_lab, align=WD_ALIGN_PARAGRAPH.RIGHT)
        p0.paragraph_format.space_after = Pt(1.2)
        add_run(p0, lab, size=FS_BODY, color=INK)
        p1 = _first_para(c_line)
        p1.paragraph_format.space_after = Pt(0)
        p1.add_run("")
        _cell_bottom_border(c_line, sz=BORDER_OUT, color=LINE)
    set_col_widths(t, widths)
    return t


def data_table(doc, headers, rows, width_cm, widths=None):
    cols = len(headers) if headers else max(len(r) for r in rows)
    if widths is None:
        if cols == 2:
            widths = [width_cm * 0.30, width_cm * 0.70]
        elif cols == 4:
            widths = [width_cm * 0.28] + [width_cm * 0.24] * 3
        else:
            widths = [width_cm / cols] * cols

    t = doc.add_table(rows=0, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tbl_borders(t, BORDER_OUT, BORDER_IN, LINE)
    _tbl_margins(t, *CELL_MAR)

    has_head = bool(headers) and any((h or "").strip() for h in headers)
    if has_head:                    # 表头全空＝无表头的作答网格，不画浅绿表头行
        row = t.add_row()
        _row_header(row)
        _row_cant_split(row)
        _set_row_h(row, ROW_H)
        for i, h in enumerate(headers):
            c = row.cells[i]
            _cell_shade(c, BAND)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = _first_para(c, align=WD_ALIGN_PARAGRAPH.CENTER)
            p.paragraph_format.keep_with_next = True   # 表头不单独留页底
            add_run(p, h, size=FS_TH, color=INK, font=Ctx.head)

    for vals in rows:
        row = t.add_row()
        _row_cant_split(row)
        _set_row_h(row, ROW_H)
        for i in range(cols):
            val = vals[i] if i < len(vals) else ""
            c = row.cells[i]
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = _first_para(c)
            add_rich(p, val, size=FS_BODY, color=INK)

    set_col_widths(t, widths)
    return t


def write_lines(doc, n, width_cm, height_mm=WRITE_H):
    """多行填写横线：逐行给下边框。
    相邻段落画同样的底边框时，Word / LibreOffice 会把它们合并成一条线，表格不会。"""
    t = doc.add_table(rows=n, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(t)
    _tbl_margins(t, 0, 0, 0, 0)
    for row in t.rows:
        _set_row_h(row, height_mm)
        _row_cant_split(row)
        c = row.cells[0]
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
        p = _first_para(c)
        p.add_run("")
        _cell_bottom_border(c, sz=BORDER_OUT, color=LINE)
    set_col_widths(t, [width_cm])
    return t


def grid_table(doc, chars, tmpdir, per, width_cm, tag_w=1.5):
    """田字格：一张无边框表，左列字头（垂直居中）、右列格子图。"""
    imgs = grid_images(chars, tmpdir, per=per)
    t = doc.add_table(rows=len(imgs), cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(t)
    _tbl_margins(t, 0, 0, 0, 0)
    for row, ch, (path, w_cm, h_cm) in zip(t.rows, chars, imgs):
        _set_row_h(row, GRID_CELL_MM + 3)
        _row_cant_split(row)
        c0, c1 = row.cells[0], row.cells[1]
        c0.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        c1.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p0 = _first_para(c0, align=WD_ALIGN_PARAGRAPH.RIGHT)
        add_run(p0, ch + "：", size=FS_H2, color=GREEN, font=Ctx.head)
        p1 = _first_para(c1)
        p1.paragraph_format.space_before = Pt(1.6)
        p1.paragraph_format.space_after = Pt(1.6)
        p1.add_run().add_picture(path, width=Cm(w_cm))
    set_col_widths(t, [tag_w, width_cm - tag_w])
    return t


def stars_table(doc, items, width_cm):
    heads = ["评价内容", "☆☆☆\n独立完成", "☆☆\n借助提示", "☆\n还需练习"]
    t = doc.add_table(rows=0, cols=4)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tbl_borders(t, BORDER_OUT, BORDER_IN, LINE)
    _tbl_margins(t, *CELL_MAR)

    row = t.add_row()
    _row_header(row)
    _row_cant_split(row)
    _set_row_h(row, ROW_H)
    for i, h in enumerate(heads):
        c = row.cells[i]
        _cell_shade(c, BAND)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        lines = h.split("\n")
        p = _first_para(c, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(p, lines[0], size=FS_TH, color=INK, font=Ctx.head)
        for extra in lines[1:]:
            p2 = _cell_para(c, align=WD_ALIGN_PARAGRAPH.CENTER)
            add_run(p2, extra, size=FS_AUX, color=MUTED, font=Ctx.head)

    for it in items:
        row = t.add_row()
        _row_cant_split(row)
        _set_row_h(row, ROW_H)
        c = row.cells[0]
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        add_run(_first_para(c), it, size=FS_BODY, color=INK)
        for k, sym in enumerate(("☆☆☆", "☆☆", "☆")):
            c2 = row.cells[k + 1]
            c2.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            add_run(_first_para(c2, align=WD_ALIGN_PARAGRAPH.CENTER), sym,
                    size=FS_BODY, color=INK)

    widths = [width_cm * 0.46] + [width_cm * 0.18] * 3
    set_col_widths(t, widths)
    return t


# ─────────────────── 田字格（图片） ───────────────────

def _font_path():
    for c in ("/System/Library/Fonts/Supplemental/Kaiti.ttc",
              "/Library/Fonts/Kaiti.ttc",
              os.path.expanduser("~/Library/Fonts/楷体_GB2312.TTF"),
              "C:/Windows/Fonts/simkai.ttf",
              "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"):
        if os.path.exists(c):
            return c
    return None


def _dashed(draw, seg, color, width, dash, gap):
    (x1, y1), (x2, y2) = seg
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist == 0:
        return
    ux, uy = dx / dist, dy / dist
    pos = 0.0
    while pos < dist:
        end = min(pos + dash, dist)
        draw.line([(x1 + ux * pos, y1 + uy * pos), (x1 + ux * end, y1 + uy * end)],
                  fill=color, width=width)
        pos = end + gap


def grid_images(chars, tmpdir, per=GRID_PER_CHAR):
    """每个字一行：首格范字 + (per-1) 空格；返回 [(路径, 宽cm, 高cm)]。"""
    from PIL import Image, ImageDraw, ImageFont

    dpi = 300
    to_px = lambda mm: int(round(mm / 25.4 * dpi))
    cw = to_px(GRID_CELL_MM)
    gp = to_px(GRID_GAP_MM)
    font_path = _font_path()
    px = lambda pt: max(1, int(round(pt / 72 * dpi)))
    outer_w = px(0.75)      # 外框 0.75pt
    mid_w = px(0.5)         # 中心横竖 0.5pt
    diag_w = px(0.45)       # 对角 0.45pt
    dash, dgap = px(2.2), px(1.6)
    out = []

    for idx, ch in enumerate(chars):
        W = cw * per + gp * (per - 1)
        img = Image.new("RGB", (W, cw), "white")
        d = ImageDraw.Draw(img)

        for k in range(per):
            x0 = k * (cw + gp)
            cx, cy = x0 + cw / 2.0, cw / 2.0
            d.rectangle([x0, 0, x0 + cw - 1, cw - 1],
                        outline="#" + LINE, width=outer_w)
            for seg in (((cx, 1), (cx, cw - 2)), ((x0 + 1, cy), (x0 + cw - 2, cy))):
                _dashed(d, seg, "#" + GRID_IN, mid_w, dash, dgap)
            for seg in (((x0 + 1, 1), (x0 + cw - 2, cw - 2)),
                        ((x0 + 1, cw - 2), (x0 + cw - 2, 1))):
                _dashed(d, seg, "#" + GRID_IN, diag_w, dash, dgap)

            if k == 0 and font_path:
                try:
                    f = ImageFont.truetype(font_path, int(cw * 0.56))
                    bb = d.textbbox((0, 0), ch, font=f)
                    tw, th = bb[2] - bb[0], bb[3] - bb[1]
                    d.text((x0 + (cw - tw) / 2 - bb[0], (cw - th) / 2 - bb[1]),
                           ch, font=f, fill="#" + INK)
                except Exception:
                    pass

        path = os.path.join(tmpdir, "grid_%02d_%s.png" % (idx, ch))
        img.save(path, dpi=(dpi, dpi))
        out.append((path, (per * GRID_CELL_MM + (per - 1) * GRID_GAP_MM) / 10.0,
                    GRID_CELL_MM / 10.0))
    return out


# ─────────────────── 解析 ───────────────────

def parse(md):
    lines = md.replace("\r\n", "\n").split("\n")
    blocks, i = [], 0
    is_sep = re.compile(r"^[\s|:\-]+$")

    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        if s.startswith("|") and i + 1 < len(lines) and is_sep.match(lines[i + 1].strip()):
            headers = cells(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            blocks.append(("table", (headers, rows)))
            continue

        m = re.match(r"^:::\s*(\w+)\s*(.*)$", s)
        if m:
            blocks.append((m.group(1), m.group(2).strip()))
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            txt = m.group(2).strip()
            kind = {1: "h1", 2: "h2", 3: "h3", 4: "h4"}[lvl]
            blocks.append((kind, txt))
            i += 1
            continue

        if s.startswith(">"):
            blocks.append(("quote", s[1:].strip()))
            i += 1
            continue

        if re.match(r"^[-*]\s+", s):
            blocks.append(("ans", re.sub(r"^[-*]\s+", "", s)))
            i += 1
            continue

        blocks.append(("p", s))
        i += 1
    return blocks


# ─────────────────── 页眉 Logo（四类文档统一复用） ───────────────────

def _logo_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            w_px, h_px = im.size
    except Exception:
        return None
    h_cm = LOGO_MAX_H_MM / 10.0
    w_cm = h_cm * w_px / h_px
    if w_cm > LOGO_W_MM / 10.0:
        w_cm = LOGO_W_MM / 10.0
        h_cm = w_cm * h_px / w_px
    return w_cm, h_cm


def _header_rule(table):
    """页眉表格只留下边框：0.5pt #CBD5CD，宽度等于版心。

    不做独立分隔线段落——页眉区 12mm ＋ 距顶余量很小，多一个段落会把正文顶下去。
    """
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + edge)
        if edge == "bottom":
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), "4")
        else:
            e.set(qn("w:val"), "none")
            e.set(qn("w:sz"), "0")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), SEP if edge == "bottom" else "auto")
        b.append(e)
    _put(tblPr, b, _TBLPR_ORDER)


def _cell_dashed(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:val"), "dashed")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:space"), "0")
        e.set(qn("w:color"), PH_BORDER)
        b.append(e)
    _put(tcPr, b, _TCPR_ORDER)


def build_header(sec, cw, text="", logo=None, logo_mode="placeholder"):
    """页眉：左 30×12mm Logo 区 ＋ 右课题名，底边一条 0.5pt #CBD5CD 分隔线。

    无论有没有 Logo，Logo 区尺寸与正文起始位置都不变；四类文档（教学设计开放式、
    逐字稿、学习清单、制作笔记）共用此实现，保证页眉外观完全一致。

    Logo 文字固定「木老师原创课件」（2026-11-05 裁定①，2026-11-08 用户重申）：
    品牌文字本身就是 Logo，**不使用「LOGO占位」占位符，也不把品牌名拆到右侧独立位置**。
    只有传入 logo 图片时才换成实图；logo_mode="hidden" 时隐藏文字但仍留位。
    """
    hdr = sec.header
    hdr.is_linked_to_previous = False
    for p in list(hdr.paragraphs):          # 清掉默认空段，避免页眉被顶高
        p._p.getparent().remove(p._p)

    t = hdr.add_table(rows=1, cols=2, width=Cm(cw))
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    _header_rule(t)
    _tbl_margins(t, 0, 0, 0, 0)
    set_col_widths(t, [LOGO_W_MM / 10.0, cw - LOGO_W_MM / 10.0])

    row = t.rows[0]
    _set_row_h(row, LOGO_H_MM)
    _row_cant_split(row)
    c_logo, c_brand = row.cells
    for c in (c_logo, c_brand):
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    if logo and os.path.exists(logo):
        size = _logo_size(logo)
        p = _first_para(c_logo, align=WD_ALIGN_PARAGRAPH.LEFT, line=1.0)
        if size:
            p.add_run().add_picture(logo, width=Cm(size[0]), height=Cm(size[1]))
        else:
            p.add_run().add_picture(logo, height=Cm(LOGO_MAX_H_MM / 10.0))
    elif logo_mode == "placeholder":
        _cell_dashed(c_logo)
        p = _first_para(c_logo, align=WD_ALIGN_PARAGRAPH.CENTER, line=1.0)
        add_run(p, "木老师原创课件", size=FS_PH, color=PH_TEXT, font=Ctx.head)

    if text:
        p = _first_para(c_brand, align=WD_ALIGN_PARAGRAPH.RIGHT, line=1.0)
        add_run(p, text, size=FS_HF, color=MUTED, font=Ctx.head)

    # 页眉部件必须以段落收尾；1pt 行高，不占位
    tail = hdr.add_paragraph()
    fmt_para(tail, before=0, after=0, line=None)
    tail.paragraph_format.line_spacing = Pt(1)
    tail.add_run("").font.size = Pt(1)
    return hdr


# ─────────────────── 渲染 ───────────────────

def build(md, out_path, header, title=None, mirror=False,
          font_head=None, font_body=None):
    Ctx.head = font_head or resolve_font(HEAD_CANDIDATES, "思源黑体")
    Ctx.body = font_body or resolve_font(BODY_CANDIDATES, "楷体")

    cw = content_width(mirror)

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = Ctx.body
    st.font.size = Pt(FS_BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), Ctx.body)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin, sec.bottom_margin = Cm(M_TOP), Cm(M_BOTTOM)
    if mirror:
        sec.left_margin, sec.right_margin = Cm(M_INNER), Cm(M_OUTER)
        settings = doc.settings.element
        mm = OxmlElement("w:mirrorMargins")
        settings.insert(0, mm)
    else:
        sec.left_margin, sec.right_margin = Cm(M_LEFT), Cm(M_RIGHT)
    sec.header_distance = Cm(HDR_DIST)
    sec.footer_distance = Cm(FTR_DIST)

    blocks = parse(md)

    # 标题素材
    h1 = next((t for k, t in blocks if k == "h1"), "") or header
    kind_line = ""
    for k, t in blocks:
        if k == "h2" and "清单" in t:
            kind_line = t
            break
    for k, t in blocks:
        if k == "h2" and "清单" in t:
            blocks = [(kk, tt) for kk, tt in blocks if not (kk == "h2" and tt == t)]
            break
    doc_title = title or (("%s｜%s" % (h1.strip(), kind_line.strip()))
                          if kind_line else h1.strip())

    # 页眉：四类统一的 Logo 区（左 30×12mm「木老师原创课件」文字 Logo ＋ 右课题 ＋ CBD5CD 分隔线）
    build_header(sec, CONTENT_W, text=doc_title, logo=None, logo_mode="placeholder")

    # 页脚：页码（首页也要，全文一致）
    for footer in (sec.footer, sec.first_page_footer):
        p = footer.paragraphs[0]
        fmt_para(p, before=0, after=0, line=None, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(p, "第 ", size=FS_HF, color=MUTED)
        add_page_field(p, size=FS_HF, color=MUTED)
        add_run(p, " 页", size=FS_HF, color=MUTED)

    tmpdir = tempfile.mkdtemp(prefix="xqd_")

    # 标题信息区：主标题（17pt 居中）+ 班级／姓名／日期
    p = doc.add_paragraph()
    fmt_para(p, before=0, after=GAP_TITLE * MM2PT, line=LINE_TITLE,
             align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, doc_title, size=FS_TITLE, color=GREEN, bold=True, font=Ctx.head)

    blank_table(doc, ["班级：", "姓名：", "日期："], cw)

    last = None          # 上一个块的类型，用于算间距
    first_band = False   # 标题信息区已占位
    prev_is_table = False

    def body_before(default_mm):
        """按上一个块决定段前距。"""
        if last in (None,):
            return 0.0
        if last in ("h2", "h3"):          # 标题之后 → 标题与正文
            return GAP_H1_TEXT * MM2PT
        if last in ("table", "blank", "grid", "stars"):
            return 0.0                     # 表格后用 spacer 控制
        return default_mm * MM2PT

    for kind, payload in blocks:
        if kind == "h1":
            continue

        if kind == "h2":                   # 一级标题栏
            if not first_band:
                gap(doc, GAP_MODULE, keep_next=True)
            else:
                gap(doc, 0.6, keep_next=True)
            band(doc, payload, cw)
            first_band = False
            last = "h2"
            prev_is_table = True
            continue

        if kind == "h3":                   # 二级标题
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=(GAP_ITEM * MM2PT) if last else 0,
                     after=0, line=1.3, keep_next=True)
            add_rich(p, payload, size=FS_H2, color=GREEN, font=Ctx.head)
            last = "h3"
            prev_is_table = False
            continue

        if kind == "h4":                   # 三级标题（与二级同尺寸、不加粗）
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=(GAP_GAP * MM2PT) if last else 0,
                     after=0, line=1.3, keep_next=True)
            add_rich(p, payload, size=FS_BODY, color=GREEN)
            last = "h4"
            prev_is_table = False
            continue

        if kind == "p":
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=body_before(GAP_GAP), after=0, line=LINE_BODY)
            add_rich(p, payload, size=FS_BODY, color=INK)
            last = "p"
            prev_is_table = False
            continue

        if kind == "ans":
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=body_before(GAP_GAP), after=0, line=LINE_BODY)
            add_rich(p, payload, size=FS_BODY, color=INK)
            last = "ans"
            prev_is_table = False
            continue

        if kind == "quote":
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=body_before(GAP_GAP) + 1.5, after=1.5,
                     line=LINE_BODY)
            add_rich(p, payload, size=FS_BODY, color=GREEN)
            last = "quote"
            prev_is_table = False
            continue

        if kind == "tip":
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=body_before(GAP_GAP), after=0, line=1.35)
            add_rich(p, payload, size=FS_AUX, color=MUTED)
            last = "tip"
            prev_is_table = False
            continue

        if kind == "table":
            headers, rows = payload
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_ITEM, keep_next=True)
            else:
                gap(doc, GAP_GAP, keep_next=True)
            data_table(doc, headers, rows, cw)
            last = "table"
            prev_is_table = True
            continue

        if kind == "blank":
            segs = [x.strip() for x in payload.split("|") if x.strip()]
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, 2.0, keep_next=True)
            else:
                gap(doc, GAP_GAP, keep_next=True)
            blank_table(doc, segs, cw)
            last = "blank"
            prev_is_table = True
            continue

        if kind == "lines":
            n = int(payload) if payload.strip().isdigit() else 1
            gap(doc, GAP_ITEM if last in ("table", "blank", "grid", "stars") else GAP_GAP,
                keep_next=True)
            write_lines(doc, n, cw)
            last = "lines"
            prev_is_table = True
            continue

        if kind == "check":
            items = [x.strip() for x in payload.split("|") if x.strip()]
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_GAP, keep_next=True)
            p = doc.add_paragraph()
            fmt_para(p, before=body_before(GAP_GAP), after=0, line=1.5)
            for i, it in enumerate(items):
                if i:
                    add_run(p, "　　", size=FS_BODY, color=INK)
                add_run(p, "□", size=12.0, color=INK)
                add_run(p, "  ", size=FS_BODY, color=INK)
                add_run(p, it, size=FS_BODY, color=INK)
            last = "check"
            prev_is_table = False
            continue

        if kind == "grid":
            parts = payload.split()
            per = GRID_PER_CHAR
            if parts and parts[-1].isdigit():
                per = int(parts[-1])
                parts = parts[:-1]
            chars = [c for c in "".join(parts) if not c.isspace()]
            gap(doc, GAP_ITEM if last in ("table", "blank", "grid", "stars") else GAP_GAP,
                keep_next=True)
            grid_table(doc, chars, tmpdir, per, cw)
            last = "grid"
            prev_is_table = True
            continue

        if kind == "stars":
            items = [x.strip() for x in payload.split("|") if x.strip()]
            if last in ("table", "blank", "grid", "stars"):
                gap(doc, GAP_ITEM, keep_next=True)
            else:
                gap(doc, GAP_GAP, keep_next=True)
            if items:
                stars_table(doc, items, cw)
            else:
                p = doc.add_paragraph()
                fmt_para(p, before=0, after=0, line=1.4)
                add_run(p, "学习自评：", size=FS_AUX, color=MUTED)
                add_run(p, "☆☆☆ 独立完成　　☆☆ 借助提示完成　　☆ 还需练习",
                        size=FS_AUX, color=MUTED)
            last = "stars"
            prev_is_table = True
            continue

        if kind == "pagebreak":
            doc.add_page_break()
            last = None
            prev_is_table = False
            continue

        # 未知块按正文处理
        p = doc.add_paragraph()
        fmt_para(p, before=GAP_GAP, after=0, line=LINE_BODY)
        add_rich(p, payload, size=FS_BODY, color=INK)
        last = "p"

    # 收尾：去掉末尾空段（保留最后一个表格）
    body = doc.element.body
    for _ in range(6):
        kids = [k for k in body.iterchildren()
                if k.tag in (qn("w:p"), qn("w:tbl"))]
        if not kids:
            break
        last_el = kids[-1]
        if last_el.tag == qn("w:p") and not "".join(last_el.itertext()).strip():
            body.remove(last_el)
        else:
            break

    doc.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="学习清单 V2.1 版式排版")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--header", default="")
    ap.add_argument("--title", default=None)
    ap.add_argument("--mirror", action="store_true", help="双面装订：内侧20/外侧18，奇偶页镜像")
    ap.add_argument("--font-head", default=None)
    ap.add_argument("--font-body", default=None)
    a = ap.parse_args()
    md = open(a.input, encoding="utf-8").read()
    build(md, a.output, a.header, a.title, a.mirror, a.font_head, a.font_body)
    print("已生成:", a.output)
    print("字族: 标题 %s / 正文 %s | 版心 %.1fcm%s"
          % (Ctx.head, Ctx.body, content_width(a.mirror),
             "（双面镜像）" if a.mirror else ""))


if __name__ == "__main__":
    main()
