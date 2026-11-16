---
name: seewo-easinote-assistant-skill
description: 希沃白板助手致力于协助教师高效创作优秀教学课件，通过本地 MCP 协议连接希沃白板 Windows 客户端，实现课件的新建、编辑、调整美化、云端同步及云课件管理等操作，覆盖备课制作、互动元素插入、课件调整优化等完整流程。仅当用户明确要求操作希沃白板，或需要创建、调整、美化课件时调用本技能；用户仅在讨论希沃白板相关话题、询问软件功能而未提出具体操作需求时，不应启用本技能。
---

# 希沃白板助手

根据用户当前任务选择一种模式，只读取该模式需要的资料。

## 路由

| 当前任务                   | 必须读取                                                                                                                                                                                                                                                                       | 按需读取                                                                                                                                                                                                                                      |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 新建课件                   | [references/creation_intake.md](references/creation_intake.md)、[references/subject_tool_guide.md](references/subject_tool_guide.md)、[references/visual_planning.md](references/visual_planning.md)、[references/page_structure_guide.md](references/page_structure_guide.md) | 教学目标阶段读 [references/curriculum_standards.md](references/curriculum_standards.md)；大纲设计阶段读 `references/subject_outlines/` 对应学科模板；当前课题确需精确 MCP 参数时读取 [references/capabilities.md](references/capabilities.md) |
| 调整已有课件               | [references/courseware_guide.md](references/courseware_guide.md)                                                                                                                                                                                                               | 需要精确 MCP 参数时读取 [references/capabilities.md](references/capabilities.md)                                                                                                                                                              |
| 连接或排障                 | [references/connection.md](references/connection.md)                                                                                                                                                                                                                           | 不加载新建课件资料                                                                                                                                                                                                                            |
| 本地 ENBX 校验、生成或同步 | 当前操作直接需要的最小资料                                                                                                                                                                                                                                                     | 不加载内容或视觉规划，除非正在新建课件                                                                                                                                                                                                        |

不要为“熟悉项目”一次性读取全部 references。

## 共同边界

- 用户素材、结构要求、极简要求和忠实复现要求优先于默认判断。
- 不复用旧课件、测试产物、固定页序、学科范例、主题池、课型骨架或候选构图。
- 只有实际访问希沃客户端时才要求 MCP 就绪；内容讨论和本地计划不以连接为门槛。
- 多个同名课件或多个候选 shell 导致目标不唯一时停止并确认，不能猜测。新建课件重导入时可关闭唯一精确同名 shell，但必须回读确认旧 shell 已消失后再打开新文件。
- MCP 返回成功后回读页数、元素或模式，不能把响应成功当成落地成功。
- 未经用户要求不云同步；终态保持备课（Edit）模式，不进入授课模式。

## 新建课件

按 [references/creation_intake.md](references/creation_intake.md) 的**四阶段检查点流程**推进，每个检查点先确认后前进、可编辑、可回溯：

1. **基本信息**：提取课题、学段、目的、页数区间（必须经用户确认：5-10 页默认、10-15、15-20、20-30，写入 `pagePlan.range`）、图片方案（写入 `imageStrategy`：`generated`/`provided`/`none`）与硬约束；
2. **教学目标**：先读 [references/curriculum_standards.md](references/curriculum_standards.md) 完成新课标对齐思考，用**宫格卡片**展示含素养指向与检测方式的目标条目（禁止表格，呈现规范见 [references/creation_intake.md](references/creation_intake.md)「对话内呈现规范」），用询问卡片确认；
3. **大纲设计**：先按 [references/subject_tool_guide.md](references/subject_tool_guide.md) 完成原生元素选型，再按学科读取 `references/subject_outlines/` 模板（语文/数学/英语读对应文件，其他学科读 `general_outlines.md`）改造为详细设计网格（**宫格卡片呈现，禁止表格**），用询问卡片确认；
4. **分段生成**：按环节分段充实 `pages.json` 并整体校验生成。

每次确认必须弹出询问卡片（AskUserQuestion）等待用户点击，不得以普通文本结尾等用户在终端回复；宿主无询问卡片能力时才降级为文本询问并说明降级。用户要求修改已完成检查点时回到该检查点，重做受影响的后续环节，不受影响部分保留。确认后面向用户只展示教学决策，不展示坐标、字号、内部字段或渲染术语。

每份新课件使用根级 `visualPlanning` 视觉计划（契约见 [references/visual_planning.md](references/visual_planning.md)）：

普通页由 AI 针对当前课题直接给出背景、图层、坐标、字号、颜色、裁切与内容绑定，并按需为需要图解的页面规划配图与图注——配图是可选增强而非每页标配，只有该页主题需要图来说明、描述、介绍或美化时才配，纯文字页、文本阅读页与课堂活动页保持无配图（决策与契约见 [references/visual_planning.md](references/visual_planning.md) 的「页面配图」）；每页先按 [references/page_structure_guide.md](references/page_structure_guide.md) 匹配一种结构类型作为组织逻辑起点（一页一结构、相邻页不重复），再自主决定具体几何；渲染器不得改选候选构图。原生元素页面遵守 [references/subject_tool_guide.md](references/subject_tool_guide.md) 的页面契约。

**文本少垫底**：标题与普通文本默认直接排布，禁止用 `shape` 色块做任何文字底板；`fill` 容器仅用于特定重要内容（核心问题、结论、答案、安全提示）或重要布局骨架（对比栏、定义框、分层卡等），`scrim` 仅作图片背景对比度兜底——完整规则唯一权威定义见 [references/visual_planning.md](references/visual_planning.md)，其他文档只引用不复述。

**形状与布局丰富度**：允许适当结合形状元素（`shape`：`rect` / `rounded` / `oval` / `line` / `arrow` / `triangle` / `callout`）创作并丰富页面——结构分区（分栏色带、对比栏底、卡片底）、视觉锚点（章节竖条、序号圆点、引导箭头、气泡）、装饰语言（同色系点缀）。页面布局避免单调，按 [references/page_structure_guide.md](references/page_structure_guide.md) 的「布局骨架」矩阵灵活使用左右分栏、上下分层、图文结合、中心聚焦、卡片流、时间轴、对比并置、围合式等几何排布，相邻页优先更换骨架、整册至少覆盖 4 种。形状红线不变：不做文字底板、不覆盖全画布；每页装饰形状建议 1–5 个、硬上限 8 个。

生成入口：

```powershell
python scripts/courseware/design/inspect_visual_blocks.py --spec pages.json
python scripts/courseware/build_v2.py --spec pages.json --require-images
```

Python 依赖见 `requirements.txt`（Pillow：图片预检与 `bgTone:"auto"` 自动实测；未安装时预检降级为扩展名检查、`bgTone:"auto"` 提取失败并报错，不影响其余功能）。慢机器可加 `--slow-mode`（全部等待节奏 ×2）。

正式生成必须完成计划和图片校验，原生生成不含全画布背景元素的整册 ENBX，在希沃客户端打开刚生成的文件并绑定其新 shell；普通页背景必须调用 `set_slide_background_image` 写入页面自身背景并回读确认，再叠加所需原生组件。客户端核对失败时修正计划或资源后重试，不得用全画布图片或色块元素回退，不得静默丢内容、丢图片或降低字号门槛。

原生背景或组件叠加中途失败且目标课件仍打开时，修正输入后使用 `build_v2.py --spec pages.json --resume` 续修。续修必须绑定唯一精确同名 shell、核对页数并回读现有元素；已存在项不得重复创建，状态无法确认时停止。

不得用结构 JSON、文本预览、本地 ENBX 文件或 PPTX 中间件冒充用户要求的希沃客户端课件。

## 调整已有课件

连接用户指定课件后先回读当前页和目标元素，再执行精确增删改。尊重原课件视觉语言；除非用户要求重做，不把新建课件的视觉规划强加给已有课件。

常用入口：

```powershell
python scripts/lifecycle/ensure_connected.py
python scripts/courseware/courseware_ops.py --port 7916 info
python scripts/courseware/courseware_ops.py --port 7916 edit-text --contains "原文" --fontSize 40
```

## 失败处理

校验、图片解码、客户端导入、原生组件回读或同步门禁任一失败时，在造成下一步外部修改前停止。说明失败阶段和可执行的修复，不使用占位图、旧课件、旧 shell 或视觉回退掩盖问题。
