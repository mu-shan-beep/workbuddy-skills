#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐字稿「课件对齐 + 时间轴 + 硬伤」校验 V6
==========================================

核心口径（2026-11-07 用户裁定）：**逐字稿只服务课件，必须完全匹配课件**。
课件是唯一依据；教学设计不进入校验——它既不提供页数、页切分，也不提供检查项。
稿子的每一页都必须能在课件里找到对应的一页，多说一句、少讲一问都算错。

课件对齐（--pptx 提供时，硬性）
  [课件]   稿页数 ＝ 课件页数；页标题有公共片段（否则 WARN：自造标题）
  [课件]   课件该页问句逐条落地（漏问／换问 → ERROR）；顺序指令条未落地 → WARN；
           「读顺这一处再继续」被写成「再从头」→ ERROR
  [PPT]    稿中写“依次出现／飞入／淡入”等：课件该页有 <p:timing> 才算有依据；
           只有 <p:transition>（切页效果）→ WARN 待人工确认；两者皆无 → ERROR；
           课件无法解析 → 未验证（不得据此判通过，也不得判错）

时间类（全部按稿自己的页区间推算，不看教学设计）
  [页数]   使用说明自述的课件页数 ＝ 实际稿页数
  [时间轴] 页号 1…N 连续、首尾相接、首页 0:00、末页 ＝ 课时长
  [时间]   页内预算：活动 ＋ 台词 ≤ 页时长（零容差）；余量「页时长 − 活动」按
           单击次数／师台词字数分档 ≥ 40／50／60 秒，容差盖不住的偏紧页才报得出来
  [时间]   页内自述“约 N 分钟”不得超过页时长；学生活动占比 < 40% 提示；
           语速默认 4.0 字/秒（--rate 可改），报表同时给 4.0 与 3.5 两档占用
  [配图]   截图张数 ＝ 稿页数

内容类
  [回指]   写“刚才有人说‘X’”，前文须有学生台词或〔学生可能说〕的预设说过 X（规范 8.1、9.2）
  [结构]   含师生对话的页若缺少〔操作〕，页面任务未落地（规范 5、4.2）
  [指代]   页首不能说“翻页前／上一页”（刚翻页，指代落空）
  [数字]   “找出 N 处”与“M 处都找到了”数字一致；“听写 N 个字”与词表字数一致
  [标记]   行首“师／生”标记后须有冒号；「师：」里混写条件应对 → ERROR（规范 14.2）
  [板书]   〔板书〕各行须覆盖板书设计图的列名（--board-keys，板书图是独立素材，不是教学设计）

用法：
    python3 audit_script.py 逐字稿-源.md
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx --images assets/ppt-第一课时
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx --board-keys 事情,心情,原因
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx --rate 3.5

复盘加固（V6，2026-11-08）：不新增工具，把约束硬化进本脚本
  [复盘]   读取 references/lessons-learned.md：
           ① 生效条目缺「当时的想法／漏检原因／防复发检查项」等必填字段 → ERROR；
           ② 生效条目 > 8 条 → WARN（须合并同类、加固已有规则，不许堆叠）；
           ③ 报表末尾打印仍生效条目的防复发检查项，复发条目置顶。
           台账读取失败记「未验证」；--no-lessons 仅供脚本调试。

结果三态：ERROR（必修）／WARN（逐条判断）／未验证（缺依据，不得冒充通过）。
退出码：0 机检通过（可含 WARN、未验证）；1 存在 ERROR。
"""

import argparse
import glob
import html
import os
import re
import sys
import zipfile

PAGE_RE = re.compile(r"^##\s*第\s*(\d+)\s*页\s*·\s*(.+?)｜(\d+):(\d+)—(\d+):(\d+)\s*$", re.M)
DUR_RE = re.compile(r"约\s*(\d+)\s*(分钟|分半)")
SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
TEXT_RE = re.compile(r"<a:t>(.*?)</a:t>", re.S)
QUES_RE = re.compile(r"[^？?。！!；;：:，,]{4,}[？?]")
# 反问／过渡问过滤：课件里以指令词开头的“问句”多为引导语，不是要学生答的待答问句
RHET_RE = re.compile(r"^(让我们|我们(来|一起)|请你(看|听|读)|下面|接下来|现在|你(看|听|读)一下|一起来)")
# 〔学生可能说〕里的预设回答也应计入回指引用池
POSS_RE = re.compile(r"^[〔【]学生可能说[〕】]\s*(.*)")

# 问句核心词提取用：疑问词与虚词，先按长度降序整体剔除，剩下的实词片段才参与比对
Q_STOP = ["为什么", "怎么样", "怎样", "怎么", "哪些", "什么", "哪里", "哪儿", "如何",
          "是否", "分别", "这里", "这些", "那些", "这个", "那个", "一下", "意思",
          "请你", "你们", "我们", "他们", "一起", "还是", "可以", "能不能", "是不是",
          "有没有", "什么意思", "说说", "想一想", "思考", "的", "了", "是", "有", "在",
          "和", "与", "就", "都", "要", "会", "能", "说", "读", "看", "想", "还", "也",
          "吗", "呢", "吧", "啊", "呀", "着", "过", "把", "被", "让", "给", "对", "从",
          "到", "用", "这", "那", "他", "她", "它", "我", "你"]

LBL_RE = re.compile(r"^(师|生)\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:]")
OP_RE = re.compile(r"^[〔【]操作[〕】]")
TEACHER_RE = re.compile(r"^师\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:]")
STUDENT_RE = re.compile(r"^生\s*(?:[（(][^）)]{0,8}[）)])?\s*[：:]")

ANIM_RE = re.compile(r"依次出现|逐个出现|逐步出现|一个个(?:出现|跳出|冒出来)|点击后出现|点击出现|自动出现|飞入|淡入|浮现")
# 14.2：教师自指的条件应对；课件原问句「如果李子甜…」不含这些词，放行
COND_HINT_RE = re.compile(
    r"若(?:学生|只说|只|答|说)|万一|一时说|说不清|说不上来|没关系|假定|如果学生|答不到|只说(?:结论|大意)")
# 课件顺序指令：把「读顺这一处再继续」写成「再从头」属反向改写
CONTINUE_RE = re.compile(r"再继续|再接着|接着背|继续(?:背|讲|读|说)|读顺这一处")
RESTART_RE = re.compile(r"再从头|从头(?:接上|背|讲|来)|重新(?:背|讲|读)一遍|从头再来")
SEQ_CMD_RE = re.compile(r"卡住时|读不顺|再继续|再接着|先.{0,12}再|然后|别漏|不要多|翻书|合上书|对照|重写|有错先改")
BACKREF_RE = re.compile(
    r"(?:刚才|前面|之前)\s*(?:有人|有同学|有孩子|那位同学|这位同学|那个同学|的同学)"
    r"(?:说|讲|提到|提出|问)[：:]?\s*[“\"]([^”\"\n]{2,40})[”\"]")
HEAD_REF_RE = re.compile(r"翻页前|上一页|前一页|前一屏|刚才那页")
FIND_N_RE = re.compile(r"找(?:出|一找)?\s*([两二三四五六七八九十\d]+)\s*处")
GOT_N_RE = re.compile(r"([两二三四五六七八九十\d]+)\s*处\s*(?:都|也|全)?\s*(?:找到|说了|说有|有)")
DICT_RE = re.compile(r"听写\s*([一两二三四五六七八九十\d]+)\s*个\s*([字词])[：:]\s*([^。\n]+)")

CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
SEG_MIN_RE = re.compile(r"(\d+|[一二两三四五六七八九十])\s*分(半|钟)?")
SEG_SEC_RE = re.compile(r"(\d+)\s*秒")

RATE = 4.5          # 教师朗读速率，字/秒
OPS_SLACK_MIN = 0.3  # 纯操作时长的容差：超过它说明学生活动本身就塞不进这一页
# 余量＝页时长 −〔操作〕活动，要装下教师语言、单击、切换与反馈。
# 按「单击次数／师台词字数」分档，不按页码写死；取整后比较，避免 40.0 秒被浮点判成 39.999。
REST_FLOOR_LIGHT = 40   # 静态短页：无单击且师台词 < 100 字
REST_FLOOR_BASE = 50    # 一般页
REST_FLOOR_HEAVY = 60   # 重点页：单击 ≥ 3 次或师台词 ≥ 180 字


def cn2int(s):
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    m = re.match(r"^十([一二三四五六七八九])$", s)
    if m:
        return 10 + CN_NUM[m.group(1)]
    return None


def seg_minutes(seg):
    """一段文字里的时长（分钟）：'约 1 分 30 秒'→1.5，'约 3 分半'→3.5。"""
    total, hit = 0.0, False
    m = SEG_MIN_RE.search(seg)
    if m:
        n = cn2int(m.group(1))
        if n is not None:
            total += n + (0.5 if m.group(2) == "半" else 0)
            hit = True
    m = SEG_SEC_RE.search(seg)
    if m:
        total += int(m.group(1)) / 60.0
        hit = True
    return total if hit else None


def line_minutes(line):
    """一行操作提示的占用时长：取首个含时长的分段（避免把“每人约 1 分 45 秒”重复计入）。"""
    for seg in re.split(r"[，,。；;]", line):
        v = seg_minutes(seg)
        if v:
            return v
    return 0.0


def to_sec(h, m):
    return int(h) * 60 + int(m)


def fmt(sec):
    return "%d:%02d" % (sec // 60, sec % 60)


def slide_effects(pptx):
    """每页效果：对象动画 <p:timing> 与切页效果 <p:transition> 分开记。

    返回 [(has_timing, has_transition)]；课件无法解析时返回 None（＝未验证，
    不等于「没有动画」，不得据此判错）。
    """
    try:
        z = zipfile.ZipFile(pptx)
        names = sorted([n for n in z.namelist() if SLIDE_RE.match(n)],
                       key=lambda n: int(SLIDE_RE.match(n).group(1)))
        out = []
        for n in names:
            xml = z.read(n).decode("utf-8", "replace")
            out.append(("<p:timing" in xml, "<p:transition" in xml))
        return out
    except Exception:
        return None


def slide_texts(pptx):
    """每页的全部文字，按 <a:t> 顺序拼成一条。"""
    z = zipfile.ZipFile(pptx)
    names = sorted([n for n in z.namelist() if SLIDE_RE.match(n)],
                   key=lambda n: int(SLIDE_RE.match(n).group(1)))
    out = []
    for n in names:
        xml = z.read(n).decode("utf-8", "replace")
        ts = [html.unescape(t).strip() for t in TEXT_RE.findall(xml)]
        out.append(" ".join(t for t in ts if t))
    return out


def han(s):
    return re.sub(r"[^\u4e00-\u9fa5]", "", s or "")


def share_frag(a, b, n=6):
    """a 是否有长度 n 的片段出现在 b 里（都只留汉字）；a 本身短于 n 时整体查。"""
    a, b = han(a), han(b)
    if not a:
        return True
    if len(a) <= n:
        return a in b
    return any(a[i:i + n] in b for i in range(len(a) - n + 1))


def q_keywords(q):
    """问句里的实词片段：剔掉疑问词与虚词后长度 ≥2 的连续汉字。"""
    s = han(q)
    for w in sorted(Q_STOP, key=len, reverse=True):
        s = s.replace(w, " ")
    return [x for x in s.split() if len(x) >= 2]


def q_cover(q, body):
    """问句在本页稿子里的覆盖率。

    实词片段整体命中给 1 分，只有局部（任一 2 字片段）命中给 0.5 分——
    稿子把“怕老师改变主意”说成“怕老师改主意”算讲到，只是换了说法。
    无实词时返回 1.0。
    """
    kws = q_keywords(q)
    if not kws:
        return 1.0
    b = han(body)
    score = 0.0
    for k in kws:
        if k in b:
            score += 1.0
        elif any(k[i:i + 2] in b for i in range(len(k) - 1)):
            score += 0.5
    return score / len(kws)


def page_mentions(body):
    """页内自述时长（分钟）。"""
    out = []
    for n, unit in DUR_RE.findall(body):
        out.append(int(n) + (0.5 if unit == "分半" else 0))
    return out


# ── 复盘台账（V6）：解析 + 加固校验 ───────────────────────────
# 案例只存在 references/lessons-learned.md，流程只在 SKILL.md §7；这里不另立工具，
# 只把「必填思考」「生效条目上限」硬化进既有校验，让规则真正会被触发。
LEDGER_PATH = os.environ.get("LT_LEDGER") or os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "references", "lessons-learned.md"))
LEDGER_HEAD = re.compile(r"^###\s*(LL-\d{3})\b.*$", re.M)
LEDGER_FIELD = re.compile(r"^- ([^：:\n]+)[：:]\s*(.*)$", re.M)
LEDGER_MUST = ("当时的想法", "漏检原因", "正确口径", "加固动作", "防复发检查项")
LEDGER_MAX_ACTIVE = 8   # 超过就合并同类、加固已有规则，不许继续堆叠（2026-11-08 用户裁定）


def read_ledger():
    """返回 (生效条目, 归档数, 错误)；条目 = (编号, 触发条件, 检查项, 字段字典, 状态)。"""
    if not os.path.isfile(LEDGER_PATH):
        return [], 0, "台账不存在：%s" % LEDGER_PATH
    try:
        text = open(LEDGER_PATH, encoding="utf-8").read()
    except (OSError, UnicodeError) as exc:
        return [], 0, "台账读取失败：%s" % exc
    heads = list(LEDGER_HEAD.finditer(text))
    if not heads:
        return [], 0, "台账未解析到 LL-xxx 条目"
    active, archived = [], 0
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        fields = {fm.group(1).strip(): fm.group(2).strip()
                  for fm in LEDGER_FIELD.finditer(text[m.end():end])}
        state = fields.get("状态", "生效")
        if state in ("已归档", "已验证"):
            archived += 1
            continue
        active.append((m.group(1), fields.get("触发条件", "所有稿"),
                       fields.get("防复发检查项", ""), fields, state))
    return active, archived, None


def main():
    ap = argparse.ArgumentParser(description="逐字稿与课件逐页对齐、时间轴与硬伤校验")
    ap.add_argument("script", help="逐字稿源稿（.md）")
    ap.add_argument("--total", type=int, default=40, help="课时总长（分钟），默认 40")
    ap.add_argument("--images", help="课件截图目录，检查张数是否等于页数")
    ap.add_argument("--pptx", help="成品课件，校验稿中所述动画是否真实存在")
    ap.add_argument("--board-keys", help="板书必须覆盖的列名，逗号分隔，如 事情,心情,原因")
    ap.add_argument("--rate", type=float, default=4.0,
                    help="教师口语折算速率（字/秒），默认 4.0；四年级课堂常用 3.5—4.0")
    ap.add_argument("--quiet", action="store_true", help="只打印结论（不关闭复盘提醒）")
    ap.add_argument("--no-lessons", action="store_true",
                    help="仅供脚本调试：不打印 [复盘] 提醒区；正式校验不许使用")
    a = ap.parse_args()

    global RATE
    RATE = a.rate

    if not os.path.isfile(a.script):
        sys.exit("找不到源稿：%s" % a.script)
    text = open(a.script, encoding="utf-8").read()

    if not PAGE_RE.search(text):
        sys.exit("未解析到页标题。格式应为：## 第 1 页 · 页面主题｜0:00—0:20")

    bounds = [m.start() for m in PAGE_RE.finditer(text)] + [len(text)]
    pages = []
    for i, m in enumerate(PAGE_RE.finditer(text)):
        p, title = int(m.group(1)), m.group(2).strip()
        s, e = to_sec(m.group(3), m.group(4)), to_sec(m.group(5), m.group(6))
        body = text[m.end():bounds[i + 1]]
        pages.append({"page": p, "title": title, "start": s, "end": e, "body": body})

    errors, warns, unver = [], [], []

    # ── 课件对齐（第一优先）──────────────────────────────────
    effects = slide_effects(a.pptx) if a.pptx else None
    slides = None
    if a.pptx and effects is None:
        unver.append("[课件] 课件 %s 无法解析（不是有效 pptx／文件损坏／已加密）："
                     "页数、页标题、问句覆盖、动画一律未验证，不得当作已核对"
                     % os.path.basename(a.pptx))
    elif a.pptx:
        slides = slide_texts(a.pptx)
        if len(slides) != len(pages):
            errors.append("[课件] 课件 %d 页，稿 %d 页，数量不等——课件是唯一权威，必须一页对一页"
                          % (len(slides), len(pages)))
        for p in pages:
            idx = p["page"] - 1
            if idx >= len(slides):
                continue
            st = slides[idx]
            if not share_frag(p["title"], st, 3):
                warns.append("[课件] 第 %d 页标题“%s”在课件该页文字里找不到，疑为自造标题"
                             % (p["page"], p["title"]))
            for q in QUES_RE.findall(st):
                if len(han(q)) < 4:
                    continue
                # 以指令词开头的“问句”多为引导语（反问／过渡），不算待答问句
                if RHET_RE.match(q.rstrip("？?")):
                    continue
                # 页标题也属于稿子，课件把问题做成页标题时，答案就在正文里
                cov = q_cover(q, p["title"] + " " + p["body"])
                if cov < 0.34:
                    errors.append("[课件] 第 %d 页课件问“%s”，稿该页几乎没接（实词覆盖 %.0f%%）"
                                  "——课件问句必须逐条落地" % (p["page"], q.strip(), cov * 100))
                elif cov < 0.67:
                    warns.append("[课件] 第 %d 页课件问“%s”，稿该页只沾到 %.0f%% 的实词，"
                                 "核对是否换了问法" % (p["page"], q.strip(), cov * 100))
            # 顺序指令条（卡住时／先…再…／对照／重写）也须在稿该页落地
            for cmd in [x for x in st.split(" ")
                        if SEQ_CMD_RE.search(x) and len(han(x)) >= 5]:
                if not share_frag(cmd, p["body"], 4):
                    warns.append("[课件] 第 %d 页课件指令“%s”，稿该页找不到对应做法"
                                 % (p["page"], cmd.strip()))
            if CONTINUE_RE.search(st) and RESTART_RE.search(p["body"]):
                errors.append("[课件] 第 %d 页课件要求“读顺这一处再继续”，稿却写“再从头”，"
                              "与课件指令相反" % p["page"])

    # ── 页数自述 ──────────────────────────────────────────────
    m = re.search(r"共\s*(\d+)\s*页", text)
    if m and int(m.group(1)) != len(pages):
        errors.append("[页数] 使用说明写“共 %s 页”，实际 %d 页" % (m.group(1), len(pages)))

    # ── 时间轴 ────────────────────────────────────────────────
    nums = [p["page"] for p in pages]
    if nums != list(range(1, len(pages) + 1)):
        errors.append("[时间轴] 页号不连续：%s（应为 1…%d）" % (nums, len(pages)))

    prev = 0
    for p in pages:
        if p["start"] != prev:
            errors.append("[时间轴] 第 %d 页起始 %s 与上页结束 %s 不相接"
                          % (p["page"], fmt(p["start"]), fmt(prev)))
        if p["end"] <= p["start"]:
            errors.append("[时间轴] 第 %d 页时长 ≤ 0（%s—%s）"
                          % (p["page"], fmt(p["start"]), fmt(p["end"])))
        prev = p["end"]

    total = a.total * 60
    if pages[0]["start"] != 0:
        errors.append("[时间轴] 首页不是 0:00（实为 %s）" % fmt(pages[0]["start"]))
    if prev != total:
        errors.append("[时间轴] 末页止于 %s，与课时长 %s 不符" % (fmt(prev), fmt(total)))

    # 教学设计不参与校验：页怎么切、每页多久，由课件页与稿子自己的时间轴决定。

    # ── 页内时间预算 ──────────────────────────────────────────
    ops_total = 0.0
    tea_total = 0
    for p in pages:
        lines = [l.strip() for l in p["body"].split("\n") if l.strip()]
        ops = sum(line_minutes(l) for l in lines if OP_RE.match(l))
        tea_chars = sum(len(TEACHER_RE.sub("", l)) for l in lines if TEACHER_RE.match(l))
        tea_min = tea_chars / RATE / 60.0
        dur = (p["end"] - p["start"]) / 60.0
        p["ops"], p["tea_min"] = ops, tea_min
        ops_total += ops
        tea_total += tea_chars
        need = ops + tea_min
        if ops > dur + OPS_SLACK_MIN:
            warns.append("[时间] 第 %d 页只有 %.1f 分钟，〔操作〕里的学生活动就有 %.1f 分钟，"
                         "本身装不下" % (p["page"], dur, ops))
        elif need > dur:
            warns.append("[时间] 第 %d 页只有 %.1f 分钟，操作 %.1f ＋ 教师台词 %d 字(%.1f) ＝ %.1f，"
                         "放不下" % (p["page"], dur, ops, tea_chars, tea_min, need))
        # 余量下限：原先 0.8 分容差会把教师组织／单击／切换的时间挤没（四轮审稿反复踩到）
        clicks_n = sum(len(re.findall(r"第\s*\d+\s*次单击", l)) for l in lines)
        floor = (REST_FLOOR_LIGHT if clicks_n == 0 and tea_chars < 100 else
                 REST_FLOOR_HEAVY if clicks_n >= 3 or tea_chars >= 180 else REST_FLOOR_BASE)
        rest = round((dur - ops) * 60)
        if rest < floor:
            warns.append("[时间] 第 %d 页余量 %d 秒（页时长 − 活动），低于分档下限 %d 秒"
                         "（单击 %d 次、师台词 %d 字）；先删重复台词，别压学生活动"
                         % (p["page"], rest, floor, clicks_n, tea_chars))

    script_min = total / 60.0
    if ops_total / script_min < 0.40:
        warns.append("[时间] 学生活动合计 %.1f 分钟，只占课时 %.0f%%，低于 40%%（规范 10.3）"
                     % (ops_total, ops_total / script_min * 100))

    # ── 页内自述时长 ──────────────────────────────────────────
    for p in pages:
        ms = page_mentions(p["body"])
        p["mentions"] = ms
        dur = (p["end"] - p["start"]) / 60.0
        if ms and max(ms) - dur >= 0.5:
            warns.append("[时间] 第 %d 页区间只有 %.1f 分钟，正文却写“约 %g 分钟”，时间不够用"
                         % (p["page"], dur, max(ms)))

    # ── 虚构 PPT 功能 ─────────────────────────────────────────
    for p in pages:
        hits = ANIM_RE.findall(p["body"])
        if not hits:
            continue
        if not a.pptx:
            warns.append("[PPT] 第 %d 页写“%s”，未提供课件，未能核实（加 --pptx 可自动判定）"
                         % (p["page"], hits[0]))
            continue
        if effects is None:
            unver.append("[PPT] 第 %d 页写“%s”，课件无法解析，动画未验证——不得当作已核实"
                         % (p["page"], hits[0]))
            continue
        idx = p["page"] - 1
        if idx >= len(effects):
            continue
        has_timing, has_trans = effects[idx]
        if has_timing:
            continue
        if has_trans:
            warns.append("[PPT] 第 %d 页写“%s”，课件该页只有切页效果（<p:transition>），"
                         "未见对象动画时间轴——确认是切换本页还是逐项出现后再留这句话"
                         % (p["page"], hits[0]))
        else:
            errors.append("[PPT] 第 %d 页写“%s”，课件该页既无动画时间轴也无切页效果（规范 5.4）"
                          % (p["page"], hits[0]))

    # ── 虚构课堂回指 ──────────────────────────────────────────
    stu_pool = []
    for p in pages:
        for l in p["body"].split("\n"):
            l = l.strip()
            if STUDENT_RE.match(l):
                stu_pool.append(STUDENT_RE.sub("", l))
            elif POSS_RE.match(l):
                stu_pool.append(POSS_RE.match(l).group(1).strip())
            for q in BACKREF_RE.findall(l):
                src = re.sub(r"[^\u4e00-\u9fa5]", "", q)
                if len(src) < 4:
                    continue
                frags = [src[j:j + 4] for j in range(0, len(src) - 3)]
                before = "".join(stu_pool)
                if frags and not any(f in before for f in frags):
                    errors.append("[回指] 第 %d 页写“刚才有人说‘%s’”，前文没有学生说过这句话"
                                  "（规范 8.1、9.2）" % (p["page"], q))

    # ── 页首指代 ──────────────────────────────────────────────
    for p in pages:
        head = [l.strip() for l in p["body"].split("\n") if l.strip()][:2]
        for l in head:
            if HEAD_REF_RE.search(l):
                warns.append("[指代] 第 %d 页开头写“%s”，刚翻页却说上一页，指代落空"
                             % (p["page"], HEAD_REF_RE.search(l).group(0)))
                break

    # ── 指令数字一致性 ────────────────────────────────────────
    for p in pages:
        for m in FIND_N_RE.finditer(p["body"]):
            if p["body"][m.end():m.end() + 2] == "以上":
                continue
            want = cn2int(m.group(1))
            for m2 in GOT_N_RE.finditer(p["body"][m.end():]):
                got = cn2int(m2.group(1))
                if want and got and want != got:
                    warns.append("[数字] 第 %d 页要求“找出%s处”，后文却说“%s处都找到了”"
                                 % (p["page"], m.group(1), m2.group(1)))
                    break
        for m in DICT_RE.finditer(p["body"]):
            want = cn2int(m.group(1)) or 0
            items = [x for x in re.split(r"[、，,／/]", m.group(3)) if x.strip()]
            units = m.group(2)
            if units == "字":
                real = sum(len(re.sub(r"[^\u4e00-\u9fa5]", "", x)) for x in items)
                label = "字"
            else:
                real = len(items)
                label = "个词"
            if want and real != want:
                warns.append("[数字] 第 %d 页“听写%s个%s”，实际是 %d %s"
                             % (p["page"], m.group(1), units, real, label))

    # ── 行首标记格式 ──────────────────────────────────────────
    for p in pages:
        for l in p["body"].split("\n"):
            l = l.strip()
            if not l or l.startswith(("〔", "【", "#", "|", "::", "!")):
                continue
            if re.match(r"^(师|生)[^\s：:]{1,8}$", l) or (
                    re.match(r"^(师|生)[（(]", l) and not LBL_RE.match(l)):
                warns.append("[标记] 第 %d 页“%s…”缺冒号或括号未闭合，排版会当正文"
                             % (p["page"], l[:12]))
            if TEACHER_RE.match(l) and COND_HINT_RE.search(l):
                errors.append("[标记] 第 %d 页「师：」里混写条件应对“%s…”，须另起〔应对提示〕行"
                              "（规范 14.2，台词要能直接照读）" % (p["page"], l[:24]))
            if "〔应对提示〕" in l or "【应对提示】" in l:
                errors.append("[标记] 第 %d 页〔应对提示〕未独立成行，混在台词或操作里"
                              % p["page"])

    # ── 结构：含对话却缺〔操作〕 ──────────────────────────────
    for p in pages:
        lines = [l.strip() for l in p["body"].split("\n") if l.strip()]
        has_op = any(OP_RE.match(l) for l in lines)
        has_dialogue = any(TEACHER_RE.match(l) or STUDENT_RE.match(l) for l in lines)
        if has_dialogue and not has_op:
            warns.append("[结构] 第 %d 页有师生对话却缺〔操作〕，页面任务没落到操作上"
                         % p["page"])

    # ── 板书列名覆盖 ──────────────────────────────────────────
    if a.board_keys:
        keys = [k.strip() for k in a.board_keys.split(",") if k.strip()]
        boards = "".join(re.findall(r"[〔【]板书[〕】](.+)", text))
        miss = [k for k in keys if k not in boards]
        if miss:
            warns.append("[板书] 〔板书〕没有覆盖板书设计的列名：%s" % "、".join(miss))

    # ── 配图 ──────────────────────────────────────────────────
    img_note = ""
    if a.images:
        files = [f for f in glob.glob(os.path.join(a.images, "p*.*"))
                 if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        if len(files) != len(pages):
            errors.append("[配图] 截图 %d 张 ≠ 稿页 %d 页（%s）" % (len(files), len(pages), a.images))
        img_note = "｜配图 %d 张" % len(files)

    # ── 复盘台账：把「必填思考」与「总量上限」变成硬校验 ─────────
    ledger_active, ledger_err = [], None
    if not a.no_lessons:
        ledger_active, _, ledger_err = read_ledger()
        if ledger_err:
            unver.append("[复盘] %s" % ledger_err)
        else:
            for _eid, _trig, _chk, _f, _st in ledger_active:
                _miss = [k for k in LEDGER_MUST if not _f.get(k)]
                if _miss:
                    errors.append("[复盘] %s 缺字段 %s（归档未完成）" % (_eid, "、".join(_miss)))
            if len(ledger_active) > LEDGER_MAX_ACTIVE:
                warns.append("[复盘] 生效条目 %d 条 > 上限 %d，须合并同类并加固已有规则"
                             % (len(ledger_active), LEDGER_MAX_ACTIVE))

    # ── 报表 ──────────────────────────────────────────────────
    slide_note = "｜课件 %d 页" % len(slides) if slides else "｜课件未解析"
    if not a.quiet:
        print("源稿：%s" % os.path.basename(a.script))
        print("页数：%d%s ｜ 总时长：%s ｜ 学生活动：%.1f 分钟（%.0f%%）%s"
              % (len(pages), slide_note, fmt(prev), ops_total,
                 ops_total / script_min * 100, img_note))
        slow = tea_total / 3.5 / 60.0
        fast = tea_total / RATE / 60.0
        if abs(RATE - 3.5) < 1e-6:
            print("台词：%d 字 ｜ 折算占用（3.5 字/秒）：%.1f 分钟" % (tea_total, slow))
        else:
            print("台词：%d 字 ｜ 折算占用：%.1f 字/秒＝%.1f 分钟，3.5 字/秒＝%.1f 分钟"
                  % (tea_total, RATE, fast, slow))
        print("")
        print("%-4s %-14s %-9s %-8s %s"
              % ("页", "起—止", "时长(分)", "操作+台词", "自述"))
        for p in pages:
            dur = (p["end"] - p["start"]) / 60.0
            mention = ",".join("%g" % x for x in p["mentions"]) or "-"
            print("%-4d %-14s %-9.1f %-8s %s"
                  % (p["page"], "%s—%s" % (fmt(p["start"]), fmt(p["end"])), dur,
                     "%.1f+%.1f" % (p["ops"], p["tea_min"]), mention))
        print("")

    for e in errors:
        print("ERROR     " + e)
    for w in warns:
        print("WARN      " + w)
    for u in unver:
        print("未验证  " + u)
    if not errors:
        print("通过机检：课件逐页对齐、时间轴连续、总长 %s%s"
              % (fmt(total), "，配图张数正确" if a.images else ""))
    if unver:
        print("注意：有 %d 项未验证，交付时须如实说明，不得写作已核实。" % len(unver))

    # ── 复盘提醒：把仍生效的防复发清单推到交付前最后一屏 ─────────
    if not a.no_lessons and not ledger_err:
        if ledger_active:
            print("")
            print("[复盘] 防复发核对（%d 条，逐条答「是／不适用」）：" % len(ledger_active))
            for _eid, _trig, _chk, _f, _st in ledger_active:
                print("  [复盘] %s%s ｜ %s ｜ %s" % (
                    "【复发·先加固已有规则】" if _st == "复发" else "", _eid, _trig, _chk))
        else:
            print("[复盘] 台账无生效条目。")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
