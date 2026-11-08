# Pedagogical review

Verdict: **ISSUES**. The skill gives an author a sound causal teaching method. Both requested cases can become falsifiable experiments. The gaps concern how an author proves learning after the experiment, especially when results are stochastic. These are iteration suggestions, not evidence that learners have failed.

Reviewed on October 27, 2026. I read `SKILL.md`, `references/teaching-and-spec.md`, `references/verification.md`, the AI English Shift adapter, and the simple isometric and mechanical guides. I did not read earlier review reports. The bundled object examples are explicitly described as technique examples rather than finished lessons in `references/simple-iso.md:5`, so they are not evidence of learning effectiveness.

## Ranked findings

### P2. A stochastic misconception needs a criterion beyond seeing one prediction fail

`SKILL.md:20` asks for a wrong prediction that operation can disprove. `references/verification.md:7` asks whether the learner can see that prediction fail. `references/teaching-and-spec.md:34` usefully requires repeatable randomness and an uncertainty explanation, but none of these instructions says how much evidence is enough or distinguishes a sample from an expected distribution.

The temperature case exposes the gap. A high-temperature batch can happen to contain more correct answers. A low-temperature batch can contain an incorrect answer. Either observation can reinforce “temperature makes it smarter” if the author treats a single outcome as proof. The skill also needs the author to translate “smarter” into an observable claim rather than pretend intelligence has been measured.

Add a stochastic verification rule. Name the observable quantity, show its expected distribution, distinguish it from sampled counts, and require a comparison that holds the prompt, model scores, and other sampling settings fixed. The agent should state when a misconception is too vague to falsify. In the forward test below, I added a second score scenario to show that answer correctness can move in either direction while the sampling rule remains the same.

### P2. The explanation step has no success criterion or transfer check

The required spec ends with an insight, caveat, and language frame in `SKILL.md:69-71`. The language guidance gives a causal sentence frame in `references/teaching-and-spec.md:65-67`. Verification checks observable model behavior in `references/verification.md:5-9`, but does not ask the learner to predict a new case without the controls or distinguish a causal explanation from copying the insight.

A learner could complete “When ___ increases, ___ decreases” correctly while retaining the original misconception. In the gear case, memorizing “this output is half a turn” does not show that the learner understands cancellation of an idler's tooth count.

Add one lightweight learning check to the design note. Specify the two causal facts a satisfactory explanation must contain, one plausible incorrect explanation, and one new input or boundary case to predict after the main interaction. This need not add a mandatory schema field or an automated language grader.

### P3. “Meaningful try” does not identify the event that permits feedback

`references/teaching-and-spec.md:28` correctly delays feedback until a meaningful try. `SKILL.md:94` also forbids a tour that supplies the answer first. The spec contract does not record what a meaningful try is. An implementation can therefore reveal the answer after a click that changes no relevant cause, or leave a learner searching for a hidden completion condition.

In each design note, name the relevant action and the observation it must produce. For the temperature case, changing temperature and comparing the expected bars is enough. A sample is optional evidence of variability. For the gear case, one completed input turn with the idler engaged is enough. Show the learner which step remains. Permit an explicit observe-without-predicting path where the host allows it. Do not turn the sequence into an unexplained lock.

### P3. Control count does not bound the number of new ideas a novice must hold

`SKILL.md:92` aims for two to four controls and discovery within a minute. The spec fields in `SKILL.md:64-73` omit learner prerequisites or a plain-language definition of the quantities in the readout. Units are required by `references/teaching-and-spec.md:32`, but units alone do not explain “probability,” “idler,” or the difference between turn count and direction.

State one observable learning goal and the minimum prerequisite in the design note. Introduce the terms beside the part or readout that uses them. Keep the first comparison to one cause, then expose equations or extra scenarios after that comparison. The two forward tests below needed these choices even though each has few controls.

## What the skill already gets right

| Dimension | Assessment and evidence |
|---|---|
| Falsifiable mechanism | Strong for deterministic claims. The claim, cause, effect, misconception, and truth model are required before geometry in `SKILL.md:16-23`. |
| Causal consistency | Strong. One model drives motion, readouts, and explanation in `SKILL.md:77` and `references/teaching-and-spec.md:32-34`. View changes cannot change the answer in `references/teaching-and-spec.md:56-61`. |
| Feedback timing | Good intent. Observation precedes correction in `references/teaching-and-spec.md:28`. The completion event needs definition. |
| Misconceptions | Required and checked through interaction in `SKILL.md:20` and `references/verification.md:7`. Vague and probabilistic claims need extra care. |
| Transfer | Not required by the current contract. Both test specs below add a new case. |
| Cognitive load | The simplest renderer, limited controls, and no nested lesson forms reduce distractions in `SKILL.md:58`, `86`, and `92`. Prerequisite language remains an author judgment. |
| Novice and accessible participation | Native controls, text results, reset, stepping, and reduced motion support the same mechanism in `SKILL.md:92-96`. The skill does not mistake a labeled SVG for operable controls. |
| Honest scientific scope | Strong. Facts, calculations, and illustrative values are distinguished in `references/teaching-and-spec.md:36-40`. Mechanical guides prohibit claiming schematic teeth are a collision solver in `references/mechanical-craft.md:32`. |

## Forward test 1. Temperature sampling for a novice

Request: “Explain temperature sampling. I thought a higher temperature made the AI smarter.”

This is a standalone conceptual spec. It follows the skill's contract without assuming a host schema. The goal is to predict how temperature changes selection among fixed candidate scores, and explain why that does not guarantee better answers. The only prerequisite is understanding “more likely” and “less likely.” A label defines probability as the expected share of many repeated selections.

| Field | Proposed content |
|---|---|
| `anchor` | “Temperature changes how likely the sampler is to choose each candidate from the same model scores.” |
| `title` | “Does turning up temperature improve an answer?” |
| `lead` | “Predict what changes, then compare the bars at low and high temperature.” |
| `predict` | 0. “It updates the model's knowledge.” 1. “It spreads selection across the same candidates, without guaranteeing correctness.” 2. “It makes the highest-scored answer more likely.” |
| `answer` | 1. |
| `config` | Three complete answer candidates for a toy factual task. Correct answer A starts with probability 0.80, incorrect B with 0.15, and incorrect C with 0.05 at temperature 1. Temperature settings are 0.5, 1, and 2. Other sampling filters are absent. All values are illustrative. |
| `insight` | “Increasing temperature gives lower-scored candidates a larger share. It does not add knowledge or test whether an answer is correct.” |
| `caveat` | “This is a three-answer sampler with fixed illustrative scores. Real language models usually sample a token at a time. Their model scores are not truth scores. Temperature can change task performance, but this model cannot measure intelligence or justify a universal accuracy claim.” |
| `frame` | “The candidates and their original scores stayed ___. Temperature changed ___. Correctness did not follow a fixed rule because ___.” |

Choose `sampler` as the mechanism and `svg-2d` as the renderer. An unadorned bar chart makes the probability changes visible. A “sample” is defined as one selection, not a new training run.

Use the mathematical rule `q_i(T) = p_i^(1/T) / sum_j p_j^(1/T)` for positive temperatures. This is equivalent to dividing fixed logits by temperature and applying softmax. The UI reads expected shares from that rule. An optional seeded batch of 100 selections shows sampled counts separately, never as a correctness verdict.

Use two primary controls, a labeled temperature selector and **Draw 100 selections**, plus reset. A later **Try another score scenario** action swaps the correct answer's initial probability with B's. It appears after the first comparison. Reset restores temperature 1, the first scenario, initial seed, empty counts, and the original prediction state.

The sequence is explicit:

1. Show the question and candidate texts. Ask for a prediction before comparing temperatures.
2. Let the learner change temperature and inspect the expected shares. Keep the original scores visible in a separate column with the label “same model scores.” This is the meaningful try.
3. Let the learner draw a batch. Explain that observed counts vary around the expected shares. Do not mark a batch right or wrong.
4. Reveal the causal insight, then offer the alternative score scenario. When the correct candidate starts below the incorrect candidate, higher temperature raises its selection probability. This prevents “low temperature always means true” from replacing the original misconception.
5. Ask the learner to explain what changed and what stayed fixed.

Expected results are calculated, not measured learning outcomes:

| Temperature | A correct, scenario 1 | B incorrect, scenario 1 | C incorrect, scenario 1 |
|---|---|---|---|
| 0.5 | 96.2406% | 3.3835% | 0.3759% |
| 1 | 80% | 15% | 5% |
| 2 | 59.4173% | 25.7284% | 14.8543% |

The second scenario makes correct A start at 15%. Its expected share rises from 3.3835% at temperature 0.5 to 25.7284% at temperature 2. Both scenarios obey the same selection rule. Neither changes which answer is factually correct.

A satisfactory explanation says both that the original model scores stay fixed and that selection probabilities change. “It thinks harder” is insufficient. The transfer prompt is “If the most highly scored answer is false, does a low temperature guarantee a correct answer?” The expected answer is no, because concentrating on a false high-scored answer does not make it true.

The accessible result names the temperature and expected shares in text. Sample counts have their own labels. No animation is needed to explain the mechanism. Keyboard operation produces the same comparisons.

Forward-test result: **conditional pass**. The contract supports this spec, but the distribution-level criterion, correctness counterexample, explanation rubric, and transfer prompt are additional author choices. The primary-source [OpenAI sampling parameter reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) supports the narrower statement that higher temperature makes selection more random. It does not support calling temperature an intelligence measure.

## Forward test 2. An idler in a gear train

Request: “Teach gear ratios. I think adding an idler changes the final ratio.”

The goal is to predict the output turn count after adding an idler while keeping the first and final gears fixed. Define the driver as the input gear, the driven gear as the final output gear, and the idler as a single freely rotating intermediate gear. The learner needs to count full and half turns. Define ratio magnitude separately from rotation direction so a sign change cannot masquerade as a speed change.

| Field | Proposed content |
|---|---|
| `anchor` | “A single intermediate idler changes the final rotation direction but leaves the speed-ratio magnitude set by the first and final tooth counts.” |
| `title` | “Does an extra gear make the output slower?” |
| `lead` | “Predict the turn count, add the idler, and turn the input once.” |
| `predict` | 0. “The output falls from half a turn to a quarter turn.” 1. “The output stays at half a turn, while its direction changes.” 2. “The output rises to one full turn.” |
| `answer` | 1. |
| `config` | Driver 12 teeth, final gear 24 teeth, optional idler 12, 24, or 36 teeth. Each trial applies one clockwise input turn. The readout reports output-turn magnitude and direction separately. All gears share a module and have parallel fixed axes in each valid arrangement. |
| `insight` | “The idler receives teeth from the driver and passes the same number to the final gear. Its tooth count cancels from the final turn ratio. Each external mesh reverses direction.” |
| `caveat` | “Ideal external spur gears with one gear per shaft. No slip, backlash, losses, or torque calculation. A compound intermediate shaft carrying two different gears is a different model. Teeth are schematic unless actual meshing geometry is implemented and checked.” |
| `frame` | “With ___ input turns, the final gear makes ___ turns because ___. Adding one idler changes ___ but does not change ___.” |

Choose a gear-ratio mechanism and a simple 2D schematic. This is sufficient to see tooth contact, markers, and signed rotation. Isometric detail adds no necessary evidence for this request.

Use these rules:

```text
Direct pair: outputTurns = -inputTurns * 12 / 24
With idler M: idlerTurns = -inputTurns * 12 / M
With idler M: outputTurns = -idlerTurns * M / 24
```

The inserted idler therefore produces positive 0.5 output turns for one positive input turn, for all allowed idler sizes. The direct pair produces negative 0.5. A visible tooth marker and counters prevent half a turn from being confused with a complete turn on an unmarked wheel.

Use **Add idler**, **Turn input once**, an idler-size selector, and reset. Keep idler size fixed for the first comparison, then enable its selector. Adding or resizing an idler changes the arrangement to a valid schematic mesh. It resets the counters and visibly marks a new trial so stale counts cannot be compared accidentally. Reset restores the direct 12:24 pair and empty counters.

The sequence is explicit:

1. Ask for a prediction. Identify input and final output on the diagram.
2. Run the direct pair for one input turn. Show half an output turn and its opposite direction.
3. Insert the idler and run one input turn. This completed comparison is the meaningful try. Show half an output turn in the same direction as the input.
4. Change idler size. Show that the idler's own turn count changes while the final turn count remains half a turn. Reveal the cancellation equation after the observation.
5. Ask the learner to explain why a larger idler does not change the final turn count.

A satisfactory explanation says that the intermediate tooth count affects both mesh ratios and cancels, while each mesh reverses direction. “Extra gears do not matter” is insufficient, because it discards direction and the compound-gear limitation.

The transfer prompt is “Keep the 12-tooth input, replace the final gear with a 36-tooth gear, and keep one idler. Predict the output for one input turn.” The expected result is one third of a turn in the input's direction. A boundary question asks whether the same cancellation must hold if the middle shaft carries two different gears. The learner should say that the single-idler rule no longer applies.

Text beside the diagram says “Input 1 turn clockwise. Output 0.5 turn clockwise. Idler 1 turn counterclockwise” for a 12-tooth idler. Reduced motion uses immediate poses or single-step tooth progression. The arrows, counters, and description carry the same result.

Forward-test result: **conditional pass**. The skill's one-model rule and gear mapping make the central experiment direct. Distinguishing magnitude from direction, adding the compound-shaft boundary, and checking transfer required additional author judgment. The primary-source [KHK idler explanation](https://khkgears.net/new/gear_knowledge/gear-nomenclature/idler-gear.html) supports the distinction between changing output direction and retaining the speed ratio.

## Checks run and limits

I ran Python assertions against the numerical models used in these specs. Probability vectors normalized at temperatures 0.5, 1, and 2. Their largest share decreased as temperature increased. Swapping the correct candidate's score produced the claimed opposite correctness trend. Idler counts of 12, 24, and 36 all yielded positive 0.5 final turns. The direct pair yielded negative 0.5. The printed values matched the tables above.

These are forward tests of spec generation and model expectations, not completed interactive artifacts or a controlled comparison of skill versions. I did not build a UI, run browser checks, observe novice learners, grade real explanations, or measure retention. Those remain necessary before claiming improved learning.

The pstack principle **Prove It Works** changed the review by requiring calculation of the two mechanisms instead of accepting plausible copy. The technical-writing and unslop guidance kept findings tied to source lines and observable behavior. I made no edits to the skill, examples, or application code.

The next iteration should add the stochastic evidence rule and a small explanation-and-transfer check to the teaching guide, then generate these two figures and observe where novice users hesitate or overgeneralize. Preserve the current schema flexibility and use design notes where the host has fixed fields.

Skipped UI construction and learner testing. The remaining risk is that a mathematically correct, operable figure can still leave the original misconception intact.
