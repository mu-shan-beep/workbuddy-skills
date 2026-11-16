#!/usr/bin/env python3
"""对账各课时的容量预算和采用稿中的教学过程。

退出码：0 对账通过 ｜ 2 数据或对账失败 ｜ 3 同课时连续两次独立修订仍超载
        4 外部估算口径待裁定 ｜ 5 容量证据未齐
脚本核验记录和稿件之间的一致性。录入者仍须评估具体课堂动作及估算依据。
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

CATS = ("阅读", "书写", "讨论互读", "反馈", "转换")
EPSILON = 1e-6


def jload(path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(data, default_limit):
    if "periods" in data:
        if not isinstance(data["periods"], list):
            raise ValueError("periods 须为课时列表")
        return [{"limit": default_limit, **period} for period in data["periods"]]
    return [{**data, "name": "单课时", "heading": None,
             "limit": data.get("limit", default_limit)}]


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def fingerprint(data, periods):
    records = []
    for period in periods:
        record = {"name": period["name"], "ext": period.get("external_baseline"),
                  "final": period.get("final_rows")}
        if period.get("source_action_fingerprint"):
            record.update(action=period["source_action_fingerprint"], heading=period.get("heading"),
                          limit=float(number(period["limit"], "课时上限")), cuts=period.get("cuts", []),
                          checks=period.get("source_checks", []))
        records.append(record)
    return digest({"source": data.get("source"), "decision": data.get("decision"), "periods": records})


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label}须为有限、非负的数字")
    return value


def label_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}须有具体内容")
    return value


def row_index(rows, label, final=False):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{label}须有环节明细")
    indexed = {}
    for row in rows:
        name = label_text(row["name"], f"{label}环节名")
        if name in indexed:
            raise ValueError(f"{label}重复环节：{name}")
        for category in (*CATS, "declared") if final else CATS:
            number(row[category], f"{label}/{name}/{category}")
        indexed[name] = row
    return indexed


def period_sections(text, periods):
    if not isinstance(periods, list) or not periods:
        raise ValueError("periods 须列出全部课时")
    names = [label_text(p["name"], "课时名") for p in periods]
    if len(set(names)) != len(names):
        raise ValueError("课时名重复")
    if len(re.findall(r"(?m)^###[ \t]+教学过程[ \t]*$", text)) != len(periods):
        raise ValueError("源稿教学过程数量与登记课时数不一致")
    headings = [p.get("heading") for p in periods]
    if len(periods) == 1 and not headings[0]:
        return [text]
    starts = []
    for name, heading in zip(names, headings):
        label_text(heading, f"{name}源稿标题")
        matches = list(re.finditer(r"(?m)^" + re.escape(heading) + r"[ \t]*$", text))
        if len(matches) != 1:
            raise ValueError(f"{name}标题在源稿中须唯一：{heading}")
        starts.append(matches[0].start())
    if any(left >= right for left, right in zip(starts, starts[1:])):
        raise ValueError("课时登记与源稿标题顺序不一致")
    course_end = re.search(r"(?m)^##[ \t]+", text[starts[-1] + len(headings[-1]):])
    end = starts[-1] + len(headings[-1]) + course_end.start() if course_end else len(text)
    return [text[start:stop] for start, stop in zip(starts, starts[1:] + [end])]


def source_actions(segment, label):
    sections = re.split(r"(?m)^###[ \t]+", segment)[1:]
    processes = [s for s in sections if s.partition("\n")[0].strip() == "教学过程"]
    if len(processes) != 1 or not any(s.partition("\n")[0].strip() == "板书设计" for s in sections):
        raise ValueError(f"{label}缺少唯一教学过程或板书标题")
    table = []
    for line in processes[0].splitlines()[1:]:
        cells = [re.sub(r"\s+", " ", cell.strip()) for cell in re.split(r"(?<!\\)\|", line.strip().removeprefix("|").removesuffix("|"))]
        if len(cells) < 2:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells) or cells[0].startswith("教学环节"):
            continue
        if len(cells) != 4 or not all(cells[:3]):
            raise ValueError(f"{label}教学过程须为含环节及师生活动的四列表")
        match = re.search(r"[（(]\s*(\d+(?:\.\d+)?)\s*分钟\s*[）)]", cells[0])
        if not match:
            raise ValueError(f"{label}环节缺用时：{cells[0]}")
        table.append((float(match[1]), cells[:3]))
    if not table:
        raise ValueError(f"{label}未找到教学过程环节")
    return table


def check_period(period, segment, actions, errors, pending):
    label = period["name"]
    limit = number(period["limit"], f"{label}课时上限")
    if not limit:
        raise ValueError(f"{label}课时上限须大于 0")
    print(f"\n--- {label}（上限 {limit}′）---")
    action_fp = digest([cells for _, cells in actions])
    print(f"  当前源稿动作指纹 {action_fp}")
    recorded = period.get("source_action_fingerprint")
    if not recorded:
        pending.append(f"{label}待逐环节核对预算并登记 source_action_fingerprint")
    elif recorded != action_fp:
        errors.append(f"{label}源稿动作已变动：逐环节重算受影响的预算后再登记指纹")

    external = period.get("external_baseline")
    external_rows = {}
    if external is None:
        pending.append(f"{label}缺独立估算明细")
    else:
        external_rows = row_index(external["rows"], f"{label}独立估算")
        external_total = number(external["total"], f"{label}独立估算合计")
        external_sum = sum(sum(r[c] for c in CATS) for r in external_rows.values())
        print(f"  外部独立基线合计 {external_sum:g} ｜声明 {external_total:g}")
        if abs(external_sum - external_total) > EPSILON:
            errors.append(f"{label}独立估算合计与明细不一致")
        if not any(isinstance(external.get(k), str) and external[k].strip() for k in ("note", "source")):
            errors.append(f"{label}独立估算缺 note/source 依据")

    final = row_index(period["final_rows"], f"{label}终稿拆解", final=True)
    for cut in period.get("cuts", []):
        row, category = cut["row"], cut["cat"]
        before = number(cut["from"], f"{label}/{row}调整前用时")
        after = number(cut["to"], f"{label}/{row}调整后用时")
        if (category not in CATS or row not in final or row not in external_rows
                or abs(external_rows[row][category] - before) > EPSILON
                or abs(final[row][category] - after) > EPSILON):
            errors.append(f"{label}/{row}/{category}调整未与基线和终稿对上")

    if len(actions) != len(final):
        errors.append(f"{label}源稿 {len(actions)} 环节、预算 {len(final)} 环节，数量不一致")
    total = 0
    for index, (name, row) in enumerate(final.items()):
        subtotal = sum(row[c] for c in CATS)
        total += subtotal
        actual = actions[index][0] if index < len(actions) else None
        print(f"  {name}：动作小计 {subtotal:g} ｜标称 {row['declared']:g} ｜终稿 {actual}")
        if row["反馈"] <= 0 or row["转换"] <= 0:
            errors.append(f"{label}/{name}须计入反馈和转换")
        if abs(row["declared"] - subtotal) > EPSILON:
            errors.append(f"{label}/{name}标称不等于五类小计")
        if actual is None or abs(row["declared"] - actual) > EPSILON:
            errors.append(f"{label}/{name}与终稿该环节用时不一致")
    for marker in period.get("source_checks", []):
        label_text(marker, f"{label}动作标记")
        if not any(marker in cell for _, cells in actions for cell in cells[1:]):
            message = f"{label}教学过程师生活动缺少标记：{marker}"
            if not recorded and marker in segment:
                pending.append(message + "，迁移时核对原登记位置")
            else:
                errors.append(message)
    print(f"  动作小计合计 {total:g} ｜终稿标称合计 {sum(t for t, _ in actions):g}")
    if total > limit + EPSILON:
        return action_fp, total - limit
    return action_fp, 0


def external_values(raw, periods):
    values = [number(float(part), "外部报告估算") for part in raw.split(",")]
    if len(values) not in (1, len(periods)):
        raise ValueError("外部估算须提供合计或每课时一个值")
    return values


def external_matches(values, periods):
    baselines = [p["external_baseline"]["total"] for p in periods]
    targets = [sum(baselines)] if len(values) == 1 else baselines
    print(f"  外部报告估算 {values} ｜独立基线 {targets}")
    return all(abs(a - b) <= EPSILON for a, b in zip(values, targets))


def record_overload(state, study_scope, overages, fingerprints):
    saved = jload(state) if state.exists() else {}
    previous = saved.get("overloads", {}) if saved.get("scope") == study_scope else {}
    if not overages and not previous:
        return False
    current = {}
    for name in overages:
        old = previous.get(name, {})
        count = old.get("fails", 0)
        if old.get("action") != fingerprints[name]:
            count += 1
        current[name] = {"action": fingerprints[name], "fails": count}
        print(f"  {name}不同的连续超载稿：{count}")
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"scope": study_scope, "overloads": current}, ensure_ascii=False), encoding="utf-8")
    return any(rec["fails"] >= 2 for rec in current.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--limit", type=float, default=40.0)
    ap.add_argument("--external-estimate", help="外部报告的估算分钟数；合计或逗号分隔的逐课时值")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    base = Path(args.baseline) if args.baseline else root / ".workbuddy/capacity-baseline.json"
    state = root / ".workbuddy/capacity-guard.state.json"
    try:
        data = jload(base)
        periods = normalize(data, args.limit)
        if data.get("source"):
            src = root / data["source"]
        else:
            sources = list((root / "源稿").glob("*-教学设计-源.md")) or list(root.glob("*-教学设计-源.md"))
            if len(sources) != 1:
                raise ValueError("未登记 source 且 源稿/ 与根目录均没有唯一的教学设计源稿")
            src = sources[0]
        sections = period_sections(src.read_text(encoding="utf-8"), periods)
        fp = fingerprint(data, periods)
        print(f"容量预算对账｜课时数 {len(periods)} ｜基线指纹 {fp}")
        pending, errors, fingerprints, overages = [], [], {}, {}
        expected = data.get("expected_fingerprint")
        if not expected:
            pending.append("未登记 expected_fingerprint，先核对当前独立基线及终稿拆解")
        elif expected != fp:
            errors.append(f"基线指纹不符（当前 {fp} ≠ 登记 {expected}），核查改动依据")
        for period, section in zip(periods, sections):
            name = period["name"]
            actions = source_actions(section, name)
            fingerprints[name], overage = check_period(period, section, actions, errors, pending)
            if overage:
                overages[name] = overage

        if args.external_estimate is not None and not errors:
            values = external_values(args.external_estimate, periods)
            if all(p.get("external_baseline") is not None for p in periods) and not external_matches(values, periods):
                print("口径不一致，作为新证据待裁定（EXIT=4）")
                return 4
        if errors:
            print("\nFAIL：" + "\n  ".join([""] + errors))
            return 2
        if pending:
            print("\n容量证据未齐，现有数据仅供对账（EXIT=5）：" + "\n  ".join([""] + pending))
            for name, minutes in overages.items():
                print(f"  {name}当前拆解超出预算 {minutes:g} 分钟")
            return 5
        if overages:
            for name, minutes in overages.items():
                print(f"FAIL：{name}动作总量超出预算 {minutes:g} 分钟")
            if record_overload(state, [str(src.resolve()), str(base.resolve())], overages, fingerprints):
                print("FUSE：同一课时两次不同修订仍超载，交用户裁定内容总量与课时")
                return 3
            return 2
        record_overload(state, [str(src.resolve()), str(base.resolve())], {}, fingerprints)
        print(f"\nPASS：{len(periods)} 个课时预算与当前源稿均对账通过｜基线指纹 {fp}")
        return 0
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        print(f"FAIL：无法核对容量记录或源稿：{exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
