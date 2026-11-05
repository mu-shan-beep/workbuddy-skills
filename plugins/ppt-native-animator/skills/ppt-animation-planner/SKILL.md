---
name: ppt-animation-planner
description: Analyze a local PowerPoint and design a reviewable, model-authored native-animation plan from compact element structure and visual modules. Use for animation planning or teaching-sequence design before writing the PPT. Do not use only to audit a finished animated file.
---

# PPT Animation Planner

Produce an animation plan; do not write animations into the presentation in this workflow.

## Workflow

1. Resolve the source file and create the analysis bundle. Structure analysis is cached by source hash; use `--no-cache` only when diagnosing the parser itself:

   ```bash
   node scripts/prepare-model-analysis.mjs INPUT.pptx --output-dir ANALYSIS_DIR
   ```

2. Start `teaching-cues-template.json` from the approved page matrix, outline, or verbatim script. Record the purpose of each teaching page. For `visualInspectionRequired` pages, inspect a selected small slide preview and describe each textless content image in `visualReviews`; use nearby caption text as context, not as proof of what the image shows. Do not render the whole deck. Use `structure-full.json` only when a compact module is structurally ambiguous.
   Review each slide's `backingTimingReview`: it names a content plate and the text modules it carries. Plan the plate with its first teaching content at the same click and start time. A whole-page background may remain static. If an empty plate is itself an intentional teaching cue, document its module and classroom action in `earlyBackingExceptions`; a generic `keepStatic` reason is insufficient.
3. Edit a copy of `model-plan-template.json`. Set `mode` and `targetApplication` first. Use `classroom-controlled` for live teaching and `microcourse-auto` only with explicit unattended authorization. Then author `deckStrategy`, choosing one or two restrained effect families plus default duration, stagger, delay, granularity, and the default `fade` transition. Plan slides with module IDs, not raw OOXML or guessed shape IDs. For every question listed in `visualQuestionReview`, classify its visual relationship on that question stage: `visualDependency: {"kind":"requires-visible","moduleIds":["..."]}` for material students must see, `{"kind":"independent","reason":"..."}` for a genuinely unrelated illustration, or `{"kind":"blind-prediction","reason":"..."}` when students should guess before seeing it. Use `requiresVisibleModuleIds` for other picture, chart, or text prerequisites. Once stage IDs are settled, complete each cue's `teacherClickBeats` with the matching stage ID and classroom reason; explain intentionally static content in `keepStatic`. A blind prediction also needs the same stage ID and reason in `deferredVisualQuestions`.
4. Compile the model plan:

   ```bash
   node scripts/compile-model-plan.mjs INPUT.pptx MODEL_PLAN.json --teaching-cues ANALYSIS_DIR/teaching-cues-template.json --analysis ANALYSIS_DIR/structure-full.json --output EXECUTABLE_PLAN.json [AUTHORIZED_FLAGS]
   ```

   Reuse the generated structure file through `--analysis`; the compiler verifies its source hash before trusting it. Pass `--allow-replace-existing`, `--allow-no-transition`, or `--allow-unattended` only when the user's request explicitly grants that permission. Authorization flags are outside the model-authored JSON; never let the model declare its own authorization.

5. Correct every compiler error. Missing teaching cues, an unreviewed content image, a static visual without classroom reason, premature answer/conclusion, incomplete card series, invalid source hash, unknown module/paragraph, unsupported click role or performance-budget overage are hard failures.
6. Report the planned stages, click stages, intentionally static modules, low-confidence slides, and protected existing/media pages. Obtain approval before application unless immediate application was explicitly requested.

## Planning decisions

- Design from meaning first. Decide what the audience should understand, then choose the smallest useful sequence of stages.
- Read every content image, data table, diagram, worked solution, and lower-page summary as part of the teaching sequence. A source shape can be a group or graphic frame with text inside it; do not treat it as decoration just because its compact role says `diagram` or its text is carried in `paragraphs`.
- On an experiment or worked example page, show evidence before the conclusion and derived formula. Keep the worked analysis hidden until the question has been discussed and the answer revealed. An agenda label such as “总结与归纳” is navigation, not a lesson conclusion.
- For a question that asks students to identify or describe a visible object, reveal the required picture no later than the question. The brief supplies high-confidence `visualQuestionDependencies` and wider `visualQuestionReview` candidates for multiple images or diagrams. Inspect selected previews and classify the actual relationship. A deliberately blind prediction needs both a stage decision and a matching teaching cue.
- When the question and required picture share a stage, use zero stagger between their modules. A common click alone does not guarantee simultaneous appearance; the compiler checks the actual start offset and delay.
- A substantial content visual may remain visible from the start only when the teacher genuinely needs it as a constant reference. Give that static decision a concrete classroom reason; inspect warnings about visuals that used to have animation.
- A large empty card or panel is not harmless decoration when its text waits for a teacher click. Treat the first carried task, question, or explanation as the panel's entrance beat; later content in that panel may still be revealed separately.
- Use `deckProfile` to set one coherent `deckStrategy` before planning individual pages. The strategy is model-authored, not code-selected, and must include a concise rationale.
- Treat each stage as a delta from `deckStrategy`: omit `effect`, `durationMs`, `staggerMs`, `delayMs`, or `granularity` when the global value is appropriate; specify only meaningful exceptions. A reveal mask must still override the effect with `fade-out`, and paragraph targets must override granularity with `paragraph` when the deck default is `shape`.
- Use `after_previous` when a stage must begin after the preceding stage finishes and `with_previous` for elements inside one visual teaching beat. In `classroom-controlled` mode, use `on_click` for a meaningful teacher-controlled question, task, discussion, evidence, answer, conclusion or cue, and provide a concise rationale. In legacy `teaching` mode, only answers may wait for a click.
- `initial` means visible before the animation timeline starts. In teaching mode, use it only for an essential always-visible reference, keep all initial stages contiguous at the start, and add a concise rationale. Never use only initial stages on a page; ordinary content, titles, and questions should use `after_previous`.
- Include every source slide in the model plan, including slides with no animatable modules. Omit `action`; the compiler derives `replace`, `design`, or `preserve` from the source structure and external authorization.
- A slide marked `mediaPolicy: "preserve-required"` is already resolved by the structure layer: leave its stages empty and do not spend model reasoning on omitted content. Its action and transition are inherited as `preserve`.
- Let deterministic code handle structural extraction, target IDs, z-order, backing plates, masks, timing XML, and safety validation. The model chooses teaching beats, semantic roles, trigger, effect, duration, grouping, and granularity. The general transition policy defaults every slide to `fade`; the model may choose `none` only for a protected media-timing risk or after an explicit user override.
- Treat parser-provided semantic roles as hints, not decisions. Interpret the actual text and relationships supplied in the compact structure contract.
- When one text box contains both a prompt and its answer in separate paragraphs, use the supplied `paragraphIds`: schedule the prompt automatically and classify the answer stage with `contentRole: "answer"`, `trigger: "on_click"`, and a short `rationale`.
- Use supplied paragraph IDs verbatim: blank paragraphs retain their original OOXML indices. Overlapping duplicate shapes form one atomic module and all original shape IDs remain targets. Slide numbers follow presentation order, not internal filenames.
- Base ordinary decisions on compact structure: text and paragraphs, bounds, member order, container bindings, confidence, and existing-animation metadata. Inspect only selected pages with textless content images or unresolved visual relationships; record their meaning in teaching cues.
- `reviewableModules` are static by default, but they are not forbidden targets. Promote one into a stage only when its content contributes to the teaching sequence, keep all members atomic, and add `promotionRationale`.
- Resume analysis and conclusions automatically after an answer reveal.
- Keep a visual module atomic. Combine modules only when they form one teaching beat and the expanded stage remains within the target application's concurrent-item budget.
- Treat a module's internal z-order and geometry as immutable. The plan may sequence modules, but must never sequence the backing and foreground members inside one module separately.
- A module with `animationMode: "reveal-mask"` represents an original functional cover that must disappear to reveal protected content. Animate it as a shape with `effect: "fade-out"`; classify the covered meaning normally to decide automatic versus answer-click timing.
- If the parser cannot confidently bind a backing plate to its foreground content, use the supplied reviewable module as one atomic unit. Leave it static unless its meaning clearly warrants animation; never split its members.
- Keep the result simple and professional. Choose only animation that helps the audience follow or understand the content; avoid decorative or attention-seeking motion.
- Choose effect, duration, stagger, delay, and granularity according to content and teaching rhythm. Put shared choices in `deckStrategy`; repeat them on a stage only when that stage intentionally differs.
- Use no more than six teaching stages on an ordinary slide or eight on a text-dense slide. Keep delay within 0–400 ms and use at most two entrance-effect families across the deck.
- Respect the `performanceProfiles` supplied in the model brief. Prefer fade or appear for WPS. Use wipe only for genuine directional structure, never for a large background, full-slide image or a large set of simultaneous freeforms.
- Use `granularity: shape` when the object should be understood as one visual unit. Use paragraph targets only when the brief marks paragraph selection as safe.
- Ordinary slides inherit the strategy's `fade` transition; omit the per-slide field. Use `transition: none` only when the compiler receives external `--allow-no-transition` authorization, and add a concise `transitionRationale`. Protected-media slides inherit `preserve`.
- Omit empty `staticModules`, ordinary `contentRole`, and decorative stage labels. Keep `contentRole` for questions and answers, and keep IDs that are referenced by answer stages.
- List an animatable module under `staticModules` only when it truly should remain visible from the beginning, and give a concrete reason.
- When classifying content as an answer, provide a short semantic reason and set `answersQuestionStageId` to an earlier question-stage ID (or `previous-slide` when the prompt is on the preceding slide). If text meaning or paragraph boundaries do not support a safe separation, do not invent one.

Read [planning rules](references/planning-rules.md) when a slide is dense, contains multiple questions, or has ambiguous cards and image groups.

When revising a presentation that already has a schema-v3 model plan, read [incremental workflow](references/incremental-workflow.md). Reuse only pages whose deterministic planning fingerprints and shared presentation context are unchanged.
