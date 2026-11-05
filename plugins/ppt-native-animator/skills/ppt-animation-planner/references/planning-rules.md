# Planning rules

Use these rules only when the normal module plan needs closer judgment.

## Teaching order

1. Establish the title or learning context automatically when appropriate.
2. In live classroom mode, pause at teacher-controlled teaching beats such as a new question, task, discussion instruction, evidence reveal, answer or conclusion.
3. Start the backing plate, text, image and icon within one teaching beat together.
4. Use automatic sequencing inside a beat and for short follow-up explanations that do not need teacher pacing.
5. In unattended microcourse mode, use automatic sequencing throughout unless the user requested interaction.

`after_previous` is sequential: it begins after the preceding stage's duration and delay. `with_previous` shares the preceding stage's start time. Do not use the two values interchangeably.

## Strategy and deltas

- Read `deckProfile` before individual slides and choose one coherent `deckStrategy` for the presentation.
- Use one dominant entrance effect and at most one secondary effect. Keep the secondary effect for content whose structure benefits from it, such as a directional process.
- In slide stages, omit fields that match the strategy defaults. Add an override only when the content supplies a reason for a different effect, duration, stagger, delay, granularity, or transition.
- Omit per-slide action and ordinary fade transitions; the compiler derives them from source structure, authorization, and the strategy. Also omit empty static lists, ordinary content roles, and unreferenced labels.
- Do not let reuse replace semantic judgment: identical-looking slides may have different teaching order, and different-looking slides may share the same rhythm.

## Page transitions

- Keep `fade` on every slide by default so page turns remain consistent and restrained.
- Keep `preserve` on media-protected pages. Use `none` only when explicit external authorization is passed to the compiler, and record the reason in `transitionRationale`.

## Visual modules

- Keep text with its visible color block, card, label plate, or picture container.
- Respect `memberZOrder`. A backing plate must never be scheduled after the text it supports.
- Treat `mask` modules as protected and static unless the source animation explicitly contains a preserved exit/reveal action.
- When the brief exposes that original exit as `animationMode: "reveal-mask"`, schedule the mask itself with `effect: "fade-out"`; keep the already-visible covered content static behind it.
- Treat aligned, similarly sized thumbnails as a complete series; do not omit later siblings because only the first images have nearby captions.
- Keep an icon with its label.
- Do not animate a full-slide background, logo, page number, navigation mark, or repeated footer.
- If one container carries both a question and its later answer, show the container with the question and reveal only the answer paragraphs later when safe paragraph IDs are available.

## Dense slides

- Combine adjacent modules that communicate one teaching point.
- Prefer rows and columns that match the visible layout over raw XML order.
- Keep title, main evidence, answer, and conclusion in distinct stages when present.
- Avoid one animation per sentence when paragraphs form a single idea.

## Ambiguity

- Do not infer an answer solely from placement, color, emphasis, or a keyword.
- Treat source-derived semantic roles as evidence only. The model may confirm or override them after reading the content.
- In `classroom-controlled` mode, a click stage must use one of `question`, `task`, `discussion`, `evidence`, `answer`, `conclusion`, or `teacher-cue`, and include a concise pacing rationale.
- An answer click stage must also use `answersQuestionStageId` to reference an earlier question stage, or `previous-slide` when the question is on the preceding slide.
- A `reviewableModule` stays static by default. The model may animate it as one atomic unit only when the content relationship is clear and it supplies `promotionRationale`; never split or reorder its members.
- Do not repair geometry, layer order, grouping, or fills in an animation plan. Those are immutable source properties checked by the auditor.
