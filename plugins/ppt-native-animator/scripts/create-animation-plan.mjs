#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { createPlan, parseArgs, renderPlanHtml, validatePresentation } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0]) {
  console.error("Usage: node scripts/create-animation-plan.mjs INPUT.pptx [--preset auto-teaching] [--output plan.json]");
  process.exit(2);
}

const input = path.resolve(positional[0]);
const sourceValidation = await validatePresentation(input);
if (!sourceValidation.valid) {
  console.error(JSON.stringify({ stage: "source-preflight", validation: sourceValidation }, null, 2));
  process.exit(1);
}
const preset = flags.preset || "auto-teaching";
const output = path.resolve(flags.output || path.join(path.dirname(input), `${path.basename(input, path.extname(input))}_animation-plan.json`));
const plan = await createPlan(input, preset);
await fs.mkdir(path.dirname(output), { recursive: true });
const htmlOutput = path.resolve(flags.html || output.replace(/\.json$/i, ".html"));
await fs.writeFile(output, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
await fs.writeFile(htmlOutput, renderPlanHtml(plan), "utf8");

const summary = plan.slides.map((slide) => ({
  slide: slide.slide,
  type: slide.detectedType,
  preset: slide.preset,
  stages: slide.stages.filter((stage) => stage.trigger !== "initial").length,
  existingAnimation: slide.existingAnimation,
}));
console.log(JSON.stringify({
  plan: output,
  review: htmlOutput,
  source: input,
  analysisMode: "deterministic-fallback",
  deliveryReady: false,
  note: "Fallback plans are review drafts and require --allow-fallback at apply time.",
  slides: summary,
}, null, 2));
