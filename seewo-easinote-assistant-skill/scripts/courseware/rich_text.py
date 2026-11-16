#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rich_text.py — 课件富文本标记解析（纯标准库，全离线可测）。

背景：平台内容设计 Prompt（skill.prompt.template.content.design v8）强制使用
`<br>` 换行、`<strong>` 加粗、`<span style="color: #FF0019">` 强调、`**bold**`
Markdown 写法与 ★●■→ 符号体系；目标客户端实测表明
客户端 add_text_element **不解释任何标记**，原样显示字面标签。

因此渲染器必须自己把标记文本拆成「行 × run（text/bold/color）」，
再按估宽逐个放置文本元素（分支 b）。本模块只做解析与几何规划，不碰 MCP。
"""
import html
import re

_RUN = dict  # {"text": str, "bold": bool, "color": str|None}

_LINE_BREAK = re.compile(r"<br\s*/?>|\n", re.I)

# ── LaTeX → Unicode 数学（客户端不渲染 LaTeX，$...$ 会带美元符号原样上屏）────
# Schema 仍要求公式写在 $...$/$$...$$ 中（_formula_valid），渲染时统一转成
# 可读 Unicode 数学：^2→²、_1→₁、\frac→a/b、\sqrt→√、\times→×、\angle→∠ 等。
_FORMULA = re.compile(r"\$\$(.+?)\$\$|\$([^$]+)\$", re.S)
_SUPERSCRIPT = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶",
                "7": "⁷", "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "=": "⁼",
                "(": "⁽", ")": "⁾", "n": "ⁿ", "x": "ˣ", "y": "ʸ", "a": "ᵃ", "b": "ᵇ", "c": "ᶜ"}
_SUBSCRIPT = {"0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆",
              "7": "₇", "8": "₈", "9": "₉", "+": "₊", "-": "₋", "=": "₌",
              "(": "₍", ")": "₎", "x": "ₓ"}
_LATEX_NAMES = {
    "times": "×", "div": "÷", "cdot": "·", "pm": "±", "mp": "∓",
    "neq": "≠", "ne": "≠", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "approx": "≈", "sim": "∼", "propto": "∝", "cong": "≌", "equiv": "≡",
    "infty": "∞", "ldots": "…", "cdots": "⋯",
    "perp": "⊥", "parallel": "∥", "angle": "∠", "triangle": "△", "degree": "°", "circ": "°",
    "Rightarrow": "⇒", "rightarrow": "→", "Leftarrow": "⇐", "leftarrow": "←",
    "Leftrightarrow": "⇔", "leftrightarrow": "↔", "therefore": "∴", "because": "∵",
    "in": "∈", "notin": "∉", "subset": "⊂", "supset": "⊃", "cup": "∪", "cap": "∩",
    "emptyset": "∅", "forall": "∀", "exists": "∃",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "Sigma": "Σ",
    "phi": "φ", "omega": "ω", "Omega": "Ω",
}


def _scriptize(text, table):
    return "".join(table.get(ch, ch) for ch in text)


def _latex_to_unicode(src):
    """把一段 LaTeX 数学（不含 $ 定界符）转成可读 Unicode。"""
    s = " %s " % src.strip()
    s = s.replace("^\\circ", "°").replace("\\%", "%").replace("\\,", " ").replace("\\;", " ")
    # \frac{a}{b} → a/b（多字符加括号）
    def frac(m):
        num, den = m.group(1).strip(), m.group(2).strip()
        num = "(%s)" % num if len(num) > 1 else num
        den = "(%s)" % den if len(den) > 1 else den
        return "%s/%s" % (num, den)
    s = re.sub(r"\\d?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", frac, s)
    # \sqrt{x} → √(x)；\sqrt x → √x
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: "√(%s)" % m.group(1).strip(), s)
    s = re.sub(r"\\sqrt\s*(\w)", r"√\1", s)
    # ^{...} / ^x 上下标
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: _scriptize(m.group(1), _SUPERSCRIPT), s)
    s = re.sub(r"\^(\\?\w)", lambda m: _scriptize(m.group(1)[-1], _SUPERSCRIPT), s)
    s = re.sub(r"_\{([^{}]*)\}", lambda m: _scriptize(m.group(1), _SUBSCRIPT), s)
    s = re.sub(r"_(\\?\w)", lambda m: _scriptize(m.group(1)[-1], _SUBSCRIPT), s)
    # 命名命令
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _LATEX_NAMES.get(m.group(1), m.group(1)), s)
    s = s.replace("{", "").replace("}", "")
    # 数学排版习惯：运算符两侧不留空格，前置符号（∠√）后不留空格，其余空白折叠
    s = re.sub(r"\s*([×÷·±≠≤≥≈=+\-*/<>])\s*", r"\1", s)
    s = re.sub(r"([∠√△])\s+", r"\1", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def convert_formula_text(piece):
    """把文本片段中的 $...$/$$...$$ 公式转为 Unicode 数学；非公式部分原样保留。"""
    if "$" not in piece:
        return piece
    return _FORMULA.sub(lambda m: _latex_to_unicode(m.group(1) or m.group(2) or ""), piece)


def _unescape(piece):
    """逐文本片段反转义（不能对整串先反转义，否则 &lt; 会变成真标签被误剥除）。"""
    return html.unescape(piece).replace("\xa0", " ")
_TOKEN = re.compile(
    r"(<strong>|</strong>|<b>|</b>"
    r"|<span\s+style\s*=\s*[\"']?\s*color\s*:\s*(#[0-9a-fA-F]{3,6})\s*[\"']?\s*>"
    r"|<span\s+color\s*>|</span>"  # 简写 <span color>：视为「主题强调色」，值由渲染层重映射
    r"|<[a-zA-Z/][^>]*>"  # 其他未知标签（剥除）；必须字母打头——否则数学比较
                          # 「a < 0 … a > 0」的 <…> 会被当标签整段吞掉（已验证）。
    r"|\*\*)"             # Markdown 粗体开关
)
_SYMBOL_LEAD = re.compile(r"^\s*([★●■→➤※])\s*")


def parse_rich(text):
    """把标记文本解析为 [[run, ...], ...]（按行组织）。

    run = {"text": str, "bold": bool, "color": str|None}；
    color 为 span 指定的 #RRGGBB（未做主题重映射，重映射见 remap_runs）。
    """
    if not text:
        return []
    text = str(text)
    lines = []
    for raw_line in _LINE_BREAK.split(text):
        runs = []
        bold = False
        color = None
        pos = 0
        for m in _TOKEN.finditer(raw_line):
            if m.start() > pos:
                piece = convert_formula_text(_unescape(raw_line[pos:m.start()]))
                if piece:
                    runs.append({"text": piece, "bold": bold, "color": color})
            tok = m.group(1)
            if tok == "**":
                bold = not bold
            elif tok in ("<strong>", "<b>"):
                bold = True
            elif tok in ("</strong>", "</b>"):
                bold = False
            elif tok.lower().startswith("<span"):
                color = m.group(2) or "#accent"  # 简写无值：哨兵色，渲染层统一重映射
            elif tok == "</span>":
                color = None
            # 其他未知标签：剥除
            pos = m.end()
        tail = convert_formula_text(_unescape(raw_line[pos:]))
        if tail:
            runs.append({"text": tail, "bold": bold, "color": color})
        lines.append([r for r in runs if r["text"]])
    return lines


def to_plain(text):
    """去掉全部标记后的纯文本（密度统计 / 单元素兜底用）。"""
    return "".join(r["text"] for line in parse_rich(text) for r in line)


def remap_runs(lines, palette):
    """把所有 span 强调色统一重映射到 palette.accent。

    prompt 规定强调色 #FF0019，但与课件主题色板冲突（如水墨蓝/自然绿），
    刻意偏离 prompt 统一用主题 accent 色，保证整册视觉一致。
    """
    accent = (palette or {}).get("accent")
    out = []
    for line in lines:
        new_line = []
        for run in line:
            run = dict(run)
            if run["color"] and accent:
                run["color"] = accent
            # 行首符号（★●■→ 等）上色为 accent，增强分区感
            m = _SYMBOL_LEAD.match(run["text"])
            if m and accent and not run["color"]:
                head, rest = run["text"][:m.end(1)], run["text"][m.end(1):]
                new_line.append({"text": head, "bold": run["bold"], "color": accent})
                if rest:
                    new_line.append({"text": rest, "bold": run["bold"], "color": None})
                continue
            new_line.append(run)
        out.append(new_line)
    return out


def est_width(text, font_size):
    """估算文本宽度（px）：CJK≈1.0em，ASCII≈0.55em。"""
    w = 0.0
    for ch in text:
        w += font_size * (0.55 if ord(ch) < 128 else 1.0)
    return w


# 折行分词：ASCII 单词保持整体，CJK/标点逐字可断（整段 CJK
# 被 \\S+ 当作一个不可断"单词"，超出列宽也不折行，直接溢出压到相邻分栏）
_WRAP_TOKEN = re.compile(r"[A-Za-z0-9]+|\s+|.", re.S)

# 客户端文本框自动宽度约 600px 封顶，超出即框内折行（实测：24px CJK 24 字=576px
# 单行、28 字→600×63 两行）。run 分块上限留 10% 余量，保证每个文本元素单行不内折。
MAX_RUN_WIDTH = 540


def wrap_lines(lines, font_size, max_width):
    """按估宽把过长的行折行（单词/字符级贪心）。返回新的行列表。"""
    out = []
    for line in lines:
        cur, cur_w = [], 0.0
        for run in line:
            for piece in _WRAP_TOKEN.findall(run["text"]) or [run["text"]]:
                pw = est_width(piece, font_size)
                if cur and cur_w + pw > max_width:
                    out.append(cur)
                    cur, cur_w = [], 0.0
                cur.append({"text": piece, "bold": run["bold"], "color": run["color"]})
                cur_w += pw
        if cur:
            out.append(cur)
        elif not line:
            out.append([])  # 保留空行（<br><br> 的间隔行）
    # 合并每个 run 内的碎片：相邻同样式 piece 合并
    merged = []
    for line in out:
        ml = []
        for run in line:
            if ml and ml[-1]["bold"] == run["bold"] and ml[-1]["color"] == run["color"]:
                ml[-1] = dict(ml[-1], text=ml[-1]["text"] + run["text"])
            else:
                ml.append(dict(run))
        merged.append(ml)
    return merged


def _take_chars(text, font_size, budget):
    """按估宽截取不超过 budget 的最长前缀，返回 (前缀, 剩余)。"""
    w = 0.0
    for i, ch in enumerate(text):
        cw = font_size * (0.55 if ord(ch) < 128 else 1.0)
        if i and w + cw > budget:
            return text[:i], text[i:]
        w += cw
    return text, ""


def plan_line_geometry(lines, x, y, font_size, max_width, line_height=None):
    """把行×run 规划为可落画的矩形列表。

    返回 [{"text","bold","color","x","y","w","h"}, ...]；
    行高默认 1.5×fontSize；每行内 run 按估宽推进 x；
    单个矩形宽度不超过 MAX_RUN_WIDTH（客户端文本框自动宽度约 600px 封顶，
    超宽会在框内折行并压到下一行——实测桃花3/一次函数3 文字折叠的根因），
    超宽 run 在同一 y 上拆成多个连续矩形，视觉上仍是一条完整行。
    """
    line_height = line_height or font_size * 1.5
    rects = []
    cy = y
    for line in wrap_lines(lines, font_size, max_width):
        cx = x
        for run in line:
            text = run["text"]
            while text:
                piece, text = _take_chars(text, font_size, MAX_RUN_WIDTH)
                w = est_width(piece, font_size)
                if piece.strip():
                    rects.append({"text": piece, "bold": run["bold"],
                                  "color": run["color"], "x": round(cx, 1), "y": round(cy, 1),
                                  "w": round(w, 1), "h": line_height})
                cx += w
        cy += line_height
    return rects
