# Incremental planning

Use this workflow only when both the earlier structure file and its schema-v3 model plan are available.

1. Analyze the revised PowerPoint normally to create its current `structure-full.json`.
2. Compare it with the earlier structure and plan:

   ```bash
   node scripts/prepare-incremental-analysis.mjs \
     CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json \
     --output-dir INCREMENTAL_DIR
   ```

   If the source structure is unchanged but selected pages need a plan-only redesign, add `--redesign-slides 8,10,36`. Use the same list again during the merge step. Forced pages are treated as changed for planning while all other reusable pages remain deterministic.

3. Read only `incremental-model-brief.json`. It contains changed pages; unchanged pages are represented by `reuse.reusableSlides` and consume no page-planning tokens.
4. Edit `incremental-model-plan-template.json`. Design every listed changed page. Keep the previous `deckStrategy` when it still fits; revise it only when changed content requires a deck-wide rhythm change.
   The patch inherits `targetApplication` and other baseline global settings. A change to `mode`, `preset`, or `deckStrategy` requires redesigning every page; the merger rejects such changes while any unchanged page is being reused.
5. Merge the patch deterministically:

   ```bash
   node scripts/merge-model-plan-patch.mjs \
     CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json PATCH_PLAN.json \
     [--redesign-slides 8,10,36] \
     --output FULL_MODEL_PLAN.json
   ```

6. Compile the full plan with the current structure supplied through `--analysis`, then apply it normally.

The code may reuse a page only when its page number, planning fingerprint, shared theme/master/layout fingerprint, and baseline plan entry all match. If shared presentation context changed, redesign every page. Never let the model declare a changed page reusable.
