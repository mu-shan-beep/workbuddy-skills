#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课件制作笔记「统一排版标准 V1.0」排版引擎
==========================================

A4 说明性文档：思源黑体标题 + 楷体正文，170mm 版心，浅绿表头全框线表格，
细分隔线分章，图片配图注。版式常量以 references/unified-spec.md 第 1 章为唯一权威，
改版式只改本文件顶部常量。

用法：
    python3 zhizuobiji_typeset.py --input 制作笔记.md \
        --header "23 王戎不取道旁李" \
        --output 23王戎不取道旁李-制作笔记.docx

    # 双面装订（奇偶页镜像：内侧 22mm / 外侧 18mm，版心仍 170mm）
    python3 zhizuobiji_typeset.py --input ... --mirror

底层构件（schema 有序插入、行高规则、表格边框）复用学习清单引擎，
两份引擎共用同一套 OOXML 约定，见 references/unified-spec.md 第 1 章。
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from xuexqingdan_typeset import (  # noqa: E402  同目录复用底层构件
    Ctx, add_page_field, add_rich, add_run, fmt_para, gap,
    resolve_font, HEAD_CANDIDATES, BODY_CANDIDATES,
    _put, _PPR_ORDER, _TBLPR_ORDER, _tbl_borders, _no_borders, _tbl_margins,
    _set_row_h, set_col_widths, _cell_shade,
    _row_cant_split, _row_header, _first_para, _cell_para, build_header,
)

# ─────────────────── 版式常量（V1.0） ───────────────────

PAGE_W, PAGE_H = 21.0, 29.7           # A4 纵向
M_TOP = M_BOTTOM = 1.8                # 上下 18mm
M_LEFT = M_RIGHT = 2.0                # 左右 20mm（单面）
M_INNER, M_OUTER = 2.2, 1.8           # 双面装订：内侧 22 / 外侧 18
HDR_DIST = 1.0                        # 页眉距上边 10mm
FTR_DIST = 1.0                        # 页脚距下边 10mm

CONTENT_W = PAGE_W - M_LEFT - M_RIGHT           # 17.0cm
MIRROR_CONTENT_W = PAGE_W - M_INNER - M_OUTER   # 17.0cm（版心等宽，只换边距）

# 颜色
GREEN = "315A4B"      # 主标题 / 一级标题 / 二级标题
INK = "2B302C"        # 三级标题 / 正文
MUTED = "596960"      # 辅助文字 / 图注 / 页眉页脚
BAND = "EDF3EE"       # 表头 / 强调区域底色
LINE = "9BA9A0"       # 表格边框
SEP = "CBD5CD"        # 分隔线

# 字号（pt）
FS_TITLE = 20.0       # 文档主标题
FS_SUBTITLE = 13.0    # 文档副标题
FS_H1 = 14.0          # 一级标题
FS_H2 = 12.0          # 二级标题
FS_H3 = 11.0          # 三级标题
FS_BODY = 11.0        # 正文
FS_TH = 10.5          # 表头
FS_TD = 10.5          # 表格正文
FS_CAP = 9.5          # 图片说明
FS_HF = 9.0           # 页眉页脚

# 行距
LINE_BODY = 1.5       # 正文
LINE_TITLE = 1.2      # 标题
LINE_CAP = 1.2        # 图注
LINE_CELL = 1.3       # 单元格多行（1.25—1.35）

# 间距（mm）
SP_H1_BEF, SP_H1_AFT = 10.0, 4.0      # 一级标题 段前/段后
SP_H2_BEF, SP_H2_AFT = 7.0, 3.0       # 二级标题
SP_H3_BEF, SP_H3_AFT = 5.0, 2.0       # 三级标题
SP_P_AFT = 3.0                        # 正文段后
SP_SUB_BEF = 6.0                      # 主标题→副标题 5—7
SP_SUB_AFT = 14.0                     # 副标题→正文 12—16
SP_TBL_BEF, SP_TBL_AFT = 4.5, 5.0     # 表格上下 4—6 / 5—7
SP_IMG_BEF, SP_IMG_AFT = 5.0, 5.0     # 图片与上下文字
SP_CAP_AFT = 3.0                      # 图注与下方文字 2—3
SP_CAP_GAP = 2.5                      # 图片与图注 2—3

# 表格
ROW_H = 12.0                          # 单行最小高 12mm
CELL_MAR = (170, 170, 142, 142)       # 左右 3mm、上下 2.5mm（twips）
BORDER_OUT = 6                        # 0.75pt
BORDER_IN = 4                         # 0.5pt

# 强调区域
NOTE_PAD_X = 4.0                      # 4—5mm
NOTE_PAD_Y = 4.0

MM2PT = 72 / 25.4


def mm2pt(mm):
    return mm * MM2PT


def content_width(mirror=False):
    return MIRROR_CONTENT_W if mirror else CONTENT_W


# ─────────────────── 构件 ───────────────────

def h2_rule(p, on=True, space_pt=6):
    """一级标题上方的章节细分隔线：直接画成段落上边框。
    比「独立的分隔线段」稳：线天然与标题同页，不会单独留在上一页页脚，
    也不额外占一行高度（规范 5.1「可使用细分隔线辅助区分章节」）。"""
    if not on:
        return p
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single")
    top.set(qn("w:sz"), "4")            # 0.5pt
    top.set(qn("w:space"), str(space_pt))
    top.set(qn("w:color"), SEP)
    bdr.append(top)
    _put(pPr, bdr, _PPR_ORDER)
    return p


def explicit_divider(doc, before=3.0, after=3.0):
    """源稿写了 :::divider 才出现的独立分隔线（0.5pt #CBD5CD）。
    章节分隔默认走 h2_rule()，不需要源稿写。"""
    p = doc.add_paragraph()
    fmt_para(p, before=mm2pt(before), after=mm2pt(after), line=None)
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), SEP)
    bdr.append(bottom)
    _put(pPr, bdr, _PPR_ORDER)
    r = p.add_run("")
    r.font.size = Pt(1)
    return p


def data_table(doc, headers, rows, width_cm, widths=None):
    """全框线表格：外 0.75pt / 内 0.5pt，表头浅绿居中 10.5pt 黑体。"""
    cols = len(headers) if headers else max(len(r) for r in rows)
    if widths is None:
        if cols == 2:
            widths = [width_cm * 0.30, width_cm * 0.70]
        elif cols == 3:
            widths = [width_cm * 0.25, width_cm * 0.35, width_cm * 0.40]
        elif cols == 4:
            widths = [width_cm * 0.28] + [width_cm * 0.24] * 3
        else:
            widths = [width_cm / cols] * cols

    t = doc.add_table(rows=0, cols=cols)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _tbl_borders(t, BORDER_OUT, BORDER_IN, LINE)
    _tbl_margins(t, *CELL_MAR)

    if headers:
        row = t.add_row()
        _row_header(row)
        _row_cant_split(row)
        _set_row_h(row, ROW_H)
        for i, h in enumerate(headers):
            c = row.cells[i]
            _cell_shade(c, BAND)
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = _first_para(c, align=WD_ALIGN_PARAGRAPH.CENTER, line=LINE_CELL)
            p.paragraph_format.keep_with_next = True
            add_rich(p, h, size=FS_TH, color=INK, font=Ctx.head)

    for vals in rows:
        row = t.add_row()
        _row_cant_split(row)
        _set_row_h(row, ROW_H)
        for i in range(cols):
            val = vals[i] if i < len(vals) else ""
            c = row.cells[i]
            # 单行居中、多行顶部对齐：同一格多段时首段居中、其余续段顶对齐由行高自然处理
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = _first_para(c, line=LINE_CELL)
            add_rich(p, val, size=FS_TD, color=INK)

    set_col_widths(t, widths)
    return t


def note_block(doc, lines, width_cm):
    """强调区域：段落底纹（纯装饰的 1×1 表，按统一判据不再使用表格）。

    多行内容用段内软换行，保证底纹是一整块、不被行距切成条。
    """
    p = doc.add_paragraph()
    fmt_para(p, before=NOTE_PAD_Y * MM2PT, after=NOTE_PAD_Y * MM2PT,
             line=LINE_BODY)
    p.paragraph_format.left_indent = Cm(NOTE_PAD_X / 10.0)
    p.paragraph_format.right_indent = Cm(NOTE_PAD_X / 10.0)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), BAND)
    pPr = p._p.get_or_add_pPr()
    pPr.insert_element_before(
        shd, "w:spacing", "w:ind", "w:jc", "w:rPr", "w:sectPr", "w:pPrChange")
    add_rich(p, lines[0], size=FS_BODY, color=INK)
    for extra in lines[1:]:
        p.add_run().add_break()
        add_rich(p, extra, size=FS_BODY, color=INK)
    return p


def figure(doc, path, caption, width_cm):
    """图片：按原始比例缩放到版心内，居中；图注 9.5pt 楷体居中。"""
    from PIL import Image
    try:
        with Image.open(path) as im:
            w_px, h_px = im.size
    except Exception:
        w_px = h_px = None

    p = doc.add_paragraph()
    fmt_para(p, before=mm2pt(SP_IMG_BEF), after=mm2pt(SP_CAP_GAP),
             line=None, align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    run = p.add_run()
    if w_px:
        nat_w_cm = w_px / 96.0 * 2.54          # 按 96dpi 估原生尺寸
        w = min(width_cm, nat_w_cm) if nat_w_cm > 1 else width_cm
        run.add_picture(path, width=Cm(w))
    else:
        run.add_picture(path, width=Cm(width_cm))

    if caption:
        pc = doc.add_paragraph()
        fmt_para(pc, before=0, after=mm2pt(SP_CAP_AFT),
                 line=LINE_CAP, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(pc, caption, size=FS_CAP, color=MUTED)


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

        # Markdown 表格
        if s.startswith("|") and i + 1 < len(lines) and is_sep.match(lines[i + 1].strip()):
            headers = cells(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            blocks.append(("table", (headers, rows)))
            continue

        # ::: 指令
        m = re.match(r"^:::\s*(\w+)\s*(.*)$", s)
        if m:
            kind, payload = m.group(1), m.group(2).strip()
            if kind == "note":
                body = [payload] if payload else []
                i += 1
                while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(":::"):
                    body.append(lines[i].strip())
                    i += 1
                if i < len(lines) and lines[i].strip().startswith(":::"):
                    i += 1
                blocks.append(("note", [b for b in body if b]))
                continue
            blocks.append((kind, payload))
            i += 1
            continue

        # 图片
        mi = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", s)
        if mi:
            blocks.append(("img", (mi.group(1).strip(), mi.group(2).strip())))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            blocks.append(({1: "h1", 2: "h2", 3: "h3", 4: "h4"}[lvl], m.group(2).strip()))
            i += 1
            continue

        # 引用（引文段，非副标题）
        if s.startswith(">"):
            blocks.append(("quote", s[1:].strip()))
            i += 1
            continue

        # 列表 → 阿拉伯序号
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            blocks.append(("li", m.group(1).strip()))
            i += 1
            continue

        blocks.append(("p", s))
        i += 1
    return blocks


# ─────────────────── 渲染 ───────────────────

def build(md, out_path, header="", title=None, subtitle=None, mirror=False,
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
    sec.different_first_page_header_footer = False   # 首页也是正文页，页眉页码同样出现

    blocks = parse(md)

    # 标题素材：首个 # 作主标题，:::subtitle 作副标题
    h1 = next((t for k, t in blocks if k == "h1"), "")
    blocks = [(k, t) for k, t in blocks if k != "h1"]
    sub = subtitle
    if sub is None:
        sub = next((t for k, t in blocks if k == "subtitle"), "")
    blocks = [(k, t) for k, t in blocks if k != "subtitle"]
    doc_title = title or h1.strip() or header

    # 页眉：四类统一的 Logo 区（左 30×12mm 木老师占位框 ＋ 右课题 ＋ CBD5CD 分隔线）
    build_header(sec, CONTENT_W, text=header or doc_title, logo=None, logo_mode="placeholder")

    # 页脚：居中页码
    p = sec.footer.paragraphs[0]
    fmt_para(p, before=0, after=0, line=None, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "第 ", size=FS_HF, color=MUTED)
    add_page_field(p, size=FS_HF, color=MUTED)
    add_run(p, " 页", size=FS_HF, color=MUTED)

    # 标题区
    p = doc.add_paragraph()
    fmt_para(p, before=mm2pt(6.0),
             after=mm2pt(SP_SUB_BEF) if sub else mm2pt(SP_SUB_AFT),
             line=LINE_TITLE, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, doc_title, size=FS_TITLE, color=GREEN, bold=True, font=Ctx.head)

    if sub:
        p = doc.add_paragraph()
        fmt_para(p, before=0, after=mm2pt(SP_SUB_AFT),
                 line=LINE_TITLE, align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(p, sub, size=FS_SUBTITLE, color=MUTED, font=Ctx.head)

    last = "head"

    def lead(mm_default):
        """表格/图片之后需要一个 spacer 才能和后面的文字拉开距离。"""
        if last in ("table", "note", "img"):
            gap(doc, 0.4)
            return 0.0
        return mm2pt(mm_default)

    li_no = 0
    pending_colw = None

    for kind, payload in blocks:
        if kind == "h2":                    # 一级标题
            first_h2 = last in ("head", None)
            p = doc.add_paragraph()
            before = 0.0 if first_h2 else mm2pt(SP_H1_BEF)
            fmt_para(p, before=before, after=mm2pt(SP_H1_AFT),
                     line=LINE_TITLE, keep_next=True)
            h2_rule(p, on=not first_h2)
            add_rich(p, payload, size=FS_H1, color=GREEN, font=Ctx.head, bold=True)
            last = "h2"
            li_no = 0
            continue

        if kind == "h3":                    # 二级标题
            p = doc.add_paragraph()
            before = 0.0 if last in ("head", None) else mm2pt(SP_H2_BEF)
            fmt_para(p, before=before, after=mm2pt(SP_H2_AFT),
                     line=LINE_TITLE, keep_next=True)
            add_rich(p, payload, size=FS_H2, color=GREEN, font=Ctx.head, bold=True)
            last = "h3"
            li_no = 0
            continue

        if kind == "h4":                    # 三级标题
            p = doc.add_paragraph()
            before = mm2pt(SP_H3_BEF) if last not in ("head", None) else 0.0
            fmt_para(p, before=before, after=mm2pt(SP_H3_AFT),
                     line=LINE_TITLE, keep_next=True)
            add_rich(p, payload, size=FS_H3, color=INK, font=Ctx.head, bold=True)
            last = "h4"
            li_no = 0
            continue

        if kind == "p":
            p = doc.add_paragraph()
            fmt_para(p, before=lead(0), after=mm2pt(SP_P_AFT), line=LINE_BODY,
                     first=Pt(FS_BODY * 2))
            add_rich(p, payload, size=FS_BODY, color=INK)
            last = "p"
            continue

        if kind == "quote":
            p = doc.add_paragraph()
            fmt_para(p, before=lead(2.0), after=mm2pt(SP_P_AFT + 1), line=LINE_BODY,
                     first=Pt(FS_BODY * 2), left=Cm(0.6))
            add_rich(p, payload, size=FS_BODY, color=MUTED)
            last = "quote"
            continue

        if kind == "li":
            li_no += 1
            p = doc.add_paragraph()
            fmt_para(p, before=lead(0) if li_no == 1 else 0.0,
                     after=mm2pt(2.0), line=LINE_BODY,
                     left=Cm(0.78), first=Cm(-0.78))
            add_run(p, "%d. " % li_no, size=FS_BODY, color=INK)
            add_rich(p, payload, size=FS_BODY, color=INK)
            last = "li"
            continue

        if kind == "table":
            headers, rows = payload
            if pending_colw and len(pending_colw) == len(headers):
                tot = sum(pending_colw)
                widths = [cw * w / tot for w in pending_colw]
            else:
                widths = None
            pending_colw = None
            gap(doc, SP_TBL_BEF if last not in ("table",) else 4.0)
            data_table(doc, headers, rows, cw, widths)
            gap(doc, SP_TBL_AFT)
            last = "table"
            continue

        if kind == "note":
            if not payload:
                continue
            gap(doc, SP_TBL_BEF)
            note_block(doc, payload, cw)
            gap(doc, SP_TBL_AFT)
            last = "note"
            continue

        if kind == "img":
            caption, path = payload
            figure(doc, path, caption, cw)
            last = "img"
            continue

        if kind == "divider":
            explicit_divider(doc)
            last = "divider"
            continue

        if kind == "caption":
            p = doc.add_paragraph()
            fmt_para(p, before=lead(0), after=mm2pt(2.5), line=LINE_CAP,
                     align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
            add_run(p, payload, size=FS_CAP, color=MUTED)
            last = "caption"
            continue

        if kind == "colw":
            nums = [float(x) for x in re.split(r"[\s,]+", payload) if x.strip()]
            pending_colw = nums or None
            continue

        if kind == "subtitle":
            continue

        if kind == "pagebreak":
            doc.add_page_break()
            last = None
            continue

        # 未知块按正文
        p = doc.add_paragraph()
        fmt_para(p, before=lead(0), after=mm2pt(SP_P_AFT), line=LINE_BODY,
                 first=Pt(FS_BODY * 2))
        add_rich(p, payload, size=FS_BODY, color=INK)
        last = "p"

    # 去掉末尾空段
    body = doc.element.body
    for _ in range(6):
        kids = [k for k in body.iterchildren() if k.tag in (qn("w:p"), qn("w:tbl"))]
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
    ap = argparse.ArgumentParser(description="课件制作笔记 V1.0 版式排版")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--header", default="")
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default=None)
    ap.add_argument("--mirror", action="store_true", help="双面装订：内侧22/外侧18，奇偶页镜像")
    ap.add_argument("--font-head", default=None)
    ap.add_argument("--font-body", default=None)
    a = ap.parse_args()
    md = open(a.input, encoding="utf-8").read()
    build(md, a.output, a.header, a.title, a.subtitle, a.mirror,
          a.font_head, a.font_body)
    print("已生成:", a.output)
    print("字族: 标题 %s / 正文 %s | 版心 %.1fcm%s"
          % (Ctx.head, Ctx.body, content_width(a.mirror),
             "（双面镜像）" if a.mirror else ""))


if __name__ == "__main__":
    main()
