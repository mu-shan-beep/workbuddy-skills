---
name: ppt-native-animation
description: Run the local PowerPoint native-animation workflow from structure analysis and model planning through editable OOXML animation writing. Use when the user wants animations added to .pptx, .pptm, .ppsx, or .potx files. Do not use for Canva-hosted animation or video-only export.
---

# PPT Native Animation

Use this skill as the end-to-end router. Deterministic code reads and writes OOXML; the model decides teaching order through the planner contract. Never let the model author OOXML directly. OfficeCLI must be installed because source and output require strict OpenXML schema validation. Use local PowerPoint or WPS for a final playback spot-check after deterministic audit.

The planning workflow is structure-first. Do not render the whole deck or send full-resolution previews to the model. Reuse source-hash structure cache entries when available. Inspect selected small previews before planning whenever the compact brief marks a page `visualInspectionRequired`; save image descriptions in teaching cues. Also preview unresolved visual relationships and performance-risk pages as needed.

## Route the work

- For analysis, teaching-order decisions, or a reviewable animation plan, follow `$ppt-animation-planner`.
- For checking an existing animated output, diagnosing missing animation, or comparing source and output, follow `$ppt-animation-auditor`.
- For a complete request, run the planner workflow, obtain approval unless the user explicitly requested immediate application, and write to a new file. The apply command always runs its deterministic audit; use the separate auditor workflow for diagnosis or a requested detailed review.

## End-to-end execution

1. Validate the source before analysis. Stop if existing animation timing is invalid; repair or select a clean source before planning. Re-run structure analysis when the parser revision changes; old saved structure files are rejected rather than reused.
2. Produce and compile the model plan as defined by the planner skill. A delivery plan requires a filled teaching-cues file; retain it beside the model and executable plans. For teaching decks, use `classroom-controlled` unless the user explicitly requests unattended playback, and set `targetApplication` to `wps` or `powerpoint` when known.
   Supply authorization through compiler flags derived from the user's request, never through fields invented inside the model plan.
   The model authors one deck-wide strategy and expresses each slide as semantic stages plus only the necessary overrides.
3. Apply the compiled plan without overwriting the source:

   ```bash
   node scripts/apply-animation-plan.mjs INPUT.pptx EXECUTABLE_PLAN.json --original-source ORIGINAL.pptx --output OUTPUT.pptx --existing replace
   ```

4. The apply command writes to a temporary file, checks it against both the editing input and the original customer file, and publishes only when file structure, teaching sequence and original media timing pass. It retains a single JSON audit manifest beside the output. If the input is a repaired copy, `--original-source` still names the customer original. Never clean all animation from an intermediate file and treat it as the original.
5. Review the audit manifest's `playbackStates` for high-risk slides, then spot-check them in the target application: protected media, teacher clicks, conclusions, answer reveals, textless content images, low-confidence modules, and the slides with the most targets. Record actual playback separately; structural success does not claim that playback was verified.
6. If the user asked only for diagnosis or review, do not modify the file.

The deterministic fallback plan is a draft-review tool. It is not delivery-ready and requires `--allow-fallback` even for an intentional test. Never substitute it for the model plan in a final teaching deck.

For a revised deck with an earlier schema-v3 structure and model plan, use the planner's incremental workflow. Only changed pages return to the model; merge unchanged page plans deterministically before compilation.

## Test and regression safety

- Never run a write/apply test directly against a user-provided original presentation.
- First copy the selected source into a dedicated test-run directory, verify the copy hash matches the original, and use only that copy as the plugin input.
- Write analysis, plans, animated outputs, and any requested audit reports beside the test copy. Keep the original read-only throughout the test.

## Invariants

- In `classroom-controlled` mode, the first context beat may start automatically; later questions, tasks, discussion instructions, evidence, answers, conclusions and teacher cues may wait for a click when the teacher needs pacing control. Elements inside one teaching beat start together.
- In `microcourse-auto` mode, ordinary content plays automatically and answers may also run automatically only with explicit unattended authorization.
- `after_previous` stages start after the preceding stage finishes; `with_previous` stages share its start time. The writer must preserve this distinction.
- Keep text, pictures, shapes, notes, page size, slide count, and media unchanged.
- Keep backgrounds, logos, page numbers, navigation, and repeated footers static by default.
- Animate a card, label plate, picture container, or other visible backing with the content it carries.
- When replacement is authorized, remove existing visual animation and have the model redesign every eligible page. Protected media pages remain byte-for-byte preserved; existing visual timing elsewhere is context only and must not silently determine the new design.
- Include every source slide in the compiled plan. Pages with no element animation still receive their planned page transition.
- Code may enforce safety, compatibility, and the user-approved default `fade` page-transition policy, but it must not choose content effects, order, duration, trigger, or granularity for the model-authored workflow. A no-transition exception requires protected media timing or explicit user authorization plus a rationale.
- Preserve source shape-tree order, geometry, groups, fills, and transforms byte-for-byte. The default lightweight structural guard blocks output when any of these change; a full semantic audit remains opt-in.
- Animation may change only visibility/effect timing. Never write motion paths or animate position, size, rotation, crop, fill, transparency, or other layout/style properties.
- A content backing plate must enter with its first carried teaching content at the same click and start time; later material inside the plate may still be revealed separately. A whole-page background may remain static. An intentionally empty plate requires a specific early-backing classroom cue. If a backing relationship cannot be established confidently, keep the uncertain objects static.
- Preserve the function of an original exit-animated foreground mask by exposing a `reveal-mask` module and writing a model-timed `fade-out`; never delete its exit and leave the cover permanently visible.
- Never use animation as a reason to regroup, ungroup, reorder, duplicate, recreate, or move source shapes.
- Keep animation simple, restrained, and subordinate to the content. Let the model choose effects, timing, grouping, and rhythm according to what improves understanding; avoid decorative complexity.
- Enforce the compiled performance budget. WPS uses the more conservative limits. Large-area wipe effects, excessive per-slide targets and large simultaneous stages are compilation errors.
- Give every slide a simple `fade` page transition by default. Use no page transition only when protected audio/video timing makes it unsafe, or when the user explicitly requests it.
- Classify protected audio/video pages before model planning. Preserve the entire page without model-authored stages when safe separation is not possible, and report it without spending model tokens on a plan that will be skipped.
- Never overwrite an existing output.

Use `scripts/create-animation-plan.mjs` only as a deterministic fallback when model planning is unavailable.
