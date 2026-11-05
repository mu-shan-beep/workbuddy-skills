# Audit rules

## Severity

- **Blocking:** output cannot open; package part or source content changed; animation targets reference missing shapes; source hash mismatch.
- **High:** a planned visual module is missing animation; ordinary content waits for a click; an answer appears automatically when click reveal was required; media timing is damaged.
- **High:** a performance budget is exceeded in a way likely to stall the target application, or a classroom-controlled teaching beat cannot be reached by click.
- **Medium:** a backing shape appears separately from its content; a complete image series is split unintentionally; stage order conflicts with the teaching sequence; playback stutters on a high-risk slide in the target application.
- **Low:** timing, effect, or grouping could be smoother but all content remains correct and reachable.

## Responsible layer

- **Parser:** source element or relationship was not discovered correctly.
- **Planner:** discovered modules were ordered, grouped, or triggered incorrectly.
- **Compiler:** an invalid model plan was accepted or a valid module was dropped.
- **Writer:** compiled targets were not represented correctly in output timing XML.
- **Compatibility:** PowerPoint, WPS, or Keynote renders valid OOXML differently.

## Stop conditions

- Do not deliver an output with blocking or high findings.
- Do not silently repair during a review-only request.
- For compatibility-only findings, state the application used for observation and preserve the valid PowerPoint-native file.
