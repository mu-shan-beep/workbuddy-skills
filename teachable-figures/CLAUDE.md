# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

An **agent skill** (`SKILL.md` is the entrypoint other agents load), not an app. It turns a lesson's claim into an interactive "predict → try → explain" figure. The repo bundles the skill's guidance (`references/`), two vendored upstream rendering toolkits (`assets/anatomy/`, `assets/iso-figure/`), fifteen complete offline example lessons (`examples/`), and tests. There is no runtime package dependency; Node ≥20 runs builders and tests, Playwright is dev-only.

## Commands

```sh
npm ci
npm test                 # node --test tests/*.test.mjs  — models, teaching specs, Anatomy builds (6 examples × light/dark)
npm run test:browser     # node --test tests/*.test.cjs  — Playwright against examples/ and assets/iso-figure/examples/
npm run audit:3d         # slow full turning-dial geometry audit (runs in a temp copy)
```

- Single test: `node --test --test-name-pattern="rocket" tests/examples.test.cjs` (or pass one file).
- Browser tests use installed Google Chrome by default; set `BROWSER_CHANNEL=chromium` for Playwright's Chromium. `PLAYWRIGHT_MODULE` overrides the module path.
- Build tests and the 3D audit copy `assets/anatomy/` to a temp dir and build there — bundled sources stay unchanged. Don't run `build.mjs` in place (outputs `assets/anatomy/examples/*/*.html` are gitignored).

## Generated content embedded in examples

Three examples contain generated regions; edit the generator, then regenerate, rather than hand-editing those regions:

- `scripts/build-rocket-visual.mjs` → rewrites the `ROCKET_STRUCTURE_*` and `ROCKET_ENGINE_*` comment-delimited blocks in `examples/rocket-launch.html`, using the Anatomy kit (`assets/anatomy/kit/`).
- `scripts/build-engine-visual.mjs` → rewrites the `ENGINE_ART_*` block in `examples/four-stroke-engine.html` (Anatomy kit turned solids; moving parts are drawn at runtime with the same camera).
- `scripts/capture-previews.mjs` → screenshots each page's figure into `examples/previews/<name>-{zh,en}-{light,dark}.jpg` for the cards in `examples/index.html` (swapped by language/scheme at runtime). Rerun after changing an example's visuals (pass lesson names to recapture only those); adding a lesson means adding its selector there and a card (one `<a>` per `article`, which the browser test counts; `how-it-works.html` is the separate `.feature` card).
- `scripts/prepare-anatomy.mjs .audit/hra` → regenerates `assets/hra/chest-meshes.json`, `provenance.json`, and the embedded JSON in `examples/human-anatomy.html` from pinned HRA GLB files (hash-checked). Download steps are in `assets/hra/README.md`.

## Architecture and conventions

- **SKILL.md workflow:** Scope (what to decline) → section 0 interaction mode (guided interview by default, direct mode on request) → mechanism → renderer → spec → build → operability → verification. Keep the README "Quick install / Two ways to use it / What it is for" sections consistent with SKILL.md's Scope and section 0.
- **Teaching model drives everything.** Each figure has one pure model (state, readouts, prediction result, accessible summary); geometry/UI only observe it. Tests assert model behavior through real interaction, not displayed wording.
- **Mechanism (`kind`) and renderer are separate choices.** `references/rendering-selection.md` routes subjects: iso-figure for box-like working devices, Anatomy kit for crafted rigid mechanisms, source meshes/custom illustration for organic anatomy and textiles. "Anatomy" is the upstream toolkit name, not a medical atlas.
- **Examples are standalone, offline HTML** — no remote scripts/assets (tests check for network requests), native controls, reset, no autoplay before prediction, scoped keyboard shortcuts, reduced-motion support, 360px mobile + both color schemes.
- **Shared lesson shell.** Every page in `examples/` inlines the same CSS and i18n script between `lesson-shell v2` … `/lesson-shell` marker comments (two-pane layout: `.panel` with intro/steps on the right, `section.figure-pane#experiment` with stage and readouts on the left; stacks below 960px). In two-pane mode the figure pane's direct children don't shrink; on short screens the pane scrolls and the shell shows a "More below" cue, and the short-viewport test requires readouts to stay in view with nothing clipped or hidden in a nested scroll — put readouts early in the pane or reorder them on short heights. Change the shell in all pages together (then rebuild the evolve pilot, see below).
- **Attention API (shell v2):** mark figure components `data-part="id"` (optional `data-zh-label`/`data-en-label` for the hover tooltip) inside `#experiment`; give a panel `.step` `data-focus="id …"` to dim every other part while it is the active step (focused element first, else the first visible step crossing 30% of the panel's height). A step without `data-focus` dims nothing. `<ol class="look"><li data-focus="…">` becomes a learner-driven ordered-highlight sequence (numbered buttons, Prev/Next/Clear, Esc; caption at the top of the figure pane). `data-ref="id …"` on terms or legend items links them to parts both ways (hover/focus spotlights the part; hovering a part marks its terms and shows its label; Enter or a touch tap pins). A "Focus guide" toggle (localStorage `tf-focus-guide`) turns step dimming off for presenters. Don't nest parts; at least one part must be in the static HTML (the shell activates only if `#experiment` has a `[data-part]` at init). Canvas/WebGL figures highlight via a page-level redraw (`data-organ` in `human-anatomy`). Every lesson is annotated; `tests/attention.test.cjs` checks all of them generically. `scripts/capture-previews.mjs` turns the focus guide off for card thumbnails. Bilingual copy uses `lang="zh"`/`lang="en"` element pairs, `data-i18n` + `data-zh`/`data-en`(`-attr`) for text-only nodes and attributes, and `tr()`/`say()` for dynamic strings. Language comes from `?lang=`, then localStorage, then the browser; tests run en-US, so they assert English text.
- **Evolving artifacts (prototype):** `references/evolving-artifacts.md` defines evidence, typed patches, slots, validation and lineage. `scripts/evolve-apply.mjs <artifact> <patch> <out>` applies a patch and writes `out` only if headless validation passes. Pilot: `examples/evolve/geometry-slices/` (v1 + patch-1 → v2, reproduced byte-for-byte by `tests/evolve.test.cjs`). If the shell changes, rebuild v1 from `geometry-slices.html`, re-apply the patch, rerun the tests.
- `examples/` is published to GitHub Pages via `git subtree push --prefix examples origin gh-pages`.
- **Licensing:** this repo's own code is MIT (`LICENSE`) and its own lesson content and written guidance are CC BY 4.0 (`LICENSE-CONTENT`); bundled third-party material keeps its own license. Keep README "Sources and licenses" in sync if scope changes.
- **Upstream provenance matters.** `references/source-manifest.json` pins upstream revisions and lists local adaptations; `references/sources-and-fusion.md` explains contribution boundaries. Keep MIT notices in `assets/*/LICENSE` and HRA CC BY 4.0 attribution. Record local changes to vendored code there.
- `references/ai-english-shift.md` is an adapter for one specific host app; its contracts apply only there.
- `reviews/` holds dated review reports and raw audit output. Only claim checks that were actually run; a quick audit is not a full audit.
- `README.md` and `README.zh-CN.md` are parallel — keep them in sync when changing user-facing docs. `dist/` (the `.skill` archive) is gitignored and attached to releases.
