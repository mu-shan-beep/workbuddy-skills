# WorkBuddy 自建技能库

本仓库是个人 WorkBuddy 技能的版本控制与备份存档，收录**自己创建与维护**的技能。

- **本地根目录**：`~/.workbuddy/skills/`
- **远程仓库**：`git@github.com:mu-shan-beep/workbuddy-skills.git`（私有）
- **主分支**：`main`

**收录原则：只备份自建技能。** 从技能中心、插件市场安装的第三方技能一律不入库，原因有二：上游可随时重新安装；内容归属他人，混入自有备份会模糊版本界限。判断依据与排除名单见文末「收录边界」。

---

## 一、技能清单

| 技能 | 一句话用途 | 体积 | 文件数 |
|---|---|---|---|
| [`lesson-typeset`](#1-lesson-typeset--文档排版引擎) | 按固定版式把教学设计、逐字稿、学习清单、制作笔记排成 Word | 1.1M | 40 |
| [`teachable-figures`](#2-teachable-figures--教学图示生成) | 把抽象概念做成可预测、可操作、可解释的教学图示 | 6.8M | 112 |
| [`interactive-courseware`](#3-interactive-courseware--交互课件制作流程) | 把「讲不清长什么样」的知识点做成单文件离线交互课件 | 52K | 5 |
| [`xhs-lesson-notes`](#4-xhs-lesson-notes--小红书备课笔记文案) | 写小红书语文课件推广笔记，含对标拆解与合规自检 | 36K | 2 |

四个技能覆盖「内容生产 → 可视化表达 → 交互化呈现 → 对外传播」的完整链路，彼此职责不重叠。

---

## 二、技能详解

### 1. `lesson-typeset` — 文档排版引擎

**做什么**：把 Markdown 源稿按预设版式渲染成符合交付标准的 `.docx`。四类文档各有独立规范，参数互不套用，避免规则打架。

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

### 2. `teachable-figures` — 教学图示生成

**做什么**：把课文、章节或技术概念转化为**可教学**的图示——学习者先预测结果，再改变条件，观察变化，最后解释原因。核心是让一个机制变得可见、可操作，而非画一张静态配图。

**支持的形态**

- 可复用的 2D 交互组件（widget）
- 可工作的等轴测 SVG 对象
- 机械装配、剖视图、爆炸图
- 概念需要空间运动才能说清时，生成真正的 3D 可旋转模型

**设计约束**：遵循 predict → try → explain 教学法；保留宿主应用的课程约定与无障碍要求；默认先做一轮简短访谈再动手，除非用户要求直接生成。

**不适用**：普通数据图表、仪表盘、幻灯片、静态插画、整门课程。

**来源说明**：基于两个 MIT 协议开源仓库二次开发，上游地址、commit、许可证与本地改动记录均写在 `references/source-manifest.json`：

- `wheresryan22/anatomy` → `assets/anatomy`
- `MrBongoC/ai-iso-skill` → `assets/iso-figure`

**目录结构**

```
teachable-figures/
├── SKILL.md
├── references/        12 份方法论文档 + 截图目录 + source-manifest.json
│   ├── learning-design.md        学习设计（写 spec 前必读）
│   ├── teaching-and-spec.md      教学法与规格
│   ├── rendering-selection.md    渲染方式选择
│   ├── simple-iso.md             等轴测工作流
│   ├── spatial-and-3d.md         空间与 3D
│   ├── mechanical-craft.md       机械结构
│   ├── verification.md           正确性与视觉保真校验
│   └── ...
├── assets/            6.4M，含 anatomy / iso-figure 素材与 HRA 网格数据
└── scripts/           构建与校验脚本
```

---

### 3. `interactive-courseware` — 交互课件制作流程

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

### 4. `xhs-lesson-notes` — 小红书备课笔记文案

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

## 三、收录边界

### 已收录（自建）

`lesson-typeset`、`teachable-figures`、`interactive-courseware`、`xhs-lesson-notes`

### 已安装但不入库（第三方）

以下两个技能装在本机，但属于第三方发布，**内容不在本仓库内**，此处仅作登记，便于换机时知道补装什么。

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

### 判断一个新技能是否该入库

按以下四条依据判断来源，命中任意一条即视为第三方，应追加到 `.gitignore`：

1. 目录下 `_skillhub_meta.json` 的 `source` 字段为 `marketplace` 或 `skillhub`
2. `_meta.json` 含 `ownerId`（技能中心发布者标识）
3. `SKILL.md` frontmatter 的 `author` 不是本人
4. 存在 `references/source-manifest.json` 且指向外部仓库

> 例外：`teachable-figures` 命中第 4 条，但本地改造已超出上游提供的内容范围，经确认后保留在库内，上游信息如实记录在 manifest 中。

---

## 四、仓库结构

```
~/.workbuddy/skills/                 ← 仓库根目录
├── README.md                        本文件
├── .gitignore                       排除第三方技能、缓存、凭证与产物
├── lesson-typeset/
├── teachable-figures/
├── interactive-courseware/
└── xhs-lesson-notes/
```

### 忽略规则覆盖范围

| 类别 | 内容 |
|---|---|
| 第三方技能 | `/ima-skills__skillhub/`、`/totorosir-workbuddy-checkin/` |
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

# 4. 第三方技能按需从市场重新安装，不在此仓库内
```

恢复后重启 WorkBuddy，技能列表才会刷新。

---

## 六、维护约定

- **提交粒度**：一次改动一个技能，提交信息写清「改了哪个技能的哪个文件、改了什么」，禁止使用 `update`、`fix` 这类无信息量的词。
- **强制流程**：修改技能内容一律走「先出效果 → 用户确认 → 再固化进 `SKILL.md` 与 `scripts/`」，不得边改边写。
- **自动备份**：每日 23:30 检查变更，有改动则提交推送，无改动不产生空提交。
- **推送失败**：只报告原因，不使用 `--force` 强推。

---

_最后整理：2026-11-05_
