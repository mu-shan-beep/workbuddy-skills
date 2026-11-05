# Compatibility

## Existing animations

- `replace`: remove existing visual animation and write the model-authored plan after external `--allow-replace-existing` authorization.
- `preserve`: skip slides with meaningful existing timing trees. Use only when the user explicitly wants to retain them.
- `skip`: same slide-level behavior as preserve, but records the choice as intentional exclusion.
- Media timing is protected at slide level. Preserve the entire page instead of merging a new animation sequence into media playback timing.
- Protected media pages classified as `preserve-required` bypass model planning and retain their source timing and transition byte-for-byte.

## File formats

- `.pptx`: fully supported.
- `.pptm`: preserve `vbaProject.bin` and the package type. For production use, compare the macro payload hash before and after processing.
- `.ppsx` and `.potx`: preserve the package extension and content types.
- `.ppt`: convert to `.pptx` with a headless local converter before analysis. Conversion can alter legacy layout or media.

## Limited objects

Animate SmartArt, grouped shapes, charts, embedded objects, and media as whole objects unless verified sub-elements are addressable. Do not invent sub-element targets.

## Playback

The generated timing trees target Microsoft PowerPoint 2019 or newer. Use `minimal` when WPS, Keynote, or older PowerPoint compatibility is more important than expressive motion.
