#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { auditAnimationResult, auditOriginalMediaPreservation, parseArgs } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !positional[1] || !positional[2]) {
  console.error("Usage: node scripts/audit-animation-result.mjs SOURCE.pptx OUTPUT.pptx PLAN.json [--original-source ORIGINAL.pptx] [--existing preserve|skip|replace] [--report REPORT.json] [--verbose]");
  process.exit(2);
}

const source = path.resolve(positional[0]);
const output = path.resolve(positional[1]);
const planPath = path.resolve(positional[2]);
const plan = JSON.parse(await fs.readFile(planPath, "utf8"));
const report = await auditAnimationResult(source, output, plan, flags.existing || plan.defaultExistingPolicy || "preserve");
report.originalMedia = await auditOriginalMediaPreservation(
  flags["original-source"] ? path.resolve(flags["original-source"]) : source, output,
);
if (!report.originalMedia.valid) {
  report.valid = false;
  report.errors.push(...report.originalMedia.errors);
}
if (flags.report) {
  const reportPath = path.resolve(flags.report);
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
}
console.log(JSON.stringify(flags["verbose"] === true ? report : {
  valid: report.valid,
  source: report.source,
  output: report.output,
  slideCount: report.slideCount,
  issueSlides: report.slides.filter((slide) => slide.status !== "covered"
    && !slide.status.startsWith("preserved")).map((slide) => slide.slide),
  errors: report.errors,
  warnings: report.warnings,
  report: flags.report ? path.resolve(flags.report) : undefined,
}, null, 2));
if (!report.valid) process.exit(1);
