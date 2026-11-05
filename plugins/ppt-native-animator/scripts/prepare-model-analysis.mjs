#!/usr/bin/env node
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  ANALYSIS_REVISION,
  buildModelBrief,
  createModelPlanTemplate,
  inspectPresentation,
  parseArgs,
  sha256,
  validatePresentation,
} from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0]) {
  console.error("Usage: node scripts/prepare-model-analysis.mjs INPUT.pptx [--output-dir DIRECTORY] [--cache-dir DIRECTORY] [--no-cache]");
  process.exit(2);
}

const input = path.resolve(positional[0]);
const sourceValidation = await validatePresentation(input);
if (!sourceValidation.valid) {
  console.error(JSON.stringify({ stage: "source-preflight", validation: sourceValidation }, null, 2));
  process.exit(1);
}
const base = path.basename(input, path.extname(input));
const outputDir = path.resolve(flags["output-dir"] || path.join(path.dirname(input), `${base}-animation-analysis`));
await fs.mkdir(outputDir, { recursive: true });

const cacheEnabled = flags["no-cache"] !== true;
const cacheDir = path.resolve(flags["cache-dir"] || path.join(os.tmpdir(), "ppt-native-animator-cache"));
const sourceHash = await sha256(input);
const cachePath = path.join(cacheDir, `${sourceHash}-inspection-v${ANALYSIS_REVISION}.json`);
let cacheHit = false;
let inspection;
if (cacheEnabled) {
  try {
    inspection = JSON.parse(await fs.readFile(cachePath, "utf8"));
    if (inspection?.schemaVersion !== 1 || inspection?.analysisRevision !== ANALYSIS_REVISION
      || inspection?.source?.sha256 !== sourceHash) inspection = null;
    else {
      const stat = await fs.stat(input);
      inspection.source = { ...inspection.source, path: input, size: stat.size, extension: path.extname(input).toLowerCase() };
      cacheHit = true;
    }
  } catch {
    inspection = null;
  }
}
if (!inspection) {
  inspection = await inspectPresentation(input);
  if (cacheEnabled) {
    await fs.mkdir(cacheDir, { recursive: true });
    await fs.writeFile(cachePath, `${JSON.stringify(inspection)}\n`, "utf8");
  }
}
const brief = buildModelBrief(inspection);
const structurePath = path.join(outputDir, "structure-full.json");
const briefPath = path.join(outputDir, "model-brief.json");
const templatePath = path.join(outputDir, "model-plan-template.json");
const teachingCuesPath = path.join(outputDir, "teaching-cues-template.json");
await fs.writeFile(structurePath, `${JSON.stringify(inspection, null, 2)}\n`, "utf8");
await fs.writeFile(briefPath, `${JSON.stringify(brief)}\n`, "utf8");
await fs.writeFile(templatePath, `${JSON.stringify(createModelPlanTemplate(brief), null, 2)}\n`, "utf8");
try {
  await fs.access(teachingCuesPath);
} catch {
  const teachingCues = {
    schemaVersion: 1,
    contract: "ppt-native-animation-teaching-cues",
    source: { sha256: brief.source.sha256 },
    instructions: "Fill every teaching purpose from the approved outline or verbatim script. Each teacherClickBeats entry is {stageId, reason} and must match an on_click model stage. Each intentionally static content module needs {moduleId, reason} in keepStatic. Review backingTimingReview: a content plate should appear with its first teaching content. Only an intentional empty-plate teaching beat may use earlyBackingExceptions as {moduleId, reason}; keepStatic alone is not an exception. For visualInspectionRequired pages, inspect a selected slide preview and describe each textless content image in visualReviews as {moduleId, description}. Only when the teacher explicitly intends a blind prediction may deferredVisualQuestions contain {stageId, reason}.",
    slides: brief.slides.map((slide) => ({
      slide: slide.slide,
      purpose: "",
      teacherClickBeats: [],
      keepStatic: [],
      earlyBackingExceptions: [],
      visualReviews: [],
      deferredVisualQuestions: [],
      notes: "",
    })),
  };
  await fs.writeFile(teachingCuesPath, `${JSON.stringify(teachingCues, null, 2)}\n`, "utf8");
}

console.log(JSON.stringify({
  source: input,
  outputDir,
  structure: structurePath,
  modelBrief: briefPath,
  modelPlanTemplate: templatePath,
  teachingCuesTemplate: teachingCuesPath,
  analysisMode: "structure-plus-teaching-cues",
  previewGenerated: false,
  cacheEnabled,
  cacheHit,
  slideCount: inspection.slideCount,
  moduleCount: brief.slides.reduce((sum, slide) => sum + slide.modules.length, 0),
}, null, 2));
