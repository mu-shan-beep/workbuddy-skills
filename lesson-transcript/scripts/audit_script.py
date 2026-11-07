#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
逐字稿「课件对齐 + 时间轴 + 硬伤」校验 V3
==========================================

核心口径（2026-11-07 用户裁定）：**逐字稿只服务课件，必须完全匹配课件**。
课件是唯一依据；教学设计不进入校验——它既不提供页数、页切分，也不提供检查项。
稿子的每一页都必须能在课件里找到对应的一页，多说一句、少讲一问都算错。

课件对齐（--pptx 提供时，硬性）
  [课件]   稿页数 ＝ 课件页数
  [课件]   稿页标题与课件该页文字有公共片段（否则 WARN：页标题自造）
  [课件]   课件该页的每个问句都在稿该页被讲（漏问／换问 → ERROR）
  [PPT]    稿中写“依次出现／飞入／淡入”等，课件该页必须真有动画

时间类（全部按稿自己的页区间推算，不看教学设计）
  [页数]   使用说明自述的课件页数 ＝ 实际稿页数
  [时间轴] 页号 1…N 连续、首尾相接、首页 0:00、末页 ＝ 课时长
  [时间]   页内预算：〔操作〕活动时长 ＋ 教师台词朗读时长 ≤ 页时长（＋0.8 分钟容差）
  [时间]   页内自述“约 N 分钟”不得超过页时长；“学生活动占比”低于 40% 提示
  [配图]   截图张数 ＝ 稿页数

内容类
  [回指]   写“刚才有人说‘X’”，前文必须有学生台词说过 X（规范 8.1、9.2）
  [指代]   页首不能说“翻页前／上一页”（刚翻页，指代落空）
  [数字]   “找出 N 处”与“M 处都找到了”数字一致；“听写 N 个字”与词表字数一致
  [标记]   行首“师／生”标记后必须有冒号，否则排版会当正文
  [板书]   〔板书〕各行须覆盖板书设计图的列名（--board-keys，板书图是独立素材，不是教学设计）

用法：
    python3 audit_script.py 逐字稿-源.md
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx --images assets/ppt-第一课时
    python3 audit_script.py 逐字稿-源.md --pptx 课件.pptx --board-keys 事情,心情,原因

退出码：0 全部通过（可含 WARN）；1 存在 ERROR。
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
SLACK_MIN = 0.8     # 页内预算容差（分钟）：教师布置任务的几十秒通常从活动净时长里挤
OPS_SLACK_MIN = 0.3  # 纯操作时长的容差：超过它说明学生活动本身就塞不进这一页


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


def slide_timings(pptx):
    """每页是否含动画时间轴（<p:timing>）。"""
    z = zipfile.ZipFile(pptx)
    names = sorted([n for n in z.namelist() if SLIDE_RE.match(n)],
                   key=lambda n: int(SLIDE_RE.match(n).group(1)))
    return [("<p:timing" in z.read(n).decode("utf-8", "replace")) for n in names]


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


def main():
    ap = argparse.ArgumentParser(description="逐字稿与课件逐页对齐、时间轴与硬伤校验")
    ap.add_argument("script", help="逐字稿源稿（.md）")
    ap.add_argument("--total", type=int, default=40, help="课时总长（分钟），默认 40")
    ap.add_argument("--images", help="课件截图目录，检查张数是否等于页数")
    ap.add_argument("--pptx", help="成品课件，校验稿中所述动画是否真实存在")
    ap.add_argument("--board-keys", help="板书必须覆盖的列名，逗号分隔，如 事情,心情,原因")
    ap.add_argument("--quiet", action="store_true", help="只打印结论")
    a = ap.parse_args()

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

    errors, warns = [], []

    # ── 课件对齐（第一优先）──────────────────────────────────
    timings = slide_timings(a.pptx) if a.pptx else None
    if a.pptx:
        slides = slide_texts(a.pptx)
        if len(slides) != len(pages):
            errors.append("[课件] 课件 %d 页，稿 %d 页，数量不等——课件是唯一权威，必须一页对一页"
                          % (len(slides), len(pages)))
        for p in pages:
            idx = p["page"] - 1
            if idx >= len(slides):
                continue
            st = slides[idx]
            if not share_frag(p["title"], st, 2):
                warns.append("[课件] 第 %d 页标题“%s”在课件该页文字里找不到，疑为自造标题"
                             % (p["page"], p["title"]))
            for q in QUES_RE.findall(st):
                if len(han(q)) < 4:
                    continue
                # 页标题也属于稿子，课件把问题做成页标题时，答案就在正文里
                cov = q_cover(q, p["title"] + " " + p["body"])
                if cov < 0.34:
                    errors.append("[课件] 第 %d 页课件问“%s”，稿该页几乎没接（实词覆盖 %.0f%%）"
                                  "——课件问句必须逐条落地" % (p["page"], q.strip(), cov * 100))
                elif cov < 0.67:
                    warns.append("[课件] 第 %d 页课件问“%s”，稿该页只沾到 %.0f%% 的实词，"
                                 "核对是否换了问法" % (p["page"], q.strip(), cov * 100))

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
    for p in pages:
        lines = [l.strip() for l in p["body"].split("\n") if l.strip()]
        ops = sum(line_minutes(l) for l in lines if OP_RE.match(l))
        tea_chars = sum(len(TEACHER_RE.sub("", l)) for l in lines if TEACHER_RE.match(l))
        tea_min = tea_chars / RATE / 60.0
        dur = (p["end"] - p["start"]) / 60.0
        p["ops"], p["tea_min"] = ops, tea_min
        ops_total += ops
        need = ops + tea_min
        if ops > dur + OPS_SLACK_MIN:
            warns.append("[时间] 第 %d 页只有 %.1f 分钟，〔操作〕里的学生活动就有 %.1f 分钟，"
                         "本身装不下" % (p["page"], dur, ops))
        elif need > dur + SLACK_MIN:
            warns.append("[时间] 第 %d 页只有 %.1f 分钟，操作 %.1f ＋ 教师台词 %d 字(%.1f) ＝ %.1f，"
                         "放不下" % (p["page"], dur, ops, tea_chars, tea_min, need))

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
        if timings is None:
            warns.append("[PPT] 第 %d 页写“%s”，未经课件核实（加 --pptx 可自动判定）"
                         % (p["page"], hits[0]))
            continue
        idx = p["page"] - 1
        if idx >= len(timings) or not timings[idx]:
            errors.append("[PPT] 第 %d 页写“%s”，但课件该页没有动画时间轴（规范 5.4）"
                          % (p["page"], hits[0]))

    # ── 虚构课堂回指 ──────────────────────────────────────────
    stu_pool = []
    for p in pages:
        for l in p["body"].split("\n"):
            l = l.strip()
            if STUDENT_RE.match(l):
                stu_pool.append(STUDENT_RE.sub("", l))
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

    # ── 报表 ──────────────────────────────────────────────────
    slide_note = "｜课件 %d 页" % len(slides) if a.pptx else ""
    if not a.quiet:
        print("源稿：%s" % os.path.basename(a.script))
        print("页数：%d%s ｜ 总时长：%s ｜ 学生活动：%.1f 分钟（%.0f%%）%s"
              % (len(pages), slide_note, fmt(prev), ops_total,
                 ops_total / script_min * 100, img_note))
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
        print("ERROR  " + e)
    for w in warns:
        print("WARN   " + w)
    if not errors:
        print("通过：课件逐页对齐、时间轴连续、总长 %s%s"
              % (fmt(total), "，配图张数正确" if a.images else ""))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
