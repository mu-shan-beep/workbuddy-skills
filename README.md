# WorkBuddy 自建技能库

本仓库是个人 WorkBuddy 技能的版本控制与备份存档，收录**自己创建与维护**的技能。

- **本地根目录**：`~/.workbuddy/skills/`
- **远程仓库**：`git@github.com:mu-shan-beep/workbuddy-skills.git`（私有）
- **主分支**：`main`

**收录原则：只备份自建技能。** 从技能中心、插件市场安装的第三方技能一律不入库，原因有二：上游可随时重新安装；内容归属他人，混入自有备份会模糊版本界限。判断依据与排除名单见文末「收录边界」。

---

## Codex 技能与插件备份（2026-11-05）

2026-11-06增量同步：更新 `codex-skills/teaching-ppt-workflow` 与 `codex-skills/ppt-visual-style`。保留《牛和鹅》经验的证据边界，补充局部修复复查、宣传原页复用及设计思路迁移规则；本次核对这两项目录共33个文件。清单中的 `date` 为初始快照日期，`scope_updates` 记录后续分范围更新，其他目录不代表本次重新核验。

本次扩展备份保留原 WorkBuddy 三项自建技能，并额外收录：

- `codex-skills/teaching-ppt-workflow`：教案包制作流程（含可画先归档再组装、AI按需简单融入规则）。
- `codex-skills/ppt-visual-style`：个人课件视觉风格规则。
- `codex-skills/interactive-courseware`：Codex 交互课件流程，与根目录 WorkBuddy 版本分别保存。
- `plugins/ppt-native-animator`：自研 PowerPoint 动画插件源码、配置、三项配套技能及测试。

下文「技能清单」统计仅指根目录 WorkBuddy 自建技能（现有 4 个），不含 codex-skills 与 plugins。第三方市场技能、系统插件、密钥、授权配置、缓存及运行产物不在本次备份内。`backup-manifest.json` 记录本次各文件校验值及来源目录。恢复时分别复制到对应宿主的技能或插件目录，凭证另行配置，不从本仓库恢复。

---


## 一、技能清单

本仓库共备份 4 个技能，全部由本人从零编写。安装来源的技能不入库，名单与介绍见[第三节](#三安装来源的技能3-个)。

| 技能 | 来源 | 一句话用途 | 体积 | 文件数 |
|---|---|---|---|---|
| [`lesson-typeset`](#1-lesson-typeset--文档排版引擎) | 自建 | 按固定版式把教学设计、逐字稿、学习清单、制作笔记排成 Word | 1.1M | 40 |
| [`lesson-transcript`](#4-lesson-transcript--逐字稿编写与审核) | 自建 | 照设计与课件逐页写课堂逐字稿，并做「设计—课件—时间」三方对读 | 60K | 5 |
| [`interactive-courseware`](#2-interactive-courseware--交互课件制作流程) | 自建 | 把「讲不清长什么样」的知识点做成单文件离线交互课件 | 52K | 5 |
| [`xhs-lesson-notes`](#3-xhs-lesson-notes--小红书备课笔记文案) | 自建 | 写小红书语文课件推广笔记，含对标拆解与合规自检 | 36K | 2 |

四个技能覆盖「写稿 → 排版 → 交互化呈现 → 对外传播」的链路，彼此职责不重叠：`lesson-transcript` 只产 Markdown 源稿，`lesson-typeset` 只负责把源稿排成 docx。

---

## 二、技能详解

### 1. `lesson-typeset` — 文档排版引擎

**做什么**：把 Markdown 源稿按预设版式渲染成符合交付标准的 `.docx`。四类文档各有独立规范，参数互不套用，避免规则打架。

> **2026-11-06 已统一化**：7 份按文档类型拆开的规范合并为 `references/unified-spec.md` 一份，8 支引擎收敛为唯一入口 `scripts/typeset.py` ＋内部 `scripts/renderers/`；成品名由源稿自动推导、原子覆盖、旧版进废纸篓。下表是统一前的分类沿革，**现行版式参数一律以 `unified-spec.md` 为准**。

| 文档类型 | 规范版本 | 关键版式 |
|---|---|---|
| 教学设计 · 开放式 | V2.0 | A4，上 28 / 下 20 / 左右 23mm，164mm 版心；标题思源黑体 + 正文楷体；六边全框线表格配浅绿表头 |
| 教学设计 · 表格式 | — | 整篇一张表，教学过程固定四列（活动名称 / 教师活动 / 学生活动 / 设计意图），参数自成一套 |
| 教学设计 · 全表格式 | V2.0-T | 第三套并列骨架，以表格为主要结构。**须点名启用，引擎尚未实现** |
| 逐字稿 | V1.1 | A4 单栏连续排版，162mm 版心；逐页标题左标题右时间；师 / 生 / 提示靠字重与灰度分层 |
| 学习清单 | V2.1 | 课堂配套练习纸；真线段书写横线、18mm 田字格、四列三星自评 |
| 制作笔记 | V1.0 | 说明性文档；一级标题上细线、浅绿强调块、图片配 9.5pt 图注 |

**支持能力**：页眉 30×12mm Logo 区三种形态（实图 / 虚线占位框 / 隐藏留位）、双面装订镜像边距、跨页重复表头、页码域。

**目录结构**

```
lesson-typeset/
├── SKILL.md                    路由表 + 五类文档流程 + 引擎实现约定
├── references/                 六份独立版式规范，一类一份，互不引用
│   ├── jxsj-spec.md            教学设计 · 开放式 V2.0
│   ├── table-spec.md           教学设计 · 表格式
│   ├── table-v20t-spec.md      教学设计 · 全表格式 V2.0-T
│   ├── zjg-spec.md             逐字稿 V1.1
│   ├── xuexqingdan-spec.md     学习清单 V2.1
│   └── zhizuobiji-spec.md      制作笔记 V1.0
├── scripts/                    七个 Python 排版引擎
│   ├── jxsj_typeset.py         教学设计（开放式）
│   ├── table_layout.py         表格式排版底座
│   ├── jxsj_legacy.py          表格式底层构件来源，不可删
│   ├── zjg_typeset.py          逐字稿
│   ├── xuexqingdan_typeset.py  学习清单
│   ├── zhizuobiji_typeset.py   制作笔记
│   └── ppt2png.py              课件转图（逐字稿用）
└── .archive/                   2026-11-04 至 11-05 的版式迭代存档
```

**使用要点**：一次只排用户点名的那一份文档，不顺手重排同课其他文件。改内容只改 Markdown 源稿，不动脚本。

---

### 2. `interactive-courseware` — 交互课件制作流程

**做什么**：把「学生想不明白它长什么样、课上又没法做对照」的知识点，做成**单文件、离线、可投屏**的 HTML 交互课件。整个文件拷进 U 盘就能上课，不依赖网络和安装。

**前置闸门**：两个条件必须同时成立才做——学生脑子里转不起来这个对象、课堂上没有办法做对照实验。任一条不成立就直接不做，避免把每个知识点都硬做成 3D。

**七阶段流程**

| 阶段 | 动作 | 卡点 |
|---|---|---|
| 0 选题闸门 | 书面回答两条标准 | 任一为否 → 不做 |
| 1 定形态 | 确定是球体、剖面、流程箭头还是场线 | 说不出形态 → 退回 0 |
| 2 出提示词 | 让模型先写制作提示词，不碰代码 | 缺页码方向约束 → 重写 |
| 3 生成 v1 | 参照 + 清单 + 要求三件套给齐 | 知识点与教材不符 → 退回 2 |
| 4 返工 · 真 | 改结构而非调参数，任意角度都成立 | 只在正面成立 → 继续改 |
| 5 返工 · 用 | 任务链 + 分层提示，关卡顺序＝板书顺序 | 只需一路点下一关 → 重做 |
| 6 交付校验 | 单文件、无外链、体积可控 | 存在 CDN 外链 → 阻断交付 |

**附带资产**

```
interactive-courseware/
├── SKILL.md                    七阶段 + 三张检查清单 + 反面清单
├── references/
│   ├── prompt-patterns.md      三件套模板、五关任务模板、三层提示模板
│   └── subject-matrix.md       学科对照表、六科「要关掉的变量」、可做/不可做速查
├── assets/
│   └── single-file-skeleton.html   可运行骨架：5 种题型、三层提示、双模式
└── scripts/
    └── check_offline.py        扫外链与 CDN、统计内联媒体、体积告警
```

**两种核心机制**：关卡顺序对齐板书顺序，不另造学习路径；分层提示——点一次给思路，连错两次才放答案，且看答案不等于过关。

---

### 3. `xhs-lesson-notes` — 小红书备课笔记文案

**做什么**：写语文课件、教案产品的小红书推广文案。定位不是卖货话术，而是**教师对教师的备课笔记**，可信度来自可复用的备课价值。

**三种输出形态**：分课时、整篇合发、总述式短帖。

**内置方法**

- 对标拆解六块法（＋1 个可选扩展块）
- 三套版式骨架公式
- 语言规范（必须项 / 禁止项）
- 体量数据与合规自检清单
- 《颐和园》《秦兵马俑》定稿作为 few-shot 示例

**迭代机制**：用户提供新对标帖或多篇爆款文案后，走「拆解 → 出改良稿 → 列拟固化条目 → 用户确认 → 固化进技能」循环，越用越准。

**不适用**：正式教案、逐字稿、学习单等内容创作。

```
xhs-lesson-notes/
├── SKILL.md                十一节：定位、流程、拆解方法、骨架、语言规范、合规自检
└── references/
    └── examples.md         定稿示例
```

---

### 4. `lesson-transcript` — 逐字稿编写与审核

**做什么**：照已确认的教学设计与成品课件，逐页写教师能直接照读的课堂逐字稿；也能反过来查已有稿子——课件页数、页面问句、课后任务、板书条数、每页时长对不对得上。

**唯一标准**：`references/script-spec.md`（用户定稿 V1.0，二十三章），涵盖角色定位、材料冲突处理（只列不改）、对齐设计与 PPT、教师语言与学生预设、提问与评价、活动实施、时间控制、衔接过渡、操作提示、多课时、输出结构、制作前核对、A–G 七类审核清单、问题修复规则、20 条红线、7 条验收标准。

**执行层**：`references/audit-playbook.md` 把「严格对应」落成可重复动作——抽课件文字 → 抄活动分钟表 → 建「环节／活动／课件页／稿页起止」对应表 → 跑校验 → 按四要素（位置／现象／依据／建议）报问题。

| 脚本 | 作用 |
|---|---|
| `scripts/pptx_text.py` | 只读 pptx 包内 XML，逐页抽文字与备注，作为对读底稿 |
| `scripts/audit_script.py` | 查页号连续、时间轴无断点、总长＝课时、每页落在设计的活动区间、页内自述“约 N 分钟”是否超时、配图张数＝页数 |

**产出**：`.workbuddy/<课文>-<课时段>-逐字稿-源.md`，语法与 `lesson-typeset` 完全对齐（`## 第 N 页 · 标题｜起—止`＋`师：/生（齐）：/〔操作〕/〔学生可能说〕/〔板书〕`），排版交 `lesson-typeset` 自动配 `pNN.jpg` 截图。

**不适用**：排版版式（归 `lesson-typeset`）、改教学设计、改课件、调 PPT 页序。

实测：《牛和鹅》两课时各 18 页课件、40 分钟，查出并修正 8 处不对齐（环节内活动分钟自造、课件四问只答三问、课后任务少一项、板书三条只写两条、课件“捉／提”错字），复校 15／13 页、各 18 图、时间轴 0:00→40:00 连续。

```
lesson-transcript/
├── SKILL.md                        边界、四段工作流、源稿契约、时间算法、只审不改
├── references/
│   ├── script-spec.md              唯一标准（V1.0，二十三章）
│   └── audit-playbook.md           对读与时间核算操作规程
└── scripts/
    ├── pptx_text.py                逐页抽课件文字与备注
    └── audit_script.py             时间轴／活动归属／配图校验
```

---

## 三、安装来源的技能（3 个）

技能面板显示「技能（7）」，其中 4 个自建、3 个是安装来的。**安装的三个均不入库**，此处只作登记，便于换机时知道该补装什么。

> 专家包与插件不在此列。它们不是独立技能，由专家中心与插件市场分发、随应用更新，无法从本仓库恢复。

### 3.1 逐个登记

#### `teachable-figures` — 教学图示

把课文、章节或技术概念转化为**可教学**的图示：学习者先预测结果，再改变条件，观察变化，最后解释原因。支持 2D 交互组件、等轴测 SVG 对象、机械装配与剖视图，概念需要空间运动才能说清时可生成真正的 3D 可旋转模型。不适用于数据图表、仪表盘、幻灯片、静态插画与整门课程。

- **版本 / 来源**：0.3.0 / GitHub 仓库安装（`ywEdAi/teachable-figures`，MIT）
- **上游 commit**：`1acdd97`（2026-11-02）
- **能做什么**：遵循 predict → try → explain 教学法；保留宿主应用的课程约定与无障碍要求；默认先做一轮简短访谈再动手。内含 15 个双语示例课、两套 vendored 渲染工具包（`anatomy`、`iso-figure`）与 HRA 人体网格数据
- **触发场景**：教学图示、交互式图解、机制演示、可旋转模型、把课本插图做成能操作的、等轴测图
- **不入库原因**：本地文件与该 commit **逐字节一致、零改造**，重装即可完整复原，归档进个人仓库没有版本价值
- **恢复方式**：见[第五节](#五在新机器上恢复)的第三方技能恢复命令

> 注意：该技能内的 `references/source-manifest.json` 含一段 `local_modifications`，记录的是**上游作者**融合 anatomy 与 iso-figure 时的改动，不是本地改动。看到 `local` 字样不要误判为本地二次开发。

#### `ima-skills__skillhub` — IMA 知识库

统一的 IMA OpenAPI 技能，负责笔记管理与知识库操作。

- **版本 / 来源**：1.1.10 / 技能中心安装（`source: skillhub`，ownerId 526443）
- **发布方**：腾讯 IMA 官方
- **能做什么**：把本地文件、网页链接存入知识库；检索知识库内容；浏览、创建、编辑笔记。既支持明确的知识库操作，也支持「帮我记一下」「搜一下知识库里有没有」这类口语化指令。
- **触发场景**：知识库、资料库、笔记、备忘录、记事、上传文件到知识库、网页收藏、知识搜索
- **不入库原因**：官方发布的通用工具，上游可随时安装最新版，且归档进个人仓库无版本价值
- **恢复方式**：从技能中心重新安装

#### `totorosir-workbuddy-checkin` — WorkBuddy 签到助手

WorkBuddy「Buddy 加油站」的每日签到自动化，接口直签，跨 Windows / macOS / Linux。

- **版本 / 来源**：3.1.7 / 插件市场安装（`source: marketplace`，author: totorosir，skillId `skill_2095648441769295872`）
- **发布方**：第三方作者 totorosir
- **能做什么**：自动完成每日签到并领取积分。三通道自动择一——本机登录态可用时零配置直签；本机无法解密登录态（如 macOS）时走一次性网页授权；也可先保存长效令牌，之后由脚本自动续期，客户端不开也能签。附带「派猫猫旅行」自动闭环、桌面通知，以及钉钉／飞书／企业微信／微信等 12 类渠道的推送。
- **触发场景**：每日签到、自动领积分、派猫猫、签到结果推送、登录态失效、需要授权
- **不入库原因**：第三方作者维护，内容归属他人
- **恢复方式**：从插件市场重新安装
- **安全提示**：它的凭证存放在 `~/.workbuddy/checkin-cred.json` 与 `checkin-rt.json`，位于技能目录**之外**，因此无论是否备份都不会进仓库。部分脚本可能被复制到 `~/.workbuddy/scripts/`，换机时需重新授权。

### 3.2 判断一个新技能是否该入库

按以下四条依据判断来源，命中任意一条即视为第三方，应追加到 `.gitignore`：

1. 目录下 `_skillhub_meta.json` 的 `source` 字段为 `marketplace` 或 `skillhub`
2. `_meta.json` 含 `ownerId`（技能中心发布者标识）
3. `SKILL.md` frontmatter 的 `author` 不是本人
4. 存在 `references/source-manifest.json` 且指向外部仓库

命中后还须做一步实证：把上游仓库拉到临时目录，与本地逐字节比对，确认改动量。**不要只读 `source-manifest.json` 的 `local_modifications` 就断定有本地改造**——那段文字可能出自上游作者之手。`teachable-figures` 就是因此被误判过一次。

---

## 四、仓库结构

```
~/.workbuddy/skills/                 ← 仓库根目录
├── README.md                        本文件
├── .gitignore                       排除第三方技能、缓存、凭证与产物
├── lesson-typeset/
├── lesson-transcript/
├── interactive-courseware/
└── xhs-lesson-notes/
```

### 忽略规则覆盖范围

| 类别 | 内容 |
|---|---|
| 第三方技能 | `/ima-skills__skillhub/`、`/totorosir-workbuddy-checkin/`、`/teachable-figures/` |
| 编译缓存 | `__pycache__/`、`*.pyc`、`*.pyo` |
| 凭证类 | `*.env`、`*-cred.json`、`*-rt.json`、`*.key`、`*.pem` |
| 运行时标记 | 根目录 `*_migration.json`（应用自动生成） |
| 排版产物 | `/output/`、`~$*`、`*.log`、`*.tmp` |

---

## 五、在新机器上恢复

```bash
# 1. 确保 SSH 密钥已配置（本机已有 ed25519 密钥，无需重新生成）
ssh -T git@github.com

# 2. 克隆到技能目录
git clone git@github.com:mu-shan-beep/workbuddy-skills.git ~/.workbuddy/skills

# 3. 若技能目录已存在，改为先备份再拉取
mv ~/.workbuddy/skills ~/.workbuddy/skills.bak
git clone git@github.com:mu-shan-beep/workbuddy-skills.git ~/.workbuddy/skills

# 4. 第三方技能不在此仓库内，按第三节的登记逐个补装
```

第三方技能恢复命令：

```bash
# teachable-figures（GitHub 仓库，零改造，可直接完整安装）
git clone https://github.com/ywEdAi/teachable-figures.git /tmp/tf-install
rsync -a --exclude='.git' /tmp/tf-install/ ~/.workbuddy/skills/teachable-figures/
rm -rf /tmp/tf-install

# ima-skills__skillhub、totorosir-workbuddy-checkin
# 分别从技能中心、插件市场重新安装
```

恢复后重启 WorkBuddy，技能列表才会刷新。

---

## 六、维护约定

- **提交粒度**：一次改动一个技能，提交信息写清「改了哪个技能的哪个文件、改了什么」，禁止使用 `update`、`fix` 这类无信息量的词。
- **强制流程**：修改技能内容一律走「先出效果 → 用户确认 → 再固化进 `SKILL.md` 与 `scripts/`」，不得边改边写。
- **自动备份**：每日 23:30 检查变更，有改动则提交推送，无改动不产生空提交。
- **推送失败**：只报告原因，不使用 `--force` 强推。

---

_最后整理：2026-11-06_
