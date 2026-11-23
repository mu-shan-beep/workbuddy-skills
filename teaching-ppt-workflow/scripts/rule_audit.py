#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则体检（全技能版）：一条命令跑完所有「机器可查」的一致性断言。

用途：每次规则修订后、每次用户要求「检查规则是否矛盾／是否杂乱」时先跑本脚本，
再补做人工读盘与新课试跑（脚本 PASS ≠ 优化完成）。

覆盖范围：~/.workbuddy/skills 下全部含 SKILL.md 的技能目录。
  - 自建技能（agent_created: true，或本机维护的教案包六件套）：缺陷判 FAIL，须当次修；
  - 第三方安装技能：只报不判 FAIL，不改其内容（不越界）。

断言项：
  1. 按需记录进度，自建入口不套用通用状态模板；
  2. 治理入口可达：三套流程技能都必须指向 self-maintenance.md；
  3. frontmatter 合规：--- 围栏、name 与目录名一致、description 非空；
  4. 人工提示词的独立结构及预览图两类入口；整体工作流同步规程。
  5. 锚点死链：跨文件 / 同文件 #锚点 必须能在目标标题中解析；
  6. 旧口径矛盾：已被用户删除的模块不得被下位文件「正向要求」；
  7. 表格结构：Markdown 表格各组列数一致；
  8. 标题唯一：同一文件内不得出现重复标题；
  9. 技能不重复：两份 SKILL.md 不得内容完全相同；
 10. 臃肿预警：SKILL.md 超过 400 行只提示（WARN，不判失败）。

退出码：0 自建范围全通过；1 自建范围有 FAIL。
"""
import glob
import hashlib
import os
import re
import sys

SKILLS = os.environ.get("RULE_AUDIT_ROOT") or os.path.expanduser("~/.workbuddy/skills")
if len(sys.argv) > 2 and sys.argv[1] == "--root":
    SKILLS = os.path.abspath(sys.argv[2])
elif len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    print("用法: rule_audit.py [--root <技能根目录>]")
    print("默认根目录：~/.workbuddy/skills；--root 仅用于在临时副本上做反向自测。")
    sys.exit(0)
PIPELINE = ["teaching-ppt-workflow", "lesson-typeset", "lesson-transcript"]
KNOWN_OWNED = set(PIPELINE) | {"xhs-lesson-notes", "ppt-visual-style", "interactive-courseware"}
FORCED_STATE = re.compile(r"LOCK\s*→\s*AUDIT\s*→\s*EXECUTE|全任务执行状态机|六大硬门禁")
ANCHOR_STRIP = r"[（）()：:，,、｜|／/《》<>「」\[\]【】#*`\s\-—…·]"
NEG = r"(不另设|严禁|禁止|不得|不附|不写|不复制|非法定|历史工具|仅保留作|不作.*来源|禁止.*替代|已删除|不再)"

results = []  # (level, name, detail)  level: PASS / FAIL / WARN / INFO


def add(level, name, detail):
    results.append((level, name, detail))


def read(p):
    return open(p, encoding="utf-8", errors="ignore").read().replace("\r\n", "\n")


def rel(p):
    return os.path.relpath(p, SKILLS)


def skill_dirs():
    out = []
    for d in sorted(os.listdir(SKILLS)):
        p = os.path.join(SKILLS, d)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, "SKILL.md")):
            out.append(d)
    return out


DIRS = skill_dirs()


def frontmatter(d):
    """返回 (是否有围栏, name, description)。"""
    txt = read(os.path.join(SKILLS, d, "SKILL.md"))
    lines = txt.split("\n")
    if not lines or lines[0].strip() != "---":
        return False, None, None
    name = desc = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^name:\s*(.*)$", line)
        if m and name is None:
            name = m.group(1).strip().strip('"\'')
        m = re.match(r"^description:\s*(.*)$", line)
        if m and desc is None:
            desc = m.group(1).strip().strip('"\'')
    return True, name, desc


def is_owned(d):
    # 用户 2026-11-13 裁定：目录内带 _skillhub_meta.json（技能市场安装标志）的技能
    # 一律判为第三方「只报不改」，即便 frontmatter 误标 agent_created: true 也不算自建。
    # 受影响：baidu-pan-ops、quark-drive、totorosir-workbuddy-checkin、wps-office-suite__skillhub。
    if os.path.isfile(os.path.join(SKILLS, d, "_skillhub_meta.json")):
        return False
    if d in KNOWN_OWNED:
        return True
    return re.search(r"(?m)^agent_created:\s*true\s*$",
                     read(os.path.join(SKILLS, d, "SKILL.md"))) is not None


OWNED = [d for d in DIRS if is_owned(d)]
THIRD = [d for d in DIRS if d not in OWNED]


def md_files(dirs):
    out = []
    for d in dirs:
        out.extend(glob.glob(os.path.join(SKILLS, d, "**", "*.md"), recursive=True))
    return sorted(set(out))


ALL_MD = md_files(DIRS)


def norm_anchor(s):
    return re.sub(ANCHOR_STRIP, "", s).lower()


def anchors_of(path):
    out = set()
    for _, line in scan_lines(path):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if m:
            out.add(norm_anchor(m.group(2)))
    return out


def scan_lines(path):
    """逐行产出 (行号, 内容)，跳过 ``` 围栏内的代码行——代码里的 # 注释不是标题。"""
    in_fence = False
    for ln, line in enumerate(read(path).split("\n"), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield ln, line


# ---------- 1. 仅在需要接续时记录进度 ----------
owner = os.path.join(SKILLS, "teaching-ppt-workflow", "SKILL.md")
owner_text = read(owner) if os.path.isfile(owner) else ""
section = re.search(r"^## 跨阶段与批量任务的进度记录\n(.*?)(?=^## )", owner_text, re.M | re.S)
required_states = ("待确认", "待返回", "待修", "已验收", "失败恢复")
missing_states = [term for term in required_states if not section or term not in section[1]]
old_entries = []
for skill in sorted(KNOWN_OWNED):
    path = os.path.join(SKILLS, skill, "SKILL.md")
    if not os.path.isfile(path) or FORCED_STATE.search(read(path)):
        old_entries.append(skill)
details = missing_states + old_entries
add("FAIL" if details else "PASS", "① 进度记录按需启用",
    "需检查：" + "、".join(details) if details else "单项按各自要求执行；交接、等待及失败恢复有状态")

# ---------- 2. 治理入口可达（全部自建技能） ----------
nogovern = []
review_entry = os.path.isfile(os.path.join(SKILLS, "rule-review", "SKILL.md"))
for s in OWNED:
    t = read(os.path.join(SKILLS, s, "SKILL.md"))
    has_legacy_entry = "self-maintenance.md" in t or "rule_audit.py" in t
    has_fact_review_entry = review_entry and "`rule-review`" in t
    if not (has_legacy_entry or has_fact_review_entry):
        nogovern.append(s)
add("PASS" if not nogovern else "FAIL", "② 治理入口可达（自建 %d 个）" % len(OWNED),
    "%d 个自建技能均已挂治理入口" % len(OWNED) if not nogovern
    else "未挂治理入口：" + "、".join(nogovern))

# ---------- 3. frontmatter 合规 ----------
bad_fm, third_fm = [], []
for d in DIRS:
    ok, name, desc = frontmatter(d)
    problems = []
    if not ok:
        problems.append("缺 --- 围栏")
    if name and name != d and not d.endswith(name):
        problems.append("name=%s 与目录名不一致" % name)
    if ok and not desc:
        problems.append("description 为空")
    elif desc is not None and len(desc.strip()) < 20:
        problems.append("description 过短（%d 字）" % len(desc.strip()))
    if not problems:
        continue
    (third_fm if d in THIRD else bad_fm).append("%s：%s" % (d, "、".join(problems)))
add("PASS" if not bad_fm else "FAIL", "③ frontmatter 合规（自建）",
    "%d 个自建技能全部合规" % len(OWNED) if not bad_fm else "\n      ".join(bad_fm))
if third_fm:
    add("INFO", "③ 附：第三方 frontmatter 异常（只报不改）", "\n      ".join(third_fm))

# ---------- 4. 人工提示词结构与整体工作流同步规程 ----------
workflow_dir = os.path.join(SKILLS, "teaching-ppt-workflow")
prompts_path = os.path.join(workflow_dir, "references", "lesson-pack-prompts.md")
prompts_text = read(prompts_path) if os.path.isfile(prompts_path) else ""
prompt_blocks = re.findall(r"^#{2,3} ([^\n]+)\n\n```Plain Text\n(.*?)\n```$", prompts_text, re.M | re.S)
total_blocks = prompts_text.count(chr(96) * 3 + "Plain Text")
invalid = [
    title for title, body in prompt_blocks
    if not re.match(r"【角色设定】\n[^\n]+\n\n【要求】\n\S", body)
    or FORCED_STATE.search(body) or re.search(r"^【[^\n]*状态机", body, re.M)
]
routes = {
    "PPT页面绘制｜有逐页预览图": ("高清", "构图", "一张"),
    "PPT页面绘制｜无逐页预览图": ("定稿大纲", "获批", "一张"),
}
for title, expected in routes.items():
    matching = [body for label, body in prompt_blocks if title == label]
    if len(matching) != 1 or not all(term in matching[0] for term in expected):
        invalid.append(title)
valid = bool(prompt_blocks) and len(prompt_blocks) == total_blocks and not invalid
add("PASS" if valid else "FAIL", "④ 人工提示词独立结构与绘图分流",
    f"已解析 {len(prompt_blocks)}/{total_blocks} 个代码块"
    + ("" if not invalid else "；需检查：" + "、".join(invalid)))

workflow_skill = read(os.path.join(workflow_dir, "SKILL.md"))
workflow_line = next((line for line in workflow_skill.splitlines() if "跨模型执行稿" in line), "")
required = ("原位", "回读", "两类正式页入口")
add("PASS" if all(term in workflow_line for term in required) else "FAIL",
    "④附 整体工作流同步规程", "原位更新后回读核对正式页两类入口")

# ---------- 5. 锚点死链 ----------
cache = {}
dead_owned, dead_third = [], []
link_pat = re.compile(r"\]\(([^)\s]+\.md)(?:#([^)]+))?\)")
total_links = 0
for f in ALL_MD:
    base = os.path.dirname(f)
    f_owned = rel(f).split("/")[0] in OWNED
    for ln, line in enumerate(read(f).split("\n"), 1):
        for m in link_pat.finditer(line):
            target, anc = m.group(1), m.group(2)
            total_links += 1
            tp = os.path.normpath(os.path.join(base, target))
            msg = None
            if not os.path.isfile(tp):
                msg = "%s:%d → 目标文件不存在 %s" % (rel(f), ln, target)
            elif anc:
                if tp not in cache:
                    cache[tp] = anchors_of(tp)
                if norm_anchor(anc) not in cache[tp]:
                    msg = "%s:%d → %s#%s 无对应标题" % (rel(f), ln, target, anc)
            if msg:
                (dead_owned if f_owned else dead_third).append(msg)
add("PASS" if not dead_owned else "FAIL", "⑤ 锚点死链（自建）",
    "共检查 %d 条 md 链接，自建 0 死链" % total_links if not dead_owned
    else "%d 处：\n      " % len(dead_owned) + "\n      ".join(dead_owned[:10]))
if dead_third:
    add("INFO", "⑤ 附：第三方死链（只报不改）",
        "%d 处：\n      " % len(dead_third) + "\n      ".join(dead_third[:8]))

# ---------- 6. 旧口径矛盾 ----------
LEGACY = [
    ("正文强制写目标矩阵/时间预算表",
     r"(正文必须包含.*(矩阵|预算表)|各课时展开.*(矩阵|时间预算表)|必须采用.*资源状态登记表|与正文【逐环节)"),
    ("反思须写预算/试教假设", r"(反思中的预算|未经试教实测|未授课的反思写课后反思要点)"),
    ("把 ppt2png 当交付链路配图来源",
     r"(先导出再重排|ppt2png\.py --pptx|是把课件导出成.*独立工具|自动探测课件截图目录)"),
    ("教案文末附件量规/模板数", r"(文末实体模板数|附件.*评价量规)"),
]
bad_legacy = []
for label, pat in LEGACY:
    for f in ALL_MD:
        if rel(f).split("/")[0] not in OWNED:
            continue
        for ln, line in enumerate(read(f).split("\n"), 1):
            if re.search(pat, line) and not re.search(NEG, line):
                bad_legacy.append("%s ｜ %s:%d" % (label, rel(f), ln))
add("PASS" if not bad_legacy else "FAIL", "⑥ 旧口径矛盾（正向要求已删模块）",
    "0 处" if not bad_legacy else "%d 处：\n      " % len(bad_legacy) + "\n      ".join(bad_legacy[:10]))

# ---------- 7. 表格列数 ----------
bad_tbl = []
for f in ALL_MD:
    if rel(f).split("/")[0] not in OWNED:
        continue
    group, gname = [], None
    for ln, line in list(scan_lines(f)) + [(0, "")]:
        if line.strip().startswith("|"):
            if not group:
                gname = ln
            group.append(line.count("|"))
        else:
            if group and len(set(group)) > 1:
                bad_tbl.append("%s 第 %d 行起表格列数不一致 %s" % (rel(f), gname, sorted(set(group))))
            group = []
add("PASS" if not bad_tbl else "FAIL", "⑦ Markdown 表格列数（自建）",
    "全部一致" if not bad_tbl else "\n      ".join(bad_tbl[:10]))

# ---------- 8. 标题唯一 ----------
# 同一父节下重名＝真缺陷（锚点会撞车）；不同父节下重名＝提示，不算失败。
dup, dup_soft = [], []
for f in ALL_MD:
    if rel(f).split("/")[0] not in OWNED:
        continue
    stack, seen = [], {}
    for ln, line in scan_lines(f):
        m = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not m:
            continue
        lvl, text = len(m.group(1)), m.group(2)
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        path = tuple(t for _, t in stack)
        key = (path, lvl, text)
        if key in seen:
            dup.append("%s:%d 与 :%d 同父节重复「%s」" % (rel(f), ln, seen[key], text))
        else:
            seen[key] = ln
        if (lvl, text) in [(l, t) for p, l, t in seen if p != path]:
            dup_soft.append("%s:%d「%s」与不同父节下的同名标题并存" % (rel(f), ln, text))
        stack.append((lvl, text))
add("PASS" if not dup else "FAIL", "⑧ 标题唯一（自建·同父节）",
    "无重复" if not dup else "\n      ".join(dup[:10]))
if dup_soft:
    add("INFO", "⑧ 附：跨父节同名标题（提示，不算失败）", "\n      ".join(dup_soft[:8]))

# ---------- 9. 技能不重复 ----------
sig = {}
for d in DIRS:
    h = hashlib.md5(read(os.path.join(SKILLS, d, "SKILL.md")).encode("utf-8")).hexdigest()[:8]
    sig.setdefault(h, []).append(d)
dupskill = [v for v in sig.values() if len(v) > 1]
add("PASS" if not dupskill else "FAIL", "⑨ 技能不重复（SKILL.md 内容）",
    "%d 个技能，内容互不相同" % len(DIRS) if not dupskill else str(dupskill))

# ---------- 10. 臃肿预警 ----------
fat = []
for d in OWNED:
    n = len(read(os.path.join(SKILLS, d, "SKILL.md")).split("\n"))
    if n > 400:
        fat.append("%s：SKILL.md %d 行（>400，建议外移到 references）" % (d, n))
add("WARN" if fat else "PASS", "⑩ 臃肿预警（自建）",
    "无超 400 行入口" if not fat else "\n      ".join(fat))

# ---------- 11. 判定契约完整性（单点登记／归属／断言绑定） ----------
ref = os.path.join(SKILLS, "teaching-ppt-workflow", "references")
scd = os.path.join(SKILLS, "teaching-ppt-workflow", "scripts")
smt = read(os.path.join(ref, "self-maintenance.md"))
lpt = read(os.path.join(ref, "lesson-pack.md"))
lrt = read(os.path.join(ref, "lesson-review.md"))
tmt = read(os.path.join(ref, "task-modes.md"))
cgt = read(os.path.join(scd, "capacity_guard.py"))
c2t = read(os.path.join(scd, "consistency_guard.py"))
contract = []
for k in ("课题级容量估算基线与口径锁定", "外部审查意见准入门禁",
          "收敛与定稿判据", "修订影响面与反向核对取证物"):
    if k not in smt:
        contract.append("单点定义表缺登记：" + k)
for phrase, owner in (("四项准入", lrt), ("收敛与定稿判据", lpt), ("change_impact", tmt)):
    if phrase not in owner:
        contract.append("唯一归属处缺判据：" + phrase)
if not all(k in cgt for k in ("fingerprint", "external-estimate", "return 4")):
    contract.append("闸门二口径未绑定指纹／待裁定退出码")
if not all(k in c2t for k in ("change_impact", "issue_repeats", "first_period_board_forbidden")):
    contract.append("影响面／收敛／板书时机未绑定一致性断言")
add("PASS" if not contract else "FAIL", "⑪ 判定契约完整性（登记／单点／断言绑定）",
    "4 项登记齐、判据在唯一归属、两支脚本断言齐" if not contract
    else "\n      ".join(contract))

# ---------- 12. 阈值单一归属（数字只在归属文件定义，提示词可自足复述） ----------
thresholds = [
    ("4~6", "lesson-pack.md", {"lesson-pack-prompts.md"}),
    ("200 字", "lesson-pack.md", {"lesson-pack-prompts.md"}),
    ("25／20／20／15／10／10", "lesson-pack.md", set()),
]
dup = []
for tok, owner, allow in thresholds:
    for path in ALL_MD:
        if not rel(path).startswith("teaching-ppt-workflow/"):
            continue
        base = os.path.basename(path)
        # 回归台账可引用历史阈值，实际执行口径才参与检查。
        if base == owner or base in allow or base == "feedback-regression.md":
            continue
        if tok in read(path):
            dup.append("%s：%s 应在 %s 定义，此处重复" % (base, tok, owner))
add("WARN" if dup else "PASS", "⑫ 阈值单一归属（跨文件重复）",
    "阈值只在归属文件定义，提示词按自足例外复述" if not dup
    else "\n      ".join(dup))

# ---------- 13. 工作流跨文件契约 ----------
from workflow_contracts import violations as workflow_violations
workflow_issues = workflow_violations(SKILLS)
add("FAIL" if workflow_issues else "PASS", "⑬ 工作流跨文件契约",
    "\n      ".join(workflow_issues) if workflow_issues else "基线计数、Markdown范围、停用入口、封面与大纲边界一致")

# ---------- 输出 ----------
print("=" * 70)
print("规则体检｜%d 个技能（自建 %d／第三方 %d）｜%d 个 Markdown 文件"
      % (len(DIRS), len(OWNED), len(THIRD), len(ALL_MD)))
print("自建：%s" % "、".join(OWNED))
print("=" * 70)
ICON = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "INFO": "ℹ️"}
for level, name, detail in results:
    print("%s %s" % (ICON[level], name))
    for line in str(detail).split("\n"):
        print("     " + line)
fails = [n for lv, n, _ in results if lv == "FAIL"]
print("-" * 70)
if fails:
    print("结论：FAIL（自建范围 %d 项未通过）→ %s" % (len(fails), "、".join(fails)))
    print("按 self-maintenance.md §4 先修再谈其他；修完重跑本脚本。")
    sys.exit(1)
print("结论：PASS（自建范围机器可查项全绿）。仍需人工读盘 + 新课试跑才算优化完成。")
sys.exit(0)
