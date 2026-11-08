# Skill review and iteration

This is the historical v0.1.0 review. See the [v0.2.0 iteration](v0.2.0.md) for the later geometry repair, five new lessons, and current verification evidence.

Reviewed October 27, 2026. The starting archive was `teachable-figures-fused.skill`, SHA-256 `655102fae7014d12e70385f4e75dd87033cb454103fc0d0cf418683d483bead8`. The original archive and the October 12 review were left unchanged.

## Verdict

The skill has a coherent causal teaching method. Its shared-model rule, renderer selection, explicit assumptions, and host-schema boundaries are useful. The largest observed defect was in copyable examples. Both lightweight examples intercepted typing outside the figure. The corrected copies pass the retained browser cases.

The independent [UI/UX review](uiux.md) and [pedagogical review](pedagogy.md) describe the baseline, before integration edits. They used the same available model in separate agent contexts. They are specialist perspectives, not a comparison across model families or a learner study.

## Findings and disposition

| Finding | Disposition |
| --- | --- |
| P1. Page-wide keyboard shortcuts consume lesson writing. | Fixed in both iso examples. Chrome reproduced an empty writing field while its typed `123` appeared on the calculator. Shortcuts now belong to the focused SVG. |
| P2. SVG keys have no native equivalents or live result. | Fixed in both iso examples. Real buttons call the existing actions. Readouts have polite live semantics. Native target sizes are checked in the browser. |
| P2. Synth lacks reset/mute and runs its scope continuously. | Fixed. Reset restores default waveform, octave, mute, and silent state. Scope scheduling stops when idle, hidden, offscreen, or under reduced motion. Different input sources retain independent note ownership. |
| P2. Stochastic claims can be judged from one lucky sample. | Guidance updated. Distinguish expected probabilities from sampled counts, hold other settings fixed, and use a correctness counterexample in the temperature spec. |
| P2. Explain has no learning criterion or transfer case. | Guidance updated without adding schema fields. Author notes identify causal facts, the meaningful observation, and an unseen prediction. |
| P2. Host adapter can send Node-only geometry into client widgets. | Adapter corrected. Precompute browser-safe data at build time or use browser-safe modules. Production-build and real-browser checks are required for host integration. |
| P2. Anatomy demos autoplay and resume tours during a learner's pause. | Open in upstream technical examples. Integration guidance explicitly requires disabling startup and idle-resume tours. No broad rewrite of the vendored demos. |
| P2. Turning-dial quick orbit audit reports four crowding defects. | Reproduced and documented. The static recorder audit passes, but the quick orbit audit exits 1. See the [raw audit output](turning-dial-quick-audit.txt). |
| P3. A small control count does not define novice prerequisites. | Guidance updated to name the learning goal and define unfamiliar quantities beside readouts. |
| P3. A technical example does not show the complete teaching loop. | Added a generated, dependency-free [gear lesson](../examples/gear-ratio.html) with prediction, two comparable trials, explanation, and transfer feedback. |

## Reproducible checks

Install the development dependency with `npm ci`. Run `npm test` and `npm run test:browser` from the repository root. The browser suite uses installed Chrome; no personal browser profile is reused.

| Evidence class | Result | Scope |
| --- | --- | --- |
| Model and spec assertions | 4 passing checks. | Ripple dispersion at frequency bounds, interference behavior, temperature distributions, and idler cancellation. Spec assertions validate the proposed mathematical examples; they are not coverage of a deployed temperature widget. |
| Standalone builds | 12 passing checks. | Six Anatomy examples in dark and light variants. Builds run in a temporary copy. Arcade and raptor builders also run their built-in recorder audits. |
| Browser regressions | 8 passing cases. | Writing-field isolation, native calculator arithmetic and recovery, synth focus release/reset/mute, mixed pointer and keyboard ownership, light/dark and 360px/desktop layouts, reduced motion, plus two gear-lesson interaction cases. |
| Skill structure | Passed. | The skill-authoring validator checks frontmatter and naming. Direct entrypoint links resolve. This does not assert that every retained upstream technical note has no historical reference. |
| README | Passed. | The beautify-github-readme audit checks local images and SVG basics. Rendered previews are inspected at GitHub width and 360px. |
| Turning-dial geometry | Known failure. | `node build.mjs --audit --quick` reports four cable/rod crowding findings. The quick run is undersampled and does not replace a full orbit audit. |

The baseline browser reproduction used real keyboard input in an added writing field. The retained browser suite drives buttons, focus, keys, and pointer events. Captured screenshots support visual checks; they do not establish screen-reader usability.

## Forward use of the skill

The pedagogy reviewer produced two teaching specs without reading the earlier review. One challenges “higher temperature makes the model smarter.” The other separates idler ratio magnitude from rotation direction. Their calculations are retained in `tests/teaching-specs.test.mjs`.

A separate author received an ordinary request to build the idler lesson, with a copy of the original skill and no reviewer findings. It produced a working page. Parent inspection found a gear-label clipping issue and a theme-dependent label description, which were corrected before publication. The parent then replayed the final source in Chrome. This is a forward-use example and a review iteration, not a blinded comparison of skill revisions.

## What to try next

1. Observe a few novice learners using the gear lesson. Ask them to predict a new final gear size before showing the controls. Record whether their explanation distinguishes direction, ratio magnitude, and mechanical losses.
2. Build the temperature lesson from the spec. Keep expected probabilities and sampled counts separate. Check whether learners avoid both “hotter means smarter” and “colder always means correct.”
3. Before using an Anatomy demo in a lesson, disable tours and repair its captions and native controls in the host. Fix the turning-dial crowding if that renderer is selected, then run its full geometry checks.

## Scope and limits

Laziness Protocol kept corrections in the existing examples and guides. No application, global skill installation, renderer framework, or new lesson schema was changed. Prove It Works required actual builds, direct model assertions, Chrome input, and inspection of the captured output.

No screen-reader session, hardware touch session, audible quality assessment, novice learner study, production host integration, TSX example build, full 3D orbit audit, or WebGL fallback review was completed. The known 3D findings remain visible rather than being counted as passes.
