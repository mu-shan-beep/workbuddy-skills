# WorkBuddy 技能库 · 全量备份仓库

本仓库是 `~/.workbuddy/skills/` 的**全量快照**：本机所有技能目录一律入库，不区分自建与他源。

- **本地根目录**：`~/.workbuddy/skills/`
- **远程仓库**：`git@github.com:mu-shan-beep/workbuddy-skills.git`（私有）
- **主分支**：`main`

> **收录原则（2026-11-08 用户裁定，2026-11-11 复核确认「以最新为准」）**
> 一律全量备份，不区分自建／插件市场／技能中心／GitHub 安装。新增技能目录直接提交，
> 不追加 `.gitignore` 排除项。理由：换机时一次 clone 即可完整复原，无需逐个重装。
> 旧版 README 的「只备份自建 4 个、第三方一律排除」口径已废止。

**本文件只写仓库级规则。** 各技能的用途、流程、版式参数与实现细节，一律以该技能自己的
`SKILL.md` 及其 `references/` 为准，此处不复述，避免两处规则打架或随版本漂移。

---

## 一、收录范围

| 类别 | 目录 |
|---|---|
| 自建技能（6，本机维护） | `lesson-typeset`、`lesson-transcript`、`xhs-lesson-notes`、`interactive-courseware`、`teaching-ppt-workflow`、`ppt-visual-style` |
| 第三方·市场安装（9，只报不改） | `quark-drive`、`baidu-pan-ops`、`totorosir-workbuddy-checkin`、`ima-skills`（官方「腾讯ima」）、`wps-office-suite__skillhub`、`teachable-figures`、`ppt-master`、`pdfkit-py`、`teardown` |

> **自建判定标准（2026-11-13 用户裁定）**：目录内含 `_skillhub_meta.json`（技能市场安装标志）的一律判为**第三方**，
> 即便 frontmatter 误标 `agent_created: true` 也不算自建，体检只报不改。
> 据此 `quark-drive`、`baidu-pan-ops`、`totorosir-workbuddy-checkin` 由「自建」改判第三方，自建口径由 9 个收紧为 **6 个**。
> 机器判定实现在 `teaching-ppt-workflow/scripts/rule_audit.py::is_owned()`。

> **同能力多版本取舍（2026-11-12）**：以官方版为主；没有官方版就以最新版为主。
> 已据此下线 `ima-skills__skillhub`（技能中心旧版 IMA 技能）与 `plugins/ppt-native-animator`（PPT 原生动画插件）。
> 删除已随提交 `6b10ab3` 入库；其父提交 `935708b` 仍含全部 57 个文件，
> 需要时用 `git checkout 935708b -- <路径>` 恢复。

✅ `codex-skills/` **已于 2026-11-13 删除**（用户裁定，`/usr/bin/trash` 移入废纸篓可恢复）。
删除前已核对：内部 3 个副本（`interactive-courseware` 差 227 行、`teaching-ppt-workflow` 差 108 行、`ppt-visual-style` 差 12 行）
均为被主目录完全替代的旧实现，主目录 `SKILL.md` 对旧副本独有文件（`agents/openai.yaml`、`references/improvement-loop.md` 等 6 个）零引用。
该目录曾因位于技能扫描路径内导致同名技能重复注册与旧版本漂移，且 `rule_audit.py` 只扫一层、从未覆盖到它——属长期失检区，一并清除。

**备份范围 ≠ 自动触发范围**：全量入库只决定「哪些文件进版本库」；哪些技能可被自动调用，
由会话路由表与 `settings.json` 的 `skillOverrides` 决定，两套口径互不影响。

---

## 二、忽略规则（与 `.gitignore` 一致）

只排除运行时数据、凭证与垃圾，**不按来源排除任何技能目录**：

| 类别 | 内容 |
|---|---|
| 运行时数据 | `/.workbuddy/`、根目录 `*_migration.json` 等应用迁移标记 |
| 凭证 / 密钥（严禁入库） | `*.env`、`*-cred.json`、`*-rt.json`、`cookie.txt`、`*.key`、`*.pem`、`*.p12`、`*.pfx`、`notify_config.json` |
| 编译与编辑器垃圾 | `__pycache__/`、`*.pyc`、`.venv/`、`.DS_Store`、`._*`、`.idea/`、`.vscode/`、`*.swp` |
| 排版产物 | `/output/`、`~$*`、`*.log`、`*.tmp` |

凭证类文件不在仓库内，换机后需重新授权；技能文件本身可完整恢复。

---

## 三、在新机器上恢复

```bash
ssh -T git@github.com                                             # 确认密钥可用
git clone git@github.com:mu-shan-beep/workbuddy-skills.git ~/.workbuddy/skills
```

已有目录时先改名留存再 clone，不要直接覆盖；恢复后重启 WorkBuddy 刷新技能列表。
第三方技能已随仓库恢复，**无需从技能中心或插件市场补装**。

---

## 四、维护约定

- **提交粒度**：一次改动一个技能，提交信息写清「改了哪个技能的哪个文件、改了什么」，不用 `update`、`fix` 这类无信息量的词。
- **强制流程**：修改技能内容一律走「先出效果 → 用户确认 → 再固化进 `SKILL.md` 与 `scripts/`」，不得边改边写。
- **自动备份**：每日 23:30 检查变更，有改动则提交推送，无改动不产生空提交。
- **推送失败**：只报告原因，不使用 `--force` 强推。
- **口径变更**：收录原则若再调整，必须同步 `.gitignore`、本文件与全局长期记忆三处，不得只改其一。
- **历史文件**：`backup-manifest.json` 是 2026-11-05 旧口径下的校验清单，仅作追溯，不再作为收录依据。

---

_最后整理：2026-11-11_
