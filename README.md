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
| 自建技能（6） | `lesson-typeset`、`lesson-transcript`、`xhs-lesson-notes`、`interactive-courseware`、`teaching-ppt-workflow`、`ppt-visual-style` |
| 网盘编排（2） | `quark-drive`、`baidu-pan-ops` |
| 安装来源技能 | `ima-skills`、`ima-skills__skillhub`、`teachable-figures`、`totorosir-workbuddy-checkin`、`ppt-master`、`pdfkit-py` |
| 宿主存档（非技能路由） | `codex-skills/`（Codex 技能快照）、`plugins/`（ppt-native-animator 插件源码） |

⚠️ `codex-skills/` 与 `plugins/` 是备份存档，但放在 `skills/` 根目录下会被平台扫描并注册成技能，
产生同名重复加载。若不需要它们参与触发，应把存档移出技能扫描路径（保留文件，换位置）。

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
