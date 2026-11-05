#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { inspectPresentation, parseArgs } from "./lib/core.mjs";

const { positional, flags } = parseArgs(process.argv.slice(2));
if (!positional[0]) {
  console.error("Usage: node scripts/inspect-presentation.mjs INPUT.pptx [--output inspection.json]");
  process.exit(2);
}

const result = await inspectPresentation(positional[0]);
const json = `${JSON.stringify(result, null, 2)}\n`;
if (flags.output) {
  await fs.mkdir(path.dirname(path.resolve(flags.output)), { recursive: true });
  await fs.writeFile(path.resolve(flags.output), json, "utf8");
  console.log(path.resolve(flags.output));
} else {
  process.stdout.write(json);
}
