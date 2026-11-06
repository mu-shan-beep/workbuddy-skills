#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3.0｜单一主表格结构 —— 正式引擎
================================================================
版式常量以 references/unified-spec.md 第 1 章为唯一权威。
2026-11-06 用户确认《牛和鹅》预览效果（18 页）后固化，版式常量与预览完全一致；
改任何一项版式参数前，仍须遵守「先出效果 → 用户确认 → 再固化」。

相对上一版 V2.0-T 预览的优化：
1. 四列活动 4:6:5:5 → **4:7:5:4**（§11.1）；
2. 通栏正文 10.5pt/1.3 → **11pt/1.45/首行缩进2字/段后3pt**（§12.2、§18.1），
   编号段落 11pt/1.4（§12.3），活动单元格仍 10.5pt/1.3/段后2pt（§18.2）；
3. **按行类型设边框**（§7.1）：标题行与通栏长文本行无边框、环节分区行 0.75pt、
   信息/活动/辅助对照/图片行 0.5pt；表格级不画线，全部由单元格级 tcBorders 控制；
4. 四列正文（含活动名称）**一律顶部对齐**（§9）；字段标签/短内容垂直居中（§9、§13.3）；
5. 章节标题段前 6mm、段后 3mm（§12.1）；行高按内容自适应（§10.2）；
6. 图片行四周 4mm 内边距（§8.2、§17.2）；板书图 11cm
   （实测 12cm 会把板书图整行推到单独一页，末页留白 259mm）。

单表原则、20 格网格、五张对照块并格（用户 2026-11-05 截图反馈）保持不变。
"""
import argparse
import os
import re
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)          # 复用同目录的 xuexqingdan_typeset 底层构件
import xuexqingdan_typeset as X

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt
from docx.table import _Cell

# ─────────────────── 版式常量（V3.0，只认本文件） ───────────────────
PAGE_W, PAGE_H = 21.0, 29.7
M_TOP, M_BOTTOM, M_LEFT, M_RIGHT = 2.8, 2.0, 2.3, 2.3
HDR_DIST, FTR_DIST = 0.8, 1.0
CONTENT_W = 16.4

NGRID = 20
TOTAL_TW = 9300            # 16.4cm ≈ 9300 twips
GW = TOTAL_TW // NGRID     # 465 twips / 格（8.2mm）

TITLE = "222222"
GREEN = "315A4B"
INK = "2B302C"
MUTED = "596960"
BAND = "EDF3EE"            # 口径覆盖③：表头/强调/分区/活动名称统一一档
LINE = "9BA9A0"            # 口径覆盖③：内外框同色
WHITE = "FFFFFF"
FOOT = "666666"

# §5.1 字族字号层级
FS_TITLE, FS_H1, FS_H2, FS_H3 = 18.0, 13.0, 11.5, 10.5
FS_TH, FS_CELL = 10.5, 10.5       # 表头 / 活动单元格·辅助表·字段内容
FS_BODY = 11.0                    # 通栏普通正文
FS_CAP, FS_HF = 9.5, 9.0

# §12 / §18 行距与段距
LINE_BODY, LINE_ITEM, LINE_CELL = 1.45, 1.4, 1.3
AFTER_BODY, AFTER_CELL = 3.0, 2.0
MM2PT = 72 / 25.4
BAND_BEFORE, BAND_AFTER = 6 * MM2PT, 3 * MM2PT        # 6mm / 3mm
SUB_BEFORE, SUB_AFTER = 3 * MM2PT, 3 * MM2PT
FIRST_INDENT = Pt(2 * FS_BODY)                         # 首行缩进 2 个汉字
HANG = Mm(6)

# §10.1 最小行高（mm）；None = 按内容自适应
H_TITLE, H_BAND, H_BAND2, H_HEAD, H_FIELD = 15.0, 13.0, 12.0, 12.0, 12.0
BORDER_THICK, BORDER_THIN = 6, 4   # 0.75pt / 0.5pt
CELL_MAR = (170, 170, 142, 142)    # 3 / 3 / 2.5 / 2.5 mm
IMG_MAR = 227                      # 图片行 4mm
IMG_W_CM = 11.0                    # §17.2 上限 154mm；实测 12cm 会把板书图整行推到新页

# §11.1 四列 4∶7∶5∶4
ACT_HEAD = [(4, "活动名称"), (7, "教师活动"), (5, "学生活动"), (4, "设计意图")]
LABEL_SPAN = 5                     # §13.1 单组字段 5＋15
JOIN = "　"

CENTER = WD_CELL_VERTICAL_ALIGNMENT.CENTER
TOP = WD_CELL_VERTICAL_ALIGNMENT.TOP
LEFT_A = WD_ALIGN_PARAGRAPH.LEFT
CENTER_A = WD_ALIGN_PARAGRAPH.CENTER


# ─────────────────── 行规格构造（bd = 边框档位） ───────────────────
def title_row(text):
    return ([(NGRID, {"t": "title", "text": text})],
            {"h": H_TITLE, "cant": True, "bd": "none"})


def band_row(text):                     # 一级章节标题：§7.1 无边框
    return ([(NGRID, {"t": "band", "text": text})],
            {"h": H_BAND, "cant": True, "keep": True, "bd": "none"})


def band2_row(text):                    # 环节分区行：§7.1 0.75pt 分隔边框
    return ([(NGRID, {"t": "band2", "text": text})],
            {"h": H_BAND2, "cant": True, "keep": True, "bd": "thick"})


def head_row(cells):
    # §15.6 单表不启用 tblHeader；续接靠同表内普通表头行
    return ([(span, {"t": "head", "text": txt}) for span, txt in cells],
            {"h": H_HEAD, "cant": True, "keep": True, "bd": "thin"})


def field_row(cells):
    """cells: [(span, 'flabel'|'ftext', text), ...]"""
    return ([(span, {"t": kind, "text": txt}) for span, kind, txt in cells],
            {"h": H_FIELD, "cant": True, "bd": "thin"})


def group_row(parts, cant=False, bd="none"):
    """§4 I 型长文本行：小标题/编号/正文/对照数据全部在一个通栏单元格内。"""
    return ([(NGRID, {"t": "group", "parts": parts})],
            {"h": None, "cant": cant, "bd": bd})


def act_row(name, t_lines, s_lines, d_lines):
    return ([(4, {"t": "actname", "text": name}),
             (7, {"t": "lines", "lines": t_lines}),
             (5, {"t": "lines", "lines": s_lines}),
             (4, {"t": "lines", "lines": d_lines})],
            {"h": None, "cant": False, "bd": "thin"})   # §15.3 长行按段落跨页


def image_row(path):
    return ([(NGRID, {"t": "image", "path": path})],
            {"h": None, "cant": True, "bd": "thin"})     # §17.3 图片不跨页拆分


# ─────────────────── 解析源稿（只补结构，不改文字） ───────────────────
def parse_source(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    rows, group, title = [], [], None
    act_open = False

    def flush_group():
        nonlocal group
        if group:
            rows.append(group_row(group))
            group = []

    def add(row):
        nonlocal act_open
        flush_group()
        rows.append(row)

    def next_content(j):
        while j < len(lines) and not lines[j].strip():
            j += 1
        return lines[j].strip() if j < len(lines) else ""

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        if s.startswith("# "):
            title = s[2:].strip()
        elif s.startswith("## "):
            add(band_row(s[3:].strip()))
            act_open = False
        elif s.startswith("#### "):
            add(band2_row(s[5:].strip()))
            add(head_row(ACT_HEAD))
            act_open = True
        elif s.startswith("### "):
            nxt = next_content(i + 1)
            if nxt.startswith(("#### ", "## ", ":::act", "![](", "| ", ":::")):
                add(band2_row(s[4:].strip()))
                act_open = False
            else:
                group.append(("sub", s[4:].strip()))
        elif s.startswith(":::row2 "):
            p = [x.strip() for x in s[8:].split("|")]
            add(field_row([(LABEL_SPAN, "flabel", p[0]),
                           (LABEL_SPAN, "ftext", p[1]),
                           (LABEL_SPAN, "flabel", p[2]),
                           (NGRID - 3 * LABEL_SPAN, "ftext", p[3])]))
            act_open = False
        elif s.startswith(":::row "):
            p = [x.strip() for x in s[7:].split("|")]
            add(field_row([(LABEL_SPAN, "flabel", p[0]),
                           (NGRID - LABEL_SPAN, "ftext", p[1])]))
            act_open = False
        elif s.startswith(":::act "):
            name = s[7:].strip()
            j, t_lines, s_lines, d_lines = i + 1, [], [], []
            while j < len(lines) and lines[j].strip() != ":::":
                ln = lines[j].strip()
                if ln.startswith("T:"):
                    t_lines.append(ln[2:].strip())
                elif ln.startswith("S:"):
                    s_lines.append(ln[2:].strip())
                elif ln.startswith("D:"):
                    d_lines.append(ln[2:].strip())
                j += 1
            if not act_open:
                add(head_row(ACT_HEAD))
                act_open = True
            add(act_row(name, t_lines, s_lines, d_lines))
            i = j
        elif s.startswith("|"):
            j, raw = i, []
            while j < len(lines) and lines[j].strip().startswith("|"):
                raw.append(lines[j].strip())
                j += 1
            rws = [[c.strip() for c in r.strip("|").split("|")]
                   for r in raw if not re.fullmatch(r"[\s\-:|]+", r.strip("|"))]
            head, data = rws[0], rws[1:]
            # 口径覆盖⑤：对照块按用户反馈并成一个通栏单元格，仍属同一主表（§14.1）
            # §7.1「辅助对照行 0.5pt 网格边框」→ 给这个容器画一圈细框
            sep = JOIN * 2
            parts = [("sub", sep.join(head))]
            for r in data:
                parts.append(("tab", "**" + r[0] + "**" + sep + sep.join(r[1:])))
            add(group_row(parts, cant=True, bd="thin"))
            act_open = False
            i = j - 1
        elif s.startswith("![]("):
            add(image_row(s[4:].rstrip(")")))
            act_open = False
        elif re.match(r"^\d+\.\s", s) or s.startswith("**"):
            group.append(("item", s))
        elif s != ":::":
            group.append(("text", s))
        i += 1

    flush_group()
    return title, rows


# ─────────────────── 20 格统一网格 + 单元格级边框 ───────────────────
def fixed_grid(t):
    tblPr = t._tbl.tblPr
    w = OxmlElement("w:tblW")
    w.set(qn("w:type"), "dxa")
    w.set(qn("w:w"), str(TOTAL_TW))
    X._put(tblPr, w, X._TBLPR_ORDER)
    ind = OxmlElement("w:tblInd")
    ind.set(qn("w:type"), "dxa")
    ind.set(qn("w:w"), "0")
    X._put(tblPr, ind, X._TBLPR_ORDER)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    X._put(tblPr, lay, X._TBLPR_ORDER)
    t.autofit = False
    grid = t._tbl.find(qn("w:tblGrid"))
    for gc in grid.findall(qn("w:gridCol")):
        gc.set(qn("w:w"), str(GW))


def set_cell_borders(cell, style):
    """§7.1 按行类型设边框：none / thin(0.5pt) / thick(0.75pt)。
    表格级 tblBorders 一律不写，全部由单元格级 tcBorders 控制，避免六边统一网格。"""
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    sz = {"none": None, "thin": BORDER_THIN, "thick": BORDER_THICK}[style]
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + edge)
        if sz is None:
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), str(sz))
            e.set(qn("w:color"), LINE)
        b.append(e)
    X._put(tcPr, b, X._TCPR_ORDER)


def set_cell_margins(cell, v):
    """§8.2 图片行四周 4—6mm。"""
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + edge)
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    X._put(tcPr, mar, X._TCPR_ORDER)


def shade_paragraph(p, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr = p._p.get_or_add_pPr()
    try:
        pPr.insert_element_before(
            shd, "w:spacing", "w:ind", "w:jc", "w:rPr", "w:sectPr", "w:pPrChange")
    except Exception:
        pPr.append(shd)


def fill_cell(cell, cs, opts):
    t = cs["t"]

    if t == "title":
        cell.vertical_alignment = CENTER
        p = cell.paragraphs[0]
        X.fmt_para(p, 2, 4, line=1.2, align=CENTER_A)
        X.add_run(p, cs["text"], size=FS_TITLE, color=TITLE, bold=True, font=X.Ctx.head)
        return

    if t in ("band", "band2", "head"):
        X._cell_shade(cell, BAND)
        cell.vertical_alignment = CENTER
        p = cell.paragraphs[0]
        before, after = (BAND_BEFORE, BAND_AFTER) if t == "band" else (SUB_BEFORE, SUB_AFTER)
        X.fmt_para(p, before, after, line=1.2,
                   align=CENTER_A if t == "head" else LEFT_A,
                   keep_next=opts.get("keep", False))
        size = {"band": FS_H1, "band2": FS_H2, "head": FS_TH}[t]
        X.add_run(p, cs["text"], size=size, color=GREEN, bold=True, font=X.Ctx.head)
        return

    if t == "flabel":                     # §9 字段名称：左对齐、垂直居中
        X._cell_shade(cell, BAND)
        cell.vertical_alignment = CENTER
        p = cell.paragraphs[0]
        X.fmt_para(p, 0, 0, line=LINE_CELL, align=LEFT_A)
        X.add_run(p, cs["text"], size=FS_TH, color=GREEN, bold=False, font=X.Ctx.head)
        return

    if t == "ftext":                      # §13.3 单行字段内容：左对齐、垂直居中
        cell.vertical_alignment = CENTER
        p = cell.paragraphs[0]
        X.fmt_para(p, 0, 0, line=LINE_CELL, align=LEFT_A)
        X.add_rich(p, cs["text"], size=FS_CELL, color=INK)
        return

    if t == "actname":                   # §9 / §11.3 活动名称：左对齐、顶部对齐
        X._cell_shade(cell, BAND)
        cell.vertical_alignment = TOP
        # §10.3 / §11.3：括号里的时间标记单独成段，整块不落单，
        # 避免跨页后页首只剩「钟）」「分）」。只分段、不增字。
        m = re.match(r"^(.*?)(（[^（）]*）)\s*$", cs["text"])
        segs = [m.group(1), m.group(2)] if m else [cs["text"]]
        for k, seg in enumerate(segs):
            p = cell.paragraphs[0] if k == 0 else cell.add_paragraph()
            X.fmt_para(p, 0, AFTER_CELL if k == len(segs) - 1 else 0,
                       line=LINE_CELL, align=LEFT_A)
            p.paragraph_format.keep_together = True
            X.add_run(p, seg, size=FS_TH, color=GREEN, bold=False, font=X.Ctx.head)
        return

    if t == "image":                      # 图版：四周 3mm，与全文表格同边距
        # 4mm 会让 LibreOffice 把整张表往左顶 1mm，边框就不再与上表齐平
        set_cell_margins(cell, CELL_MAR[0])
        cell.vertical_alignment = CENTER
        p = cell.paragraphs[0]
        X.fmt_para(p, 0, 0, line=1.0, align=CENTER_A)
        if os.path.exists(cs["path"]):
            p.add_run().add_picture(cs["path"], width=Cm(IMG_W_CM))
        return

    if t == "group":                      # §4 I 型：一个通栏单元格内的多段落
        cell.vertical_alignment = TOP
        for k, (kind, text) in enumerate(cs["parts"]):
            p = cell.paragraphs[0] if k == 0 else cell.add_paragraph()
            if kind == "sub":
                X.fmt_para(p, SUB_BEFORE if k else 0, SUB_AFTER, line=1.25, align=LEFT_A)
                shade_paragraph(p, BAND)
                X.add_run(p, text, size=FS_H2, color=GREEN, bold=True, font=X.Ctx.head)
            elif kind == "item":          # §12.3 编号段落 11pt / 1.4 / 悬挂缩进
                X.fmt_para(p, 0, AFTER_BODY, line=LINE_ITEM, left=HANG,
                           first=Mm(-6), align=LEFT_A)
                X.add_rich(p, text, size=FS_BODY, color=INK)
            elif kind == "tab":           # §5.1 辅助表正文 10.5pt / §18.2 1.3 / 段后 2pt
                X.fmt_para(p, 0, AFTER_CELL, line=LINE_CELL, align=LEFT_A)
                X.add_rich(p, text, size=FS_CELL, color=INK)
            else:                         # §12.2 通栏正文 11pt / 1.45 / 首行 2 字 / 段后 3pt
                X.fmt_para(p, 0, AFTER_BODY, line=LINE_BODY,
                           first=FIRST_INDENT, align=LEFT_A)
                X.add_rich(p, text, size=FS_BODY, color=INK)
        return

    # 活动单元格正文：§9 顶部对齐、§18.2 10.5pt / 1.3 / 段后 2pt / 首行 0
    cell.vertical_alignment = TOP
    for k, line in enumerate(cs.get("lines", [cs.get("text", "")])):
        p = cell.paragraphs[0] if k == 0 else cell.add_paragraph()
        X.fmt_para(p, 0, AFTER_CELL, line=LINE_CELL, align=LEFT_A)
        X.add_rich(p, line, size=FS_CELL, color=INK)


def build_table(doc, rows_spec):
    t = doc.add_table(rows=0, cols=NGRID)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    # §7.1 不写表格级 tblBorders；每行的边框由 tcBorders 单独决定
    X._tbl_margins(t, *CELL_MAR)
    fixed_grid(t)

    for cells, opts in rows_spec:
        row = t.add_row()
        if opts.get("h") is not None:
            X._set_row_h(row, opts["h"])
        if opts.get("cant"):
            X._row_cant_split(row)
        tr = row._tr
        tcs = tr.findall(qn("w:tc"))
        for tc in tcs[len(cells):]:
            tr.remove(tc)
        for idx, (span, cs) in enumerate(cells):
            tc = tcs[idx]
            tcPr = tc.get_or_add_tcPr()
            gs = OxmlElement("w:gridSpan")
            gs.set(qn("w:val"), str(span))
            X._put(tcPr, gs, X._TCPR_ORDER)
            w = OxmlElement("w:tcW")
            w.set(qn("w:type"), "dxa")
            w.set(qn("w:w"), str(span * GW))
            X._put(tcPr, w, X._TCPR_ORDER)
            cell = _Cell(tc, t)
            set_cell_borders(cell, opts.get("bd", "thin"))
            fill_cell(cell, cs, opts)
    return t


# ─────────────────── 文档 ───────────────────
def build(md_path, out_path, header_text, font_head=None, font_body=None):
    X.Ctx.head = font_head or X.resolve_font(X.HEAD_CANDIDATES, "思源黑体")
    X.Ctx.body = font_body or X.resolve_font(X.BODY_CANDIDATES, "楷体")

    title, rows = parse_source(md_path)
    # 源稿一般放在课题的 .workbuddy/ 下，图片写作 assets/xxx.jpg（相对课题根）。
    # 当前目录找不到时回退到源稿上一级，避免换个课题就丢图；不改变已确认预览。
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
    st.font.size = Pt(FS_BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), X.Ctx.body)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin, sec.bottom_margin = Cm(M_TOP), Cm(M_BOTTOM)
    sec.left_margin, sec.right_margin = Cm(M_LEFT), Cm(M_RIGHT)
    sec.header_distance, sec.footer_distance = Cm(HDR_DIST), Cm(FTR_DIST)

    # 口径覆盖①：沿用四类共用的 build_header()，不加参数、不分叉
    X.build_header(sec, CONTENT_W, text=header_text or title,
                   logo=None, logo_mode="placeholder")
    for footer in (sec.footer, sec.first_page_footer):
        p = footer.paragraphs[0]
        X.fmt_para(p, 0, 0, line=None, align=CENTER_A)
        X.add_run(p, "第 ", size=FS_HF, color=FOOT)
        X.add_page_field(p, size=FS_HF, color=FOOT)
        X.add_run(p, " 页", size=FS_HF, color=FOOT)

    # §1.1 全文只有一张表：主标题即首行
    all_rows = ([title_row(title)] if title else []) + rows

    # §16.1 / §16.2 防孤立：单表里全局 keepNext 链会把板书图整组推到单独一页
    # （实测末页只剩一张图、留白 259mm）。改为两处定向约束：
    # ①板书标题 → 板书图；②「四、教学过程」→ 紧随的环节标题。
    for k, (cells, opts) in enumerate(all_rows):
        cs = cells[0][1]
        if cs["t"] in ("band", "band2", "head"):
            nxt = all_rows[k + 1][0][0][1] if k + 1 < len(all_rows) else None
            opts["keep"] = bool(
                (nxt and nxt["t"] == "image") or "教学过程" in cs.get("text", ""))

    build_table(doc, all_rows)
    doc.save(out_path)
    return len(all_rows), title


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--header", default="", help="页眉右侧课题；留空则用源稿主标题")
    a = ap.parse_args()
    n, t = build(a.input, a.output, a.header)
    print("生成完成：%s | 单表总行数 %d | 主标题 %s" % (a.output, n, t))
