#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { mergeModelPlanPatch, parseArgs } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !positional[1] || !positional[2] || !positional[3]) {
  console.error("Usage: node scripts/merge-model-plan-patch.mjs CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json PATCH_PLAN.json --output FULL_MODEL_PLAN.json [--redesign-slides 3,8,12]");
  process.exit(2);
}
if (!flags.output) {
  console.error("--output is required.");
  process.exit(2);
}

const [currentPath, baselinePath, baselinePlanPath, patchPath] = positional.slice(0, 4).map((value) => path.resolve(value));
const output = path.resolve(flags.output);
const [current, baseline, baselinePlan, patchPlan] = await Promise.all([
  fs.readFile(currentPath, "utf8").then(JSON.parse),
  fs.readFile(baselinePath, "utf8").then(JSON.parse),
  fs.readFile(baselinePlanPath, "utf8").then(JSON.parse),
  fs.readFile(patchPath, "utf8").then(JSON.parse),
]);
const redesignSlides = String(flags["redesign-slides"] || "").split(",").map((value) => value.trim()).filter(Boolean).map(Number);
const merged = mergeModelPlanPatch(current, baseline, baselinePlan, patchPlan, { forceSlides: redesignSlides });
await fs.mkdir(path.dirname(output), { recursive: true });
await fs.writeFile(output, `${JSON.stringify(merged, null, 2)}\n`, "utf8");
console.log(JSON.stringify({
  output,
  slides: merged.slides.length,
  patchedSlides: patchPlan.slides.map((slide) => slide.slide),
  reusedSlides: merged.slides.map((slide) => slide.slide).filter((slide) => !patchPlan.slides.some((item) => item.slide === slide)),
}, null, 2));
