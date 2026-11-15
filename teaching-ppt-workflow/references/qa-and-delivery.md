# QA and Delivery Checklist

Choose checks for the current output; do not turn an isolated task into a full-project audit. Necessary self-checks support the deliverable and do not require a separate report.

## Select checks by output

| Output | Check |
|---|---|
| Lesson plan or revision | Accurate sources, observable objectives, executable activities, aligned assessment, appropriate lesson capacity and requested format |
| Pure on-slide outline | Page order, complete student-facing text, staged answers; no teacher notes, internal timing notes, visual instructions, field labels or explanatory preface in the outline body. Needed reference-search keywords belong in a separate copy area; omit them when references are sufficient or only the pure outline is requested. |
| Style-reference analysis | Images actually inspected; concise reusable style description only; no unsolicited drawing, sample page, new keyword list or copied composition |
| Preview images | Drawing uses available references, reusable analysis, an approved direction/template, or explicit autonomous-design instructions; needed reference analysis may happen inside the drawing task. No repeated search/decomposition deliverable; independently organized lesson content, one verified full-resolution image per page from an original, source export or independent reconstruction; see [image source and readability checks](visual-planning.md#逐页选择制作方式) |
| Courseware production / existing PPT edit | Default deliverable is the Canva design link; produce an editable .pptx only when the user explicitly requests a deliverable pptx file. Never directly create an editable PPTX. New decks follow the Canva whole-image route; verify the actual saved design and link. File-integrity and media-preservation checks apply only to explicitly requested edits of an existing local PPT or a temporary image-only import container. |
| Verbatim script | Actual finished-deck page sequence (课件成品页序), natural spoken language, clear questions/transitions, realistic interaction and media time; hypothetical student replies labeled |
| Teaching-content review | Evidence-based problems with exact locations and actionable advice; use provided artifacts only, no mutations or technical audit |
| Materials analysis | Traceable confirmed requirements, useful source inventory, reference versus requirement distinction, only consequential open questions |
| Repaired Canva design | Correct copy, missing/duplicate/fragmented layers, edges and backgrounds, faithful redrawing, tested editability, actual saved result; see `canva-layer-repair.md` |
| Learning sheet | 按 [学习清单](teaching-resources.md#12-学习清单制作或修订) 核对已确认任务、实际作答载体、教材原句和主要任务的完成标准。用学生视角做一遍关键题，检查支架是否代答、不同材料是否重复要求同一产出。交 Word 时查看 A4 实际版面。 |
| Board image | Confirmed wording and relationships preserved, specified style and suitable ratio, readable knowledge structure rather than a decorated summary slide |
| Usage notes | 按 [制作与使用笔记](teaching-resources.md#14-课件制作与使用笔记) 核对采用成品、实际页序、备课材料和关键操作，按实际课件格式取证。查四部分结构、教师能否按说明使用、正文是否混入内审内容或课件入口。 |
| Whole-image assembly | Unchanged source image per page in numeric order and correct aspect ratio. Verify any approved delayed elements in presentation mode; see [assembly](teaching-resources.md#15-预览图整图组装) |
| Promotional poster or collage | Intended publicity format rather than a PPT cover; truthful resource claims; collages use actual unchanged slides and specified arrangement |
| Resource package | Only requested existing resources, correct versions and names, preserved source bytes, expected archive entries and successful integrity check; no unsolicited content review |

The remaining sections apply when their corresponding artifacts or features are in scope. Skip absent media, animation and linked documents rather than inventing work to fill a checklist.

**关键图片素材预检**。排版／交付整理第一步遵循 `lesson-typeset/SKILL.md` §1.0 和 `references/unified-spec.md` 2.5／2.5.1，运行 `check_assets.py` 并主动报告齐备情况及缺项影响。由该技能执行缺项处理与暂停条件。

Check the task boundary too: a standalone style analysis must not generate images, but a drawing request or an active full-production commission must not stop merely because there is no separate analysis document or the latest message only supplies requested materials. Respect explicit analysis-only or pause instructions.

## Content

- Confirm current topic, textbook edition/grade if known, period and canonical artifact before checking detailed content; a well-written resource for another lesson is still the wrong deliverable.
- Slide count and order match the approved outline.
- Section names, titles, key terms and quotations are consistent.
- 整套教案包逐项核对用词是否适合真实课堂及阅读对象：学生材料让相应年级读得懂、知道怎样做；教师材料自然、准确、能组织教学。清除误入课堂正文的制作、审查、委托沟通或宣传措辞，修正含糊口语、代词不明和给学生贴标签的表达；不机械删改正确术语或教材原句。
- Text is supported by customer instructions or source material.
- 新产出交付前检查是否带入教材页码：同时核对“第…页”、页码范围、P/p页码等表达，及从旧稿、教材截图或参考图继承的可见页码；改用课文部分、课后表格或关键语句定位。检查正文、表格、图片和备注，不将课号、课时、课件自身页序或文件自身页码误删。此项只约束后续产出，不自动回改已采用成果；教材来源页码保留在内部核对中。
- The provided questions, activities, conclusions and any assigned homework form a coherent learning path; do not invent additional activities merely to fill a structure.
- No obsolete placeholder, draft note or unsupported claim remains.
- A story-based completion statement corresponds to an actual student product, record or performance, not just an attractive ending scene.

## Cross-document synchronization

- 按 [权威维度裁决](lesson-pack.md#权威维度裁决单向从属的落地口径) 核对差异。教案提供已确认的课堂任务及顺序，现行课件成品提供讲稿与制作笔记的实际页序、上屏文字和操作依据。学生上屏标题可用课堂语言。发现冲突先定位来源，再依本次授权修订对应产物。
- **全流程同类全扫**：任一产物发现缺陷进行修复时，必须回查本阶段及关联阶段同类全部对象并实际代入验证（改动一处填空扫全课填空，改动一页上屏扫连续页与后续讲稿），严禁点状替换。
- 对同一课堂任务，逐项核对相关课件、清单和逐字稿的题干、作答动作、记录符号、呈现时机和达标标准。讲稿的提问、结论及媒体提示按实际课件核对。
- Classroom timing is plausible after adding discussion and media duration.
- Teacher language sounds natural and is not copied onto slides unnecessarily.

## Layout and visuals

- 避免把质检变成重复展示。已显示的同一图像可供两轮不同重点的实际复核；保存副本与生成原图一致时，以文件校验确认身份，不重复向用户输出整页。需要放大时只查看必要局部。生成PPT图中的局部字形不清、单字错漏等可手工修正问题，只标明页码、位置、问题与建议改法，状态为待用户修正，不自动重绘或覆盖原图；用户明确要求代修后才重新生成，并说明修改点；检查轮次不能靠重复工具调用或展示次数冒充。

- For preview-matched text repairs, compare font appearance, relative sizing, wrapping, baselines and title/page-number separation against the approved page. Geometric non-overlap alone is not visual verification.
- Official template, logo, footer and locked cover treatment are preserved.
- Titles, margins, alignment and type hierarchy are consistent.
- 每页字体不超过2种，整套不超过3种；优先微软雅黑、思源黑体、楷体等常用且目标电脑已安装的字体。原生课件检查真实字体与替代情况；图片样稿只按可见字形核对风格，真实字体家族标为未验证，不以提示词代替检查。
- Text is readable from classroom distance.
- Images are clear, proportionally cropped and relevant.
- PPT 样稿与正式页按 [视觉分镜、逐页绘图与验收](visual-planning.md) 核对原图、连续页和实际文件。保存、导入及交付时比对实际尺寸与清晰度。
- No object extends outside the safe area or overlaps another unintentionally.
- The page layout follows the actual reading or learning relationship: observation, comparison, process, practice or conclusion, rather than a repeated card/icon recipe.
- Titles and tasks say something concrete, without empty motivational or research-report language. Repeated design choices improve familiarity without making every page identical.
- Necessary source text and task conditions remain complete; do not hide a density problem by shrinking type or deleting key content.

## Media

- Distinguish a visible player frame, timer or reveal button from an implemented feature. Identify the real asset/control/animation and its behavior; static decoration does not pass a functional check. A missing feature can be reported without adding it when implementation is outside scope.
- Every linked or embedded file exists.
- Video and audio play in the target application.
- Poster frame and ending state are intentional.
- Playback duration fits the lesson plan.
- Fonts and codecs are compatible with the delivery environment where known.

## Animation

- Click order follows the teacher's sequence.
- Targets, groups and triggers are correct.
- No unexpected automatic playback occurs.
- Slides remain understandable if animation is skipped.
- Native-animation audit passes when an animation tool is used.

## File integrity

- PPTX opens without a repair warning.
- For a full-deck creation, global revision or formal complete-PPTX delivery, render all slides; for a bounded edit, render the changed and affected pages. Inspect renderer discrepancies in the target presentation app. A text-only review or preview-image task does not need this file-level gate.
- Representative slideshow playback has been tested, including changed animation, timer, audio or video behavior where applicable. Opening the file is not a playback test.
- Record each affected dynamic page as `已播放通过`, `播放失败`, or `未验证`, with the tested application; never report `未验证` as passed.
- Delivery filenames are clear and free of temporary suffixes.
- 图片交付前验证实际文件存在、可解码及尺寸/数量；ZIP实际打开并检查条目、完整性及内容与交付图片一致。文件可读与用户端可下载分别报告：本地检查不等于已验证用户下载。用户反馈无法下载时，先检查交付文件和当前有效的附件/下载入口，必要时重新附上已核对文件；未经复现不把中文文件名、签名过期或其他猜测写成根因。不只重发同一失效入口，也不把其他聊天的 sandbox 路径或临时链接当作当前可用交付。
- 整包交付验收仅核对教学设计、PPT课件、制作笔记、逐字稿、学习清单五项及各自采用版本。必须严格落实末端交付契约：
  - **交付落位**：成品必须以 `--mode commit` 直接输出至课题根目录下的 `交付文件/` 文件夹中。
  - **格式约束**：课件默认交付可画设计链接（用户明确要求时才交付 `.pptx` 文件）；其余四项（教学设计、逐字稿、学习清单、制作笔记）**一律只交 Word（`.docx`），严禁保留或交付 `.pdf`**。
  - **安全清理**：未排版的旧稿、旧命名版本或包外副本统一使用 `/usr/bin/trash` 移入系统废纸篓；源稿、大纲、样稿、素材、工作日志、旧版、重复格式和额外压缩包不进入最终交付。

## Delivery report

每次完成成果或修订的自检后，均向用户输出简明质检结果，与实际成果一起交付；这是本用户的固定要求，不能只列检查动作或说“已检查两轮”。按本次范围用短表或几个条目呈现：

- **结论与对象**：当前文件、课时及页码范围；说明“通过／修改后通过／需修改／部分未验证”，避免笼统称整套通过。
- **实际轮次与检查结果**：本次真实检查了什么、发现什么，问题定位到页或模块；没有发现问题时如实写明，不为显得严格虚构缺陷。
- **处理状态**：已修并复查、待用户修正、仍待处理或可选优化；只读检查保持只读，不能把建议写成已完成修复。历史轮次不能当作本次新检查。
- **未验证项**：仅列与该阶段相关的实际边界。大纲文字审查不能证明字号、范字显示、答案显隐、投影可读性或课堂用时已通过；这些留到相应样稿、成品或试教阶段验证。

评分只在已有明确标准或用户要求时提供，教案口径按 [lesson-pack.md](lesson-pack.md) 的两种模式执行，不为大纲自动沿用教案总分或随意报90分。质检简表放在聊天中，不混进逐页上屏文字、学生学习单等成果正文；默认不另建质检报告副本。检查结果不能代替流程要求的用户确认，也不因有待后续阶段验证的项目自动新增关卡。
