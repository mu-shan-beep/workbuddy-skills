# UI and UX review

Verdict is ISSUES for the bundled interaction examples. The skill's written guidance is substantially stronger than those examples. Review date is October 27, 2026. File references below describe the reviewed baseline before integration changes.

## Scope and evidence

Read `SKILL.md`, the teaching, simple-iso, mechanical, spatial, verification, and provenance guides, both bundled standalone HTML examples, and selected Anatomy interaction sources. Did not read earlier review reports. Treated the skill text as review material, not authorization to run its workflow.

Ran the actual inline calculator and synth JavaScript in Node VM contexts with a minimal DOM substitute. This was a temporary baseline probe. The retained real-browser regression suite is `tests/browser.test.cjs`. This confirms handler and model behavior. It does not establish browser focus, pointer capture, audio playback, layout, or screen-reader behavior. No browser observations are claimed in this report. The parent agent owns real-browser verification.

Prove It Works shaped the evidence labels. Only the inline-JavaScript checks that ran receive runtime results. The technical-writing and unslop skills shaped the report's wording.

## What already works

- `SKILL.md:64-73` specifies a useful first action, prediction, observable insight, assumptions, and reset state before geometry.
- `SKILL.md:92-102` explicitly requires keyboard equivalents, scoped shortcuts, reduced-motion operation, meaningful feedback, mobile checks, and honest verification claims.
- `references/simple-iso.md:45-49` directly warns against the examples' global shortcuts and requires native equivalents, mute, and visual feedback. `references/sources-and-fusion.md:39` accurately says that unchanged examples are not completed accessible lessons. These are acknowledged reference limitations, not hidden defects in the skill's instructions.
- Calculator arithmetic and clear state passed the VM checks. Synth note names, octave changes, and release on window blur passed. Both examples derive visible readouts from their model state rather than maintaining a second explanation.

## Ranked findings

### P1. Copied shortcut handlers can consume a learner's writing

`assets/iso-figure/examples/pocket-calculator.html:160-164` and `assets/iso-figure/examples/desk-synth.html:207-212` register handlers on `window`. Neither checks the event target or whether the figure has focus. In the VM checks, an event whose target was an INPUT caused calculator `8` and Backspace to change the calculator and call `preventDefault`. Synth `a` started a note and `x` changed octave with the same target. A lesson that embeds this input pattern can block ordinary text entry in its explanation exercise.

The written guard at `references/simple-iso.md:45` is correct, but authors copying the working example must repair it themselves. Scope shortcuts to the figure, ignore editable targets and modifier combinations, and keep release handling safe when focus moves. Add a regression check that types a sentence and deletes a character in an adjacent writing field while the figure's state stays unchanged.

### P2. The standalone examples expose a picture instead of named controls

The only focusable control in the calculator is its SVG with `role="img"` at `assets/iso-figure/examples/pocket-calculator.html:85`. Keys are generated as plain groups at lines 111-117. Synth uses the same pattern at `assets/iso-figure/examples/desk-synth.html:89` and 119-125. Neither file contains native buttons or a native equivalent for the SVG keys. Their readout spans at calculator line 86 and synth line 90 have no status or live-region semantics.

Static evidence establishes missing control semantics. A screen-reader session is still needed to assess each browser's actual announcement. A keyboard shortcut table helps sighted keyboard users, but does not expose named actions, selected waveform, or an announced calculation result through standard control navigation.

Provide native controls beside the decorative object. Send all controls through the existing shared model actions. Use one concise result/status region that announces a completed calculation or note state change without streaming oscilloscope frames. Keep the decorative SVG hidden from control navigation when the equivalent controls convey everything necessary.

### P2. The synth lacks a recoverable and motion-safe lesson state

`assets/iso-figure/examples/desk-synth.html:130-175` supports changing waveform, octave, and held notes, but offers no reset or mute action. Releasing notes makes it silent, but does not restore waveform and octave. `desk-synth.html:178-186` requests another animation frame unconditionally and reads and redraws the oscilloscope after audio initialization. There is no visibility or reduced-motion check in that loop. The reduced-motion CSS at line 82 only removes the group transition.

The VM confirmed that the script registers an animation frame immediately before any interaction. It did not measure browser CPU use or test an audio engine. Source inspection establishes that neither reduced-motion nor offscreen state gates this loop.

Add Reset and Mute using the current state and audio gain. Reset must release every held input and restore the default waveform and octave. Stop the scope loop while hidden, silent, or under reduced motion. Preserve a stable waveform and numerical frequency so the interaction still explains the result. Reuse the existing readout instead of adding another display.

### P2. Technical reference tours can take control away from an experiment

`assets/anatomy/examples/turning-dial/live.js:12` enables a tour by default. Lines 27-33 resume it after 3.6 seconds of inactivity, and lines 243-246 advance the dial's target automatically. The arcade source also starts with touring enabled at `assets/anatomy/examples/arcade-cabinet/live.js:431` and resumes it through lines 529-542. These are useful rendering demonstrations, but direct reuse changes state before a learner predicts and can change it again while the learner is explaining.

The fusion already prohibits automatic tours before prediction at `SKILL.md:94` and `references/sources-and-fusion.md:23`. Make the intended integration point concrete. Show a short example in which touring defaults to false and a named Demo action enables it after prediction or on request. Keep it stopped after manual interaction unless the learner explicitly restarts it. A tour should not restart solely because a learner pauses to think.

### P2. Small projected controls need a mobile equivalent

At `assets/iso-figure/examples/desk-synth.html:57-62`, fixed body and figure padding leaves about 274 CSS pixels for a 620-unit-wide SVG on a 360px viewport. Its 38 by 16 unit waveform keys at lines 121-122 therefore project to small hit areas. The seven-unit label text at line 70 shrinks further. This is a source-based size estimate, not a browser measurement. In addition, `touch-action:none` covers the whole SVG, including blank space, which prevents ordinary vertical touch scrolling from starting there.

Use the native equivalents from the accessibility fix as the mobile interaction route. Give them readable labels and generous targets. Restrict touch suppression to keys or the actual drag area. Confirm the true hit rectangles, scroll behavior, and caption wrapping at 360px in the browser before assigning a mobile pass.

## Test-case matrix

| Case | Expected behavior | Result and evidence |
|---|---|---|
| Calculator `4 + 5 Enter` | Display and readout show 9 | PASS in inline-JS VM. |
| Calculator Escape after calculation | Display 0; no pending operation, accumulator, or tape | PASS in inline-JS VM. |
| Calculator keys with INPUT target | Writing continues and model stays unchanged | FAIL in inline-JS VM. `8` and Backspace prevent the default action and change calculator state. |
| Synth `a`, then window blur | Readout identifies C4; blur clears held notes | PASS in inline-JS VM. Audio output not tested. |
| Synth `x` with INPUT target | Writing continues and octave stays unchanged | FAIL in inline-JS VM. Default is prevented and octave becomes 5. |
| Control navigation and result announcements | Each action has a named control; results are announced without continuous chatter | Static deficiency. Native controls and result/status semantics are absent in the two standalone examples. Browser and assistive-technology check pending. |
| Synth reduced motion and hidden state | Stable result; no continuous scope loop | Static deficiency. Loop has no media or visibility gate. Actual browser frame activity pending. |
| Synth Reset and Mute | Restore default state and stop sound on request | Static deficiency. Neither action exists in the baseline. |
| Turning dial after learner pauses | Learner keeps the state until taking another action | Static deficiency for lesson reuse. Tour resumes after the hard-coded idle delay. |
| 360px touch, layout, and both themes | Readable labels, usable targets, no clipping, ordinary page scrolling | Browser check pending. Source-based target-size concern identified. |

## Suggested iteration

1. Repair shortcut isolation and add native equivalents to the two smallest examples. This gives authors a correct input pattern to copy without expanding the renderer.
2. Add synth reset, mute, and motion/visibility gating. Test reset while notes are held, after octave changes, and after a pointer cancellation.
3. Include one small completed teachable example that follows the fused prediction and observation contract. Keep the upstream technical examples, but label their remaining integration work beside their links.
4. Run actual pointer and keyboard cases on desktop and 360px, in both themes and reduced motion. Check that the next and previous controls are reachable, result announcements are useful, and writing fields retain every keystroke.

No skill, model, or example files were edited by this reviewer. Skipped real-browser, assistive-technology, audio, and hardware-touch checks. The primary remaining risk is copying technical demonstrations into a lesson without applying the skill's explicit interaction requirements.
