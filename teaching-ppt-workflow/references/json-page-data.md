# JSON 页面数据与单页请求

本页维护既有绘图环节的数据机制，不另建工作流或确认阶段。JSON 是整套课件的单一页面数据源；单页提示词告诉绘图模型画什么。执行次序见 [实际请求审核](visual-planning.md#发送绘图调用前)，确认点仍见 [教案包流程](lesson-pack.md)。

## 唯一数据与定稿绑定

复用现有 `pages.json` 或页面矩阵，补齐字段，不并行维护另一套文案。项目级保存 `project_id`、`source_revision`、`pages`；每页保存唯一 `page_id`、`title`、`visible_text`（含标题的完整首屏字符串数组）、`deferred_text`（各项含 `text` 与 `trigger`）、`teaching_task`、`composition`、`style`、`references`、`output` 和 `review`。`output` 含 `aspect_ratio` 与 `format`；课堂页沿用既定 16:9、PNG 要求。

每页的 `source_binding` 把文案绑定到已确认的大纲源件：

| 字段 | 取值与核对 |
|---|---|
| `path`、`sha256` | 定稿 UTF-8 文本的真实路径及文件字节 SHA-256；相对路径按 JSON 所在目录解析 |
| `page_span` | 本页原文的 `[起点, 终点]` 字符区间，左闭右开；从原件读取后定位，不能猜页序 |
| `visible_spans` | 与 `visible_text` 逐项对应的字符区间，全部须在本页区间内；保留原字、标点、注音与换行 |
| `deferred_spans` | 与后显文案逐项对应的原文区间；不进入首屏提示词 |
| `confirmation` | 现有确认记录中的 `quote` 与 `at`；不得自造确认，不新增一次确认 |

绑定由助手根据原稿建立，用户无需手填字符位置。首次建立时实际核对本页范围与首屏／后显分工是否完整；脚本不能识别选区遗漏或判断确认原话是否真实。之后每次提取都核源件指纹，并将每项 JSON 文案与对应原文逐字比较；仅填版本名或声称“已锁定”不算绑定。原件或选区改变后重新核采用版本，不为兼容旧绑定重画已有采用页。

`references` 各项包含 `path`、`role` 和 `use`：`style` 延续视觉语言，`material` 核教材人物或事实素材，`layout` 还原本页获批构图。先实际看图，核用途和采用状态；多页总览先隔离当前页。工具记录附件顺序与实际字节指纹，保留文字、构图、画风的职责分工，不以整页旧图替代当前页设计。

## 单页提取与最终工具参数

在本技能目录运行；路径替换为当前项目，过程文件放已有工作资料区。

```bash
python3 scripts/page_request.py prepare --pages /项目/pages.json --page-id L02-P03 --request /项目/current-request.json --call /项目/tool-args.json
python3 scripts/page_request.py audit --pages /项目/pages.json --page-id L02-P03 --request /项目/current-request.json --call /项目/tool-args.json
```

提取只读当前页。完整首屏文案、教学任务、独立构图、画风、附件用途及输出规格组成独立提示词；其他页、后显答案、验收状态和批次信息不发送给绘图工具。工具拒绝重复 JSON 键、重复页号、缺字段、失效源件、文案与原文不符、缺附件，以及审核后改变的数据或请求。

项目可用 `tool_mapping` 配置当前工具的真实字段：`prompt_key`、`attachments_key`、`options`。缺省映射为本环境图片工具的 `prompt` 与 `referenced_image_paths`；WorkBuddy 或其他工具须先核实际能力和参数，按需设置映射，不能猜接口。选项不得覆盖文案及附件，不能自动附带未登记的历史图片。`prepare` 同时生成请求记录和可直接提交的 `tool_arguments`，省去再次编写提示词。

`audit --call` 将**准备实际发送的完整参数对象**与 `tool_arguments` 比较，错文案、错图、附件次序变化或额外参数均拒绝。执行环境支持时直接读取同一个参数对象调用工具；否则逐项核对实际调用内容，不缩写、不重组。检查后改动即重审。此脚本不拦截工具调用，只有参数文件接受检查但未用于真实调用时，不能宣称实际调用已核验；隐藏上下文也不虚称已隔离。

## 生成与验收写回同一 JSON

实际提交后，马上在当前页 `review` 记录请求路径、指纹、真实调用标识（若工具提供）及待返回状态。收到返回后先登记实际文件，再按原有两轮图片检查核验；把问题、检查结果和下一步写回当前页，不只在聊天中说“完成”。

结果记录包含 `page_id`、请求中的 `source_sha256`、`status`、`output_file`、`checks` 与 `issues`。状态使用 `pending`（待返回／待核）、`generated`（已返回未验）、`repair`（待修）或 `passed`（内部验收通过）。`checks` 每项包含 `item`、`result` 与具体 `evidence`；登记通过时还需实际 `reviewer`。基于真实观察填写，不让脚本自动评价画面。

```bash
python3 scripts/page_request.py record --pages /项目/pages.json --page-id L02-P03 --request /项目/current-request.json --result /项目/result.json
```

`record` 核请求与结果身份、文件存在及检查记录，原位写回本页 `review` 并保留 `history`；不改其他页或定稿文案。尚未返回可先记 `pending`，已返回记 `generated`；`repair` 须写具体问题，`passed` 须有真实文件、检查证据且无未解决问题。它校验记录完整性，不代替视觉验收。用户确认独立保存；请求内容变化时旧确认不继承，不把内部通过冒充用户确认。

继续任务先读同一 JSON，再核当前源件、已采用文件与待返回调用。待返回的先回查，验收通过的按实物复用，待修的带原问题恢复。若源件、请求或实际文件已变，旧记录不直接作为本次通过凭据；仍按现有失败次数、修改授权和阶段确认执行。

## 能力边界

没有文件或执行能力时，可用同结构 JSON 作为明确的接续数据，人工逐字核输入并写回可访问的记录；如实说明自动源件比对、最终参数检查或落盘哪项未执行。不得只依赖聊天上下文猜当前页，不建立第二份“权威”记录。

本机制负责内容准确传递、输入隔离、进度与验收记录。出图质量继续按原有流程核实；故障修复沿用当前工具、产物和授权，不借本机制新增交付物或改制作路线。
