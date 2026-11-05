#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐字稿「课件对照版」排版引擎
============================

把课堂逐字稿排成「一页课件 = 一段对照」的 Word 文档，**不排页码**，
页序由截图本身承担。

两种版式，用 `--layout` 选，**每次排版前必须问用户要哪一种**：

    side   左右：左列截图、右列稿子，紧凑，页数少（默认）
    stack  上下：截图独占整行放大，稿子在下满宽，图看得清，页数略多

用法：
    python3 zjg_typeset.py --input draft.md --output 19秦兵马俑-第二课时-逐字稿.docx \
        --header "19 秦兵马俑 · 第二课时 逐字稿" \
        --images assets/ppt [--layout side|stack] [--img-width 12]

逐字稿不使用强调色，靠宋体／楷体与灰度区分师／生／提示。

输入为「规范 Markdown」子集，映射规则见 references/zjg-spec.md。
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.shared import Cm

from jxsj_typeset import (
    ACCENTS, FONT_HEI, FONT_SONG, FS_BODY, TABLE_W_CM,
    _el, _set_cell_borders, _set_fonts, _set_ppr, build_styles,
    normalize_xml, setup_section,
)

# ───────────────────────────── 版式常量 ─────────────────────────────
# 改版式只改这一段。

FONT_KAI = "楷体"

FS_PAGE = 10.5          # 表头「第 N 页 · 环节名」——五号宋体
FS_TIME = 9.0           # 时间区间——小五宋体
FS_Z = 10.5             # 稿子正文——五号
FS_SUB = 9.0            # 副标题

LINE_Z = 1.38           # 块内行距

COL_IMG_CM = 6.4        # 图列宽（仅左右排列用到）
COL_TXT_CM = 8.0        # 文字列宽（后两列合并）
GRID_CM = [COL_IMG_CM, 4.0, COL_TXT_CM - 4.0]   # 合计 14.4cm，表头行的合并依据

LAYOUTS = ("side", "stack")
IMG_W_CM = 5.4          # 左右排列的图片宽度，16:9 → 高 3.04cm
IMG_W_STACK_CM = 11.0   # 上下排列的图片宽度，16:9 → 高 6.19cm；12cm 会多排一页


C_OP = "595959"         # 〔操作〕深灰
C_GUESS = "909090"      # 〔学生可能说〕浅灰

PAGE_RE = re.compile(r"^第\s*(\d+)\s*页\s*[·・.、:：]?\s*(.*)$")
TIME_RE = re.compile(
    r"\s*[｜|]\s*(\d{1,2}:\d{2}\s*[—\-–~至]\s*\d{1,2}:\d{2})\s*$")
IMG_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


# ───────────────────────────── 行内格式 ─────────────────────────────

def add_run(p, text, font=FONT_SONG, size=FS_Z, bold=False, color="000000"):
    r = p.add_run(text)
    _set_fonts(r._r.get_or_add_rPr(), font, size=size, bold=bold, color=color)
    return r


def add_rich(p, text, font=FONT_SONG, size=FS_Z, color="000000", bold=False):
    """支持 **加粗** 行内标记。"""
    pos = 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            add_run(p, text[pos:m.start()], font, size, bold, color)
        add_run(p, m.group(1), font, size, True, color)
        pos = m.end()
    if pos < len(text):
        add_run(p, text[pos:], font, size, bold, color)


def style_of(line):
    """按行首标记判定这一行是操作提示、师语、生语还是预判。"""
    s = line.lstrip()
    if s.startswith("〔操作〕") or s.startswith("【操作】"):
        return "op"
    if s.startswith("〔学生可能说〕") or s.startswith("【学生可能说】"):
        return "guess"
    if s.startswith("〔") or s.startswith("【"):
        return "note"
    if s.startswith("生（齐）") or s.startswith("生(齐)"):
        return "stu_all"
    if s.startswith("生："):
        return "stu"
    if s.startswith("师："):
        return "tea"
    return "body"


# ───────────────────────────── 段落参数 ─────────────────────────────

def _para(p, *, before=0, after=0, line=LINE_Z, first_chars=0,
          align="left", keep_next=False):
    _set_ppr(p._p, before=before, after=after, line=line,
             first_line_chars=first_chars, align=align,
             keep_next=keep_next, widow=True)


# ───────────────────────────── 单块的行 ─────────────────────────────

def _block_borders(table):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    b = _el("tblBorders")
    for edge in ("top", "left", "bottom", "right"):
        b.append(_el(edge, val="single", sz="4", space="0", color="808080"))
    # 整表连续，块与块之间的分隔线交给 insideH；表头行自己那条 0.75pt 黑线会盖过它
    b.append(_el("insideH", val="single", sz="4", space="0", color="808080"))
    b.append(_el("insideV", val="none", sz="0", space="0", color="auto"))
    tblPr.append(b)


def _set_cell_w(cell, w):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcW")):
        tcPr.remove(old)
    tcPr.append(_el("tcW", w=w, type="dxa"))


def new_block_table(doc):
    """建立**整份文档共用的一个表**：每块（一页课件）追加两行。

    整表结构：行序列为「表头行、主体行、表头行、主体行……」，
    块与块之间靠 insideH 分隔线相连，不再是一块一个表格——
    分成多个表时块间会留出空隙和两条并排的线，看着像断掉了。
    """
    table = doc.add_table(rows=0, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _block_borders(table)

    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    tblPr.append(_el("tblW", w=int(round(TABLE_W_CM * 567)), type="dxa"))
    for old in tblPr.findall(qn("w:tblLayout")):
        tblPr.remove(old)
    tblPr.append(_el("tblLayout", type="fixed"))
    for old in tblPr.findall(qn("w:tblInd")):
        tblPr.remove(old)
    tblPr.append(_el("tblInd", w=0, type="dxa"))
    for old in tblPr.findall(qn("w:jc")):
        tblPr.remove(old)
    tblPr.append(_el("jc", val="center"))
    mar = _el("tblCellMar")
    for edge in ("top", "left", "bottom", "right"):
        mar.append(_el(edge, w="113", type="dxa"))   # 0.2cm
    tblPr.append(mar)

    widths = [int(round(w * 567)) for w in GRID_CM]
    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for c, w in zip(grid.findall(qn("w:gridCol")), widths):
            c.set(qn("w:w"), str(w))
    return table


def _fill_image(cell, img_path, width_cm, align="left"):
    cell.text = ""
    p = cell.paragraphs[0]
    _para(p, line=1.0, align=align)
    if img_path and os.path.exists(img_path):
        p.add_run().add_picture(img_path, width=Cm(width_cm))
    else:
        add_run(p, "（缺图：%s）" % (os.path.basename(img_path) if img_path else "未提供"),
                FONT_SONG, 8.0, False, "A0A0A0")


def _fill_body(cell, lines):
    cell.text = ""
    first = True
    for raw in lines:
        txt = raw.strip()
        if not txt:
            continue
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        _para(p, line=LINE_Z, align="left")
        kind = style_of(txt)
        if kind == "op":
            add_rich(p, txt, FONT_KAI, FS_Z, C_OP, True)
        elif kind == "guess":
            add_rich(p, txt, FONT_KAI, FS_Z, C_GUESS, False)
        elif kind == "note":
            add_rich(p, txt, FONT_KAI, FS_Z, C_OP, False)
        elif kind == "stu_all":
            add_rich(p, txt, FONT_SONG, FS_Z, "000000", True)
        else:
            add_rich(p, txt, FONT_SONG, FS_Z, "000000", False)
    if not cell.paragraphs[0].text:
        add_run(cell.paragraphs[0], "", FONT_SONG, FS_Z)


def add_block_rows(table, page_no, title, time_text, lines, img_path,
                   layout="side", img_w=None):
    """往整表里追加一块：表头行（标题＋时间）＋ 图与稿子。

    列网格 6.4 / 4.0 / 4.0 两种版式通用，表头行总是「前两列合并放标题，
    第三列放时间右对齐」，时间才能贴到右边界。

    版式 side（左右）：主体行 = 第一列截图 + 后两列合并放稿子，纵向紧凑。
    版式 stack（上下）：图行三列合并、截图放大居中；文行三列合并、稿子满宽。
    """
    widths = [int(round(w * 567)) for w in GRID_CM]

    # ── 表头行 ──
    r0 = table.add_row()
    cs = r0.cells
    c_time = cs[2]                      # 先取引用，merge 会改变 cells 的展开结果
    head = cs[0].merge(cs[1])
    _set_cell_w(head, widths[0] + widths[1])
    _set_cell_w(c_time, widths[2])

    head.text = ""
    hp = head.paragraphs[0]
    _para(hp, line=1.0, align="left", keep_next=True)   # 表头不得与主体行分页
    label = "第 %d 页" % page_no
    if title:
        label += " · " + title
    add_run(hp, label, FONT_HEI, FS_PAGE, False)

    c_time.text = ""
    tp = c_time.paragraphs[0]
    _para(tp, line=1.0, align="right", keep_next=True)
    if time_text:
        add_run(tp, time_text, FONT_SONG, FS_TIME, False, "595959")
    for cell in (head, c_time):
        # 只画表头下那条粗线；上/左/右由表格外框继承，写 none 会把框线挖断
        _set_cell_borders(cell, bottom=("single", 6, "000000"))
    # 注意：整表只有一个表，不能设 tblHeader——它只对表格开头几行生效，
    # 会把第一块的表头重复到之后每一页。
    r0._tr.get_or_add_trPr().append(_el("cantSplit"))

    # ── 上下排列：图行 + 文行，各自三列合并 ──
    if layout == "stack":
        ri = table.add_row()
        ci = ri.cells[0].merge(ri.cells[2])
        _set_cell_w(ci, sum(widths))
        _fill_image(ci, img_path, img_w or IMG_W_STACK_CM, "center")
        ci.vertical_alignment = 0
        ri._tr.get_or_add_trPr().append(_el("cantSplit"))   # 图片本就不能拆

        rt = table.add_row()
        ct = rt.cells[0].merge(rt.cells[2])
        _set_cell_w(ct, sum(widths))
        ct.vertical_alignment = 0
        _fill_body(ct, lines)
        # 文行不设 cantSplit：满宽后行数少，允许跨页续排才不会留半页空白
        return table

    # ── 左右排列：主体行 = 图列 + 合并的文字列 ──
    r1 = table.add_row()
    cs = r1.cells
    c_img, c_tail = cs[0], cs[2]
    body = cs[1].merge(c_tail)
    _set_cell_w(c_img, widths[0])
    _set_cell_w(body, widths[1] + widths[2])

    for c in (c_img, body):
        c.vertical_alignment = 0      # 顶对齐
    # 主体行不设 cantSplit：允许跨页续排，否则每块都要独占一页、下半页全空

    _fill_image(c_img, img_path, img_w or IMG_W_CM, "left")
    # 图列右侧那条浅灰竖线单独加；其余边留给外框与 insideV 继承
    _set_cell_borders(c_img, right=("single", 4, "C8C8C8"))
    _fill_body(body, lines)
    return table


# ───────────────────────────── Markdown 解析 ─────────────────────────────

def parse(md):
    """切成 [('title'|'sub'|'h2'|'h3'|'para', text) | ('block', dict)]。"""
    blocks = []
    cur = None
    for raw in md.split("\n"):
        line = raw.rstrip()
        s = line.strip()
        if not s or s in ("---", "***"):
            continue
        if s.startswith("# "):
            blocks.append(("title", s[2:].strip()))
            cur = None
            continue
        if s.startswith("## "):
            head = s[3:].strip()
            time_text, body = "", head
            m = TIME_RE.search(head)
            if m:
                time_text = m.group(1).replace(" ", "")
                body = head[:m.start()].strip()
            mp = PAGE_RE.match(body)
            if mp:
                cur = {"page": int(mp.group(1)), "title": mp.group(2).strip(),
                       "time": time_text, "lines": [], "img": None}
                blocks.append(("block", cur))
                continue
            cur = None
            blocks.append(("h2", body))
            continue
        if s.startswith("### "):
            cur = None
            blocks.append(("h3", s[4:].strip()))
            continue
        mi = IMG_RE.match(s)
        if mi:
            if cur is not None and cur["img"] is None:
                cur["img"] = mi.group(1).strip()
            else:
                blocks.append(("para", s))
            continue
        if cur is not None:
            cur["lines"].append(s)
        else:
            blocks.append(("para", s))
    return blocks


# ───────────────────────────── 主渲染 ─────────────────────────────

def render(md, out_path, header, images_dir=None, accent="navy",
           layout="side", img_w=None):
    accent = ACCENTS.get(accent, accent.lstrip("#"))
    doc = Document()
    build_styles(doc, accent)
    setup_section(doc, header, page_number=False)     # 逐字稿不排页码

    blocks = parse(md)
    title_done = False
    sub_done = False
    cur_table = None      # 整份文档共用一个表，遇到段落才开新表

    for kind, payload in blocks:
        if kind != "block":
            cur_table = None      # 段落插进表格会把它劈开，之后重新建表

        if kind == "title":
            p = doc.add_paragraph(style="文档标题")
            add_run(p, payload, FONT_HEI, 15.0, True)
            title_done = True
            continue

        if kind == "para" and title_done and not sub_done:
            # 标题后的第一段：副标题（课题·年级·课时·时长），居中五号
            p = doc.add_paragraph()
            _para(p, before=0, after=10, line=1.0, align="center")
            add_run(p, payload, FONT_SONG, FS_SUB, False, "404040")
            sub_done = True
            continue

        if kind == "h2":
            p = doc.add_paragraph()
            _para(p, before=12, after=4, line=1.0, align="left", keep_next=True)
            add_run(p, payload, FONT_HEI, FS_BODY, False)
            sub_done = True
            continue

        if kind == "h3":
            p = doc.add_paragraph()
            center = "课时" in payload
            _para(p, before=14 if center else 10, after=6,
                  line=1.05, align="center" if center else "left",
                  keep_next=True)
            add_run(p, payload, FONT_HEI, 13.0 if center else FS_BODY, center)
            sub_done = True
            continue

        if kind == "para":
            p = doc.add_paragraph()
            _para(p, before=0, after=0, line=1.5, first_chars=2, align="both")
            add_rich(p, payload, FONT_SONG, FS_Z)
            sub_done = True
            continue

        if kind == "block":
            img = payload["img"]
            if img is None and images_dir:
                for ext in ("jpg", "jpeg", "png"):
                    cand = os.path.join(images_dir, "p%02d.%s"
                                        % (payload["page"], ext))
                    if os.path.exists(cand):
                        img = cand
                        break
            elif img and not os.path.isabs(img) and images_dir:
                img = os.path.join(images_dir, os.path.basename(img))
            if cur_table is None:
                cur_table = new_block_table(doc)
            add_block_rows(cur_table, payload["page"], payload["title"],
                           payload["time"], payload["lines"], img,
                           layout=layout, img_w=img_w)

    # 末尾空段落清理
    body = doc.element.body
    last = body[-2] if len(body) > 1 else None
    if last is not None and last.tag == qn("w:p") and not "".join(
            t.text or "" for t in last.iter(qn("w:t"))).strip():
        body.remove(last)

    normalize_xml(doc)
    doc.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="逐字稿「课件对照版」排版引擎")
    ap.add_argument("--input", required=True, help="规范 Markdown 路径")
    ap.add_argument("--output", required=True, help="输出 docx 路径")
    ap.add_argument("--header", default="", help="页眉文字")
    ap.add_argument("--images", default=None,
                    help="课件截图目录（内含 p01.png、p02.png …）")
    ap.add_argument("--layout", default="side", choices=list(LAYOUTS),
                    help="版式：side=左右（默认，紧凑）／stack=上下（图放大）")
    ap.add_argument("--img-width", type=float, default=None,
                    help="截图宽度 cm，默认 side 5.4 / stack 11.0")
    ap.add_argument("--accent", default="navy",
                    help="已保留但无效果：逐字稿不使用强调色")
    a = ap.parse_args()

    md = open(a.input, encoding="utf-8").read()
    render(md, a.output, a.header, a.images, a.accent,
           layout=a.layout, img_w=a.img_width)
    print("已生成：%s（版式：%s）" % (a.output, a.layout))


if __name__ == "__main__":
    main()
