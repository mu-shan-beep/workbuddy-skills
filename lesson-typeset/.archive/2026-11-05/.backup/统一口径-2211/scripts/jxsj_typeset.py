#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
教学设计「自用版」排版引擎
==========================

按固定版式规范（A4 / 边距 2.5·2.5·2.8·2.8 / 1.75 倍行距 / 全黑白不施色 / 全文宋体 /
三线表 / 无封面无目录）把教学设计内容渲染为 .docx。

用法：
    python3 jxsj_typeset.py --input draft.md --output out.docx \
        --header "17 长城" [--title 覆盖标题]

输入为「规范 Markdown」子集，映射规则见 references/markdown-mapping.md。
"""

import argparse
import re
import sys
import unicodedata

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ───────────────────────────── 版式常量 ─────────────────────────────
# 改版式只改这一段，不要散落到函数里。

PAGE_W_CM = 21.0
PAGE_H_CM = 29.7
M_TOP, M_BOTTOM, M_LEFT, M_RIGHT = 2.5, 2.5, 2.8, 2.8
HDR_DIST, FTR_DIST = 1.5, 1.75
CONTENT_W_CM = PAGE_W_CM - M_LEFT - M_RIGHT          # 15.4cm
TABLE_INDENT_CM = 0.5                                 # 表格左右各缩进
TABLE_W_CM = CONTENT_W_CM - TABLE_INDENT_CM * 2       # 14.4cm

LINE_BODY = 1.75        # 正文行距
LINE_TABLE = 1.0        # 表格行距

# 字号（pt）：小三 15 / 四号 14 / 小四 12 / 五号 10.5 / 小五 9
FS_TITLE = 15.0
FS_H1 = 14.0
FS_H2 = 12.0
FS_H3 = 12.0
FS_COURSE = 13.0        # 「第一课时」这类分课时标题，须强于二级标题
FS_BODY = 12.0
FS_LABEL = 12.0         # 课时目标 / 任务一 这类标签行
FS_TABLE = 10.5
FS_CAPTION = 10.5
FS_BOARD = 9.0
FS_HDR_FTR = 10.5

# 段前段后（pt）
SP_TITLE_AFTER = 18
SP_H1_BEFORE, SP_H1_AFTER = 16, 6
SP_H2_BEFORE, SP_H2_AFTER = 12, 3
SP_H3_BEFORE, SP_H3_AFTER = 12, 2
SP_COURSE_BEFORE, SP_COURSE_AFTER = 20, 8
SP_LABEL_BEFORE, SP_LABEL_AFTER = 3, 0
SP_CAP_BEFORE, SP_CAP_AFTER = 6, 3

FONT_SONG = "宋体"
# 全文统一宋体：用户要求「整个教学设计统一使用宋体」，标题改用加粗 + 字号拉开层级
FONT_HEI = "宋体"
FONT_WEST = "宋体"        # 中西文同字族，满足「统一使用宋体」

ACCENTS = {"navy": "2C3E50", "green": "2F5D50"}

# 三线表线宽（1/8 pt）
RULE_THICK = 12   # 1.5pt
RULE_THIN = 6     # 0.75pt


# ───────────────────────────── 底层工具 ─────────────────────────────

def _el(tag, **attrs):
    if ":" not in tag:
        tag = "w:" + tag
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn("w:" + k), str(v))
    return e


def _ensure_child(owner, tag):
    """兼容 style 对象、run 对象与裸 XML 元素三种入参。"""
    getter = getattr(owner, "get_or_add_" + tag.lstrip("w:"), None)
    if getter is not None:
        return getter()
    node = owner if owner.tag == qn(tag) else owner.find(qn(tag))
    if node is None:
        node = OxmlElement(tag)
        owner.insert(0, node) if owner.tag.endswith("Default") else owner.append(node)
    return node


def _set_cell_borders(cell, **edges):
    """只写确实要显示的边，其余留给表格级继承。

    关键教训：单元格 tcBorders 的优先级高于 tblBorders。一旦在某个边上写
    val="none"，就会把表格外框那条线**挖掉**。所以这里不写的边一律不生成
    元素，让外框和内部线各自继承。
    边名取 top / left / bottom / right，值为 (val, sz, color)。
    """
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    if not edges:
        return
    bdr = _el("tcBorders")
    for edge in ("top", "left", "bottom", "right"):     # schema 顺序
        spec = edges.get(edge)
        if spec is None:
            continue
        val, sz, color = spec
        bdr.append(_el(edge, val=val, sz=sz, space="0", color=color))
    tcPr.append(bdr)


def _set_fonts(rpr_owner, eastasia, size=None, bold=None, color=None):
    """给 style 或 run 设置字体：eastAsia 指定，ascii/hAnsi/cs 统一取 FONT_WEST（宋体）。"""
    rPr = _ensure_child(rpr_owner, "w:rPr")
    for old in rPr.findall(qn("w:rFonts")):
        rPr.remove(old)
    rPr.insert(0, _el("rFonts", ascii=FONT_WEST, hAnsi=FONT_WEST,
                      eastAsia=eastasia, cs=FONT_WEST, hint="eastAsia"))
    if size is not None:
        for old in rPr.findall(qn("w:sz")) + rPr.findall(qn("w:szCs")):
            rPr.remove(old)
        rPr.append(_el("sz", val=int(round(size * 2))))
        rPr.append(_el("szCs", val=int(round(size * 2))))
    if bold is not None:
        for old in rPr.findall(qn("w:b")) + rPr.findall(qn("w:bCs")):
            rPr.remove(old)
        b = _el("b", val="1" if bold else "0")
        rPr.append(b)
        rPr.append(_el("bCs", val="1" if bold else "0"))
    if color:
        for old in rPr.findall(qn("w:color")):
            rPr.remove(old)
        rPr.append(_el("color", val=color))


def _set_ppr(ppr_owner, *, before=None, after=None, line=None, rule="auto",
             first_line_chars=None, align=None, left_cm=None,
             keep_next=False, widow=True):
    """在 style 或 paragraph 的 pPr 上写间距、缩进、对齐、分页控制。"""
    pPr = _ensure_child(ppr_owner, "w:pPr")

    if before is not None or after is not None or line is not None:
        for old in pPr.findall(qn("w:spacing")):
            pPr.remove(old)
        attrs = {}
        if before is not None:
            attrs["before"] = int(round(before * 20))
        if after is not None:
            attrs["after"] = int(round(after * 20))
        if line is not None:
            if rule == "auto":
                attrs["line"] = int(round(240 * line))
                attrs["lineRule"] = "auto"
            else:
                attrs["line"] = int(round(line * 20))
                attrs["lineRule"] = "exact"
        pPr.append(_el("spacing", **attrs))

    if first_line_chars is not None or left_cm is not None:
        for old in pPr.findall(qn("w:ind")):
            pPr.remove(old)
        attrs = {}
        if left_cm is not None:
            attrs["left"] = int(round(left_cm * 567))
        if first_line_chars is not None:
            attrs["firstLineChars"] = int(first_line_chars * 100)
            attrs["firstLine"] = int(round(FS_BODY * 20 * first_line_chars))
        if attrs:
            pPr.append(_el("ind", **attrs))

    if align is not None:
        for old in pPr.findall(qn("w:jc")):
            pPr.remove(old)
        pPr.append(_el("jc", val=align))

    if keep_next:
        if pPr.find(qn("w:keepNext")) is None:
            pPr.append(_el("keepNext"))
    if widow:
        if pPr.find(qn("w:widowControl")) is None:
            pPr.append(_el("widowControl", val="1"))


def _tint(hex_color, ratio):
    """把强调色按比例混白，生成 10% 底纹色。ratio=0.10 → 极浅。"""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: int(round(c * ratio + 255 * (1 - ratio)))
    return "%02X%02X%02X" % (mix(r), mix(g), mix(b))


# ─────────────────── OOXML 子元素顺序规范化 ───────────────────
# Word 对 tblPr / tcPr / pPr 的子元素顺序是强校验的，顺序错了会静默丢属性。

_ORDER = {
    "tblPr": ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual",
              "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc",
              "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout",
              "tblCellMar", "tblLook", "tblCaption", "tblDescription"],
    "trPr": ["cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore",
             "wAfter", "cantSplit", "trHeight", "tblHeader", "tblCellSpacing",
             "jc", "hidden"],
    "tcPr": ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders",
             "shd", "noWrap", "tcMar", "textDirection", "tcFitText",
             "vAlign", "hideMark"],
    # 边框子元素顺序写错会整段失效：表格外框在 Word / 腾讯文档里直接消失
    "tblBorders": ["top", "left", "start", "bottom", "right", "end",
                   "insideH", "insideV"],
    "tcBorders": ["top", "left", "start", "bottom", "right", "end",
                  "insideH", "insideV", "tl2br", "tr2bl"],
    "pPr": ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
            "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd",
            "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
            "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN",
            "bidi", "adjustRightInd", "snapToGrid", "spacing", "ind",
            "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
            "textDirection", "textAlignment", "textboxTightWrap",
            "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr"],
    "rPr": ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps",
            "strike", "dstrike", "outline", "shadow", "emboss", "imprint",
            "noProof", "snapToGrid", "vanish", "webHidden", "color",
            "spacing", "w", "kern", "position", "sz", "szCs", "highlight",
            "u", "effect", "bdr", "shd", "fitText", "vertAlign", "rtl",
            "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"],
}


def normalize_xml(doc):
    """按 schema 顺序重排 tblPr / trPr / tcPr / pPr / rPr 的子元素。"""
    root = doc.element
    for tag, order in _ORDER.items():
        index = {qn("w:" + n): i for i, n in enumerate(order)}
        for node in root.iter(qn("w:" + tag)):
            kids = list(node)
            kids.sort(key=lambda e: index.get(e.tag, len(order)))
            for k in kids:
                node.append(k)


# ───────────────────────────── 样式定义 ─────────────────────────────

def build_styles(doc, accent):
    """按速查表建立段落样式，全文只用样式，不手动改格式。"""
    styles = doc.styles
    # tint 仅为 --accent 接口保留：本版式全黑白，没有任何地方消费它。
    tint = _tint(accent, 0.10)

    # 文档默认：全文宋体（中西文同族）
    dd = styles.element.find(qn("w:docDefaults"))
    if dd is not None:
        rpr_def = dd.find(qn("w:rPrDefault"))
        if rpr_def is not None:
            _set_fonts(rpr_def, FONT_SONG, size=FS_BODY, color="000000")

    # 正文
    body = styles["Normal"]
    body.name = "正文"
    _set_fonts(body.element, FONT_SONG, size=FS_BODY, bold=False, color="000000")
    _set_ppr(body.element, before=0, after=0, line=LINE_BODY,
             first_line_chars=2, align="both", widow=True)
    # 允许标点溢出边界 + 中文版式（避头尾、中西文自动间距）
    body_pPr = body.element.get_or_add_pPr()
    for tag in ("overflowPunct", "kinsoku", "autoSpaceDE", "autoSpaceDN"):
        if body_pPr.find(qn("w:" + tag)) is None:
            body_pPr.append(_el(tag))

    def make(name, eastasia, size, bold, *, before, after, line=None,
             align="left", first_line_chars=0, keep_next=False):
        try:
            st = styles[name]
        except KeyError:
            st = styles.add_style(name, 1)   # WD_STYLE_TYPE.PARAGRAPH
        st.base_style = body
        st.quick_style = True
        _set_fonts(st.element, eastasia, size=size, bold=bold, color="000000")
        _set_ppr(st.element, before=before, after=after,
                 line=line if line is not None else LINE_BODY,
                 first_line_chars=first_line_chars, align=align,
                 keep_next=keep_next, widow=True)
        return st

    make("文档标题", FONT_HEI, FS_TITLE, True,
         before=0, after=SP_TITLE_AFTER, align="center")
    make("标题1", FONT_HEI, FS_H1, True,
         before=SP_H1_BEFORE, after=SP_H1_AFTER, keep_next=True)
    make("标题2", FONT_HEI, FS_H2, True,
         before=SP_H2_BEFORE, after=SP_H2_AFTER, keep_next=True)
    make("标题3", FONT_SONG, FS_H3, True,
         before=SP_H3_BEFORE, after=SP_H3_AFTER, keep_next=True)
    make("课时标题", FONT_HEI, FS_COURSE, True,
         before=SP_COURSE_BEFORE, after=SP_COURSE_AFTER,
         align="center", keep_next=True)
    make("标签行", FONT_SONG, FS_LABEL, True,
         before=SP_LABEL_BEFORE, after=SP_LABEL_AFTER,
         first_line_chars=2, keep_next=True)
    make("表题", FONT_HEI, FS_CAPTION, True,
         before=SP_CAP_BEFORE, after=SP_CAP_AFTER, align="center", keep_next=True)
    make("图题", FONT_HEI, FS_CAPTION, True,
         before=SP_CAP_AFTER, after=SP_CAP_BEFORE, align="center")
    make("表格文字", FONT_SONG, FS_TABLE, False,
         before=0, after=0, line=LINE_TABLE, align="left")

    return {"accent": accent, "tint": tint}


# ───────────────────────────── 页面设置 ─────────────────────────────

def setup_section(doc, header_text, page_number=True):
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(PAGE_W_CM), Cm(PAGE_H_CM)
    s.top_margin, s.bottom_margin = Cm(M_TOP), Cm(M_BOTTOM)
    s.left_margin, s.right_margin = Cm(M_LEFT), Cm(M_RIGHT)
    s.header_distance, s.footer_distance = Cm(HDR_DIST), Cm(FTR_DIST)

    # 页眉：课题名，五号宋体居中
    hp = s.header.paragraphs[0]
    hp.text = ""
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hp.paragraph_format.space_before = Pt(0)
    hp.paragraph_format.space_after = Pt(0)
    r = hp.add_run(header_text)
    _set_fonts(r._r.get_or_add_rPr(), FONT_SONG, size=FS_HDR_FTR, color="000000")

    # 页脚：页码居中，五号宋体。
    # 逐字稿不排页码（页序由课件截图承担），此时页脚留空。
    fp = s.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.paragraph_format.space_before = Pt(0)
    fp.paragraph_format.space_after = Pt(0)
    if not page_number:
        return
    fld_begin = _el("fldChar", fldCharType="begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld_end = _el("fldChar", fldCharType="end")
    run = fp.add_run()
    _set_fonts(run._r.get_or_add_rPr(), FONT_SONG, size=FS_HDR_FTR, color="000000")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


# ───────────────────────────── 段落渲染 ─────────────────────────────

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def add_rich(paragraph, text, size=None, eastasia=None, color=None, base_bold=False):
    """渲染行内 **加粗**。"""
    pos = 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            r = paragraph.add_run(text[pos:m.start()])
            _set_fonts(r._r.get_or_add_rPr(), eastasia or FONT_SONG,
                       size=size, bold=base_bold, color=color)
        r = paragraph.add_run(m.group(1))
        _set_fonts(r._r.get_or_add_rPr(), eastasia or FONT_SONG,
                   size=size, bold=True, color=color)
        pos = m.end()
    if pos < len(text):
        r = paragraph.add_run(text[pos:])
        _set_fonts(r._r.get_or_add_rPr(), eastasia or FONT_SONG,
                   size=size, bold=base_bold, color=color)


def add_para(doc, text, style="正文", eastasia=None, indent=True):
    p = doc.add_paragraph(style=style)
    if not indent:
        ind = p._p.get_or_add_pPr()
        for old in ind.findall(qn("w:ind")):
            ind.remove(old)
        ind.append(_el("ind", firstLineChars="0", firstLine="0"))
    add_rich(p, text, eastasia=eastasia)
    return p


# ───────────────────────────── 三线表 ─────────────────────────────

def _col_weight(cells):
    """一列内容的代表长度：取 90 分位。

    早期用 75 分位，短表里只要有一个明显偏长的单元格（如「品读语言、体会心情」）
    就会被判成窄列而折行，末行只剩一两个字。90 分位让长值也能占满一行，
    又不会被个别超长单元格独占宽度。
    """
    lens = sorted(len(c) for c in cells if c)
    if not lens:
        return 0.0
    return lens[min(len(lens) - 1, int(len(lens) * 0.9))]


def column_ratios(headers, ncol, rows=()):
    """有语义的表头直接用固定比例；不认识的表再按内容长度自适应。

    「设计意图」这类列字数少但句子长，纯按字数压会挤成七行，
    所以熟悉的表一律走经验值。
    """
    joined = "".join(headers)
    if ncol == 4 and "环节" in joined:
        return [0.10, 0.32, 0.30, 0.28]
    if ncol == 3 and "教师活动" in joined:
        return [0.40, 0.30, 0.30]
    if ncol == 2 and ("项目" in joined or "内容" in joined):
        return [0.22, 0.78]
    if ncol == 1:
        return [1.0]

    weights = []
    for j in range(ncol):
        cells = [r[j] for r in rows if j < len(r)]
        # 表头也要占宽度：短内容列（如「低/中/必需」）若只按内容算，
        # 表头会被压成两行。表头加粗，同字数下比常规略宽，乘 1.2。
        hw = len(headers[j]) * 1.1 if j < len(headers) else 0
        w = max(_col_weight(cells), hw) or 1.0
        weights.append(w)
    total = sum(weights) or 1.0
    fit = [max(0.14, w / total) for w in weights]
    s = sum(fit)
    return [round(f / s, 4) for f in fit]


def _three_line_borders(table):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = _el("tblBorders")
    b.append(_el("top", val="single", sz=RULE_THICK, space="0", color="000000"))
    b.append(_el("left", val="none", sz="0", space="0", color="auto"))
    b.append(_el("bottom", val="single", sz=RULE_THICK, space="0", color="000000"))
    for edge in ("right", "insideH", "insideV"):
        b.append(_el(edge, val="none", sz="0", space="0", color="auto"))
    tblPr.append(b)


def _table_geometry(table, ratios, width_cm=TABLE_W_CM, indent_cm=TABLE_INDENT_CM):
    ncol = len(ratios)
    tblPr = table._tbl.tblPr
    table.autofit = False

    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    tblPr.append(_el("tblW", w=int(round(width_cm * 567)), type="dxa"))
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    tblPr.append(_el("tblLayout", type="fixed"))
    # 居中放置 → 左右自然各留出 indent_cm，比只设左缩进更稳
    for old in tblPr.findall(qn("w:tblInd")):
        tblPr.remove(old)
    tblPr.append(_el("tblInd", w=0, type="dxa"))
    for old in tblPr.findall(qn("w:jc")):
        tblPr.remove(old)
    tblPr.append(_el("jc", val="center"))
    for old in tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(old)
    mar = _el("tblCellMar")
    mar.append(_el("top", w="85", type="dxa"))
    mar.append(_el("left", w="108", type="dxa"))
    mar.append(_el("bottom", w="85", type="dxa"))
    mar.append(_el("right", w="108", type="dxa"))
    tblPr.append(mar)

    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        cols = grid.findall(qn("w:gridCol"))
        for c, ratio in zip(cols, ratios):
            c.set(qn("w:w"), str(int(round(width_cm * ratio * 567))))

    # 逐格写入 tcW，兼顾不认 gridCol 的渲染器
    for row in table.rows:
        for cell, ratio in zip(row.cells, ratios):
            tcPr = cell._tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old)
            tcPr.append(_el("tcW", w=int(round(width_cm * ratio * 567)), type="dxa"))


def _cell_text(cell, text, *, bold=False, color=None, align="left",
               eastasia=None, size=FS_TABLE):
    cell.text = ""
    raw = re.split(r"<br\s*/?>|\n", str(text))
    chunks = []
    for c in raw:
        c = c.strip()
        if not c:
            continue
        # 单元格内以「1.」起头的条目，按「；2.」「。3.」等拆成独立段落
        if re.match(r"^\d{1,2}[.、]\s*", c):
            c = re.sub(r"(?<=[；;。])\s*(?=\d{1,2}[.、]\s*)", "\n", c)
        chunks.extend([x.strip() for x in c.split("\n") if x.strip()])
    chunks = chunks or [""]
    for i, chunk in enumerate(chunks):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        p.style = p.part.document.styles["表格文字"]
        p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT,
                       "center": WD_ALIGN_PARAGRAPH.CENTER,
                       "right": WD_ALIGN_PARAGRAPH.RIGHT}[align]
        p.paragraph_format.line_spacing = LINE_TABLE
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.first_line_indent = Pt(0)
        add_rich(p, chunk, size=size, eastasia=eastasia or FONT_SONG,
                 color=color, base_bold=bold)


def add_three_line_table(doc, headers, rows, width_cm=TABLE_W_CM,
                         indent_cm=TABLE_INDENT_CM, size=None):
    """三线表。传入 cell 时即为嵌套表，用 width_cm / size 适配窄栏。"""
    ncol = len(headers)
    cell_size = size if size is not None else FS_TABLE
    table = doc.add_table(rows=0, cols=ncol)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    _three_line_borders(table)

    hdr = table.add_row()
    trPr = hdr._tr.get_or_add_trPr()
    trPr.append(_el("tblHeader"))          # 跨页重复表头
    trPr.append(_el("cantSplit"))
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        _cell_text(c, h, bold=True, align="center", eastasia=FONT_HEI,
                       size=cell_size)
        c.vertical_alignment = 1           # CENTER
        for p in c.paragraphs:             # 表头跟着首行，不孤悬页末
            p.paragraph_format.keep_with_next = True
        # 表头不加任何底纹：靠加粗与下方 0.75pt 细线区分，黑白打印零损耗
        tcPr = c._tc.get_or_add_tcPr()
        for old in tcPr.findall(qn("w:shd")):
            tcPr.remove(old)
        # 只加表头下那条线；顶线由表格级 tblBorders 提供，不能写 none 挖掉
        _set_cell_borders(c, bottom=("single", RULE_THIN, "000000"))

    for idx, row in enumerate(rows):
        r = table.add_row()
        trPr = r._tr.get_or_add_trPr()
        trPr.append(_el("cantSplit"))      # 行不跨页拆分
        keep = idx < len(rows) - 1
        for i in range(ncol):
            val = row[i] if i < len(row) else ""
            c = r.cells[i]
            _cell_text(c, val, size=cell_size)
            c.vertical_alignment = 1
            # 整表尽量落在一页：除末行外，单元格段落都 keepNext，
            # 避免页末只留下表头加一两行。真放不下时仍会跨页并重复表头。
            if keep:
                for p in c.paragraphs:
                    p.paragraph_format.keep_with_next = True

    _table_geometry(table, column_ratios(headers, ncol, rows),
                    width_cm=width_cm, indent_cm=indent_cm)
    return table


# ───────────────────────────── 板书块 ─────────────────────────────

def _set_board_fonts(run):
    """板书 run：中西文统一宋体，且关闭一切可能改变字宽/字距的开关。

    字符画依赖「1 汉字 = 2 半角」的严格比例；只要有一个字符落到
    Times New Roman，制表符的宽度就变了，整张图立刻散架。
    """
    rPr = run._r.get_or_add_rPr()
    for old in rPr.findall(qn("w:rFonts")):
        rPr.remove(old)
    rPr.insert(0, _el("rFonts", ascii=FONT_SONG, hAnsi=FONT_SONG,
                      eastAsia=FONT_SONG, cs=FONT_SONG, hint="eastAsia"))
    rPr.append(_el("color", val="000000"))
    rPr.append(_el("sz", val=int(round(FS_BOARD * 2))))
    rPr.append(_el("szCs", val=int(round(FS_BOARD * 2))))
    rPr.append(_el("kern", val="0"))


def _board_paragraph_props(p):
    """关掉中西文自动间距、避头尾、标点溢出、网格对齐，否则空格宽度会被改写。"""
    pPr = p._p.get_or_add_pPr()
    for tag in ("autoSpaceDE", "autoSpaceDN", "kinsoku", "overflowPunct",
                "snapToGrid"):
        for old in pPr.findall(qn("w:" + tag)):
            pPr.remove(old)
        pPr.append(_el(tag, val="0"))


def _disp_width(ch):
    """半角=1、全角=2。制表符类字符在宋体中按半角处理。"""
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def _board_spans(line):
    """把一行字符画按「2 个及以上连续空格」切成若干 (半角列号, 文本)。

    单空格（如 "├─ 城墙顶" 里的那个）属于同一段，不切。
    """
    spans, buf, buf_col, col, i = [], "", 0, 0, 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == " ":
            j = i
            while j < n and line[j] == " ":
                j += 1
            run = j - i
            if run >= 2 and buf:
                spans.append((buf_col, buf))
                buf = ""
                col += run
                buf_col = col
            else:
                if buf:              # 段内单空格保留；前导空格只推进列号
                    buf += " " * run
                col += run
            i = j
            continue
        if not buf:
            buf_col = col
        buf += ch
        col += _disp_width(ch)
        i += 1
    if buf:
        spans.append((buf_col, buf))
    return spans


def _render_board_line(p, spans, tab_pt):
    """用制表位把每段推到绝对列位置——对齐不再依赖空格宽度。

    空格宽度随字体而变（宋体 0.5em、华文宋体约 0.24em），靠空格画图
    在换字体后必然散架；制表位是绝对坐标，与字体度量无关。
    """
    pPr = p._p.get_or_add_pPr()
    tabs = _el("tabs")
    for col, _ in spans:
        if col > 0:
            tabs.append(_el("tab", val="left", pos=int(round(col * tab_pt * 20))))
    if len(tabs):
        pPr.append(tabs)
    for col, text in spans:
        if col > 0:
            tr = p.add_run("\t")
            _set_board_fonts(tr)
        r = p.add_run(text)
        _set_board_fonts(r)


def add_board(doc, lines):
    """板书行：单格细框，宋体小五，固定行距，保证字符画不散。"""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    tblPr = t._tbl.tblPr
    b = _el("tblBorders")
    for edge in ("top", "left", "bottom", "right"):
        b.append(_el(edge, val="single", sz=4, space="0", color="808080"))
    tblPr.append(b)
    _table_geometry(t, [1.0])

    # 板书图必须整块呈现，不允许被页面从中间切开
    trPr = t.rows[0]._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))
    trPr.append(_el("keepNext"))

    tab_pt = FS_BOARD * 0.5     # 一个半角列 = 半个字号
    cell = t.rows[0].cells[0]
    cell.text = ""
    for i, ln in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        p.style = p.part.document.styles["表格文字"]
        pf = p.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(FS_BOARD * 1.15)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        pf.first_line_indent = Pt(0)
        _board_paragraph_props(p)
        spans = _board_spans(ln) if ln.strip() else [(0, " ")]
        _render_board_line(p, spans, tab_pt)
    return t


# ───────────────────────────── Markdown 解析 ─────────────────────────────

def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse_markdown(md):
    """把规范 Markdown 拆成 (kind, payload) 序列。"""
    lines = md.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    is_sep = re.compile(r"^[\s|:\-]+$")

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line:
            i += 1
            continue

        # 代码块 / 板书块
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

        # 表题 / 图题
        m = re.match(r"^:::caption\s+(.+)$", line)
        if m:
            out.append(("caption", m.group(1)))
            i += 1
            continue

        # 图片：整行一张图（板书照片、课堂实拍等），按正文宽排满
        m = re.match(r"^!\[[^\]]*\]\((.+?)\)\s*$", line)
        if m:
            out.append(("image", m.group(1).strip()))
            i += 1
            continue

        # 表格
        if line.startswith("|") and i + 1 < len(lines) and is_sep.match(lines[i + 1].strip()):
            headers = split_row(line)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            out.append(("table", (headers, rows)))
            continue

        # 标题
        m = re.match(r"^(#{1,5})\s+(.*)$", line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            out.append(({1: "title", 2: "h1", 3: "h2", 4: "h3"}.get(level, "label"), text))
            i += 1
            continue

        # 复选框
        m = re.match(r"^[-*]\s+\[\s?\]\s+(.*)$", line)
        if m:
            out.append(("checkbox", m.group(1)))
            i += 1
            continue

        # 项目符号
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            out.append(("bullet", m.group(1)))
            i += 1
            continue

        # 有序列表
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


# ───────────────────────────── 主渲染 ─────────────────────────────

def render(md, out_path, header=None, accent="navy", title_override=None):
    accent_hex = ACCENTS.get(accent, accent).lstrip("#").upper()
    doc = Document()
    palette = build_styles(doc, accent_hex)
    setup_section(doc, header or "")

    blocks = parse_markdown(md)
    title_seen = False
    auto_no = 0          # 当前列表编号，无序列表也复用它生成序号
    prev_kind = None

    for kind, payload in blocks:
        if kind == "title":
            p = doc.add_paragraph(style="文档标题")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_rich(p, title_override or payload, size=FS_TITLE, eastasia=FONT_HEI)
            title_seen = True

        elif kind == "h1":
            doc.add_paragraph(payload, style="标题1")

        elif kind == "h2":
            # 「第一课时」这类分课时标题居中加码，层级要压过环节标题。
            # 必须带冒号或接空白才算：否则「第一课时核心检测」这类小节
            # 也会被误判成课时标题，读者会以为又开了一课时。
            if re.match(r"^第[一二三四五六七八九十\d]+课时(?=[：:　\s]|$)", payload):
                doc.add_paragraph(payload, style="课时标题")
            else:
                doc.add_paragraph(payload, style="标题2")

        elif kind == "h3":
            doc.add_paragraph(payload, style="标题3")

        elif kind == "label":
            doc.add_paragraph(payload, style="标签行")

        elif kind == "caption":
            doc.add_paragraph(payload, style="表题")

        elif kind == "para":
            add_para(doc, payload)

        elif kind == "ordered":
            num, text = payload
            p = doc.add_paragraph(style="正文")
            ind = p._p.get_or_add_pPr()
            for old in ind.findall(qn("w:ind")):
                ind.remove(old)
            ind.append(_el("ind", left="680", hanging="340",
                           leftChars="0", firstLineChars="0"))
            add_rich(p, "%s. %s" % (num, text))

        elif kind in ("bullet", "checkbox"):
            # 全文只允许阿拉伯数字序号：无序列表与复选框就地转成序号。
            # 连续的一组列表项共用一段编号，遇正文/表格/标题即从 1 重计。
            auto_no = (auto_no + 1
                       if prev_kind in ("ordered", "bullet", "checkbox") else 1)
            p = doc.add_paragraph(style="正文")
            ind = p._p.get_or_add_pPr()
            for old in ind.findall(qn("w:ind")):
                ind.remove(old)
            ind.append(_el("ind", left="680", hanging="340",
                           leftChars="0", firstLineChars="0"))
            add_rich(p, "%d. %s" % (auto_no, payload))

        elif kind == "table":
            headers, rows = payload
            add_three_line_table(doc, headers, rows)
            # 表格没有 space_after，正文会紧贴底线；用一个固定行距的空段落
            # 撑出 9pt 呼吸空间（段前段后归零，不引入额外行高）。
            gap = doc.add_paragraph()
            gap.paragraph_format.space_before = Pt(0)
            gap.paragraph_format.space_after = Pt(0)
            gap.paragraph_format.line_spacing = Pt(9)
            gap.paragraph_format.first_line_indent = Pt(0)

        elif kind == "board":
            add_board(doc, payload)

        elif kind == "image":
            # 板书照片等整幅图：按表格宽（14.4cm）居中排满，超出页面高度时
            # 等比缩小，避免一张竖图把整页撑破
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf = p.paragraph_format
            pf.first_line_indent = Pt(0)
            pf.space_before = Pt(6)
            pf.space_after = Pt(6)
            pf.line_spacing = 1.0
            pic = p.add_run().add_picture(payload, width=Cm(TABLE_W_CM))
            max_h = Cm(19.5)
            if pic.height > max_h:
                ratio = max_h / pic.height
                pic.width = int(pic.width * ratio)
                pic.height = int(max_h)

        # 维护列表编号：非列表项清零，显式有序号以其数字为准
        if kind not in ("ordered", "bullet", "checkbox"):
            auto_no = 0
        elif kind == "ordered":
            auto_no = int(payload[0])
        prev_kind = kind

    # 去掉文档末尾多余空段
    body = doc.element.body
    for p in list(doc.paragraphs)[::-1]:
        if p.text.strip() == "" and p.style.name != "正文":
            p._p.getparent().remove(p._p)
        else:
            break

    normalize_xml(doc)
    doc.save(out_path)
    return title_seen


def main():
    ap = argparse.ArgumentParser(description="教学设计「自用版」排版")
    ap.add_argument("--input", required=True, help="规范 Markdown 草稿")
    ap.add_argument("--output", required=True, help="输出 .docx 路径")
    ap.add_argument("--header", default="", help="页眉文字（通常写课题名）")
    ap.add_argument("--accent", default="navy",
                    help="已保留但无效果：本版式全黑白，没有任何着色点")
    ap.add_argument("--title", default=None, help="覆盖文档标题")
    a = ap.parse_args()

    md = open(a.input, encoding="utf-8").read()
    render(md, a.output, header=a.header or a.title or "",
           accent=a.accent, title_override=a.title)
    print("已生成:", a.output)


if __name__ == "__main__":
    main()
