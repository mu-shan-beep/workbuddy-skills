#!/usr/bin/env python3
"""课堂呈现面自检：板书可作答 / 上屏自足 / 反思可回溯 / 动作承接 / 环节级零余量。

只读教案源稿，输出「位置＋原句＋判据」，不评分、不计轮次。
退出码：0 已覆盖范围未发现候选；2 无法读取或有明确失败；3 有待人工核实项；4 无法确认全部课时覆盖。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from capacity_guard import CATS, span

TASK_VERB = re.compile(r"选|圈|写|说|填|用|批注|命名|摘|画|标")
PLACEHOLDER = re.compile(r"[＿_]|（\s{2,}）|示例|例如|如:|如：")
LOCATED_TASK = re.compile(r"第\s*[\d一二三四五六七八九十]+\s*(?:自然)?段")
OUTPUT_SCOPE = re.compile(r"(?:圈出|划出|找出|摘抄|标出).{2,}")
OUTPUT_VERB = re.compile(r"读|说|写|圈|画|议|交流|填|抄|背|批注|展示|汇报|标|连|勾|推")
TEACHER_MONOLOGUE = re.compile(r"(点拨|讲解|介绍|说明|点明|追问|讲述)[^。；]{0,24}(用意|写法|好处|作用|深意)")
TEACHER_ACTION_HINT = re.compile(r"请学生|让学生|组织|巡视|指名|引导")

findings = []


def add(level, where, quote, reason):
    findings.append((level, where, quote.strip()[:60], reason))


def split_periods(lines):
    """按 '## ...课时...' 切块，返回 [(课时名, 行列表)]。"""
    marks = [(i, l.strip("# ").strip()) for i, l in enumerate(lines)
             if l.startswith("## ") and "课时" in l]
    if not marks:
        return [("全文", list(enumerate(lines)))]
    out = []
    for n, (idx, name) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        out.append((name, list(enumerate(lines[idx:end], start=idx))))
    return out


def rows_of(block):
    """取四列表的数据行：[(行号, 环节, 教师, 学生, 意图)]。"""
    rows, header_seen = [], False
    for idx, ln in block:
        s = ln.strip()
        if not s.startswith("|") or s.count("|") < 5:
            if s:
                header_seen = False
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != 4 or set(s.replace("|", "").strip()) <= set("-: "):
            continue
        if cells[1:]==["教师活动", "学生活动", "设计意图"]:
            header_seen = True
            continue
        if header_seen:
            rows.append((idx, cells[0], cells[1], cells[2], cells[3]))
    return rows


def check_board(name, block):
    """只定位板书空格，来源与填入方式由人工核验。"""
    board, in_board = [], False
    for idx, ln in block:
        if ln.startswith("###") and "板书" in ln:
            in_board = True
            continue
        if in_board and (ln.startswith("## ") or ln.startswith("### ")):
            in_board = False
        if in_board:
            board.append((idx, ln))
    for idx, ln in board:
        for m in re.finditer(r"（[\s　]{2,}）", ln):
            add("WARN", f"{name} 板书设计（第{idx+1}行）", ln,
                "板书留有空格，请核填入内容来自哪个课堂活动，以及由谁口述、记录或书写。")



def check_screen(name, block):
    """缺少行动线索时提示人工核对材料、动作和产出。"""
    for idx, ln in block:
        for m in re.finditer(r"【上屏[：:]([^】]*)】", ln):
            body = m.group(1).strip()
            if re.search(r"抄写[^。；]{0,8}段", body):
                continue  # 抄写类任务指向既有段落，不需要另给句式
            if LOCATED_TASK.search(body) and OUTPUT_SCOPE.search(body):
                continue
            if TASK_VERB.search(body) and not PLACEHOLDER.search(body):
                add("WARN", f"{name} 上屏（第{idx+1}行）", f"【上屏：{body}】",
                    "请依实际可见材料核对对象、任务动作和预期产出。")


def check_teacher_student(name, rows):
    """教师独白式动作而学生无产出动作 → WARN。"""
    for idx, env, tch, stu, _ in rows:
        if TEACHER_MONOLOGUE.search(tch) and not OUTPUT_VERB.search(stu):
            add("WARN", f"{name} 环节「{env[:14]}」（第{idx+1}行）",
                TEACHER_MONOLOGUE.search(tch).group(0),
                "教师替学生完成比较/归纳，学生列无对应产出动作")


def check_reflection(lines, body_text):
    """反思中的引号短语在教案正文零命中 → WARN。"""
    start = next((i for i, l in enumerate(lines) if l.startswith("#") and "教学反思" in l), None)
    if start is None:
        return
    ref = "\n".join(lines[start + 1:])
    body_only = "\n".join(lines[:start])
    # 顺序配对引号，避免同一字符既开又闭导致错位截取
    quotes, buf, opened = [], [], False
    tail = ""      # 引号外的近期文字，用于判否定语境
    pre = ""       # 开引号前的脚本文本
    for ch in ref:
        if ch in "“”\"":
            if opened:
                q = "".join(buf).strip()
                if len(q) >= 4 and not re.search(r"不是|而非|不要|别|避免|不直接", pre[-10:]):
                    quotes.append(q)
                buf, opened = [], False
            else:
                buf, opened = [], True
                pre = tail
            tail += ch
            continue
        if opened:
            buf.append(ch)
        else:
            tail += ch
    flat = re.sub(r"\s", "", body_only)
    for q in quotes:
        core = re.sub(r"\s", "", q)
        if core and core not in flat:
            add("WARN", "教学反思", q, "反思引语在教案正文零命中，疑教案与实授冲突")


def check_zero_margin(name, rows, baseline, pname):
    """标称＝动作上限的环节数达到半数 → WARN。"""
    if not baseline:
        return False
    rec = next((p for p in baseline["periods"] if p.get("name") == pname), None)
    if rec is None:
        key = re.sub(r"^[一二三四五六七八九十]+、", "", pname)
        rec = next((p for p in baseline.get("periods", []) if p.get("name") == key), None)
    if not rec or not rec.get("final_rows"):
        return False
    zero = total = 0
    for r in rec.get("final_rows", []):
        up = sum(span(r.get(category, 0), f"{name}/{category}")[1] for category in CATS)
        total += 1
        if abs(up - r.get("declared", 0)) <= 0.01:
            zero += 1
    if total and zero * 2 >= total:
        add("WARN", f"{name} 容量", f"{zero}/{total} 个环节标称等于动作上限",
            "请核哪些环节可按现场情况缩短，确认实际余量的可用性。")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="教学设计源稿路径")
    ap.add_argument("--baseline", default="", help="capacity-baseline.json 路径，可选")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"源稿不存在：{src}")
        return 2
    lines = src.read_text(encoding="utf-8").split("\n")
    body_text = "\n".join(lines)

    baseline = None
    if args.baseline:
        try:
            payload = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
            periods = payload.get("periods") if isinstance(payload, dict) else None
            if not isinstance(periods, list) or not all(isinstance(period, dict) for period in periods):
                raise ValueError("缺可用课时列表")
            baseline = payload
        except (OSError, ValueError):
            add("WARN", "预算输入", args.baseline, "未读到有效预算，环节余量待核对。")

    covered, skipped = [], []
    for name, block in split_periods(lines):
        rows = rows_of(block)
        if not rows:
            skipped.append(name)
            add("WARN", name, "", "未识别四列教学过程数据行，该课时的呈现面检查未执行。")
            continue
        check_board(name, block)
        check_screen(name, block)
        check_teacher_student(name, rows)
        try:
            margin_checked = check_zero_margin(name, rows, baseline, name)
        except (ValueError, TypeError, AttributeError):
            margin_checked = False
        if baseline is not None and not margin_checked:
            add("WARN", name, "", "未匹配到可核对的环节预算，余量待人工检查。")
        covered.append({"period": name, "rows": len(rows), "margin_checked": margin_checked})

    check_reflection(lines, body_text)

    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]
    coverage = {"covered": covered, "skipped": skipped, "baseline_read": baseline is not None}
    if args.json:
        print(json.dumps({"fail": fails, "warn": warns, "coverage": coverage}, ensure_ascii=False, indent=2))
    else:
        print(f"课堂呈现面自检：{src}")
        print(f"覆盖 {len(covered)} 个课时、{sum(item['rows'] for item in covered)} 行，未覆盖 {len(skipped)} 个课时。")
        for lv, where, quote, reason in fails + warns:
            print(f"[{lv}] {where}\n       原句：{quote}\n       判据：{reason}")
        print(f"合计 FAIL {len(fails)} 项、WARN {len(warns)} 项")
    if skipped:
        return 4
    return 2 if fails else (3 if warns else 0)


if __name__ == "__main__":
    sys.exit(main())
