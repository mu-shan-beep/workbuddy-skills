---
name: ppt-animation-auditor
description: Audit a local animated PowerPoint against its source and executable plan for missing targets, incorrect click behavior, separated containers, content changes, media changes, and invalid OOXML. Use for checking, diagnosing, or reviewing animation output. Read-only by default; do not use to design a new plan.
---

# PPT Animation Auditor

Audit first and report evidence. Do not repair or rewrite a presentation unless the user separately asks for a fix.

## Required inputs

- Source PowerPoint.
- Original customer PowerPoint when the animation input was a repaired copy.
- Animated output PowerPoint.
- Executable animation plan used to create the output.
- Existing-animation policy when it differs from the plan default.

If the plan is unavailable, run structural validation and visual review, but clearly label coverage conclusions as incomplete.
If the model plan and teaching cues are missing, do not claim the animation was model-designed. Compare protected media timing against the original customer file, not only against a cleaned intermediate copy.

## Deterministic audit

Run:

```bash
node scripts/audit-animation-result.mjs SOURCE.pptx OUTPUT.pptx EXECUTABLE_PLAN.json --original-source ORIGINAL.pptx --existing replace --report AUDIT.json
```

The audit must verify:

- the output passes strict OpenXML schema validation through OfficeCLI;
- source and plan hashes match;
- non-slide package parts, including media and notes, are byte-identical;
- slide content is unchanged outside animation and transition XML;
- shape-tree order, geometry, grouping, transforms, fills, and styling are byte-identical;
- no motion path or property animation changes position, size, rotation, crop, fill, transparency, or apparent stacking;
- preserved source timing XML is byte-identical;
- every planned animation target is present unless the page was deliberately preserved or conservatively skipped;
- no unplanned target from the original animation remains on a replaced page, including pages planned with only a transition;
- strict plan coverage, container synchronization, paragraph visibility and the selected interaction mode's click rules still pass.
- teacher click cues, image/caption pairing, complete card series, question/answer separation, and evidence-before-conclusion order pass;
- every declared prerequisite is visible when its teaching stage starts, and a visual identification question does not appear before its required picture unless the teacher explicitly approved a blind prediction;
- every question on a page with instructional visuals has an explicit visual relationship decision; the audit report includes the settled visible shapes after each teacher click;
- actual animation timing and click order match the executable plan exactly, not merely the set of animated shapes;
- original video/audio timing and media relationships remain intact.
- conclusions, derived formulas and worked analysis are not exposed before their evidence or answer; substantial static content visuals are reported for teaching review.
- target-application performance budgets still pass: per-slide target count, simultaneous stage size, concurrent wipe count and large-area wipe restrictions.

## Structural playback review

Use the source structure, model brief, executable plan, timing XML, and audit report. Do not generate slide previews. Check especially:

- later images in a row are not missing animation;
- text backgrounds do not appear before their text;
- large content plates do not sit empty through a teacher click; only a separately documented early-backing classroom cue may exempt one;
- foreground masks never receive an automatic entrance and backing plates never appear after their text;
- every backing-and-content module appears simultaneously without internal stagger or temporary layer inversion;
- ordinary text follows the selected classroom-controlled or microcourse-auto pacing;
- answer content is not visible before its reveal;
- preserved audio/video slides still behave as expected.

Report findings by slide with severity, evidence, and the responsible layer: parser, planner, compiler, writer, or compatibility. Read [audit rules](references/audit-rules.md) for severity and stopping criteria.

After deterministic audit passes, spot-check high-risk slides in the target PowerPoint or WPS application when available. Check actual click order, video/audio preservation and visible stutter. Do not replace the structural audit with a visual check.
