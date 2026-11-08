# Transformer and Chinese clothing teaching examples

These are standalone, dependency-free, offline HTML pages. They add no runtime packages or shared library changes. Both use native controls, explicit reset, a prediction, an inspectable comparison, explanation and a transfer question. Neither starts an animation loop.

## Transformer data flow

`examples/transformer-flow.html` teaches that causal masking blocks future contributions before softmax, regardless of a raw similarity score. The central misconception is that a sufficiently strong score can bypass the mask.

The data model has three four-dimensional input vectors, a selected query index, a causal-mask flag and a selected calculation stage. One pure `model(query, causal)` supplies all numbers. The figure calculates Q/K/V, scaled dot-product scores, masking, stable softmax, weighted values, output projection, residual addition, population-variance layer normalization, a hand-specified FFN, and another residual plus normalization. `Model the Domain` informed the choice to keep the selected query and mask together and derive every displayed result from them.

A meaningful try compares the query “see” with both mask settings. An explanation should say that forbidden scores become negative infinity before softmax and that the remaining weights renormalize. The transfer asks which positions the final query can read. All three are permitted, including itself.

The source is [Vaswani et al., Attention Is All You Need, §3](https://arxiv.org/html/1706.03762v7#S3), inspected on 2026-10-27. The surrounding architecture context is distinguished from the calculated toy. The original paper is encoder-decoder with cross-attention. This example calculates one reduced decoder-style block, one head, four model dimensions, two key/value dimensions, illustrative position vectors, and hand-chosen parameters. It has no trained behavior or vocabulary head. Its attention weights are not next-token probabilities.

Useful browser selectors and expected results:

- `[data-query="0"]`, `[data-query="1"]` and `[data-query="2"]` select query positions.
- `#causal` toggles the mask. Default masked “see” weights are `[0.3444632017684351, 0.655536798231565, 0]`. Displayed weighted value is `[0.593, 0.472]`.
- With `#causal` unchecked for “see”, its weighted value displays `[0.762, 0.152]`; the future token has positive weight.
- `[data-stage="0"]` through `[data-stage="6"]` and `#previous` / `#next` inspect all seven calculation stages.
- At the final query, toggling the mask leaves all weights unchanged. Its final block output is approximately `[1.4136133434, -0.0641678716, 0.0625191823, -1.4119646541]`.
- `#reset` restores query 2, mask on and stage 1. It clears prediction, transfer answer and `#writing`.

`selfCheck()` tests normalization, forbidden zero weights, finite outputs, first-query identity weighting, a hand-calculated value mix/projection/residual, the hand-calculated population variance for layer normalization, ReLU/FFN behavior and final-position mask invariance.

## Chinese clothing

`examples/chinese-clothing.html` teaches inspection of overlap and component relationships. It is bounded to the China National Silk Museum's Ming yesa robe, not a generic historical costume or complete reconstructed outfit.

The principal source is the [museum's collection record for 明代曲水如意云纹暗花缎曳撒袍](https://www.chinasilkmuseum.com/zggd/info_21.aspx?itemid=1900), inspected on 2026-10-27. The page separates the recorded material, dimensions and broad construction from the teaching reconstruction. The definition of right closure is supported by [Wuhan Textile University's published explanation by Tao Hui](https://fashion.wtu.edu.cn/info/1135/3226.htm). That source explains a term; it is not evidence for details of this museum object.

The prediction asks what becomes visible when the outer front moves away. The meaningful try is opening and closing the outer front. The lighter inner front remains underneath. The part selector and exploded view then expose the relation between the upper body and pleated lower portion of one robe. The transfer asks what happens if the image is mirrored while its wearer-relative direction labels are retained.

The state has a selected part, an outer-front inspection flag and a spread percentage. `viewModel(state)` computes display translations only. Inspecting or separating the drawing does not change historical claims. Source limits are explicit. The silhouette, pleat count, inner-front extent, seams and offsets are illustrative; the drawing is not a measured pattern, cloth simulation, or evidence of undergarments. Color never encodes rank or social status.

Useful browser selectors and expected results:

- `#part` selects `all`, `collar`, `sleeves` or `pleats` and updates the adjacent explanation.
- `#open` opens the outer front. Its SVG transform becomes `translate(88 -12)` and the textual result states that the inner front is visible.
- `#explode` steps through 0, 25, 50, 75 and 100. Home gives zero, End gives 100, and an arrow key changes it by 25.
- At 100% spread, `#upper` moves by −13 and `#lower` by +35 SVG units. Inspection connectors meet those translated boundaries. At zero both translations are zero.
- `#reset` restores the assembled, closed, whole-robe view and clears both answers and `#writing`.

`selfCheck()` checks initial assembly, every spread step, both outer-front states, finite positions, separation distance and the endpoint.

## Verification actually performed

Installed headless Google Chrome ran both pages. Console output was clean. Both built-in self-checks passed. The browser reported no horizontal page overflow at 360px and 1100px.

Real mouse input toggled the Transformer mask, selected query and FFN stages, opened the clothing front and activated clothing reset. Real keyboard input toggled the mask with Space, activated Transformer reset, typed into the writing fields, and operated the clothing range with Home, End and ArrowRight. Both resets cleared writing. Both examples retained their controls in reduced-motion mode.

Screenshots were captured and visually inspected for Transformer desktop light and mobile dark, plus clothing mobile light, mobile dark with the front open and full spread, and desktop light. The clothing SVG viewport was enlarged after checking the fully spread state so the lower annotation remains visible. Connector endpoints now follow the upper and lower translations.

The inspection did not include assistive-technology sessions, physical touch devices, classroom learners or specialist textile-conservation review. These are schematic teaching examples. They do not demonstrate model training, natural-language generation, garment fabrication or a fully evidenced historical ensemble.
