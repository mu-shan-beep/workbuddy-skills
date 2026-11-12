# Source of Truth and Change Propagation

**规则文件之间发生冲突时，按 `SKILL.md`「规则权威层级」裁决；本文件的 Authority order 只适用于素材、文案与版本来源，不用于裁决规则条文。一切以最新确认版本为准。**

Use this reference when a commissioned multi-artifact project must align a PPT with a lesson plan, script, media or feedback. The page matrix is an internal control document, not the user-facing PPT outline. A standalone writing or review task does not need a project matrix or all source types.

## Project brief fields

For every resumed or supporting-resource task, first check the compact identity: topic, textbook edition/grade if known, lesson period, current artifact/design and approved version. This applies even when no project matrix is needed. Other lessons supply style or method only; their vocabulary, questions, page counts and resource lists are not current-project facts. Read recent sources narrowly and reuse a compact task record rather than reloading unrelated chats.

- Project identity
- Audience and lesson duration
- Teaching objective
- Deliverables
- Official template and locked elements
- Customer requirements
- Source files
- Scope exclusions
- Open decisions
- Canonical working files

## Page matrix fields

Use the following fields when the project needs a full matrix; omit irrelevant fields for smaller tasks. Teacher language, student activity, visual intent, media timing and production notes stay internal or in their own deliverables, never inside the mode-03 pure on-slide outline.

| Field | Purpose |
|---|---|
| 页码 | Stable slide number or temporary slide ID |
| 环节 | Lesson section |
| 页面目标 | What students should notice, discuss or conclude |
| PPT标题 | Exact on-slide title |
| PPT内容 | Key visible content |
| 教师语言 | Script cue or linked script paragraph |
| 学生活动 | Expected student action |
| 视觉 | Photo, illustration, diagram or layout intent |
| 生产方式 | 可画整图组装；明确需要编辑时在可画处理，不直接制作可编辑PPTX |
| 媒体 | Audio/video file and duration |
| 动画 | Trigger and reveal order |
| 来源类型 | Customer, source, proposal or pending |
| 来源位置 | File and page/paragraph |
| 状态 | Draft, pending, approved, change requested, locked |

## Authority order

Use this default order unless the user states otherwise:

1. latest direct user/customer instruction;
2. approved change list or communication record;
3. official template, contest rule or required textbook edition;
4. approved lesson plan or outline;
5. existing canonical PPT;
6. internal design suggestion.

When two sources conflict, record the conflict. Do not silently choose the visually convenient source.

Apply authority by purpose rather than treating the newest uploaded image as a new instruction. Confirmed on-slide copy governs wording; textbook/material excerpts govern factual diagrams and data; style references govern only visual inspiration. Approved previews of this actual project govern faithful reconstruction. An official template governs its locked layout. A newly uploaded style sample does not override these roles. If the sources disagree within the same role and the latest explicit instruction does not resolve it, ask about that specific conflict.

## Change propagation map

| Change type | Check these linked items |
|---|---|
| Section name（源自已确认教学设计） | 其变化须先落到教学设计，再由 Transition slide、page header、navigation、script transition、summary 跟随；**不得为对齐幻灯片而改教学设计标题** |
| Knowledge point | Evidence/example, teacher explanation, student question, conclusion, homework |
| Activity order | Slide order, script order, timing, media cue, animation order |
| Customer wording | Every repeated instance and quotation mark/punctuation consistency |
| Page addition/removal | Page numbers, thumbnails, navigation, script references, media links |
| Visual replacement | Crop, source, caption, animation target, contrast and readability |
| Video/audio change | File link, poster frame, duration, script cue, total lesson timing |
| Animation change | Target element, click trigger, grouping, teacher cue, fallback readability |
| Student task or expected output | Learning-sheet prompt and writing space, script cue, assessment and final completion claim |
| Final deck count or feature change | Actual page references and operation claims in the usage notes, resource inventory and promotional copy |

## Feedback round procedure

1. Preserve the customer's wording in the change log.
2. Translate it into slide-level actions, with the intended result, locked elements and a check that can establish completion.
3. Separate required actions from optional design improvements.
4. Identify linked documents and animation/media dependencies.
5. Apply the batch once.
6. Render affected slides.
7. Update the change status. Update an existing page matrix when lesson content, page order, activities or mapped fields change; a small isolated visual correction needs only a brief change record. Edit linked lesson plans, scripts or other deliverables only when the commission includes those changes; otherwise note the affected content without rewriting it.
8. Run a full check only if the batch affects global style, order or repeated terms.

## In-place revision rule

Revise the current canonical source file directly, preserving its path and filename. Do not generate `_Vn`, revised, optimized or final copies for routine feedback rounds. If the current adopted file already has such a suffix, keep that file as the source; do not switch to an older sibling or rename existing files without a request.

Track revision identity with a timestamp, change summary or content hash in the existing task/check record. A new revision does not require a new file. Read-only checks do not modify or duplicate the source. Do not create routine backup files; format-required temporary writes and necessary compatibility tests follow [local-editing.md](local-editing.md), with the verified result saved to the same canonical path and temporary files removed.

Separate files are appropriate for an explicitly requested save-as, a different format, or a distinct commissioned deliverable. Copies made for final resource packaging do not replace or multiply canonical working files. Do not delete pre-existing files or older copies as part of this default rule.
