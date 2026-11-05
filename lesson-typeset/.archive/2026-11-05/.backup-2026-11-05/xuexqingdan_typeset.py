#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 学习清单「自用版」排版引擎（已固化进 lesson-typeset 技能）
#
# 设计口径（本类独立，不与教学设计/逐字稿共用页面网格或字号）：
#   - A4；页边距 2.2 / 2.4 / 2.8 / 2.5；版心宽 15.7cm；宋体；强调色 navy
#   - 正文/标题/表格统一五号字（10.5pt）；全文 1.5 倍行距
#   - 所有填字表：完整边框网格（外框四边 + 内部横竖线，浅灰 BFBFBF 细线）
#   - 表格内文字一律不加粗（表头、数据、田字格示范字、勾选框均正常粗细）
#   - 所有填字表统一表格级单元格内边距 0.3cm（Word 标准 tblCellMar，跨软件渲染一致）
#   - 单元格文字垂直居中（vAlign=center）
#   - 填空横线用下划线字符 "_"（不用段末下划线空格、不用制表位引导符——
#     LibreOffice 对这两种都不渲染，字符下划线在任何软件都稳定显示）
#   - 田字格练写：大字框 + 三条练写线；自评/互查用 □ 勾选项
#
# 用法：
#   python3 ~/.workbuddy/skills/lesson-typeset/scripts/xuexqingdan_typeset.py \
#       --header "17 长城" --lesson 1 \
#       --title "17 长城｜第一课时 学习清单" --subtitle "识字写字 · 梳理内容 · 图解长城" \
#       --output 17长城-第一课时-学习清单.docx
#   （第二课时把 --lesson 2、--title/--subtitle/--output 改掉即可）
#
# 内容每课不同：排新课文时，复制本文件、改写下面的 lesson1() / lesson2()
# 两个内容函数（只改小节标题、字词、勾选项，不要动通用构件与版式常量）。
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips
import argparse
import re

# ── 版式常量（对齐 lesson-typeset 自用版）──
PAGE_W, PAGE_H = 21.0, 29.7
M_TOP, M_BOTTOM, M_LEFT, M_RIGHT = 2.2, 2.4, 2.8, 2.5
CONTENT_W = PAGE_W - M_LEFT - M_RIGHT          # 15.7cm（21 − 2.8 − 2.5）
FONT = "宋体"
ACCENT = "2C3E50"
FS_TITLE, FS_SUB, FS_H, FS_BODY, FS_TBL = 16.0, 10.5, 10.5, 10.5, 10.5
LINE_BODY = 1.5
RULE_THICK, RULE_THIN = 12, 6
CELL_PAD = 0.3          # 所有填字表统一标准单元格内边距（cm）

def twp(cm):
    """厘米 → twips（正确换算）。"""
    return int(Cm(cm).twips)

# ── 底层工具 ──
def _el(tag, **a):
    if ":" not in tag:
        tag = "w:" + tag
    e = OxmlElement(tag)
    for k, v in a.items():
        e.set(qn("w:" + k), str(v))
    return e

def _set_cell_borders(cell, **edges):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:tcBorders")):
        tcPr.remove(old)
    if not edges:
        return
    bdr = _el("tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        spec = edges.get(edge)
        if spec is None:
            continue
        val, sz, color = spec
        bdr.append(_el(edge, val=val, sz=sz, space="0", color=color))
    tcPr.append(bdr)

def _set_tbl_borders(table, **edges):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(old)
    bdr = _el("tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        spec = edges.get(edge)
        if spec is None:
            continue
        val, sz, color = spec
        bdr.append(_el(edge, val=val, sz=sz, space="0", color=color))
    tblPr.append(bdr)

def _set_tbl_cell_margin(table, cm=CELL_PAD):
    """表格级单元格边距（Word 标准语义，跨软件渲染更一致）。所有表统一调用。"""
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblCellMar")):
        tblPr.remove(old)
    mar = _el("tblCellMar")
    v = twp(cm)
    for edge in ("top", "left", "bottom", "right"):
        mar.append(_el(edge, w=str(v), type="dxa"))
    tblPr.append(mar)

def _set_table_widths(table, widths_cm):
    tblPr = table._tbl.tblPr
    for old in tblPr.findall(qn("w:tblW")):
        tblPr.remove(old)
    tblPr.append(_el("tblW", w=twp(sum(widths_cm)), type="dxa"))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row in table.rows:
        for i, c in enumerate(row.cells):
            c.width = Cm(widths_cm[i])
            tcPr = c._tc.get_or_add_tcPr()
            for old in tcPr.findall(qn("w:tcW")):
                tcPr.remove(old)
            tcPr.append(_el("tcW", w=twp(widths_cm[i]), type="dxa"))

def _set_row_height(row, cm, rule="atLeast"):
    trPr = row._tr.get_or_add_trPr()
    for old in trPr.findall(qn("w:trHeight")):
        trPr.remove(old)
    trPr.append(_el("trHeight", val=twp(cm), hRule=rule))

def _set_vcenter(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn("w:vAlign")):
        tcPr.remove(old)
    tcPr.append(_el("vAlign", val="center"))

def clear_cell(cell):
    tc = cell._tc
    for p in tc.findall(qn("w:p")):
        tc.remove(p)
    tc.append(OxmlElement("w:p"))
    return cell.paragraphs[0]

_ORDER = {
    "tblPr": ["tblStyle","tblpPr","tblOverlap","bidiVisual","tblStyleRowBandSize",
              "tblStyleColBandSize","tblW","jc","tblCellSpacing","tblInd",
              "tblBorders","shd","tblLayout","tblCellMar","tblLook","tblCaption",
              "tblDescription"],
    "tcPr": ["cnfStyle","tcW","gridSpan","hMerge","vMerge","tcBorders","shd",
             "noWrap","tcMar","textDirection","tcFitText","vAlign","hideMark"],
    "pPr": ["pStyle","keepNext","keepLines","pageBreakBefore","framePr",
            "widowControl","numPr","suppressLineNumbers","pBdr","shd","tabs",
            "suppressAutoHyphens","kinsoku","wordWrap","overflowPunct",
            "topLinePunct","autoSpaceDE","autoSpaceDN","bidi","adjustRightInd",
            "snapToGrid","spacing","ind","contextualSpacing","mirrorIndents",
            "suppressOverlap","jc","textDirection","textboxTightWrap",
            "outlineLvl","divId","cnfStyle","rPr","sectPr"],
    "rPr": ["rStyle","rFonts","b","bCs","i","iCs","caps","smallCaps","strike",
            "dstrike","outline","shadow","emboss","imprint","noProof","snapToGrid",
            "vanish","webHidden","color","spacing","w","kern","position","sz",
            "szCs","highlight","u","effect","bdr","shd","fitText","vertAlign",
            "rtl","cs","em","lang","eastAsianLayout","specVanish","oMath"],
}
def normalize_xml(doc):
    root = doc.element
    for tag, order in _ORDER.items():
        index = {qn("w:" + n): i for i, n in enumerate(order)}
        for node in root.iter(qn("w:" + tag)):
            kids = list(node)
            kids.sort(key=lambda e: index.get(e.tag, len(order)))
            for k in kids:
                node.append(k)

# ── 段落 / 字符 ──
def _rpr(run, size=None, bold=None, color=None, u=None):
    rPr = run._element.get_or_add_rPr()
    if size is not None:
        for old in rPr.findall(qn("w:sz")) + rPr.findall(qn("w:szCs")):
            rPr.remove(old)
        rPr.append(_el("sz", val=int(round(size*2))))
        rPr.append(_el("szCs", val=int(round(size*2))))
    if bold is not None:
        for old in rPr.findall(qn("w:b")) + rPr.findall(qn("w:bCs")):
            rPr.remove(old)
        rPr.append(_el("b", val="1" if bold else "0"))
        rPr.append(_el("bCs", val="1" if bold else "0"))
    if color:
        for old in rPr.findall(qn("w:color")):
            rPr.remove(old)
        rPr.append(_el("color", val=color))
    if u:
        for old in rPr.findall(qn("w:u")):
            rPr.remove(old)
        rPr.append(_el("u", val=u))
    for old in rPr.findall(qn("w:rFonts")):
        rPr.remove(old)
    rPr.insert(0, _el("rFonts", ascii=FONT, hAnsi=FONT, eastAsia=FONT, cs=FONT))

def _ppr(p, before=0, after=0, line=LINE_BODY, first=False, align=None, bdr_bottom=False):
    pPr = p._p.get_or_add_pPr()
    for old in pPr.findall(qn("w:spacing")):
        pPr.remove(old)
    pPr.append(_el("spacing", before=int(round(before*20)), after=int(round(after*20)),
                   line=int(round(240*line)), lineRule="auto"))
    for old in pPr.findall(qn("w:ind")):
        pPr.remove(old)
    if first:
        pPr.append(_el("ind", firstLine=int(round(FS_BODY*20*2))))
    if align:
        for old in pPr.findall(qn("w:jc")):
            pPr.remove(old)
        pPr.append(_el("jc", val=align))
    if bdr_bottom:
        pBdr = _el("pBdr")
        pBdr.append(_el("bottom", val="single", sz="6", space="1", color="000000"))
        pPr.append(pBdr)

def P(doc, text="", *, size=FS_BODY, bold=False, color=None, before=0, after=0,
      line=LINE_BODY, first=False, align=None):
    p = doc.add_paragraph()
    _ppr(p, before=before, after=after, line=line, first=first, align=align)
    if text:
        r = p.add_run(text)
        _rpr(r, size=size, bold=bold, color=color)
    return p

def R(p, text, *, size=FS_BODY, bold=False, color=None, u=None):
    r = p.add_run(text)
    _rpr(r, size=size, bold=bold, color=color, u=u)
    return r

def blank(p, n=20, size=FS_BODY):
    r = p.add_run("_" * n)
    _rpr(r, size=size)

# ── 文档骨架 ──
def setup_page(doc, header):
    sec = doc.sections[0]
    sec.page_width = Cm(PAGE_W); sec.page_height = Cm(PAGE_H)
    sec.top_margin = Cm(M_TOP); sec.bottom_margin = Cm(M_BOTTOM)
    sec.left_margin = Cm(M_LEFT); sec.right_margin = Cm(M_RIGHT)
    sec.header_distance = Cm(1.5); sec.footer_distance = Cm(1.5)
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    hp = sec.header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    R(hp, header, size=9, color="808080")
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 页码域必须拆成 begin / instrText / separate / 结果 / end 五段，
    # 塞进同一个 run 时 LibreOffice 与部分预览器会把 "PAGE" 当正文直接显示。
    _add_page_field(fp)

def add_title(doc, title, subtitle):
    P(doc, title, size=FS_TITLE, bold=True, align="center", before=0, after=2, line=1.2)
    P(doc, subtitle, size=FS_SUB, color=ACCENT, align="center", before=0, after=6, line=1.2)

def add_info(doc):
    p = doc.add_paragraph()
    _ppr(p, before=0, after=3, line=1.5)
    R(p, "班级：", size=FS_BODY, bold=True); blank(p, 12)
    R(p, "    姓名：", size=FS_BODY, bold=True); blank(p, 12)
    R(p, "    日期：", size=FS_BODY, bold=True); blank(p, 12)

def add_section(doc, title):
    P(doc, title, size=FS_H, bold=True, before=2, after=1, line=1.5)

def add_tip(doc, text):
    P(doc, text, size=FS_BODY, color="000000", before=0, after=0, line=1.5)

# 横线填字表（完整边框网格；表头不加粗；统一 0.3cm 单元格内边距；文字垂直居中）
def grid_table(doc, widths_cm, header, rows, pad=CELL_PAD, rh_d=0.7, rh_h=0.55, exact=False):
    ncol = len(widths_cm)
    nrow = (1 if header else 0) + len(rows)
    t = doc.add_table(nrow, ncol)
    _set_table_widths(t, widths_cm)
    _set_tbl_cell_margin(t, pad)
    # 全部边框：外框 + 内部横竖线统一细网格（浅灰，干净不抢眼）
    _set_tbl_borders(t,
                     top=("single", RULE_THIN, "BFBFBF"),
                     bottom=("single", RULE_THIN, "BFBFBF"),
                     left=("single", RULE_THIN, "BFBFBF"),
                     right=("single", RULE_THIN, "BFBFBF"),
                     insideH=("single", RULE_THIN, "BFBFBF"),
                     insideV=("single", RULE_THIN, "BFBFBF"))
    r = 0
    if header:
        for j, h in enumerate(header):
            c = t.rows[r].cells[j]
            pp = clear_cell(c); pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            R(pp, h, size=FS_TBL, bold=False)
            _set_vcenter(c)
        _set_row_height(t.rows[r], rh_h, "exact" if exact else "atLeast")
        r += 1
    for ri, row in enumerate(rows):
        for j in range(ncol):
            c = t.rows[r].cells[j]
            pp = clear_cell(c)
            if row[j]:
                R(pp, row[j], size=FS_TBL)
            _set_vcenter(c)
        _set_row_height(t.rows[r], rh_d, "exact" if exact else "atLeast")
        r += 1
    return t

# 我会写：大字框 + 每条 3 条练写线（示范字不加粗）
def char_practice(doc, chars):
    n = len(chars)
    w = 4.0
    widths = [w] * n
    t = doc.add_table(1 + 3, n)
    _set_table_widths(t, widths)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, ch in enumerate(chars):
        c = t.rows[0].cells[j]
        pp = clear_cell(c); pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        R(pp, ch, size=38, bold=False)
        _set_vcenter(c)
        _set_cell_borders(c, top=("single", RULE_THIN, "000000"),
                         left=("single", RULE_THIN, "000000"),
                         bottom=("single", RULE_THIN, "000000"),
                         right=("single", RULE_THIN, "000000"))
    _set_row_height(t.rows[0], 1.15)
    for ri in range(1, 4):
        for j in range(n):
            c = t.rows[ri].cells[j]
            clear_cell(c)
            _set_vcenter(c)
            _set_cell_borders(c, bottom=("single", RULE_THIN, "000000"))
        _set_row_height(t.rows[ri], 0.52)
    return t

# 勾选项（□ 不加粗）
def checkboxes(doc, items, cols=2):
    nrow = (len(items) + cols - 1) // cols
    t = doc.add_table(nrow, cols)
    _set_table_widths(t, [CONTENT_W/cols]*cols)
    _set_tbl_borders(t)
    idx = 0
    for ri in range(nrow):
        for j in range(cols):
            c = t.rows[ri].cells[j]
            pp = clear_cell(c)
            if idx < len(items):
                R(pp, "□ ", size=FS_BODY, bold=False)
                R(pp, items[idx], size=FS_BODY)
                idx += 1
            _set_vcenter(c)

def writeline(doc, label=None, before=2, after=2):
    p = doc.add_paragraph()
    _ppr(p, before=before, after=after, line=1.5)
    if label:
        R(p, label, size=FS_BODY)
    blank(p, 56)
    return p

# ── 内容区（每课不同：排新课文时改写下面的 lesson1/lesson2）──
def lesson1(doc, title, subtitle):
    add_title(doc, title, subtitle)
    add_info(doc)
    add_section(doc, "一、我会写")
    add_tip(doc, "观察字形，先认真练写，再检查容易写错的笔画。")
    char_practice(doc, ["旋", "隔", "慧"])
    p = P(doc, before=1, after=1, line=1.5)
    R(p, "我最需要注意的一个字是：", size=FS_BODY, bold=True); blank(p, 14)
    R(p, "    容易写错的地方：", size=FS_BODY, bold=True); blank(p, 16)
    add_section(doc, "二、梳理课文")
    add_tip(doc, "默读课文，用简短的词语概括四个自然段的主要内容。")
    grid_table(doc, [3.2, 12.2], None,
               [["第1自然段", ""], ["第2自然段", ""],
                ["第3自然段", ""], ["第4自然段", ""]])
    add_section(doc, "三、我来介绍长城")
    add_tip(doc, "默读第2自然段，结合教材插图，用短语记录构造的特点或作用。")
    grid_table(doc, [4.0, 11.4], ["长城构造", "特点或作用（用短语填写）"],
               [["城墙顶", ""], ["礌石孔", ""], ["瞭望口", ""], ["敌楼", ""]])
    add_section(doc, "四、我的课堂自评")
    checkboxes(doc, [
        "我能指认至少4处长城构造。", "我能说清3处构造的作用。",
        "我能按照一定顺序向同桌介绍。", "我愿意根据建议改进表达。"], cols=2)

def lesson2(doc, title, subtitle):
    add_title(doc, title, subtitle)
    add_info(doc)
    add_section(doc, "一、探究“伟大的奇迹”")
    add_tip(doc, "读课文，先圈画关键词句，再用短语记录不同方面的依据。")
    grid_table(doc, [3.0, 6.2, 6.2],
               ["角度", "课文依据（词语或句子）", "我从中看出……"],
               [["第1处", "", ""], ["第2处", "", ""]])
    writeline(doc, "我认为长城是“伟大的奇迹”，因为：")
    add_section(doc, "二、发现修筑的不容易")
    add_tip(doc, "默读第3自然段，用关键词梳理条石、城砖的取得或运输方式。")
    grid_table(doc, [4.0, 11.4], ["材料", "怎样取得或运送？"],
               [["条石", ""], ["城砖", ""]])
    add_section(doc, "三、我的世界文化遗产资料卡")
    add_tip(doc, "选择一项中国的世界文化遗产，提取两条简明信息，并记录资料出处。")
    grid_table(doc, [3.6, 11.8], None, [
        ["名称", ""], ["申遗成功时间", ""], ["基本情况①", ""],
        ["基本情况②", ""], ["资料出处", ""]], pad=CELL_PAD, rh_d=0.9, exact=True)
    add_tip(doc, "提示：申遗时间无法查证时，可填写“待核实”；资料出处要便于再次查找。")
    checkboxes(doc, ["信息能核对", "用自己的话整理", "资料出处清楚"], cols=3)
    writeline(doc, "我根据建议修改了：")
# ── Markdown 驱动模式（推荐：与教学设计、逐字稿同一套输入口径）──
# 源稿语法见 references/xuexqingdan-spec.md §3。
MD_TABLE_SEP = re.compile(r"^\|?[\s:|-]+\|?$")
MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
MD_LABEL_BLANK = re.compile(r"^([^：:_]{1,18})[：:]\s*_+\s*$")   # 「标签：____」
MD_BARE_BLANK = re.compile(r"^_+$")                             # 单独一行 ____

def _rich(p, text, size=FS_BODY):
    """段落内支持 **加粗**。"""
    pos = 0
    for m in MD_BOLD.finditer(text):
        if m.start() > pos:
            R(p, text[pos:m.start()], size=size)
        R(p, m.group(1), size=size, bold=True)
        pos = m.end()
    if pos < len(text):
        R(p, text[pos:], size=size)
    return p

def add_tip_rich(doc, text):
    return _rich(P(doc, "", before=0, after=0, line=LINE_BODY), text)

def _md_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]

def _table_widths(header, rows):
    """列宽：两列时左窄右宽（填字表惯例），三列以上首列 3.6cm、其余均分。"""
    ncol = len(header) if header else len(rows[0])
    if ncol == 2:
        return [4.2, CONTENT_W - 4.2]
    first = 3.6
    rest = (CONTENT_W - first) / (ncol - 1)
    return [first] + [rest] * (ncol - 1)

def render_md(doc, md_path, header, title=None, subtitle=""):
    """把学习清单 Markdown 排成练习纸。"""
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    plain = [l for l in lines if l.strip()]
    doc_title = title
    for l in plain:                       # 用第一个 ## 兜底当标题
        if l.startswith("## "):
            doc_title = doc_title or (header + "｜" + l[3:].strip())
            break
    add_title(doc, doc_title or header, subtitle)
    add_info(doc)

    i, n = 0, len(lines)
    list_no = 0
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue

        if s.startswith("# "):            # 课文名，只作页眉/标题素材，不进正文
            i += 1
            continue

        if s.startswith("## "):           # 课时标题已在文档标题用过，正文不再重复
            list_no = 0
            i += 1
            continue

        if s.startswith("### "):
            add_section(doc, s[4:].strip())
            list_no = 0
            i += 1
            continue

        if s == ":::pagebreak":
            doc.add_page_break()
            i += 1
            continue

        if s.startswith(":::write"):       # :::write 演 练 撤 —— 田字格
            chars = s[len(":::write"):].split()
            char_practice(doc, chars)
            i += 1
            continue

        if s.startswith(":::check"):       # :::check A | B | C —— □ 勾选项
            items = [x.strip() for x in s[len(":::check"):].split("|") if x.strip()]
            checkboxes(doc, items, cols=3 if len(items) >= 3 else 2)
            i += 1
            continue

        if s.startswith("|"):              # 表格块
            block = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows = [_md_cells(b) for b in block if not MD_TABLE_SEP.match(b)]
            has_header = len(block) >= 2 and bool(MD_TABLE_SEP.match(block[1]))
            header_row = rows[0] if has_header else None
            body = rows[1:] if has_header else rows
            grid_table(doc, _table_widths(header_row, body), header_row, body,
                       rh_d=0.95)
            list_no = 0
            continue

        if s.startswith("- "):             # 列表 → 阿拉伯数字编号
            list_no += 1
            add_tip(doc, "%d. %s" % (list_no, s[2:].strip()))
            i += 1
            continue

        if s.startswith("**") and s.endswith("**") and len(s) > 4 and s.count("**") == 2:
            P(doc, s[2:-2].strip(), bold=True, before=2, after=0)
            i += 1
            continue

        if "姓名" in s and "_" in s:       # 信息行
            i += 1
            continue

        if MD_LABEL_BLANK.match(s):        # 连续「标签：____」→ 一张填字表
            labels = []
            while i < n:
                cur = lines[i].strip()
                m = MD_LABEL_BLANK.match(cur)
                if m:
                    labels.append(m.group(1).strip())
                    i += 1
                elif MD_BARE_BLANK.match(cur):
                    i += 1                 # 续写的空横线，单元格本身已提供空间
                elif not cur:
                    i += 1                 # 标签之间允许空行
                else:
                    break
            if len(labels) >= 2:
                grid_table(doc, [4.2, CONTENT_W - 4.2], None,
                           [[lab, ""] for lab in labels], rh_d=1.15)
            else:
                add_tip(doc, s)
            continue

        add_tip_rich(doc, s)
        i += 1


def _add_page_field(fp):
    """页脚页码域。属性名必须是 w:fldCharType——写成 w:val 时它就不是域，
    LibreOffice / 预览器会把 "PAGE" 当正文直接显示（2026-11-05 修）。"""
    run = fp.add_run()
    _rpr(run, size=9, color="808080")
    run._r.append(_el("fldChar", fldCharType="begin"))
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    run._r.append(instr)
    run._r.append(_el("fldChar", fldCharType="end"))



def main():
    ap = argparse.ArgumentParser(description="学习清单自用版排版引擎（支持 Markdown 输入）")
    ap.add_argument("--input", help="学习清单 Markdown 源稿；给了它就走 md 模式")
    ap.add_argument("--header", required=True, help="页眉文字，如「17 长城」")
    ap.add_argument("--lesson", choices=["1", "2"], help="md 模式下可省略；不给 --input 时必填")
    ap.add_argument("--title", help="文档标题；md 模式下不给则用「页眉｜第一个 ##」")
    ap.add_argument("--subtitle", default="", help="副标题")
    ap.add_argument("--output", required=True, help="输出 docx 路径")
    args = ap.parse_args()

    doc = Document()
    setup_page(doc, args.header)
    if args.input:
        render_md(doc, args.input, args.header, args.title, args.subtitle)
    elif args.lesson == "1":
        lesson1(doc, args.title or args.header, args.subtitle)
    else:
        lesson2(doc, args.title or args.header, args.subtitle)
    normalize_xml(doc)
    doc.save(args.output)
    print("OK", args.output)

if __name__ == "__main__":
    main()
