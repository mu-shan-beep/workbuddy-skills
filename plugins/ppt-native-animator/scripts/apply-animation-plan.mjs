#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { applyPlan, auditAnimationResult, auditOriginalMediaPreservation, parseArgs, sha256,
  validatePresentation, validateStructuralIntegrity } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !positional[1] || !flags.output) {
  console.error("Usage: node scripts/apply-animation-plan.mjs INPUT.pptx PLAN.json --output OUTPUT.pptx --original-source ORIGINAL.pptx [--existing preserve|skip|replace] [--allow-fallback]");
  process.exit(2);
}

const input = path.resolve(positional[0]);
const planPath = path.resolve(positional[1]);
const output = path.resolve(flags.output);
const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
const existingPolicy = flags.existing || plan.defaultExistingPolicy || "preserve";
const isFallback = plan.fallbackPlan === true || plan.deliveryReady === false
  || plan.planningMode === "deterministic-fallback";
if (!isFallback && (!flags["original-source"] || plan.planningMode !== "model-v3-strategy-delta"
  || plan.planningEvidence?.workflow !== "model-authored-with-teaching-cues")) {
  console.error("Delivery requires --original-source and a model-authored plan compiled with saved teaching cues.");
  process.exit(1);
}
const originalSource = path.resolve(flags["original-source"] || input);
if (!isFallback) {
  for (const evidence of [plan.planningEvidence.modelPlan, plan.planningEvidence.teachingCues]) {
    if (!evidence?.path || await sha256(evidence.path).catch(() => null) !== evidence.sha256) {
      console.error("Saved model plan or teaching cues changed or are missing. Recompile the executable plan.");
      process.exit(1);
    }
  }
}
const sourceValidation = await validatePresentation(input);
if (!sourceValidation.valid) {
  console.error(JSON.stringify({ stage: "source-preflight", validation: sourceValidation }, null, 2));
  process.exit(1);
}
if (isFallback && flags["allow-fallback"] !== true) {
  console.error("This is a deterministic fallback plan. It is review-only by default; use a model-authored executable plan for delivery, or pass --allow-fallback for an intentional draft test.");
  process.exit(1);
}
try {
  await fs.access(output);
  console.error(`Output already exists and will not be overwritten: ${output}`);
  process.exit(1);
} catch {
  // Expected: output does not exist.
}

await fs.mkdir(path.dirname(output), { recursive: true });
const extension = path.extname(output) || ".pptx";
const temporaryOutput = path.join(
  path.dirname(output),
  `.${path.basename(output, extension)}.pending-${process.pid}-${Date.now()}${extension}`,
);

try {
  const result = await applyPlan(input, plan, temporaryOutput, existingPolicy);
  const validation = await validatePresentation(temporaryOutput);
  const structuralIntegrity = await validateStructuralIntegrity(input, temporaryOutput);
  const audit = await auditAnimationResult(input, temporaryOutput, plan, existingPolicy);
  const originalMedia = await auditOriginalMediaPreservation(originalSource, temporaryOutput);
  if (!validation.valid || !structuralIntegrity.valid || !audit.valid || !originalMedia.valid) {
    console.error(JSON.stringify({
      stage: "post-write-validation",
      output: temporaryOutput,
      summary: result.summary,
      errors: [...validation.errors, ...structuralIntegrity.errors, ...audit.errors, ...originalMedia.errors],
      issueSlides: audit.slides.filter((slide) => slide.teachingErrors.length || slide.missingTargets.length
        || slide.extraTargets.length).map((slide) => ({ slide: slide.slide, status: slide.status,
        teachingErrors: slide.teachingErrors, missingTargets: slide.missingTargets, extraTargets: slide.extraTargets })),
      published: false,
    }, null, 2));
    process.exitCode = 1;
  } else {
    const manifest = {
      schemaVersion: 1,
      status: isFallback ? "test-draft" : "structural-and-teaching-audit-passed",
      playbackStatus: "not-verified-in-presentation-app",
      originalSource: { path: originalSource, sha256: await sha256(originalSource) },
      inputSource: { path: input, sha256: plan.source.sha256 },
      executablePlan: { path: planPath, sha256: await sha256(planPath) },
      planningEvidence: plan.planningEvidence || null,
      originalMedia: { ...originalMedia, output },
      audit: { valid: audit.valid, warnings: audit.warnings, slides: audit.slides },
    };
    const manifestPath = `${output}.animation-audit.json`;
    const temporaryManifest = `${temporaryOutput}.animation-audit.json`;
    await fs.writeFile(temporaryManifest, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
    try {
      await fs.rename(temporaryOutput, output);
      await fs.rename(temporaryManifest, manifestPath);
    } catch (error) {
      await Promise.all([fs.rm(output, { force: true }), fs.rm(temporaryManifest, { force: true })]);
      throw error;
    }
    console.log(JSON.stringify({
      output,
      summary: result.summary,
      validation: { valid: validation.valid, errors: validation.errors },
      structuralIntegrity: { valid: structuralIntegrity.valid, errors: structuralIntegrity.errors },
      originalMedia: { valid: originalMedia.valid, errors: originalMedia.errors },
      audit: {
        valid: audit.valid,
        issueSlides: audit.slides.filter((slide) => slide.teachingErrors.length || slide.teachingWarnings.length
          || slide.missingTargets.length || slide.extraTargets.length).map((slide) => slide.slide),
        errors: audit.errors,
        warnings: audit.warnings,
      },
      manifest: manifestPath,
      published: true,
    }, null, 2));
  }
} finally {
  await fs.rm(temporaryOutput, { force: true });
}
