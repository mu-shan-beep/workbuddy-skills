#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import {
  buildModelBrief,
  compileModelPlan,
  inspectPresentation,
  parseArgs,
  sha256,
  summarizeExecutablePlan,
  validateExecutablePlan,
  validateTeachingCues,
  validatePresentation,
} from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !positional[1]) {
  console.error("Usage: node scripts/compile-model-plan.mjs INPUT.pptx MODEL_PLAN.json --teaching-cues CUES.json [--analysis STRUCTURE.json] [--output EXECUTABLE_PLAN.json] [--allow-replace-existing] [--allow-no-transition] [--allow-unattended]");
  process.exit(2);
}
if (!flags["teaching-cues"]) {
  console.error("A saved teaching-cues.json is required for a delivery-ready model plan.");
  process.exit(2);
}

const input = path.resolve(positional[0]);
const sourceValidation = await validatePresentation(input);
if (!sourceValidation.valid) {
  console.error(JSON.stringify({ stage: "source-preflight", validation: sourceValidation }, null, 2));
  process.exit(1);
}
const modelPlanPath = path.resolve(positional[1]);
const output = path.resolve(flags.output || modelPlanPath.replace(/\.json$/i, "-executable.json"));
const modelPlan = JSON.parse(await fs.readFile(modelPlanPath, "utf8"));
const teachingCuesPath = path.resolve(flags["teaching-cues"]);
const teachingCues = JSON.parse(await fs.readFile(teachingCuesPath, "utf8"));
const inspection = flags.analysis
  ? JSON.parse(await fs.readFile(path.resolve(flags.analysis), "utf8"))
  : undefined;
const currentInspection = inspection || await inspectPresentation(input);
const cueErrors = validateTeachingCues(buildModelBrief(currentInspection), modelPlan, teachingCues);
if (cueErrors.length) {
  console.error(JSON.stringify({ stage: "teaching-cues", errors: cueErrors }, null, 2));
  process.exit(1);
}
const authorization = {
  allowReplaceExisting: flags["allow-replace-existing"] === true,
  allowNoTransition: flags["allow-no-transition"] === true,
  allowUnattended: flags["allow-unattended"] === true,
};
const plan = await compileModelPlan(input, modelPlan, authorization, { inspection });
const briefBySlide = new Map(buildModelBrief(currentInspection).slides.map((slide) => [slide.slide, slide]));
for (const slidePlan of plan.slides) {
  const cue = teachingCues.slides.find((entry) => entry.slide === slidePlan.slide);
  const modules = [...(briefBySlide.get(slidePlan.slide)?.modules || []),
    ...(briefBySlide.get(slidePlan.slide)?.reviewableModules || [])];
  const kept = new Set((cue?.keepStatic || []).map((entry) => entry.moduleId));
  slidePlan.approvedStaticVisualIds = modules.filter((module) => kept.has(module.moduleId))
    .flatMap((module) => module.memberIds);
  const earlyBackings = new Set((cue?.earlyBackingExceptions || []).map((entry) => entry.moduleId));
  slidePlan.approvedEarlyBackingIds = modules.filter((module) => earlyBackings.has(module.moduleId))
    .flatMap((module) => module.memberIds);
  slidePlan.approvedDeferredVisualQuestionStageIds = (cue?.deferredVisualQuestions || [])
    .map((entry) => entry.stageId);
}
plan.planningEvidence = {
  workflow: "model-authored-with-teaching-cues",
  modelPlan: { path: modelPlanPath, sha256: await sha256(modelPlanPath) },
  teachingCues: { path: teachingCuesPath, sha256: await sha256(teachingCuesPath) },
};
const executableValidation = validateExecutablePlan(plan, currentInspection, plan.defaultExistingPolicy);
if (!executableValidation.valid) {
  console.error(JSON.stringify({ stage: "performance-and-coverage", validation: executableValidation }, null, 2));
  process.exit(1);
}
await fs.mkdir(path.dirname(output), { recursive: true });
await fs.writeFile(output, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
console.log(JSON.stringify({
  source: input,
  modelPlan: modelPlanPath,
  teachingCues: teachingCuesPath,
  executablePlan: output,
  analysisReused: Boolean(inspection),
  summary: summarizeExecutablePlan(plan),
}, null, 2));
