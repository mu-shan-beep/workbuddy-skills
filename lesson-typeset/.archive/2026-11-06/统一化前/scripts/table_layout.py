#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""教学设计「表格式」排版引擎（对齐已交付的《出塞教学设计》模板）
================================================================

整份教学设计装进一张 4 列网格表，四种行型：

    ┌────────────────────────────────────┐
    │  大节分组行（C8C8C8 居中）           │   ## 一、教学基本信息
    ├────────────────────────────────────┤
    │  章节 / 环节标题（独立整行，不跨页）  │   ### 课时内标题 / #### 环节一
    ├──────────┬─────────────────────────┤
    │  标签    │  内容                   │   :::row / :::row2
    ├──────────┼──────────┬──────────┬───┤
    │  活动名称 │ 教师活动  │ 学生活动  │设计意图│   :::act + T:/S:/D: + :::
    ├──────────┴──────────┴──────────┴───┤
    │  整行内容（正文、嵌套表、板书照片）    │
    └────────────────────────────────────┘

版式：全文宋体 / 正文四号 14pt·教学过程小四 12pt / 行距 1.45·1.18 /
      0.5pt 全框线 / 页边距 2.54·3.17 / 四列 2.10·5.60·3.70·3.26cm。

用法：
    python3 table_layout.py --input draft.md --output out.docx \
        [--title "《牛和鹅》教学设计"] [--subtitle "副标题（一般不要）"]

草稿语法见 references/table-spec.md：
    :::row  标签 | 值
    :::row2 标签 | 值 | 标签 | 值
    :::act 活动名 / T: 教师活动 / S: 学生活动 / D: 设计意图 / :::
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

import jxsj_legacy as J
from jxsj_legacy import (_el, _set_fonts, add_rich, add_three_line_table,
                         normalize_xml, parse_markdown)

SONG = "宋体"
FS = 14.0              # 四号，与参考模板一致
FS_TITLE = 18.0        # 小二
FS_SUB = 10.5
LINE = 1.45            # 参考模板为 1.5；收到 1.45 是为把全文压进整页
FS_ACT = 12.0          # 教学过程四列用小四：列宽有限，四号会折成两三字一行
LINE_ACT = 1.18

PAGE_W, PAGE_H = 21.0, 29.7
M_TB, M_LR = 2.54, 3.17
CONTENT_W = PAGE_W - M_LR * 2                       # 14.66cm

# 4 列网格：2.10 / 5.60 / 3.70 / 3.26（合计 14.66cm）
# 教学过程以「活动名称 / 教师活动 / 学生活动 / 设计意图」四列落位，
# 其余行按 1+3（标签行）或整行合并（分组行、内容行）使用。
GRID = [2.10, 5.60, 3.70, 3.26]
# 先各自化成 twips，再按列求和：跨列格必须等于 tblGrid 相邻列之和，
# 否则差 1 twip 也算不一致（Word 会按 tcW 重排，列宽就漂）。
GRID_TW = [int(round(g * 567)) for g in GRID]
NCOL = len(GRID)
NEST3_RATIO = (0.36, 0.20, 0.44)   # 嵌套三列表：中列要放得下「受挫、觉得为难」
BORDER_SZ = 4                       # 0.5pt，全框线统一线宽
FILL_BAND = "C8C8C8"
FILL_LEAD = "F0F0F0"   # 课时内章节标题，比大节分组行浅两档

ALIGN = {"both": WD_ALIGN_PARAGRAPH.JUSTIFY,
         "left": WD_ALIGN_PARAGRAPH.LEFT,
         "center": WD_ALIGN_PARAGRAPH.CENTER,
         "right": WD_ALIGN_PARAGRAPH.RIGHT}


# ───────────────────────────── 基础工具 ─────────────────────────────

def _ind(p, chars=0, left_tw=None, hang_tw=None):
    pPr = p._p.get_or_add_pPr()
    for old in pPr.findall(qn("w:ind")):
        pPr.remove(old)
    attrs = {}
    if left_tw is not None:
        attrs["left"] = int(left_tw)
        attrs["leftChars"] = 0
    if hang_tw is not None:
        attrs["hanging"] = int(hang_tw)
    if chars:
        attrs["firstLineChars"] = int(chars * 100)
        attrs["firstLine"] = int(round(FS * 20 * chars))
    elif left_tw is None and hang_tw is None:
        attrs["firstLineChars"] = 0      # 显式清零，否则继承正文的 2 字符缩进
        attrs["firstLine"] = 0
    if attrs:
        pPr.append(_el("ind", **attrs))


def _shade(cell, fill):
    if not fill:
        return
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:shd")):
        tcPr.remove(old)
    tcPr.append(_el("shd", val="clear", color="auto", fill=fill))


def _clear_cell(cell):
    """合并后单元格会留下多个空段，只保留一个并清空。"""
    for p in cell.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    p0 = cell.paragraphs[0]
    for r in list(p0.runs):
        p0._p.remove(r._r)
    return p0


class Writer:
    """往单元格里按顺序追加段落 / 表格 / 图片。"""

    def __init__(self, cell):
        self.cell = cell
        self._first = True
        self.auto_no = 0
        self.prev = None

    def p(self):
        if self._first:
            self._first = False
            return self.cell.paragraphs[0]
        return self.cell.add_paragraph()

    def close(self):
        """保证单元格以段落收尾（Word 硬性要求）。"""
        body = self.cell._tc
        last = body.findall(qn("w:p"))[-1] if body.findall(qn("w:p")) else None
        children = [c for c in body if c.tag in (qn("w:p"), qn("w:tbl"))]
        if children and children[-1].tag == qn("w:tbl"):
            p = self.cell.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = Pt(6)


def write_para(w, text, *, bold=False, size=FS, indent=2, align="both",
               before=0, after=0, line=LINE, keep=False, keep_lines=False,
               left_tw=None, hang_tw=None):
    p = w.p()
    p.alignment = ALIGN[align]
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    if left_tw is not None or hang_tw is not None:
        _ind(p, 0, left_tw=left_tw, hang_tw=hang_tw)
    else:
        _ind(p, indent)
    add_rich(p, text, size=size, eastasia=SONG, base_bold=bold)
    if keep:
        pf.keep_with_next = True
    if keep_lines:
        pf.keep_together = True
    return p


# ───────────────────────────── 行构造 ─────────────────────────────

def band_row(table, text, *, center=True, fill=FILL_BAND, size=FS,
             before=3, after=3):
    row = table.add_row()
    cells = list(row.cells)
    cell = cells[0].merge(cells[-1])
    _clear_cell(cell)
    _shade(cell, fill)
    cell.vertical_alignment = 1
    write_para(Writer(cell), text, bold=True, size=size, indent=0,
               align="center" if center else "left",
               before=before, after=after, keep=True)
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))
    return row


def subhead_row(table, text, fill=None):
    """小节 / 环节标题：独立一行，与下一行同页，避免标题孤悬页末。

    fill：课时内章节标题用的浅底纹；环节标题不传，保持白底。
    """
    row = table.add_row()
    cells = list(row.cells)
    cell = cells[0].merge(cells[-1])
    _clear_cell(cell)
    _shade(cell, fill)
    cell.vertical_alignment = 1
    write_para(Writer(cell), text, bold=True, indent=2, align="left",
               before=8, after=5, keep=True)
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))
    trPr.append(_el("keepNext"))
    return row


def kv_row(table, label, value):
    row = table.add_row()
    cells = list(row.cells)
    left, right = cells[0], cells[1].merge(cells[-1])
    for c in (left, right):
        _clear_cell(c)
        c.vertical_alignment = 1
    # 标签列只有 2.1cm：四号字的四字标签会折行，标签统一用小四
    write_para(Writer(left), label, bold=True, size=FS_ACT, indent=0,
               align="center", before=3, after=3)
    write_para(Writer(right), value, indent=0, align="left", before=3, after=3)
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))


def kv2_row(table, l1, v1, l2, v2):
    row = table.add_row()
    cells = list(row.cells)
    a, b, c, d = cells[0], cells[1], cells[2], cells[3]
    for cell in (a, b, c, d):
        _clear_cell(cell)
        cell.vertical_alignment = 1
    write_para(Writer(a), l1, bold=True, size=FS_ACT, indent=0, align="center",
               before=3, after=3)
    write_para(Writer(b), v1, indent=0, align="left", before=3, after=3)
    write_para(Writer(c), l2, bold=True, size=FS_ACT, indent=0, align="center",
               before=3, after=3)
    write_para(Writer(d), v2, indent=0, align="left", before=3, after=3)
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))


def content_row(table):
    """整行内容行。允许跨页续排——不设 cantSplit。"""
    row = table.add_row()
    cells = list(row.cells)
    cell = cells[0].merge(cells[-1])
    _clear_cell(cell)
    cell.vertical_alignment = 0        # TOP
    return Writer(cell)


def act_head_row(table):
    """教学过程四列表头：活动名称 / 教师活动 / 学生活动 / 设计意图。"""
    row = table.add_row()
    for cell, title in zip(row.cells, ("活动名称", "教师活动", "学生活动", "设计意图")):
        _clear_cell(cell)
        _shade(cell, FILL_LEAD)
        cell.vertical_alignment = 1
        write_para(Writer(cell), title, bold=True, size=FS_ACT, indent=0,
                   align="center", before=2, after=2, keep=True)
    trPr = row._tr.get_or_add_trPr()
    trPr.append(_el("cantSplit"))
    return row


def act_row(table, name, t_paras, s_paras, d_paras):
    """一个教学活动的四列行。允许跨页断行——不设 cantSplit。"""
    row = table.add_row()
    cells = list(row.cells)
    for c in cells:
        _clear_cell(c)
        c.vertical_alignment = 0        # TOP
    write_para(Writer(cells[0]), name, bold=True, size=FS_ACT, indent=0,
               align="left", before=2, after=2, line=LINE_ACT,
               keep_lines=True)
    for idx, paras in ((1, t_paras), (2, s_paras), (3, d_paras)):
        w = Writer(cells[idx])
        for text in paras:
            write_para(w, text, size=FS_ACT, indent=0, align="left",
                       before=1, after=1, line=LINE_ACT)
    # 活动行允许跨页断行：整行强推会在上一页尾部留下大片空白（实测 27→31 页）。
    # 表头行自身 cantSplit + 段落 keepNext，保证「表头 + 活动首行」不分离。
    return row


# ───────────────────────────── 内容渲染 ─────────────────────────────

def render_nested_table(w, headers, rows):
    size = 9.5 if len(headers) >= 4 else 10.5
    was_first = w._first
    width_cm = CONTENT_W - 0.40
    add_three_line_table(w.cell, headers, rows,
                         width_cm=width_cm, indent_cm=0.0, size=size)
    # 嵌套表与主表同一套全框线，避免一页里两种表格外观
    nested = w.cell.tables[-1]
    grid_borders(nested)
    nested_widths(nested, width_cm)
    # add_table 追加在原有空段之后：若表格是单元格第一个元素，删掉那段，
    # 否则表格上方会多出一条空白行
    if was_first:
        paras = w.cell.paragraphs
        if len(paras) > 1 and not paras[0].text.strip():
            paras[0]._p.getparent().remove(paras[0]._p)
    w._first = False
    # add_table 会补一个空段，压成 6pt 空隙
    for p in w.cell.paragraphs[-1:]:
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = Pt(6)


def render_image(w, path):
    p = w.p()
    p.alignment = ALIGN["center"]
    pf = p.paragraph_format
    pf.space_before = Pt(6)
    pf.space_after = Pt(6)
    pf.line_spacing = 1.0
    _ind(p, 0)
    run = p.add_run()
    _set_fonts(run._r.get_or_add_rPr(), SONG, size=FS)
    pic = run.add_picture(path, width=Cm(CONTENT_W - 0.6))
    max_h = Cm(19.5)
    if pic.height > max_h:
        ratio = max_h / pic.height
        pic.width = int(pic.width * ratio)
        pic.height = int(max_h)


def render_block(w, kind, payload):
    if kind == "para":
        write_para(w, payload)

    elif kind == "label":
        write_para(w, payload, bold=True, indent=2, before=2, after=0)

    elif kind == "ordered":
        num, text = payload
        write_para(w, "%s. %s" % (num, text))

    elif kind in ("bullet", "checkbox"):
        # 全文只保留阿拉伯数字序号
        w.auto_no = (w.auto_no + 1
                     if w.prev in ("ordered", "bullet", "checkbox") else 1)
        write_para(w, "%d. %s" % (w.auto_no, payload))

    elif kind == "h3":          # 四级标题：活动一…，留在内容流里
        write_para(w, payload, bold=True, indent=2, before=6, after=2)

    elif kind == "subhead":     # 小节标题：加粗段落
        write_para(w, payload, bold=True, indent=2, before=10, after=5)

    elif kind == "table":
        render_nested_table(w, payload[0], payload[1])

    elif kind == "image":
        render_image(w, payload)

    elif kind == "board":
        for ln in payload:
            write_para(w, ln, indent=0, line=1.0)

    # 维护自动编号状态
    if kind == "ordered":
        w.auto_no = int(payload[0])
        w.prev = "ordered"
    elif kind in ("bullet", "checkbox"):
        w.prev = "bullet"
    else:
        w.auto_no = 0
        w.prev = kind


# ───────────────────────────── 表格骨架 ─────────────────────────────

def build_table(doc):
    t = doc.add_table(rows=0, cols=NCOL)
    grid_borders(t)
    return t


def grid_borders(t):
    """全框线：六条边一律 single 0.5pt 自动色，无粗外框、无隐藏线。

    0.5pt（sz=4）是 Word 里最细的常规框线；用户 2026-11-04 明确
    「表格的所有框线都需要显示，不能加粗」，因此主表与嵌套表同此一套，
    不再使用 1.5pt 顶/底线的三线表外观。
    """
    tblPr = t._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = _el("tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b.append(_el(edge, val="single", sz=BORDER_SZ, space="0", color="auto"))
    tblPr.append(b)
    # 三线表留下的表头下 0.75pt 线会与网格线叠成粗线，一并清掉
    for tc in t._tbl.iter(qn("w:tc")):
        tcPr = tc.find(qn("w:tcPr"))
        if tcPr is None:
            continue
        for old in tcPr.findall(qn("w:tcBorders")):
            tcPr.remove(old)


def nested_widths(t, width_cm):
    """嵌套表按列数给固定比例：三列 36/20/44，其余沿用引擎自适应。"""
    if len(t.columns) != 3:
        return
    ratios = NEST3_RATIO
    total_tw = int(round(width_cm * 567))
    # 末列吃掉舍入余数，三列之和与 tblW 严格相等
    widths = [int(round(total_tw * r)) for r in ratios[:2]]
    widths.append(total_tw - sum(widths))
    tblPr = t._tbl.tblPr
    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    tblPr.append(_el("tblW", w=total_tw, type="dxa"))
    grid = t._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for col, w in zip(grid.findall(qn("w:gridCol")), widths):
            col.set(qn("w:w"), str(w))
    for row in t.rows:
        for cell, w in zip(row.cells, widths):
            tcPr = cell._tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old)
            tcPr.append(_el("tcW", w=w, type="dxa"))


def finish_table(t):
    """固定布局 + 列宽 + 逐格 tcW（按 gridSpan 求和）。"""
    tblPr = t._tbl.tblPr
    for tag in ("tblW", "jc", "tblLayout", "tblCellMar", "tblInd"):
        for old in tblPr.findall(qn("w:" + tag)):
            tblPr.remove(old)
    tblPr.append(_el("tblW", w=sum(GRID_TW), type="dxa"))
    tblPr.append(_el("jc", val="center"))
    tblPr.append(_el("tblLayout", type="fixed"))
    mar = _el("tblCellMar")
    mar.append(_el("top", w="40", type="dxa"))
    mar.append(_el("left", w="85", type="dxa"))
    mar.append(_el("bottom", w="40", type="dxa"))
    mar.append(_el("right", w="85", type="dxa"))
    tblPr.append(mar)

    grid = t._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for col, tw in zip(grid.findall(qn("w:gridCol")), GRID_TW):
            col.set(qn("w:w"), str(tw))

    for row in t.rows:
        start = 0                       # 本格在该行的起始列（跨列时后移 span）
        for tc in row._tr.findall(qn("w:tc")):
            span = 1
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is not None:
                gs = tcPr.find(qn("w:gridSpan"))
                if gs is not None:
                    span = int(gs.get(qn("w:val")))
            # 必须从 start 起算：旧写法 sum(GRID[:span]) 让每个单列格都取到
            # 第一列 2.10cm，四列宽度声明成一样，Word 里列宽就塌了。
            w_tw = sum(GRID_TW[start:start + span])
            if tcPr is None:
                tcPr = _el("tcPr")
                tc.insert(0, tcPr)
            for old in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old)
            tcPr.append(_el("tcW", w=w_tw, type="dxa"))
            start += span


# ───────────────────────────── 主流程 ─────────────────────────────

ACT_C = "\x1e"      # 活动四列之间的分隔
ACT_P = "\x1f"      # 同一列内段落之间的分隔


def preprocess(md):
    """: ::row / :::row2 / :::act 转成单行标记，交给 block 解析。"""
    out = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        s = lines[i].strip()

        if s.startswith(":::act "):
            name = s[len(":::act "):].strip()
            cols = {"T": [], "S": [], "D": []}
            i += 1
            while i < len(lines):
                t = lines[i].strip()
                if not t:
                    i += 1
                    continue
                if len(t) > 2 and t[:2] in ("T:", "S:", "D:"):
                    cols[t[0]].append(t[2:].strip())
                    i += 1
                    continue
                if t == ":::":
                    i += 1
                break
            out.append("@@ACT@@" + name + ACT_C +
                       ACT_C.join(ACT_P.join(cols[k]) for k in ("T", "S", "D")))
            continue

        if s.startswith(":::row2 "):
            out.append("@@ROW2@@" + s[len(":::row2 "):])
        elif s.startswith(":::row "):
            out.append("@@ROW@@" + s[len(":::row "):])
        else:
            out.append(lines[i])
        i += 1
    return "\n".join(out)


def render(md, out_path, title=None, subtitle=None):
    doc = Document()

    # 页面：A4，边距与参考模板一致
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(PAGE_W), Cm(PAGE_H)
    s.top_margin = s.bottom_margin = Cm(M_TB)
    s.left_margin = s.right_margin = Cm(M_LR)
    J.setup_section(doc, "")
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(PAGE_W), Cm(PAGE_H)
    s.top_margin = s.bottom_margin = Cm(M_TB)
    s.left_margin = s.right_margin = Cm(M_LR)

    # 正文样式：宋体四号 / 1.5 倍 / 两端对齐 / 首行缩进 2 字符
    normal = doc.styles["Normal"]
    _set_fonts(normal.element, SONG, size=FS, color="000000")
    J._set_ppr(normal.element, before=0, after=0, line=LINE,
               first_line_chars=2, align="both", widow=True)

    # 嵌套表依赖「表格文字」样式
    if "表格文字" not in [st.name for st in doc.styles]:
        st = doc.styles.add_style("表格文字", 1)
        st.base_style = normal
        _set_fonts(st.element, SONG, size=10.5, color="000000")
        J._set_ppr(st.element, before=0, after=0, line=1.0,
                   first_line_chars=0, align="left", widow=True)

    blocks = parse_markdown(preprocess(md))

    # 标题（表格外）
    title_text, sub_text = title, subtitle
    rest = []
    for kind, payload in blocks:
        if kind == "title":
            # 标题一律走表格外的段外标题；命令行给了 --title 时丢弃草稿里的同名标题，
            # 否则它会作为空块落进表格第一行
            if title_text is None:
                title_text = payload
            continue
        rest.append((kind, payload))
    # 首段若在第一个一级标题之前，视为副标题
    if rest and sub_text is None and rest[0][0] == "para" and \
            not any(k in ("h1", "h2") for k, _ in rest[:1]) and \
            rest[0][1] and len(rest[0][1]) <= 24:
        sub_text = rest[0][1]
        rest = rest[1:]

    if title_text:
        p = doc.add_paragraph()
        p.alignment = ALIGN["center"]
        pf = p.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(4)
        pf.line_spacing = 1.2
        _ind(p, 0)
        add_rich(p, title_text, size=FS_TITLE, eastasia=SONG, base_bold=True)

    if sub_text:
        p = doc.add_paragraph()
        p.alignment = ALIGN["center"]
        pf = p.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(10)
        pf.line_spacing = 1.0
        _ind(p, 0)
        add_rich(p, sub_text, size=FS_SUB, eastasia=SONG)

    table = build_table(doc)

    buf = []            # 待落成「整行内容行」的块
    head_pending = [False]   # 每个课时只在第一个活动前放一次四列表头
    in_lesson = [False]      # 是否处在「第X课时教学设计」之内

    def flush():
        if not buf:
            return
        # 含嵌套表的行也允许跨页续排：嵌套表首行已设 tblHeader，续排页会重复表头
        # （Word / WPS 支持；LibreOffice 预览不重复，属渲染差异）。
        w = content_row(table)
        for kind, payload in buf:
            render_block(w, kind, payload)
        w.close()
        buf.clear()

    for i, (kind, payload) in enumerate(rest):
        if kind == "h1":
            flush()
            band_row(table, payload, center=True, before=5, after=5)
            # 进入新课时：教学过程开始时放一次四列表头
            if "课时" in payload:
                head_pending[0] = True
            in_lesson[0] = "课时" in payload

        elif kind == "h2":
            # 课时内的大标题（一、本课时教学目标…）：单独占一整行、独占一个表格行；
            # 课时外的小标题（教学重点、教师准备…）仍是正文流里的加粗段落，与内容同格。
            if in_lesson[0]:
                flush()
                subhead_row(table, payload, fill=FILL_LEAD)
            else:
                buf.append(("subhead", payload))

        elif kind == "h3":
            # 环节标题：表格外独立一行、不加底纹，与下面的活动行同页
            flush()
            subhead_row(table, payload)

        elif kind == "para" and payload.startswith("@@ACT@@"):
            flush()
            if head_pending[0]:
                act_head_row(table)
                head_pending[0] = False
            parts = payload[len("@@ACT@@"):].split(ACT_C)
            name = parts[0]
            rest = (parts + ["", "", ""])[1:4]
            t_cell, s_cell, d_cell = rest
            act_row(table, name,
                    [x for x in t_cell.split(ACT_P) if x],
                    [x for x in s_cell.split(ACT_P) if x],
                    [x for x in d_cell.split(ACT_P) if x])

        elif kind == "para" and payload.startswith("@@ROW@@"):
            flush()
            parts = [x.strip() for x in payload[len("@@ROW@@"):].split("|")]
            if len(parts) >= 2:
                kv_row(table, parts[0], "|".join(parts[1:]))

        elif kind == "para" and payload.startswith("@@ROW2@@"):
            flush()
            parts = [x.strip() for x in payload[len("@@ROW2@@"):].split("|")]
            while len(parts) < 4:
                parts.append("")
            kv2_row(table, parts[0], parts[1], parts[2], parts[3])

        else:
            buf.append((kind, payload))
    flush()

    finish_table(table)
    normalize_xml(doc)
    doc.save(out_path)


def main():
    ap = argparse.ArgumentParser(description="教学设计表格式排版")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default=None)
    a = ap.parse_args()
    md = open(a.input, encoding="utf-8").read()
    render(md, a.output, title=a.title, subtitle=a.subtitle)
    print("已生成:", a.output)


if __name__ == "__main__":
    main()
