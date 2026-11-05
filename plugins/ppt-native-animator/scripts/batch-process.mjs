#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { createPlan, parseArgs } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0]) {
  console.error("Usage: node scripts/batch-process.mjs DIRECTORY [--preset auto-teaching] [--output-dir draft-plans] (deterministic review drafts only)");
  process.exit(2);
}

const sourceDir = path.resolve(positional[0]);
const outputDir = path.resolve(flags["output-dir"] || path.join(sourceDir, "animation-plans"));
const preset = flags.preset || "auto-teaching";
await fs.mkdir(outputDir, { recursive: true });

const supported = new Set([".pptx", ".pptm", ".ppsx", ".potx"]);
const files = (await fs.readdir(sourceDir, { withFileTypes: true }))
  .filter((entry) => entry.isFile() && supported.has(path.extname(entry.name).toLowerCase()))
  .map((entry) => path.join(sourceDir, entry.name));
const results = [];
for (const file of files) {
  try {
    const plan = await createPlan(file, preset);
    const output = path.join(outputDir, `${path.basename(file, path.extname(file))}_fallback-draft-plan.json`);
    await fs.writeFile(output, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
    results.push({ file, plan: output, status: "review-draft", deliveryReady: false });
  } catch (error) {
    results.push({ file, status: "failed", error: error.message });
  }
}
console.log(JSON.stringify({ sourceDir, outputDir, preset, analysisMode: "deterministic-fallback", deliveryReady: false, results }, null, 2));
