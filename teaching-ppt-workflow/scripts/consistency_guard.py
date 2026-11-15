#!/usr/bin/env python3
"""核对课时结构、已登记的修订影响及外部意见。0 通过，2 核对失败。"""
import argparse
import collections
import hashlib
import re
import sys
from pathlib import Path

from capacity_guard import jload, label_text, normalize, period_sections

REQUIRED = ("本课时教学目标", "教学过程", "板书设计")
LEGACY_SCOPES = ("first_period", "second_period")


def outline_scopes(text, data, cfg):
    if "periods" in data or "final_rows" in data:
        periods = normalize(data, 40)
    else:
        periods = [{"name": key, "heading": cfg[key]["start"]}
                   for key in LEGACY_SCOPES if key in cfg]
    sections = period_sections(text, periods)
    scopes = {p["name"]: section for p, section in zip(periods, sections)}
    for key, section in zip(LEGACY_SCOPES, sections):
        if key in cfg:
            scopes[key] = section
    return sections, scopes


def section_text(segment, heading):
    pattern = r"(?m)^###[ \t]+" + re.escape(heading) + r"[ \t]*$"
    match = re.search(pattern, segment)
    if not match:
        return ""
    return re.split(r"(?m)^###[ \t]+", segment[match.end():], maxsplit=1)[0]


def check_structure(sections, scopes, cfg, errors):
    print("=== 课时结构与出示时机 ===")
    for index, section in enumerate(sections, 1):
        missing = [heading for heading in REQUIRED if not section_text(section, heading).strip()]
        if missing:
            errors.append(f"第 {index} 课时结构缺 {'、'.join(missing)}")
    timing = cfg.get("timing", {})
    for section, key, legacy_key in ((None, "forbidden", "first_period_forbidden"),
                                     ("板书设计", "board_forbidden", "first_period_board_forbidden")):
        forbidden = timing.get(key, {})
        if legacy_key in timing:
            forbidden = {**forbidden, "第一课时": timing[legacy_key]}
        for scope, phrases in forbidden.items():
            segment = sections[0] if legacy_key in timing and scope == "第一课时" else scopes[scope]
            if section:
                segment = section_text(segment, section)
            for phrase in phrases:
                if label_text(phrase, "出示时机标记") in segment:
                    errors.append(f"{scope}{section or ''}提前出示：{phrase}")
    if not timing:
        print("  未登记出示时机标记")


def check_changes(text, scopes, cfg, errors):
    print("=== 修订回流与影响面 ===")
    regression = cfg.get("regression", {})
    for phrase in regression.get("forbidden_strings", []):
        if label_text(phrase, "回流标记") in text:
            errors.append("已删动作回流：" + phrase)
    if regression.get("require_unique_upscreen"):
        ups = re.findall(r"【上屏：(.+?)】", text)
        dup = [key for key, count in collections.Counter(ups).items() if count > 1]
        if dup:
            errors.append("上屏文案重复：" + "、".join(dup))
    impact = cfg.get("change_impact", [])
    if cfg.get("require_change_impact") and not impact:
        errors.append("本次修订缺 change_impact 影响面记录")
    for item in impact:
        segment = scopes[item["scope"]]
        if item.get("section"):
            segment = section_text(segment, item["section"])
        marker = label_text(item["marker"], "影响面标记")
        if marker not in segment:
            errors.append(f"影响面标记未落到 {item['scope']}/{item.get('section') or '课时'}：{marker}")


def check_intake(text, scopes, cfg, errors):
    print("=== 外部问题的版本与证据 ===")
    source_fp = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    print(f"  当前源稿内容指纹 {source_fp}")
    intake = cfg.get("intake", {})
    issues = intake.get("issues", [])
    for issue in issues:
        name = label_text(issue["id"], "外部问题编号")
        if type(issue.get("accepted")) is not bool:
            errors.append(f"外部问题 {name} 缺采纳状态")
            continue
        if not issue["accepted"]:
            continue
        if issue.get("source_fingerprint") != source_fp:
            errors.append(f"外部问题 {name} 尚未对当前版本复核")
        location = scopes[issue["scope"]] if issue.get("scope") else text
        if issue.get("section"):
            location = section_text(location, issue["section"])
        if label_text(issue.get("marker"), f"外部问题 {name} 的现稿锚点") not in location:
            errors.append(f"外部问题 {name} 的证据位置未在当前稿命中")
        label_text(issue.get("evidence"), f"外部问题 {name} 的依据")
        if issue.get("mode_ok") is not True:
            errors.append(f"外部问题 {name} 与当前审查模式不符")
        if label_text(issue.get("kind"), f"外部问题 {name} 的类别") == "timing" and issue.get("estimate_ok") is not True:
            errors.append(f"外部问题 {name} 的估时口径待裁定")
    legacy_reports = intake.get("reports", [])
    if legacy_reports:
        print(f"  旧报告级记录 {len(legacy_reports)} 条，仅作历史记录")
    if not issues:
        print("  未登记当前稿的外部问题，未做逐问题证据核对")
    escalated = set(cfg.get("escalated", []))
    for name, count in cfg.get("issue_repeats", {}).items():
        if type(count) is not int or count < 0:
            errors.append(f"问题 {name} 重复轮次须为非负整数")
        elif count >= 3 and name not in escalated:
            errors.append(f"同一问题 {name} 重复 {count} 轮，待用户裁定")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    root = Path(ap.parse_args().root).resolve()
    try:
        data = jload(root / ".workbuddy/capacity-baseline.json")
        cfg = data.get("consistency")
        if not cfg:
            raise ValueError("容量记录缺 consistency 段")
        source = (root / data["source"]).read_text(encoding="utf-8")
        sections, scopes = outline_scopes(source, data, cfg)
        errors = []
        check_structure(sections, scopes, cfg, errors)
        check_changes(source, scopes, cfg, errors)
        check_intake(source, scopes, cfg, errors)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        errors = [f"无法核对一致性记录或源稿：{exc}"]
    if errors:
        print("\nFAIL：" + "\n  ".join([""] + errors))
        return 2
    print("\nPASS：课时结构与已登记的检查项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
