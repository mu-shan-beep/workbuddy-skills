# PPT 原生动画助手

这是一个本地 Codex 插件，用代码读取 PowerPoint 的结构与图层，把精简结构和教师教学节点交给大模型设计教学动画，再由确定性代码校验并写入可编辑的原生动画。规划阶段不批量渲染页面；写入后必须完成结构审计，并对高风险页面在目标 PowerPoint 或 WPS 中抽查播放。插件不覆盖原文件。

测试或回归时必须先将用户原始 PPT 复制到独立测试目录并校验哈希；结构分析、动画写入和审计只处理测试副本，禁止直接写入原文件。

运行环境需要 Node.js、系统 `zip`/`unzip` 和 `officecli`。源文件与成品都要通过 OfficeCLI 的 OpenXML 结构校验；如果原课件本身存在无效动画结构，先修复源文件再重新规划，不继续叠加动画。

## 推荐：大模型规划流水线

1. 先校验源文件，再准备结构包、视觉模块、教学节点模板和模型方案模板：

   ```bash
   node scripts/prepare-model-analysis.mjs "课件.pptx" --output-dir "课件-动画分析"
   ```

2. 从通过的页面矩阵、大纲或逐字稿先填写 `teaching-cues-template.json` 中每页的授课目的。`visualInspectionRequired` 页只渲染选定的小预览，核对无文字图片的含义并填入 `visualReviews`。大模型读取精简的 `model-brief.json` 和教学目的，编辑 `model-plan-template.json`。阶段 ID 确定后，再把每个教师点击节点及其课堂理由写入 `teacherClickBeats`，并为刻意保持静态的教学内容填写 `keepStatic`：

   - 真人课堂默认使用 `classroom-controlled`：首个情境可自动出现，后续提问、任务、讨论、证据、答案和结论可由教师点击控制；同一教学节点内部同时出现。
   - 自动微课使用 `microcourse-auto`，需要用户明确授权无人值守播放。
   - `initial` 只表示打开页面时已经可见，不会写入动画时间轴；教学模式下必须说明理由、只能连续出现在最前面，且不能成为页面唯一的阶段。
   - 所有点击阶段必须注明教学角色和停顿理由；答案还必须关联前面的题目阶段。
   - 同一文本框中的题目与答案位于不同段落且结构允许时，大模型可以通过 `paragraphIds` 让题目自动出现、答案点击出现。
   - 色块、卡片、图片和其承载文字作为完整视觉模块编排。
   - 每个可动画模块必须进入一个阶段，或者附理由标记为静态。
   - 源文件的每一页都必须保留在方案中；没有元素入场动画的页面也要执行翻页策略。
   - `after_previous` 表示等待上一阶段结束，`with_previous` 才表示同时开始。
   - 有提问且有教学图片、图表或组合图的页面，方案必须标明问题与视觉材料的关系：需要先看到、无关，或教师有意先猜后看。无关和先猜后看必须说明理由。
   - 受保护媒体页面在结构阶段直接标记为保留，不把注定跳过的内容交给模型设计。
   - 原动画中的功能性遮罩退出会转换为 `reveal-mask` 模块，由模型决定揭示时机并使用 `fade-out`。
   - 每页默认使用简洁的淡化翻页；只有受保护媒体时序存在风险，或用户明确允许时，模型才能选择无翻页动画，并必须写明理由。

3. 将模型方案编译为不可歧义的执行方案：

   ```bash
   node scripts/compile-model-plan.mjs "课件.pptx" "模型动画方案.json" --teaching-cues "课件-动画分析/teaching-cues-template.json" --output "可执行动画方案.json" --allow-replace-existing
   ```

4. 写入临时文件，强制执行文件有效性、结构完整性、覆盖率、性能预算和完整动画审计；全部通过后才发布正式输出。替换原动画时会清除所有旧时间轴，审计同时查找遗漏目标和计划之外残留的目标：

   ```bash
   node scripts/apply-animation-plan.mjs "课件.pptx" "可执行动画方案.json" --original-source "客户原稿.pptx" --output "课件_动画版.pptx"
   ```

5. 在目标 PowerPoint 或 WPS 中抽查动画对象最多、同时擦除最多、含媒体和含点击揭示的高风险页面。

写入成功后只生成一份动画版 PPTX，并在旁边保存 `.animation-audit.json`，记录原稿、模型方案、教学节点和审计结果。实际播放检查单独标为未验证，直到在目标软件中完成抽查。

正式编译要求留存模型方案与教学节点；写入前会核对两者未被替换。静态教学内容必须在节点文件里写明课堂理由。受保护媒体页整页保留，成稿还要与客户原稿比较视频、音频文件和播放时间线；不能把清理过动画的中间副本当作原稿。

教学顺序检查会阻止实验结论、推导公式或例题解析提前出现；检查照片与说明是否分离、同组卡片是否漏项、原本有动画的教学视觉是否未经说明变为静态，并拦截未填写的教学占位文字。母版说明页和目录页不按课堂结论页处理。

观察性问题有“可见前提”检查：例如问学生“这是吉普车还是汽车”，对应图片必须在问题出现前或同时可见。含多张图片、图表或组合图的提问页也必须由模型判断依赖关系，不能跳过。小而关键的图片会进入选定页面预览。模型可用 `requiresVisibleModuleIds` 声明其他图片、图表或文字前提；确需先猜后看图时，须在方案和教学节点文件的 `deferredVisualQuestions` 中分别说明教师意图。

审计会模拟每个教学节点和每次教师点击后可见的元素，识别前景遮罩盖住的内容，并检查答案、证据和结论的先后；图片与问题虽在同一点击阶段，但有错开间隔、延迟或遮罩尚未退场时也会被拦截。同时把成品的动画时间线与可执行方案逐字比对，防止形状虽然都带动画但实际点击顺序错误。完整逐点击记录只写入 `.animation-audit.json`，终端默认输出简短摘要。实际 WPS 或 PowerPoint 播放仍需抽查。

本版更新了内容识别规则，结构缓存已升级；旧版 `structure-full.json` 不能继续用于编译或增量复用。重新执行结构分析后再规划动画。仅凭文件格式和目标数量通过校验，仍不能代替对教学节奏的检查。

0.3.4 保留源文件中的全部重叠重复形状，并把重复内容绑定为同一动画模块；段落动画使用包含空白段落的原始 OOXML 编号，审计按段落判断题答可见性。页码按 `presentation.xml` 的实际顺序读取，内部文件名不再等同于课堂页码。性能预算按同一次点击下时间区间的峰值并发计算，包含跨阶段的 `with_previous` 和错开播放。

编译和应用结果会分别报告方案总阶段、初始可见阶段、实际动画阶段、自动阶段、点击答案阶段、动画目标数、动画页数和仅转场页数，避免把“初始可见”误计为动画。

模型方案不能直接写 OOXML，也不能自行声明用户授权。替换原动画、取消翻页或无人值守播放等授权只能通过编译命令的外部参数传入。编译阶段会核对源文件指纹、逐页完整性、模块/段落覆盖率、元素编号、模型答案判断与理由、重复目标以及文字与底板关系，错误方案不会生成 PPT。代码负责结构安全，不替大模型决定内容语义或动画设计。

为降低 token 与处理耗时，模型默认读取压缩结构；仅在无文字教学图片或关系不清的页面读取选定小预览。修改课件时只重新规划变动页面。完整元素清单和原动画逐目标明细不进入常规模型上下文。

解析器按照 PowerPoint `spTree` 的原始顺序记录真实 `zIndex`，同时记录填充、透明度、组合对象和前景遮罩关系。模型只决定教学阶段；元素坐标、层级、底板绑定、重复版式、原动画保护、OOXML 写入和成品审计全部由本地代码处理，以降低 token 消耗并避免视觉结构被重建。

动画只允许改变元素的出现时机和进入效果，不得修改坐标、尺寸、旋转、裁切、填充、组合关系或层级顺序。底板与其承载的文字/图片必须作为同一视觉模块同时出现；关系不确定时保持静态。任何页面结构差异都会使审计失败。

## 内置 Skills

- `ppt-native-animation`：完整流程和统一入口。
- `ppt-animation-planner`：只负责分析页面和设计、编译动画方案，不写入 PPT。
- `ppt-animation-auditor`：只负责比较源文件、成品和方案，默认不修复文件。

## 快速使用

下面的预设流程只用于草稿预览和兼容测试，不能代替正式模型规划。

1. 生成动画方案：

   ```bash
   node scripts/create-animation-plan.mjs "课件.pptx" --preset auto-teaching --output "课件_动画方案.json"
   ```

2. 审阅同时生成的结构化 HTML 方案文件；其中不包含页面图片。

3. 确认后仅作草稿测试，必须显式添加 `--allow-fallback`：

   ```bash
   node scripts/apply-animation-plan.mjs "课件.pptx" "课件_动画方案.json" --output "课件_动画草稿.pptx" --existing replace --allow-fallback
   ```

4. 校验：

   ```bash
   node scripts/validate-presentation.mjs "课件_动画版.pptx"
   ```

## 预设

`minimal`、`microcourse-auto`、`classroom-controlled`、`classroom-step`、`question-answer`、`text-reading`、`process-diagram`、`data-analysis`、`visual-story`。

`auto-teaching` 会根据每页内容自动选择上述预设。

若源 PPT 没有变化，但需要重新设计指定页面的教学节奏，可在增量分析和合并时使用相同的 `--redesign-slides` 参数：

```bash
node scripts/prepare-incremental-analysis.mjs CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json --redesign-slides 8,10,36 --output-dir incremental
node scripts/merge-model-plan-patch.mjs CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json PATCH_PLAN.json --redesign-slides 8,10,36 --output FULL_MODEL_PLAN.json
```

增量合并保留 `targetApplication` 等全局设置。改变授课模式、预设或全局动画策略时，必须重新规划全部页面，避免旧页面在未复核的情况下继承新的默认值。

## 测试与发布

`npm test` 默认运行单元测试及真实 PPTX 包回归。包回归通过 OfficeCLI 在临时目录创建小型课件，验证空白段落题答揭示、重复答案同步、重排页序及非数字内部文件名、WPS 设置继承、跨阶段并发和错误目标拦截。测试会编译计划、写入原生动画、执行完整审计，并独立检查成品目标；不会操作用户课件。`npm run test:unit` 可单独运行快速单元测试。

发布前先让 `package.json` 与插件清单使用相同的新版本号，再执行 `npm test` 和 `npm run release:manifest`，生成完整发布文件哈希。安装后在新安装目录执行 `npm run release:verify -- --against /path/to/source/ppt-native-animator`，同时验证安装文件与源目录，防止同版本缓存遗漏源代码更新。

## 当前范围

当前稳定支持淡入、擦除、遮罩淡出揭示、按段落显示、单击触发、与上一动画同时以及上一动画之后。动画总体保持简洁克制，以帮助理解内容为标准；具体内容动画的效果、顺序和节奏由大模型依据页面内容和教学节点决定。真人课堂允许教师在提问、任务、讨论、证据、答案、结论等教学节点单击控制；自动微课才连续播放。编译器根据 PowerPoint 或 WPS 目标环境限制每页动画对象、同时播放对象、擦除数量和大面积擦除。每页默认使用统一淡化翻页，只有用户明确允许时才可取消。插件会识别跨页重复的品牌字、导航和页脚并保持静止；承载文字的色块、卡片、标签底板和图片容器会与内部文字绑定为同一动画模块；原动画中承担揭示功能的前景遮罩会转换为受保护的淡出模块。主流程在外部授权后删除原有视觉动画并由大模型重新设计；受保护的音频、视频页面在分析阶段直接标记为整页保留。
