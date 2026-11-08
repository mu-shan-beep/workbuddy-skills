# Gear-ratio lesson author notes

The lesson tests the belief that adding a gear always makes the output slower. Open `gear-ratio.html` in a browser. It works offline and uses no dependencies, remote resources, storage, or network requests.

## Teaching spec

- Claim and anchor. Adding a single simple idler does not change the magnitude of the final speed ratio when the driver and output tooth counts stay fixed.
- Prediction. Compare less than, exactly, or more than half an output turn after adding an idler. The first option states the misconception.
- Cause and effect. Toggle one 18-tooth idler between a 12-tooth driver and a 24-tooth output. Run the same one-turn input in each arrangement.
- Evidence. Separate unsigned turn counters, rotation marks, direction text, and a retained comparison table make both results visible. The explanation appears after both arrangements reach one input turn.
- Insight. The idler passes the same 12 teeth onward. The output advances 12 of its 24 teeth. The calculation is 12/18 × 18/24 = 12/24 = 1/2. Each external mesh reverses direction.
- Transfer. Replace the idler with 30 teeth while allowing the shafts to move. The answer remains half a turn clockwise.
- Explanation frame. “The idler changes ___, while the output still turns ___ because ___.”
- Limits. Ideal external gears with common tooth spacing, rigid teeth, fixed shafts, no slip, and a prescribed driver motion. Friction, backlash, drag, inertia, motor response, and compound intermediate shafts are outside the model.

## Model and implementation

One state object holds the idler choice, driver turns, saved prediction, running state, and completed observations. One pure `model(teeth, inputTurns)` function derives each gear's signed rotation. The picture, unsigned counters, direction description, and completion values consume that model. Turns are the unit. Clockwise is positive in the SVG. The legal input interval is zero to one turn.

The 2D gear centers are separated by the sum of their pitch radii. Radius is three drawing units per tooth. Rigid groups rotate around their fixed centers. Tooth outlines are simplified schematic shapes, not manufacturing profiles. No copied assets are included, so no upstream asset license notices are required. Verification used the supplied skill's existing browser driver without modifying it.

Native buttons, radio fields, checkbox, and range input provide keyboard operation. The slider advances by quarter turns. Reduced motion makes the full-turn button jump to the endpoint and retains manual stepping. The run button pauses and resumes. Animation pauses when the experiment leaves the viewport or the document is hidden. Reset clears the prediction, observations, writing, transfer answer, and current turn.

Model the Domain shaped the single state object and shared pure model. Prove It Works shaped the browser checks against the actual page. A single file was the smallest safe implementation. There were no independent implementation workstreams or shared writers. No subagents were created.

## Verification

The built-in `selfCheck()` runs on page load and throws on failure. It checks zero, quarter, half, three-quarter, and full input turns, opposite and same output directions, and invariance with 18-tooth and 30-tooth idlers.

Local headless Chrome checks exercised the misconception choice, native keyboard stepping, both one-turn runs, pause and resume, the explanation gate, transfer feedback, and complete reset. A 360-pixel dark-theme reduced-motion run checked the checkbox with Space, the slider with Home and ArrowRight, an immediate full-turn result, and no horizontal overflow. Desktop and mobile screenshots were visually inspected. Light and dark themes were checked. Browser consoles were clean.

Not checked with a screen reader, touch hardware, Safari, or Firefox. No physical gear accuracy or motor-load simulation is claimed. Nothing was published.
