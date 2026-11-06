#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教学设计「统一排版标准 V2.0」排版引擎
======================================

A4 纵向，上 28 / 下 20 / 左右 23mm（双面 26·20 镜像），版心 164 × 249mm；
页眉左侧固定 30×12mm Logo 区（有图插图标、无图虚线占位框、可隐藏留位）；
标题思源黑体、正文楷体；表格统一六边全框线（外 0.75pt / 内 0.5pt）+ 浅绿表头。

版式参数全部来自 references/jxsj-spec.md（V2.0），改版式只改本文件顶部常量。

用法：
    python3 jxsj_typeset.py --input draft.md --output 17长城-教学设计.docx \
        --header "17 长城"

    # 有品牌 Logo（等比缩进 30×12mm 预留区，最高 10mm）
    python3 jxsj_typeset.py --input ... --logo assets/brand/logo.png

    # 正式无 Logo 版：隐藏占位框，保留页眉空间
    python3 jxsj_typeset.py --input ... --logo-mode hidden

    # 双面装订（奇偶页镜像：内侧 26mm / 外侧 20mm，版心仍 164mm）
    python3 jxsj_typeset.py --input ... --mirror

底层 OOXML 构件（schema 有序插入、行高规则、表格边框）复用学习清单引擎，
版式常量各自独立，见 SKILL.md「引擎实现约定」。
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from xuexqingdan_typeset import (  # noqa: E402  同目录复用底层构件
    Ctx, add_page_field, fmt_para, gap, resolve_font, build_header,
    HEAD_CANDIDATES, BODY_CANDIDATES,
    _put, _PPR_ORDER, _TBLPR_ORDER, _TCPR_ORDER, _TRPR_ORDER,
    _tbl_borders, _no_borders, _tbl_margins, _set_row_h, set_col_widths,
    _cell_shade, _row_cant_split, _row_header, _first_para, _cell_para,
    BORDER_OUT, BORDER_IN, MM2PT,
)

# ─────────────────── 版式常量（V2.0） ───────────────────

PAGE_W, PAGE_H = 21.0, 29.7           # A4 纵向
M_TOP, M_BOTTOM = 2.8, 2.0            # 上 28 / 下 20mm
M_LEFT = M_RIGHT = 2.3                # 单面左右各 23mm
M_INNER, M_OUTER = 2.6, 2.0           # 双面装订：内侧 26 / 外侧 20mm
HDR_DIST, FTR_DIST = 0.8, 1.0         # 页眉距顶 8mm / 页脚距底 10mm

CONTENT_W = PAGE_W - M_LEFT - M_RIGHT            # 16.4cm = 164mm
MIRROR_CONTENT_W = PAGE_W - M_INNER - M_OUTER    # 16.4cm（版心不变，只换边距）

# 页眉 Logo 预留区
LOGO_W_MM = 30.0
LOGO_H_MM = 12.0
LOGO_MAX_H_MM = 10.0

# 颜色
INK_TITLE = "222222"   # 文档主标题
GREEN = "315A4B"       # 一级 / 二级标题、模块标签
INK = "2B302C"         # 三级 / 四级标题、正文
AUX = "596960"         # 辅助文字、副标题、图注、页眉右字
FTR = "666666"         # 页脚页码
SEP = "CBD5CD"         # 页眉分隔线
LINE = "9BA9A0"        # 表格边框
TH_BAND = "EDF3EE"     # 表头底纹
PH_BORDER = "B8B8B8"   # Logo 占位框虚线
PH_TEXT = "999999"     # Logo 占位文字

# 字号（pt）
FS_TITLE = 18.0        # 文档主标题
FS_SUB = 10.5          # 文档副标题
FS_H1 = 14.0           # 一级标题
FS_H2 = 12.0           # 二级标题
FS_H3 = 11.0           # 三级标题
FS_H4 = 11.0           # 四级标题
FS_COURSE = 13.0       # 课时标题
FS_LINK = 11.5         # 环节标题
FS_TAG = 10.5          # 模块标签
FS_BODY = 11.0         # 普通正文 / 列表
FS_TH = 10.5           # 表格表头
FS_TD = 10.5           # 表格正文
FS_CAP = 9.5           # 图片说明 / 表题
FS_HF = 9.0            # 页眉页脚
FS_PH = 8.0            # Logo 占位文字

# 行距
LINE_TITLE = 1.2
LINE_H = 1.2
LINE_COURSE = 1.3
LINE_LINK = 1.25
LINE_BODY = 1.45
LINE_CELL = 1.3
LINE_CAP = 1.2

# 间距（pt；规范以 mm 记，这里换算）
def mm(v):
    return round(v * MM2PT, 1)

SP_TITLE_BEF, SP_TITLE_AFT = mm(6), mm(5)
SP_SUB_AFT = mm(8)
SP_H1_BEF, SP_H1_AFT = mm(8), mm(4)
SP_H2_BEF, SP_H2_AFT = mm(5), mm(2.5)
SP_H3_BEF, SP_H3_AFT = mm(4), mm(2)
SP_H4_BEF, SP_H4_AFT = mm(3), mm(1.5)
SP_COURSE_BEF, SP_COURSE_AFT = mm(8), mm(5)
SP_LINK_BEF, SP_LINK_AFT = mm(5), mm(2.5)
SP_TAG_BEF, SP_TAG_AFT = mm(4), mm(2)
SP_BODY_AFT = 3.0
SP_CAP_BEF, SP_CAP_AFT = mm(4), mm(2)
SP_FIG_BEF, SP_FIG_AFT = mm(5), mm(5)
SP_FIGCAP_BEF, SP_FIGCAP_AFT = mm(2.5), mm(4)

# 缩进
IND_BODY_CHARS = 2
IND_TAG_MM = 4.0
LIST_STEP_MM = 4.0     # 二 / 三 / 四级列表各自再缩进 4mm
LIST_GAP_MM = 3.0      # 编号与文字间距

# 表格
ROW_H_MM = 12.0
CELL_MAR = (170, 170, 142, 142)   # 左/右 3mm、上/下 2.5mm（twips）
TBL_BEF, TBL_AFT = mm(4), mm(5)

DEFAULT_IMG_W_CM = CONTENT_W
MAX_IMG_H_CM = 20.0

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


# ─────────────────── 页面与页眉页脚 ───────────────────

# build_header / _logo_size / _header_rule / _cell_dashed 已统一收口到
# xuexqingdan_typeset（四类文档共用，避免多份 copy 漂移），见上方 import。


def build_footer(sec, page_number=True):
    ftr = sec.footer
    ftr.is_linked_to_previous = False
    p = ftr.paragraphs[0]
    fmt_para(p, before=0, after=0, line=None, align=WD_ALIGN_PARAGRAPH.CENTER)
    if page_number:
        add_page_field(p, size=FS_HF, color=FTR)
    return ftr


# ─────────────────── 样式 ───────────────────

def _fmt_run(run, size=None, color=None, font=None, bold=None):
    """run 层显式给全部属性：不依赖样式继承，避免标题被默认 bold=False 冲掉。"""
    f = font or Ctx.body
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
    if bold is not None:
        run.font.bold = bold
    return run


def add_rich(p, text, size, color, font, bold=False):
    """行内 **加粗**。"""
    for seg in BOLD_RE.split(text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**") and len(seg) > 4:
            _fmt_run(p.add_run(seg[2:-2]), size=size, color=color, font=font, bold=True)
        else:
            _fmt_run(p.add_run(seg), size=size, color=color, font=font, bold=bold)


STYLES = {}

_JC = {WD_ALIGN_PARAGRAPH.LEFT: "left", WD_ALIGN_PARAGRAPH.CENTER: "center",
       WD_ALIGN_PARAGRAPH.RIGHT: "right", WD_ALIGN_PARAGRAPH.JUSTIFY: "both"}


def _set_style_align(st, align):
    """显式写 style/pPr/jc。

    python-docx 的 `style.paragraph_format.alignment` 对自定义样式不落盘
    （实测 jc 丢失、标题与表题全变成左对齐），必须自己按 schema 顺序插入。
    """
    if align is None:
        return
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), _JC.get(align, "left"))
    _put(st.element.get_or_add_pPr(), jc, _PPR_ORDER)


def build_styles(doc):
    """建立可复用样式（V2.0 §20）。渲染时 run 层再显式覆盖，双保险。"""
    styles = doc.styles

    # 文档默认字体
    dd = styles.element.find(qn("w:docDefaults"))
    if dd is not None:
        rpr = dd.find(qn("w:rPrDefault"))
        if rpr is not None:
            rPr = rpr.find(qn("w:rPr"))
            if rPr is None:
                rPr = OxmlElement("w:rPr")
                rpr.append(rPr)
            rf = OxmlElement("w:rFonts")
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                rf.set(qn(attr), Ctx.body)
            rPr.insert(0, rf)

    normal = styles["Normal"]
    normal.name = "正文"
    normal.font.name = Ctx.body
    normal.font.size = Pt(FS_BODY)
    rPr = normal.element.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.insert(0, rf)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rf.set(qn(attr), Ctx.body)
    fmt_para(normal, before=0, after=SP_BODY_AFT, line=LINE_BODY,
             first=Cm(FS_BODY * IND_BODY_CHARS * 0.03528))
    _set_style_align(normal, WD_ALIGN_PARAGRAPH.LEFT)
    STYLES["正文"] = dict(font=Ctx.body, size=FS_BODY, bold=False, color=INK)

    def mk(name, font_kind, size, bold, color, *, before=0.0, after=0.0,
           line=LINE_BODY, align=WD_ALIGN_PARAGRAPH.LEFT, first_chars=0,
           left_mm=0.0, keep_next=False):
        font = Ctx.head if font_kind == "head" else Ctx.body
        try:
            st = styles[name]
        except KeyError:
            st = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = normal
        st.quick_style = True
        st.font.name = font
        st.font.size = Pt(size)
        st.font.bold = bold
        st.font.color.rgb = RGBColor.from_string(color)
        r = st.element.get_or_add_rPr()
        rf = r.find(qn("w:rFonts"))
        if rf is None:
            rf = OxmlElement("w:rFonts")
            r.insert(0, rf)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            rf.set(qn(attr), font)
        fmt_para(st, before=before, after=after, line=line,
                 first=Cm(size * first_chars * 0.03528),
                 left=Cm(left_mm / 10.0), keep_next=keep_next)
        _set_style_align(st, align)
        STYLES[name] = dict(font=font, size=size, bold=bold, color=color)
        return st

    mk("文档标题", "head", FS_TITLE, True, INK_TITLE,
       before=SP_TITLE_BEF, after=SP_TITLE_AFT, line=LINE_TITLE,
       align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    mk("文档副标题", "head", FS_SUB, False, AUX,
       before=0, after=SP_SUB_AFT, line=LINE_TITLE,
       align=WD_ALIGN_PARAGRAPH.CENTER)
    mk("标题1", "head", FS_H1, True, GREEN,
       before=SP_H1_BEF, after=SP_H1_AFT, line=LINE_H, keep_next=True)
    mk("标题2", "head", FS_H2, True, GREEN,
       before=SP_H2_BEF, after=SP_H2_AFT, line=LINE_H, keep_next=True)
    mk("标题3", "head", FS_H3, False, INK,
       before=SP_H3_BEF, after=SP_H3_AFT, line=LINE_H, keep_next=True)
    mk("标题4", "body", FS_H4, True, INK,
       before=SP_H4_BEF, after=SP_H4_AFT, line=LINE_H, keep_next=True)
    mk("课时标题", "head", FS_COURSE, True, GREEN,
       before=SP_COURSE_BEF, after=SP_COURSE_AFT, line=LINE_COURSE,
       align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    mk("环节标题", "head", FS_LINK, True, GREEN,
       before=SP_LINK_BEF, after=SP_LINK_AFT, line=LINE_LINK, keep_next=True)
    mk("模块标签", "head", FS_TAG, True, GREEN,
       before=SP_TAG_BEF, after=SP_TAG_AFT, line=LINE_H,
       left_mm=IND_TAG_MM, keep_next=True)
    mk("表题", "head", FS_CAP, True, AUX,
       before=SP_CAP_BEF, after=SP_CAP_AFT, line=LINE_CAP,
       align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    mk("图注", "body", FS_CAP, False, AUX,
       before=SP_FIGCAP_BEF, after=SP_FIGCAP_AFT, line=LINE_CAP,
       align=WD_ALIGN_PARAGRAPH.CENTER)
    mk("表格表头", "head", FS_TH, True, INK_TITLE,
       before=0, after=0, line=LINE_CELL, align=WD_ALIGN_PARAGRAPH.CENTER)
    mk("表格文字", "body", FS_TD, False, INK,
       before=0, after=0, line=LINE_CELL)
    mk("页眉字", "head", FS_HF, False, AUX, before=0, after=0, line=1.0)
    mk("页脚字", "body", FS_HF, False, FTR, before=0, after=0, line=1.0,
       align=WD_ALIGN_PARAGRAPH.CENTER)


def emit(doc, style, text, *, indent=True, list_num=None, level=0):
    """按样式渲染一段，run 层显式写字体字号颜色加粗。"""
    spec = STYLES[style]
    p = doc.add_paragraph(style=style)
    if list_num is not None:
        # 编号正文：编号顶格，续行悬挂缩进到文字起始位
        hang = (len(list_num) * 0.5 * spec["size"] * 0.03528
                + LIST_GAP_MM / 10.0 + level * LIST_STEP_MM / 10.0)
        fmt_para(p, before=0, after=2.5, line=LINE_BODY,
                 left=Cm(hang), first=Cm(-hang),
                 align=WD_ALIGN_PARAGRAPH.LEFT)
        add_rich(p, "%s %s" % (list_num, text), spec["size"], spec["color"],
                 spec["font"], spec["bold"])
    else:
        add_rich(p, text, spec["size"], spec["color"], spec["font"], spec["bold"])
        if not indent:
            # 只清缩进，不动对齐：图注等居中样式不能被这里改成左对齐
            fmt_para(p, before=0, after=2.5, line=LINE_BODY, first=Cm(0),
                     left=Cm(0))
    return p


# ─────────────────── 表格 ───────────────────

def _col_weight(cells):
    lens = sorted(len(c) for c in cells if c)
    if not lens:
        return 0.0
    return lens[min(len(lens) - 1, int(len(lens) * 0.9))]


def column_ratios(headers, ncol, rows=()):
    joined = "".join(headers)
    if ncol == 4 and ("环节" in joined or "活动名称" in joined):
        return [0.15, 0.30, 0.28, 0.27]
    if ncol == 3 and "教师活动" in joined:
        return [0.40, 0.30, 0.30]
    if ncol == 2 and ("项目" in joined or "内容" in joined):
        return [0.28, 0.72]
    if ncol == 1:
        return [1.0]
    ws = []
    for j in range(ncol):
        cells = [r[j] for r in rows if j < len(r)]
        hw = len(headers[j]) * 1.1 if j < len(headers) else 0
        ws.append(max(_col_weight(cells), hw) or 1.0)
    total = sum(ws) or 1.0
    fit = [max(0.14, w / total) for w in ws]
    s = sum(fit)
    return [round(f / s, 4) for f in fit]


def _cell_blocks(text):
    raw = re.split(r"<br\s*/?>|\n", str(text))
    out = []
    for c in raw:
        c = c.strip()
        if not c:
            continue
        if re.match(r"^\d{1,2}[.、]\s*", c):
            c = re.sub(r"(?<=[；;。])\s*(?=\d{1,2}[.、]\s*)", "\n", c)
        out.extend([x.strip() for x in c.split("\n") if x.strip()])
    return out or [""]


def add_table(doc, headers, rows, cw):
    ncol = len(headers)
    t = doc.add_table(rows=0, cols=ncol)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    t.autofit = False
    _tbl_borders(t, outer=BORDER_OUT, inner=BORDER_IN, color=LINE)
    _tbl_margins(t, *CELL_MAR)

    hdr = t.add_row()
    _row_header(hdr)
    _row_cant_split(hdr)
    _set_row_h(hdr, ROW_H_MM)
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        _cell_shade(c, TH_BAND)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = _first_para(c, align=WD_ALIGN_PARAGRAPH.CENTER, line=LINE_CELL)
        add_rich(p, h, FS_TH, INK_TITLE, Ctx.head, True)
        p.paragraph_format.keep_with_next = True

    for row in rows:
        r = t.add_row()
        _set_row_h(r, ROW_H_MM)
        # 数据行一律允许跨页断行：教学过程四列的行动辄 10cm 高，
        # 加 cantSplit 会把整行推到下一页、上一页留十几厘米空白。
        blocks_per_cell = [_cell_blocks(row[i] if i < len(row) else "") for i in range(ncol)]
        # 段数不足以判断「多行」：一大段折行后同样是多行正文，
        # 所以只要最长内容超过约 2 行就按顶部对齐（规范 §14.2）。
        multi = (max(len(b) for b in blocks_per_cell) > 1
                 or max(len(x) for b in blocks_per_cell for x in b) > 30)
        for i in range(ncol):
            c = r.cells[i]
            c.vertical_alignment = (WD_CELL_VERTICAL_ALIGNMENT.TOP if multi
                                    else WD_CELL_VERTICAL_ALIGNMENT.CENTER)
            for k, chunk in enumerate(blocks_per_cell[i]):
                p = (_first_para(c, align=WD_ALIGN_PARAGRAPH.LEFT, line=LINE_CELL)
                     if k == 0 else _cell_para(c, align=WD_ALIGN_PARAGRAPH.LEFT))
                p.paragraph_format.space_after = Pt(1 if k < len(blocks_per_cell[i]) - 1 else 0)
                add_rich(p, chunk, FS_TD, INK, Ctx.body, False)

    set_col_widths(t, [cw * r for r in column_ratios(headers, ncol, rows)])
    return t


# ─────────────────── 解析 ───────────────────

def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_markdown(md):
    lines = md.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    is_sep = re.compile(r"^[\s|:\-]+$")

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.startswith("```") or line.startswith(":::board"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```") \
                    and lines[i].strip() != ":::":
                buf.append(lines[i].rstrip())
                i += 1
            i += 1
            out.append(("board", buf))
            continue

        m = re.match(r"^:::caption\s+(.+)$", line)
        if m:
            out.append(("caption", m.group(1)))
            i += 1
            continue

        m = re.match(r"^:::subtitle\s*(.*)$", line)
        if m:
            out.append(("subtitle", m.group(1)))
            i += 1
            continue

        m = re.match(r"^:::label\s+(.+)$", line)
        if m:
            out.append(("label", m.group(1)))
            i += 1
            continue

        if line == ":::pagebreak":
            out.append(("pagebreak", None))
            i += 1
            continue

        m = re.match(r"^!\[([^\]]*)\]\((.+?)\)\s*$", line)
        if m:
            out.append(("image", (m.group(1).strip(), m.group(2).strip())))
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and is_sep.match(lines[i + 1].strip()):
            headers = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            out.append(("table", (headers, rows)))
            continue

        m = re.match(r"^(#{1,5})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            out.append(({1: "title", 2: "h1", 3: "h2", 4: "h3", 5: "h4"}[level], text))
            i += 1
            continue

        m = re.match(r"^[-*]\s+\[\s?\]\s+(.*)$", line)
        if m:
            out.append(("checkbox", m.group(1)))
            i += 1
            continue

        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            out.append(("bullet", m.group(1)))
            i += 1
            continue

        m = re.match(r"^(\d+)[.、)]\s+(.*)$", line)
        if m:
            out.append(("ordered", (m.group(1), m.group(2))))
            i += 1
            continue

        m = re.match(r"^\*\*(.+?)\*\*$", line)
        if m:
            out.append(("label", m.group(1).strip()))
            i += 1
            continue

        out.append(("para", line))
        i += 1

    return out


# ─────────────────── 主渲染 ───────────────────

COURSE_RE = re.compile(r"^第[一二三四五六七八九十\d]+课时(?=[：:　\s]|$)")


def render(md, out_path, header=None, title_override=None, subtitle=None,
           logo=None, logo_mode="placeholder", mirror=False,
           font_head=None, font_body=None, page_number=True, img_width=None):
    Ctx.head = font_head or resolve_font(HEAD_CANDIDATES, "思源黑体")
    Ctx.body = font_body or resolve_font(BODY_CANDIDATES, "楷体")

    cw = MIRROR_CONTENT_W if mirror else CONTENT_W
    img_w = min(img_width or DEFAULT_IMG_W_CM, cw)

    doc = Document()
    build_styles(doc)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin, sec.bottom_margin = Cm(M_TOP), Cm(M_BOTTOM)
    if mirror:
        sec.left_margin, sec.right_margin = Cm(M_INNER), Cm(M_OUTER)
        doc.settings.element.insert(0, OxmlElement("w:mirrorMargins"))
    else:
        sec.left_margin, sec.right_margin = Cm(M_LEFT), Cm(M_RIGHT)
    sec.header_distance, sec.footer_distance = Cm(HDR_DIST), Cm(FTR_DIST)
    sec.different_first_page_header_footer = False      # 首页同样有 Logo 区

    build_header(sec, cw, header or "", logo=logo, logo_mode=logo_mode)
    build_footer(sec, page_number=page_number)

    blocks = parse_markdown(md)
    auto_no = 0
    prev_kind = None
    title_seen = False
    sub_used = False

    for kind, payload in blocks:
        if kind == "title":
            p = doc.add_paragraph(style="文档标题")
            spec = STYLES["文档标题"]
            add_rich(p, title_override or payload, spec["size"], spec["color"],
                     spec["font"], True)
            title_seen = True

        elif kind == "subtitle":
            p = doc.add_paragraph(style="文档副标题")
            spec = STYLES["文档副标题"]
            add_rich(p, subtitle or payload, spec["size"], spec["color"], spec["font"], False)
            sub_used = True

        elif kind == "h1":
            emit(doc, "标题1", payload)
        elif kind == "h2":
            emit(doc, "课时标题" if COURSE_RE.match(payload) else "标题2", payload)
        elif kind == "h3":
            emit(doc, "环节标题" if payload.startswith("环节") else "标题3", payload)
        elif kind == "h4":
            emit(doc, "标题4", payload)
        elif kind == "label":
            emit(doc, "模块标签", payload)
        elif kind == "caption":
            emit(doc, "表题", payload)
        elif kind == "para":
            emit(doc, "正文", payload, indent=True)

        elif kind == "ordered":
            num, text = payload
            emit(doc, "正文", text, list_num=num + ".")
        elif kind in ("bullet", "checkbox"):
            auto_no = (auto_no + 1
                       if prev_kind in ("ordered", "bullet", "checkbox") else 1)
            emit(doc, "正文", payload, list_num="%d." % auto_no)

        elif kind == "table":
            headers, rows = payload
            gap(doc, 4, keep_next=True)
            add_table(doc, headers, rows, cw)
            gap(doc, 5)

        elif kind == "image":
            alt, path = payload
            if os.path.exists(path):
                p = doc.add_paragraph()
                # 图注间距由图片段落的段后给（图片是 inline，行高自带 surplus，
                # 靠图注的段前撑不开距离，实测只剩 0.7mm）
                fmt_para(p, before=SP_FIG_BEF,
                         after=SP_FIGCAP_BEF if alt else SP_FIG_AFT,
                         line=1.0, first=Cm(0), align=WD_ALIGN_PARAGRAPH.CENTER,
                         keep_next=bool(alt))
                pic = p.add_run().add_picture(path, width=Cm(img_w))
                if pic.height > Cm(MAX_IMG_H_CM):
                    k = Cm(MAX_IMG_H_CM) / pic.height
                    pic.width = int(pic.width * k)
                    pic.height = int(Cm(MAX_IMG_H_CM))
                if alt:
                    cap = doc.add_paragraph(style="图注")
                    fmt_para(cap, before=0, after=SP_FIGCAP_AFT, line=LINE_CAP,
                             first=Cm(0), align=WD_ALIGN_PARAGRAPH.CENTER)
                    add_rich(cap, alt, FS_CAP, AUX, Ctx.body, False)
            else:
                print("[warn] 图片不存在：%s" % path, file=sys.stderr)

        elif kind == "board":
            print("[warn] 板书字符画已停用：请改用 ![](图片路径)。本次按纯文本输出。",
                  file=sys.stderr)
            for ln in payload:
                if ln.strip():
                    emit(doc, "正文", ln, indent=False)

        elif kind == "pagebreak":
            p = doc.add_paragraph()
            fmt_para(p, before=0, after=0, line=None, first=Cm(0))
            p.add_run().add_break(WD_BREAK.PAGE)

        if kind not in ("ordered", "bullet", "checkbox"):
            auto_no = 0
        elif kind == "ordered":
            auto_no = int(payload[0])
        prev_kind = kind

    # 未写副标题时，主标题后不留空
    if not sub_used and not subtitle:
        pass

    # 清掉文末多余空段
    for p in list(doc.paragraphs)[::-1]:
        if p.text.strip() == "" and p.style.name != "正文":
            p._p.getparent().remove(p._p)
        else:
            break

    doc.save(out_path)
    return title_seen


def main():
    ap = argparse.ArgumentParser(description="教学设计统一排版标准 V2.0")
    ap.add_argument("--input", required=True, help="规范 Markdown 草稿")
    ap.add_argument("--output", required=True, help="输出 .docx 路径")
    ap.add_argument("--header", default="", help="页眉右侧文字，通常写课题名")
    ap.add_argument("--title", default=None, help="覆盖文档主标题")
    ap.add_argument("--subtitle", default=None, help="覆盖副标题")
    ap.add_argument("--logo", default=None, help="品牌 Logo 图片")
    ap.add_argument("--logo-mode", default="placeholder",
                    choices=["placeholder", "hidden"], help="无 Logo 时的处理")
    ap.add_argument("--mirror", action="store_true", help="双面装订镜像边距")
    ap.add_argument("--font-head", default=None, help="标题字族（默认思源黑体）")
    ap.add_argument("--font-body", default=None, help="正文字族（默认楷体）")
    ap.add_argument("--img-width", type=float, default=None, help="图片宽度 cm，上限 16.4")
    ap.add_argument("--no-page-number", action="store_true", help="不排页码")
    ap.add_argument("--accent", default=None, help="兼容旧命令，无效果（V2.0 配色固定）")
    a = ap.parse_args()

    md = open(a.input, encoding="utf-8").read()
    render(md, a.output, header=a.header, title_override=a.title,
           subtitle=a.subtitle, logo=a.logo, logo_mode=a.logo_mode,
           mirror=a.mirror, font_head=a.font_head, font_body=a.font_body,
           page_number=not a.no_page_number, img_width=a.img_width)
    print("已生成:", a.output)


if __name__ == "__main__":
    main()
