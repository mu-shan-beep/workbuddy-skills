#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { buildIncrementalPlanningBundle, parseArgs } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !positional[1] || !positional[2]) {
  console.error("Usage: node scripts/prepare-incremental-analysis.mjs CURRENT_STRUCTURE.json BASELINE_STRUCTURE.json BASELINE_MODEL_PLAN.json [--output-dir DIRECTORY] [--redesign-slides 3,8,12]");
  process.exit(2);
}

const [currentPath, baselinePath, baselinePlanPath] = positional.slice(0, 3).map((value) => path.resolve(value));
const outputDir = path.resolve(flags["output-dir"] || path.join(path.dirname(currentPath), "incremental"));
const [current, baseline, baselinePlan] = await Promise.all([
  fs.readFile(currentPath, "utf8").then(JSON.parse),
  fs.readFile(baselinePath, "utf8").then(JSON.parse),
  fs.readFile(baselinePlanPath, "utf8").then(JSON.parse),
]);
const redesignSlides = String(flags["redesign-slides"] || "").split(",").map((value) => value.trim()).filter(Boolean).map(Number);
const bundle = buildIncrementalPlanningBundle(current, baseline, baselinePlan, { forceSlides: redesignSlides });
await fs.mkdir(outputDir, { recursive: true });
const briefPath = path.join(outputDir, "incremental-model-brief.json");
const templatePath = path.join(outputDir, "incremental-model-plan-template.json");
await Promise.all([
  fs.writeFile(briefPath, `${JSON.stringify(bundle.brief)}\n`, "utf8"),
  fs.writeFile(templatePath, `${JSON.stringify(bundle.template, null, 2)}\n`, "utf8"),
]);
console.log(JSON.stringify({
  currentStructure: currentPath,
  baselineStructure: baselinePath,
  baselinePlan: baselinePlanPath,
  incrementalBrief: briefPath,
  incrementalPlanTemplate: templatePath,
  reusableSlides: bundle.brief.reuse.reusableSlides,
  changedSlides: bundle.brief.reuse.changedSlides,
  forcedSlides: bundle.brief.reuse.forcedSlides,
  modelSlideCount: bundle.brief.slides.length,
  previewGenerated: false,
}, null, 2));
