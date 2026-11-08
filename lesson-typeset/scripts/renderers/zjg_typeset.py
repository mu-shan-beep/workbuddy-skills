#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
课堂逐字稿「统一排版标准 V1.1」排版引擎
========================================

A4 单栏连续排版：思源黑体标题 + 楷体台词，162mm 版心，
页眉左侧固定 30×12mm 的 Logo 区（有图插图标、无图用「木老师原创课件」文字 Logo），
章节标题居中 15pt、逐页标题左标题右时间，教师／学生／提示按字重与灰度分层。

版式常量以 references/unified-spec.md 第 1 章为唯一权威；改动前先出预览、经用户确认。

用法：
    python3 zjg_typeset.py --input 逐字稿.md \
        --header "23 王戎不取道旁李 · 第一课时 逐字稿" \
        --images assets/ppt \
        --output 23王戎不取道旁李-第一课时-逐字稿.docx

    # 有品牌 Logo（等比缩放进 30×12mm 预留区，最高 10mm）
    python3 zjg_typeset.py --input ... --logo assets/brand/logo.png

    # 正式无 Logo 版：隐藏占位框，但保留页眉预留空间
    python3 zjg_typeset.py --input ... --logo-mode hidden

    # 双面装订（奇偶页镜像：内侧 26mm / 外侧 22mm，版心仍 162mm）
    python3 zjg_typeset.py --input ... --mirror

底层 OOXML 构件（schema 有序插入、行高规则、表格边框）复用学习清单引擎，
三份引擎共用同一套约定，见 SKILL.md「引擎实现约定」。
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING, WD_TAB_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

from xuexqingdan_typeset import (  # noqa: E402  同目录复用底层构件
    Ctx, add_page_field, add_rich, add_run, fmt_para,
    resolve_font, HEAD_CANDIDATES, BODY_CANDIDATES,
    _put, _PPR_ORDER, _TBLPR_ORDER, _TCPR_ORDER, _TRPR_ORDER,
    _tbl_borders, _tbl_margins, _set_row_h, set_col_widths, build_header,
    _cell_shade, _row_cant_split, _row_header, _first_para, _cell_para,
    BORDER_OUT, BORDER_IN,
)

# ─────────────────── 版式常量（V1.1） ───────────────────

PAGE_W, PAGE_H = 21.0, 29.7           # A4 纵向
M_TOP, M_BOTTOM = 2.6, 2.0            # 上 26 / 下 20mm
M_LEFT = M_RIGHT = 2.4                # 左右各 24mm
M_INNER, M_OUTER = 2.6, 2.2           # 双面装订：内侧 26 / 外侧 22
HDR_DIST = 0.9                        # 页眉距纸张顶端 9mm
FTR_DIST = 1.0                        # 页脚距纸张底端 10mm

CONTENT_W = PAGE_W - M_LEFT - M_RIGHT           # 16.2cm = 162mm
MIRROR_CONTENT_W = PAGE_W - M_INNER - M_OUTER   # 16.2cm（版心不变，只换边距）

# 页眉 Logo 区
LOGO_W_MM = 30.0                      # 预留区 30 × 12mm
LOGO_H_MM = 12.0
LOGO_MAX_H_MM = 10.0                   # 实际最大显示高度

# 颜色
INK = "222222"        # 主标题 / 章节标题 / 台词
GREEN = "315A4B"      # 逐页标题 / 板书提示
MUTED = "596960"      # 预设回答 / 操作提示 / 时间
AUX = "666666"        # 页眉页脚 / 图注
SEP = "CBD5CD"        # 分隔线
LINE = "9BA9A0"       # 表格边框
TH_BAND = "F2F5F2"    # 表头底色
PH_BORDER = "B8B8B8"  # Logo 占位框虚线
PH_TEXT = "999999"    # Logo 占位文字

# 字号（pt）
FS_TITLE = 20.0       # 文档主标题
FS_SUB = 10.5         # 文档副标题
FS_CH = 15.0          # 一级章节标题
FS_PAGE = 11.5        # 逐页标题
FS_TEA = 12.0         # 教师台词
FS_STU = 11.5         # 学生齐答 / 学生发言
FS_PRESET = 10.5      # 学生预设回答
FS_OP = 10.5          # 操作提示
FS_BOARD = 10.5       # 板书提示
FS_BODY = 11.0        # 说明性正文
FS_HF = 9.0           # 页眉页脚
FS_TIME = 10.0        # 时间标记
FS_TH = 10.5          # 表格表头
FS_TD = 10.5          # 表格正文
FS_CAP = 9.5          # 图片说明
FS_PH = 8.0           # Logo 占位文字

# 行距
LINE_TITLE = 1.2
LINE_CH = 1.25
LINE_TEA = 1.45
LINE_STU = 1.4
LINE_PRESET = 1.35
LINE_OP = 1.35
LINE_BODY = 1.5
LINE_CAP = 1.2
LINE_CELL = 1.3

# 间距（mm）
SP_TITLE_BEF, SP_TITLE_AFT = 8.0, 5.0
SP_SUB_AFT = 10.0
SP_CH_BEF, SP_CH_AFT = 8.0, 5.0
SP_PAGE_BEF, SP_PAGE_AFT = 6.0, 2.5
SP_BODY_AFT = 3.0
SP_TBL_BEF, SP_TBL_AFT = 5.0, 5.0
SP_IMG_BEF, SP_IMG_AFT = 5.0, 5.0
SP_CAP_GAP, SP_CAP_AFT = 2.5, 4.0

# 台词间距（pt，规范 §13 以 pt 记）
SP_LINE_BEF, SP_LINE_AFT = 1.0, 2.0
SP_HINT_BEF, SP_HINT_AFT = 2.0, 2.0

# 缩进
IND_HINT_MM = 4.0     # 预设回答 / 操作 / 板书 整体左缩进
IND_BODY_CHARS = 2    # 说明性正文首行缩进 2 字

# 表格
ROW_H = 12.0
CELL_MAR = (170, 170, 142, 142)       # 左/右 3mm、上/下 2.5mm（twips）

DEFAULT_IMG_W_CM = 12.0               # 默认截图宽度（不超过版心 16.2cm）

MM2PT = 72 / 25.4

PAGE_RE = re.compile(r"^第\s*(\d+)\s*页\s*[·・.、:：]?\s*(.*)$")
TIME_RE = re.compile(r"\s*[｜|]\s*(\d{1,2}:\d{2}\s*[—\-–~至]\s*\d{1,2}:\d{2})\s*$")
IMG_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")


# ─────────────────── 段落与行内格式 ───────────────────

def _para(p, before=0.0, after=0.0, line=LINE_BODY, left_mm=0.0,
          first_mm=0.0, align=WD_ALIGN_PARAGRAPH.LEFT, keep_next=False):
    """统一入口：间距用 pt，缩进用 mm。"""
    fmt_para(p, before=before, after=after, line=line,
             left=Cm(left_mm / 10.0), first=Cm(first_mm / 10.0),
             align=align, keep_next=keep_next)


def _width_units(text):
    """全角算 1，半角算 0.5。"""
    return sum(1.0 if ord(ch) > 127 else 0.5 for ch in text)


def _label_mm(label, size_pt):
    return _width_units(label) * size_pt * 0.3528


def _split_label(text):
    """拆出「师：」「〔操作〕」这类行首标识，标识单独加粗、单独占悬挂缩进。"""
    if text[:1] in ("〔", "【"):
        for close in ("〕", "】"):
            i = text.find(close)
            if 0 < i <= 12:
                return text[:i + 1], text[i + 1:]
        return "", text
    for sep in ("：", ":"):
        i = text.find(sep)
        if 0 < i <= 8:
            return text[:i + 1], text[i + 1:]
    return "", text


def style_of(line):
    s = line.lstrip()
    if s.startswith("〔操作〕") or s.startswith("【操作】"):
        return "op"
    if s.startswith("〔学生可能说〕") or s.startswith("【学生可能说】"):
        return "preset"
    if s.startswith("〔板书〕") or s.startswith("【板书】"):
        return "board"
    if s.startswith("〔") or s.startswith("【"):
        return "note"
    # 学生／教师标记允许任意短括号标注：生：、生（齐）：、生（部分）：、师（指名）：……
    # 2026-11-07 修：原先只认「生（齐）」，`生（部分）：` 被判成 body，字号与悬挂缩进随即丢失，
    # 在成品里表现为层级塌陷（同一页出现两种学生台词样式）。
    if re.match(r"^生\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:]", s):
        return "stu"
    if re.match(r"^师\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:]", s):
        return "tea"
    return "body"


def emit_line(doc, text):
    """一行台词／提示／正文。间距、字号、缩进全部按规范 §7—§11。"""
    kind = style_of(text)
    label, rest = _split_label(text)

    if kind == "tea":
        hang = _label_mm(label, FS_TEA)
        p = doc.add_paragraph()
        _para(p, before=SP_LINE_BEF, after=SP_LINE_AFT, line=LINE_TEA,
              left_mm=hang, first_mm=-hang)
        add_run(p, label, size=FS_TEA, color=INK, bold=True)
        add_rich(p, rest, size=FS_TEA, color=INK)
        return p

    if kind == "stu":
        hang = _label_mm(label, FS_STU)
        p = doc.add_paragraph()
        _para(p, before=SP_LINE_BEF, after=SP_LINE_AFT, line=LINE_STU,
              left_mm=hang, first_mm=-hang)
        add_run(p, label, size=FS_STU, color=INK, bold=True)
        add_rich(p, rest, size=FS_STU, color=INK)
        return p

    if kind == "preset":
        hang = _label_mm(label, FS_PRESET)
        p = doc.add_paragraph()
        _para(p, before=SP_LINE_BEF, after=SP_LINE_AFT, line=LINE_PRESET,
              left_mm=IND_HINT_MM + hang, first_mm=-hang)
        add_run(p, label, size=FS_PRESET, color=MUTED, bold=True)
        add_rich(p, rest, size=FS_PRESET, color=MUTED)
        return p

    if kind in ("op", "board", "note"):
        size = FS_OP if kind == "op" else FS_BOARD
        color = GREEN if kind == "board" else MUTED
        hang = _label_mm(label, size)
        p = doc.add_paragraph()
        _para(p, before=SP_HINT_BEF, after=SP_HINT_AFT, line=LINE_OP,
              left_mm=IND_HINT_MM + hang, first_mm=-hang)
        add_run(p, label, size=size, color=color, bold=True)
        add_rich(p, rest, size=size, color=color)
        return p

    # 说明性正文
    p = doc.add_paragraph()
    _para(p, before=0, after=SP_BODY_AFT, line=LINE_BODY,
          first_mm=IND_BODY_CHARS * FS_BODY * 0.3528)
    add_rich(p, text, size=FS_BODY, color=INK)
    return p


# ─────────────────── 真段落样式（2026-11-08） ───────────────────
# 此前分层全靠 run 局部格式，成品里 189 个非空段落都挂 Normal，后续改版式得逐段改。
# 这里补命名段落样式，只在渲染末尾把 p.style 指过去，不动任何 run：视觉与旧版完全一致，
# 但「标题／教师台词／操作提示／应对提示」在 Word 样式面板里成了可维护的独立对象。
ZJG_STYLES = {
    "ZJG 文档标题": (FS_TITLE,  INK,    True,  LINE_TITLE,  "head"),
    "ZJG 副标题":   (FS_SUB,    INK,    False, LINE_TITLE,  "head"),
    "ZJG 章节标题": (FS_CH,     INK,    True,  LINE_CH,     "head"),
    "ZJG 小标题":   (FS_PAGE,   GREEN,  True,  LINE_TITLE,  "head"),
    "ZJG 逐页标题": (FS_PAGE,   GREEN,  True,  LINE_TITLE,  "head"),
    "ZJG 教师台词": (FS_TEA,    INK,    True,  LINE_TEA,    "body"),
    "ZJG 学生台词": (FS_STU,    INK,    True,  LINE_STU,    "body"),
    "ZJG 预设回答": (FS_PRESET, MUTED,  True,  LINE_PRESET, "body"),
    "ZJG 操作提示": (FS_OP,     MUTED,  True,  LINE_OP,     "body"),
    "ZJG 板书提示": (FS_BOARD,  GREEN,  True,  LINE_OP,     "body"),
    "ZJG 应对提示": (FS_OP,     MUTED,  True,  LINE_OP,     "body"),
    "ZJG 正文":     (FS_BODY,   INK,    False, LINE_BODY,   "body"),
    "ZJG 图注":     (FS_CAP,    AUX,    False, LINE_CAP,    "body"),
}
KIND2STYLE = {
    "tea": "ZJG 教师台词", "stu": "ZJG 学生台词", "preset": "ZJG 预设回答",
    "op": "ZJG 操作提示", "board": "ZJG 板书提示", "note": "ZJG 应对提示",
    "body": "ZJG 正文",
}


def ensure_styles(doc):
    """建样式，不改任何既有 run 格式；样式里只放静态属性，悬挂缩进仍由 _para 动态算。"""
    normal = doc.styles["Normal"]
    for name, (size, color, bold, line, family) in ZJG_STYLES.items():
        st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = normal
        font = Ctx.head if family == "head" else Ctx.body
        st.font.name = font
        st.font.size = Pt(size)
        st.font.bold = bold
        st.font.color.rgb = RGBColor.from_string(color)
        try:
            st.element.rPr.rFonts.set(qn("w:eastAsia"), font)
        except AttributeError:
            pass
        st.paragraph_format.line_spacing = line
        st.quick_style = True       # 出现在 Word 样式库，方便教师／后续维护


def apply_styles(doc, titles=(), subtitles=(), chapters=(), subheads=()):
    titles, subtitles = set(titles), set(subtitles)
    chapters, subheads = set(chapters), set(subheads)
    for par in doc.paragraphs:
        t = par.text.strip()
        if not t:
            continue                      # 图片段无文字，保持原样
        if t in titles:
            name = "ZJG 文档标题"
        elif t in subtitles:
            name = "ZJG 副标题"
        elif t in chapters:
            name = "ZJG 章节标题"
        elif t in subheads:
            name = "ZJG 小标题"
        elif re.match(r"^第\s*\d+\s*页", t):
            name = "ZJG 逐页标题"
        elif t.startswith("（缺图"):
            name = "ZJG 图注"
        else:
            name = KIND2STYLE.get(style_of(t), "ZJG 正文")
        par.style = doc.styles[name]


# ─────────────────── 页眉 / 页脚 ───────────────────

# build_header 已统一收口到 xuexqingdan_typeset（四类文档共用，避免多份 copy 漂移），见上方 import。


def build_footer(sec, page_number=True):
    ftr = sec.footer
    ftr.is_linked_to_previous = False
    p = ftr.paragraphs[0]
    fmt_para(p, before=0, after=0, line=None, align=WD_ALIGN_PARAGRAPH.CENTER)
    for old in list(p._p):
        if old.tag == qn("w:fldSimple"):
            p._p.remove(old)
    if page_number:
        add_page_field(p, size=FS_HF, color=AUX)
    return ftr


# ─────────────────── 构件 ───────────────────

def heading_page(doc, page_no, title, time_text, cw):
    """逐页标题：左标题 + 右时间（右侧制表位，不用连续空格推）。"""
    p = doc.add_paragraph()
    _para(p, before=SP_PAGE_BEF, after=SP_PAGE_AFT, line=LINE_TITLE,
          keep_next=True)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(cw), WD_TAB_ALIGNMENT.RIGHT)

    label = "第 %d 页" % page_no
    if title:
        label += " · " + title
    add_run(p, label, size=FS_PAGE, color=GREEN, font=Ctx.head, bold=True)
    if time_text:
        add_run(p, "\t", size=FS_TIME, color=MUTED, font=Ctx.head)
        add_run(p, time_text, size=FS_TIME, color=MUTED, font=Ctx.head)
    return p


def figure(doc, path, caption="", width_cm=DEFAULT_IMG_W_CM):
    """图片：等比缩放、居中，与上下文字 4—6mm；图注 9.5pt 居中。"""
    if not path or not os.path.exists(path):
        p = doc.add_paragraph()
        _para(p, before=SP_IMG_BEF, after=SP_IMG_AFT, line=1.0,
              align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(p, "（缺图：%s）" % (os.path.basename(path) if path else "未提供"),
                size=FS_CAP, color=AUX)
        return p

    from PIL import Image
    try:
        with Image.open(path) as im:
            w_px, h_px = im.size
    except Exception:
        w_px = h_px = None

    w = min(width_cm, CONTENT_W)
    if w_px:
        nat_w = w_px / 96.0 * 2.54
        w = min(w, nat_w) if nat_w > 1 else w

    p = doc.add_paragraph()
    _para(p, before=SP_IMG_BEF, after=SP_CAP_GAP, line=1.0,
          align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
    p.add_run().add_picture(path, width=Cm(w))

    if caption:
        pc = doc.add_paragraph()
        _para(pc, before=0, after=SP_CAP_AFT, line=LINE_CAP,
              align=WD_ALIGN_PARAGRAPH.CENTER)
        add_run(pc, caption, size=FS_CAP, color=AUX)
    return p


def data_table(doc, headers, rows, cw):
    """表格：外 0.75pt / 内 0.5pt、表头浅绿、内边距 3/3/2.5/2.5mm、行高 12mm。"""
    cols = len(headers) if headers else max((len(r) for r in rows), default=1)
    weights = []
    for i in range(cols):
        lens = [len(headers[i]) if i < len(headers) else 0]
        lens += [len(r[i]) for r in rows if i < len(r)]
        weights.append(max(max(lens), 4) ** 0.75)
    tot = sum(weights)
    widths = [cw * w / tot for w in weights]

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
            _cell_shade(c, TH_BAND)
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
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p = _first_para(c, line=LINE_CELL)
            add_rich(p, val, size=FS_TD, color=INK)

    set_col_widths(t, widths)
    return t


# ─────────────────── 解析 ───────────────────

def _split_time(head):
    time_text, body = "", head
    m = TIME_RE.search(head)
    if m:
        time_text = m.group(1).replace(" ", "")
        body = head[:m.start()].strip()
    return body, time_text


def parse(md):
    lines = md.replace("\r\n", "\n").split("\n")
    blocks, cur = [], None
    is_sep = re.compile(r"^[\s|:\-]+$")
    i = 0

    def cells(line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    while i < len(lines):
        s = lines[i].strip()
        if not s or s in ("---", "***"):
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
            cur = None
            blocks.append(("table", (headers, rows)))
            continue

        # 图片（页内图挂在当前页块上）
        mi = IMG_RE.match(s)
        if mi:
            alt, path = mi.group(1).strip(), mi.group(2).strip()
            if cur is not None and cur["img"] is None:
                cur["img"] = (alt, path)
            else:
                blocks.append(("img", (alt, path)))
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl, txt = len(m.group(1)), m.group(2).strip()
            i += 1
            if lvl == 1:
                cur = None
                blocks.append(("title", txt))
                continue
            body, time_text = _split_time(txt)
            mp = PAGE_RE.match(body)
            if mp:
                cur = {"page": int(mp.group(1)), "title": mp.group(2).strip(),
                       "time": time_text, "lines": [], "img": None}
                blocks.append(("page", cur))
                continue
            cur = None
            blocks.append(("chapter" if lvl == 2 else "subhead", body))
            continue

        if cur is not None:
            cur["lines"].append(s)
        else:
            blocks.append(("p", s))
        i += 1

    return blocks


# ─────────────────── 主渲染 ───────────────────

def build(md, out_path, header="", images_dir=None, img_width=None,
          logo=None, logo_mode="placeholder", mirror=False,
          font_head=None, font_body=None, page_number=True):
    Ctx.head = font_head or resolve_font(HEAD_CANDIDATES, "思源黑体")
    Ctx.body = font_body or resolve_font(BODY_CANDIDATES, "楷体")

    cw = MIRROR_CONTENT_W if mirror else CONTENT_W
    img_w = min(img_width or DEFAULT_IMG_W_CM, cw)

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = Ctx.body
    st.font.size = Pt(FS_BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), Ctx.body)
    ensure_styles(doc)

    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(PAGE_W), Cm(PAGE_H)
    sec.top_margin, sec.bottom_margin = Cm(M_TOP), Cm(M_BOTTOM)
    if mirror:
        sec.left_margin, sec.right_margin = Cm(M_INNER), Cm(M_OUTER)
        doc.settings.element.insert(0, OxmlElement("w:mirrorMargins"))
    else:
        sec.left_margin, sec.right_margin = Cm(M_LEFT), Cm(M_RIGHT)
    sec.header_distance = Cm(HDR_DIST)
    sec.footer_distance = Cm(FTR_DIST)
    sec.different_first_page_header_footer = False   # 首页同样有页眉 Logo 区

    build_header(sec, cw, header, logo=logo, logo_mode=logo_mode)
    build_footer(sec, page_number=page_number)

    blocks = parse(md)
    seen_title = False
    sub_done = False
    subtitle = ""
    style_titles = [x for k, x in blocks if k == "title"]
    style_chapters = [x for k, x in blocks if k == "chapter"]
    style_subheads = [x for k, x in blocks if k == "subhead"]

    for kind, payload in blocks:
        if kind == "title":
            p = doc.add_paragraph()
            _para(p, before=SP_TITLE_BEF, after=SP_TITLE_AFT, line=LINE_TITLE,
                  align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
            add_run(p, payload, size=FS_TITLE, color=INK, font=Ctx.head, bold=True)
            seen_title = True
            continue

        if kind == "p" and seen_title and not sub_done:
            # 主标题后的第一段 = 副标题（年级·课时·时长）
            p = doc.add_paragraph()
            _para(p, before=0, after=SP_SUB_AFT, line=LINE_TITLE,
                  align=WD_ALIGN_PARAGRAPH.CENTER)
            add_run(p, payload, size=FS_SUB, color=INK, font=Ctx.head)
            subtitle = payload
            sub_done = True
            continue

        if kind == "chapter":
            p = doc.add_paragraph()
            _para(p, before=SP_CH_BEF, after=SP_CH_AFT, line=LINE_CH,
                  align=WD_ALIGN_PARAGRAPH.CENTER, keep_next=True)
            add_run(p, payload, size=FS_CH, color=INK, font=Ctx.head, bold=True)
            sub_done = True
            continue

        if kind == "subhead":
            p = doc.add_paragraph()
            _para(p, before=SP_PAGE_BEF, after=SP_PAGE_AFT, line=LINE_TITLE,
                  keep_next=True)
            add_run(p, payload, size=FS_PAGE, color=GREEN, font=Ctx.head, bold=True)
            sub_done = True
            continue

        if kind == "page":
            heading_page(doc, payload["page"], payload["title"], payload["time"], cw)
            img = payload["img"]
            path = None
            caption = ""
            if img:
                caption, path = img
                if not os.path.isabs(path) and images_dir:
                    path = os.path.join(images_dir, os.path.basename(path))
            elif images_dir:
                for ext in ("jpg", "jpeg", "png"):
                    cand = os.path.join(images_dir, "p%02d.%s" % (payload["page"], ext))
                    if os.path.exists(cand):
                        path = cand
                        break
            if path:
                figure(doc, path, caption, img_w)
            for line in payload["lines"]:
                emit_line(doc, line)
            sub_done = True
            continue

        if kind == "img":
            caption, path = payload
            if not os.path.isabs(path) and images_dir:
                path = os.path.join(images_dir, os.path.basename(path))
            figure(doc, path, caption, img_w)
            continue

        if kind == "table":
            headers, rows = payload
            t = data_table(doc, headers, rows, cw)
            gap_after = doc.add_paragraph()
            _para(gap_after, before=0, after=0, line=None)
            gap_after.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            gap_after.paragraph_format.line_spacing = Pt(SP_TBL_AFT * MM2PT)
            gap_after.add_run("").font.size = Pt(1)
            sub_done = True
            continue

        if kind == "p":
            emit_line(doc, payload)
            sub_done = True
            continue

    # 去掉末尾空段
    body = doc.element.body
    for el in reversed(list(body)):
        if el.tag == qn("w:p"):
            if "".join(t.text or "" for t in el.iter(qn("w:t"))).strip():
                break
            body.remove(el)
        elif el.tag == qn("w:sectPr"):
            continue
        else:
            break

    apply_styles(doc, style_titles, [subtitle] if subtitle else [],
                   style_chapters, style_subheads)

    doc.save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="课堂逐字稿「统一排版标准 V1.1」排版引擎")
    ap.add_argument("--input", required=True, help="规范 Markdown 路径")
    ap.add_argument("--output", required=True, help="输出 docx 路径")
    ap.add_argument("--header", default="", help="页眉右侧文字（一般写课题 · 课时）")
    ap.add_argument("--images", default=None,
                    help="课件截图目录，内含 p01.jpg、p02.jpg …（也接受 png，优先 jpg）")
    ap.add_argument("--img-width", type=float, default=None,
                    help="截图宽度 cm，默认 12.0，上限为版心 16.2")
    ap.add_argument("--logo", default=None, help="品牌 Logo 图片；给了就替代文字 Logo")
    ap.add_argument("--logo-mode", default="placeholder", choices=["placeholder", "hidden"],
                    help="无 Logo 时：placeholder=保留虚线占位框（默认）／hidden=隐藏但留位")
    ap.add_argument("--mirror", action="store_true",
                    help="双面装订：内侧 26mm、外侧 22mm，版心仍 162mm")
    ap.add_argument("--font-head", default=None, help="强制标题字族")
    ap.add_argument("--font-body", default=None, help="强制正文字族")
    ap.add_argument("--no-page-number", action="store_true", help="不排页码")
    a = ap.parse_args()

    md = open(a.input, encoding="utf-8").read()
    build(md, a.output, a.header, images_dir=a.images, img_width=a.img_width,
          logo=a.logo, logo_mode=a.logo_mode, mirror=a.mirror,
          font_head=a.font_head, font_body=a.font_body,
          page_number=not a.no_page_number)
    print("已生成：%s" % a.output)


if __name__ == "__main__":
    main()
