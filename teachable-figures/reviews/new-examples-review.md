# Independent review of the five new examples

Reviewed on 27 October 2026. This review inspected the source of the five new lessons and their directory. It also inspected the author notes. The review covers model consistency, teaching claims, controls, and selected rendered states. It does not audit the upstream mechanical orbit figures.

## Findings

1. **P2. The cone's base endpoint hides most of the cut face.** In `examples/geometry-slices.html`, the render function creates both a gold cut disk and a blue base disk. At `h = 8`, both disks occupy `y = -4`. Sorting their triangles by centroid depth interleaves the coincident surfaces. In Chrome, setting `h = 8` and the viewing elevation to `70°` produces a mostly blue disk with a few gold sectors. That contradicts the legend and the intended endpoint, where the cut face equals the base. Omit one redundant disk at that endpoint. Verify the actual rendered gold face as well as the numeric area. The affected render function was at line 22 when reviewed. The parent retained a browser regression that inspects the actual frontmost SVG fill at three points on the cap.

2. **P3. Revised predictions keep the previous feedback.** The submit handlers in `examples/transformer-flow.html`, line 73, and `examples/chinese-clothing.html`, line 34, update `state.prediction` without calling `render()`. In Chrome, save the correct prediction, compare both model states, then save the incorrect prediction. Both pages continue to say that the prediction matches the observation. Calling `render()` after saving keeps the teaching feedback consistent with the learner's current answer. This finding was reproduced on both pages.

## Teaching and scope assessment

The cone lesson has a valid anchor claim. Its radius calculation is linear in distance from the apex, and its area is quadratic. The two named comparison states and the threefold-distance transfer question test that distinction. Rendered views at `h = 0`, `2`, `4`, and `7.9` retained a coherent cut surface. The endpoint defect above needs correction before release.

The anatomy lesson teaches relative positions rather than a clinical anatomy atlas. The code preserves patient-relative left and right under rotation. The cutaway, lung visibility control, and the marker help inspect occlusion without moving the organs. Front, oblique, both side views, and a rear view were visually inspected. The rear cover correctly hides the organs. The marker remains an explicitly labeled schematic location. The sourced relationships agree with the [NHLBI respiratory-system description](https://www.nhlbi.nih.gov/health/lungs/respiratory-system). Simple ellipsoids and the omitted airway branches are consistent with the stated limits.

The rocket lesson separates initial lift, fuel loss, burnout, and coast. The analytic expressions account for a mass that decreases during powered flight. Pad support prevents negative altitude before liftoff. The explanation correctly allows delayed liftoff and continued upward velocity after burnout. The fixed-throttle and constant-gravity limits are visible. The prediction and coast transfer question address distinct misconceptions. A scene screenshot at the initial state was inspected. This independent pass did not rerun the full numerical integration comparison owned by the repository test suite.

The Transformer lesson derives all displayed quantities from the same query and mask state. Its score scaling, forbidden-score replacement before softmax, value mixture, residual paths, and stated post-normalization toy block are consistent with its parameters. The page distinguishes attention weights from output-token probabilities and marks the omitted cross-attention and vocabulary output. These boundaries agree with [Attention Is All You Need, section 3](https://arxiv.org/html/1706.03762v7#S3). The seven numbered stages expose data transformations without implying trained language behavior. The default experiment was visually inspected.

The clothing lesson limits itself to one Ming robe. Its object name, material, dimensions, closure, sleeves, and pleated lower portion agree with the [China National Silk Museum record](https://www.chinasilkmuseum.com/zggd/info_21.aspx?itemid=1900). The [Wuhan Textile University explanation](https://fashion.wtu.edu.cn/info/1135/3226.htm) supports the terminology for right closure. The SVG's outer front overlaps toward the wearer's right, which appears on the viewer's left. The page separates documented construction from its illustrative silhouette and inspection offsets. The open-front, fully separated state was visually inspected. Its labels and lower annotation remained inside the SVG.

The directory reaches all six lessons. Its descriptions accurately distinguish actual rotated three-dimensional geometry, a one-dimensional rocket simulation, a toy Transformer block, and a flat garment-structure diagram.

## Verification and limits

The first direct Chrome launch failed inside the sandbox. The approved local Chrome launch succeeded. The reviewer loaded all five actual HTML files and inspected selected screenshots. The viewport was 1100 pixels wide. Both revised-prediction findings were reproduced through native form and checkbox interaction. Source review checked labels, native controls, reset handlers, and explicit scope statements.

This independent pass did not run a learner study, a screen-reader session, a touch-device session, or an exhaustive mesh-intersection check. Mobile and theme claims in the author notes require the repository browser tests to remain the release evidence. The review found no need for new runtime dependencies or a broader rendering framework.

## Integration follow-up

The parent reproduced both findings with retained Chrome cases in `tests/examples.test.cjs`. At the base endpoint the cone now emits only the cut disk, avoiding a coincident second cap. Both prediction submit handlers render immediately after updating the saved answer. The three focused regressions failed before these edits and pass afterward.
