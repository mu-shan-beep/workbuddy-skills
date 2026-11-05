# Existing PPT Editing

Read this reference for a bounded change to an existing deck, especially when file editing might affect an official template, media or animation. Keep the independent executor skill responsible for its command syntax.

## Efficient edit pass

1. Identify the current canonical source file and intended target app. Keep its path and filename unchanged and save revisions in place; do not create a new `_Vn`, revised or optimized copy by default. On the first edit to this deck, validate the file and note existing defects; use a temporary compatibility test only when needed for an unverified editor or complex content. Record each change's slide/object, desired result, locked elements and acceptance check.
2. Read only affected slides and shape identifiers. Search the deck once if the target is unknown; reuse the result in later calls.
3. Choose one editor for the pass. Use `officecli-pptx` for deterministic changes to a saved PPTX, `wps-ppt` for work owned by an active WPS session, or `presentations:Presentations`/`ppt-master` when the file operation or template work requires them. Save and close one editor session before switching.
4. Make related edits in one batch where possible. Run operations against the same file sequentially, including previews and validation; OfficeCLI's resident session can contend even on concurrent reads. Flush the file before a different program reads it. Save the approved batch back to the current source path, not a separate file for the batch or each operation.
5. Verify the saved object and compare before/after renders of changed slides. Check text wrapping, clipping, overlap, alignment and locked template elements; a successful save or structural validation does not establish layout quality. Structural validity, visual appearance and actual playback are distinct checks. Run a full-deck check only for global changes or at a formal review or delivery gate.

When a live editor is used, pass only the file, affected slides, approved wording/assets and relevant template, media or animation constraints. Record the saved output and verification. Check linked documents for consequences, but edit them only when synchronization is part of the user's requested scope.

## Save and cleanup

- Routine edits save directly to the current source file. Do not create a standing rollback file or a new delivery version for every edit. Track changes with concise notes, timestamps or content hashes rather than duplicate artifacts.
- If a format writer requires a temporary output, or a complex-deck compatibility test genuinely needs a protected input, use temporary storage only for that operation. After verification, write the result back to the same canonical path and remove temporary files. These are implementation necessities, not permission to create persistent revised copies. On failure, restore the same source path from the temporary protection when available; do not publish an unverified result as a successful edit.
- Create a separately named result only when the user requests it or the requested deliverable has a genuinely different format or purpose. Do not rename, delete or consolidate existing user files merely to enforce this rule. Packaging copies are for the requested resource package and do not create new working versions.

## Complex PPTX compatibility gate

When complex-deck preservation has not been established for the chosen editor, or a relevant editor upgrade requires retesting, use a temporary compatibility copy and clean it up after recording the result. Routine verified edits do not repeat this copy step. A tiny synthetic deck can confirm basic read/write commands; it cannot establish that a customer's masters, media or animation survive.

- Run [check_pptx_preservation.py](../scripts/check_pptx_preservation.py) against original and edited copies. It checks slide order, text-change locations, media paths and bytes, slide timing trees, package relationships, and template parts. Pass intended changes with `--allow-slide-structure-change`, `--allow-text-slides`, `--allow-timing-slides`, `--allow-media-change`, `--allow-relationship-change`, or `--allow-template-change` only when the change list explains them. Review every allowed difference; the script does not test layout or playback.
- Compare the requested content and changed-slide preview. If shared masters or presentation parts were rewritten, inspect one representative unchanged slide too.
- If media links or package locations intentionally changed, inspect the affected relationship targets. If animation matters, verify click sequence and targets in the target app; an unchanged timing tree is insufficient.
- Inspect changed pages in the target presentation app when a renderer shows placeholders or the layout depends on native rendering. Play relevant timers, audio and video. An error-free file opening confirms only that the file opens.

After this deck passes its route check, routine bounded edits need targeted validation and changed-slide review. Repeat the broader gate only for relevant global, media, animation or editor changes.

## Keep context small

- Prefer one targeted shape read, one mutation batch and one changed-page preview batch. Return only selected fields from large tool output.
- Consult executor help for uncertain commands or properties, then return only the relevant lines. Avoid loading an entire property schema for operations already documented and verified.
- Reuse the change list as a small cache of slide numbers, shape IDs, approved text and verification status.
- Avoid full-deck shape dumps, all-slide screenshots and repeated source extraction for isolated changes.
