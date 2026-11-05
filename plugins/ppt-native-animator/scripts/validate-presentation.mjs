#!/usr/bin/env node
import { parseArgs, validatePresentation } from "./lib/core.mjs";

const { positional } = parseArgs(process.argv.slice(2));
if (!positional[0]) {
  console.error("Usage: node scripts/validate-presentation.mjs INPUT.pptx");
  process.exit(2);
}

const result = await validatePresentation(positional[0]);
console.log(JSON.stringify(result, null, 2));
if (!result.valid) process.exit(1);
