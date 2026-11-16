#!/usr/bin/env python3
"""规则一致性扫描：把跨文件矛盾的候选筛出来。

只筛候选。关键词未命中的位置仍需要人工追查。

用法：
  python3 scan.py <目录>                  # 默认扫描对立词和数字
  python3 scan.py <目录> --same 可编辑,标签数
  python3 scan.py <目录> --fact 交付形态 --same 可画,可编辑,PPTX
  python3 scan.py <目录> --opposites
  python3 scan.py <目录> --numbers
  python3 scan.py <目录> --same 交付 --context 0   # 只输出命中句，不输出前后文

设计约束：
  - 只读，不写任何文件
  - 输出按"关键词/类别"分组，每组内按文件排序，便于并排读
  - 全角半角、代码块内容一并纳入（规则常藏在模板里）
"""

import argparse
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".workbuddy"}
MD_EXT = (".md",)

# 对立检测词表
MUST_WORDS = ["必须", "一律", "固定", "必写", "必含", "只能", "只写", "仅", "不得不用", "强制"]
BAN_WORDS = ["禁止", "不得", "不写", "不要", "严禁", "不许", "不能", "不作", "不设"]

# 数值扫描：数字 + 中文量词
NUM_PAT = re.compile(
    r"\d+\s*(?:个|条|字|页|字符|课时|篇|处|项|次|张|分钟|%|％)"
    r"|[一二三四五六七八九十两]+\s*(?:个|条|字|页|课时|篇|处|项|次|张)"
)


def collect(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for f in sorted(filenames):
            if f.endswith(MD_EXT):
                files.append(os.path.join(dirpath, f))
    return sorted(files)


def segments(path):
    """返回 [(行号, 句子)]，表格按单元格切，正文按句切。"""
    out = []
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        return out
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if s.startswith("|"):
            for cell in s.split("|"):
                c = cell.strip()
                if c and not re.fullmatch(r"[-:\s]+", c):
                    out.append((i, c))
        else:
            for sent in re.split(r"(?<=[。！？；])", s):
                t = sent.strip()
                if t:
                    out.append((i, t))
    return out


def rel(path, root):
    return os.path.relpath(path, root)


def group_by_keyword(files, root, keywords, context, fact=None):
    """有事实名称时合并别名，否则按原有方式逐个输出关键词。"""
    groups = [(f"事实「{fact}」", keywords)] if fact else [
        (f"关键词「{word}」", [word]) for word in keywords
    ]
    for label, terms in groups:
        aliases = [term.casefold() for term in terms]
        rows = []
        for f in files:
            for lineno, sent in segments(f):
                if any(alias in sent.casefold() for alias in aliases):
                    rows.append((rel(f, root), lineno, sent))
        print(f"\n{'=' * 72}\n【同义并列】{label} 命中 {len(rows)} 处\n{'=' * 72}")
        if not rows:
            print("  （无命中）")
            continue
        has_requirement = any(word in sent for _, _, sent in rows for word in MUST_WORDS)
        has_prohibition = any(word in sent for _, _, sent in rows for word in BAN_WORDS)
        if has_requirement and has_prohibition:
            print("  ⚠ 同组含「必须类」与「禁止类」词，按对象、条件和原文判读")
        # 按文件聚合，同一文件连续输出
        cur = None
        for r in rows:
            if r[0] != cur:
                print(f"\n  ▸ {r[0]}")
                cur = r[0]
            line = r[2] if context else r[2][:200]
            # 标注该句倾向：必/禁。同一关键词下出现 [必][禁] 并存，最可能是矛盾
            tag = ""
            if any(w in r[2] for w in MUST_WORDS):
                tag += "[必]"
            if any(w in r[2] for w in BAN_WORDS):
                tag += "[禁]"
            print(f"    L{r[1]:<4} {tag:6} {line}")


def scan_opposites(files, root):
    """对立检测：必须类与禁止类各拉一张清单，人工看是否指向同一对象。"""
    must_rows, ban_rows = [], []
    for f in files:
        for lineno, sent in segments(f):
            if any(w in sent for w in MUST_WORDS):
                must_rows.append((rel(f, root), lineno, sent))
            if any(w in sent for w in BAN_WORDS):
                ban_rows.append((rel(f, root), lineno, sent))

    for title, rows in (("「必须／一律／固定」类", must_rows), ("「禁止／不写／不设」类", ban_rows)):
        print(f"\n{'=' * 72}\n【对立检测】{title} 共 {len(rows)} 句\n{'=' * 72}")
        cur = None
        for r in rows:
            if r[0] != cur:
                print(f"\n  ▸ {r[0]}")
                cur = r[0]
            print(f"    L{r[1]:<4} {r[2][:200]}")
    print(
        f"\n{'!' * 72}\n判读：把两张清单里指向【同一个对象】的句子挑出来并排读。"
        f"\n  核对适用条件和原文，确认同一动作在相同条件下是否给出对立要求。\n{'!' * 72}"
    )


def scan_numbers(files, root):
    """数值扫描：同一件事的多个数字说法。"""
    print(f"\n{'=' * 72}\n【数值扫描】含数字量词的规则句\n{'=' * 72}")
    cur = None
    n = 0
    for f in files:
        for lineno, sent in segments(f):
            if NUM_PAT.search(sent):
                n += 1
                if rel(f, root) != cur:
                    print(f"\n  ▸ {rel(f, root)}")
                    cur = rel(f, root)
                print(f"    L{lineno:<4} {sent[:200]}")
    print(f"\n共 {n} 句。判读：同一对象（标签数／字数／页数／条数）出现不同数字，即为漂移。")


def main():
    ap = argparse.ArgumentParser(description="规则一致性扫描（只读）")
    ap.add_argument("root", help="要扫描的目录")
    ap.add_argument("--same", help="同义并列，逗号分隔的关键词")
    ap.add_argument("--fact", help="把 --same 的所有关键词视为同一事实的别名")
    ap.add_argument("--opposites", action="store_true", help="对立检测")
    ap.add_argument("--numbers", action="store_true", help="数值扫描")
    ap.add_argument("--context", type=int, default=1, help="0=截断长句，1=完整输出（默认）")
    args = ap.parse_args()
    keywords = [term.strip() for term in (args.same or "").split(",") if term.strip()]
    if (args.same is not None or args.fact is not None) and not keywords:
        ap.error("--same 至少需要一个关键词；--fact 与 --same 一起使用")

    if not os.path.isdir(args.root):
        sys.exit(f"目录不存在：{args.root}")

    files = collect(args.root)
    if not files:
        sys.exit("未找到任何 .md 文件")

    print(f"扫描目录：{os.path.abspath(args.root)}")
    print(f"文件数：{len(files)}")
    for f in files:
        print(f"  - {rel(f, args.root)}")

    ran = False
    if args.same:
        ran = True
        group_by_keyword(files, args.root, keywords, args.context, args.fact)
    if args.opposites or not (args.same or args.numbers):
        ran = True
        scan_opposites(files, args.root)
    if args.numbers or not (args.same or args.opposites):
        ran = True
        scan_numbers(files, args.root)

    if not ran:
        print("未指定检查项。可用 --same / --opposites / --numbers")
    print("\n提醒：以上只是候选。矛盾要人读原文确认，脚本不判对错。")


if __name__ == "__main__":
    main()
