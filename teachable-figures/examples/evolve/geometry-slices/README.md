# Evolving cone lesson — one round

| File | Role |
| --- | --- |
| `v1.html` | Evolvable base lesson (slots, artifact state, explanation probe, evidence export) |
| `evidence-1.json` | Scripted sample export: correct ×4 choice, linear explanation, transfer answered 3 |
| `patch-1.json` + `components/` | The agent's hypothesis, decision and typed operations: add the area-tiles view, add a counting probe, hide the formula hint, carry over the prediction and explanation |
| `v2.html` | Produced by `node scripts/evolve-apply.mjs v1.html patch-1.json v2.html` (run in this folder) |
| `v2.report.json` | Validation checks and the structural diff |

Contract: [references/evolving-artifacts.md](../../../references/evolving-artifacts.md). The learner and evidence here are illustrative, not study data.
