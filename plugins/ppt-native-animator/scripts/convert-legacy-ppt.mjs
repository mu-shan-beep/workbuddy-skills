#!/usr/bin/env node
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { parseArgs } from "./lib/core.mjs";

const execFileAsync = promisify(execFile);
const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0] || !flags["output-dir"]) {
  console.error("Usage: node scripts/convert-legacy-ppt.mjs INPUT.ppt --output-dir DIRECTORY");
  process.exit(2);
}
const input = path.resolve(positional[0]);
const outputDir = path.resolve(flags["output-dir"]);
if (path.extname(input).toLowerCase() !== ".ppt") throw new Error("Input must be a legacy .ppt file");
await fs.mkdir(outputDir, { recursive: true });
const candidates = ["soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"];
let lastError;
for (const executable of candidates) {
  try {
    await execFileAsync(executable, ["--headless", "--convert-to", "pptx", "--outdir", outputDir, input]);
    const output = path.join(outputDir, `${path.basename(input, ".ppt")}.pptx`);
    await fs.access(output);
    console.log(output);
    process.exit(0);
  } catch (error) {
    lastError = error;
  }
}
throw new Error(`LibreOffice headless conversion is unavailable: ${lastError?.message ?? "unknown error"}`);
