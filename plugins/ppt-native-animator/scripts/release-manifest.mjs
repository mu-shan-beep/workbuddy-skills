#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, sha256 } from "./lib/core.mjs";

const { flags } = parseArgs(process.argv.slice(2));
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestName = ".codex-plugin/release-manifest.json";
const ignored = new Set(["node_modules", ".git", ".DS_Store"]);

async function releaseFiles(directory, relative = "") {
  const files = [];
  for (const entry of await fs.readdir(path.join(directory, relative), { withFileTypes: true })) {
    if (ignored.has(entry.name)) continue;
    const name = path.posix.join(relative, entry.name);
    if (name === manifestName) continue;
    if (entry.isSymbolicLink()) throw new Error(`Release files must not be symlinks: ${name}`);
    if (entry.isDirectory()) files.push(...await releaseFiles(directory, name));
    else if (entry.isFile()) files.push({ path: name, sha256: await sha256(path.join(directory, name)) });
  }
  return files.sort((a, b) => a.path.localeCompare(b.path));
}

async function metadata(directory) {
  const plugin = JSON.parse(await fs.readFile(path.join(directory, ".codex-plugin/plugin.json"), "utf8"));
  const pkg = JSON.parse(await fs.readFile(path.join(directory, "package.json"), "utf8"));
  if (!/^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$/.test(plugin.name || "")) throw new Error("Invalid plugin name.");
  if (plugin.name !== pkg.name || plugin.version !== pkg.version) throw new Error("Plugin and package names/versions do not match.");
  return { name: plugin.name, version: plugin.version };
}

async function verify(directory) {
  const manifest = JSON.parse(await fs.readFile(path.join(directory, manifestName), "utf8"));
  const meta = await metadata(directory);
  if (manifest.schemaVersion !== 1 || manifest.name !== meta.name || manifest.version !== meta.version) {
    throw new Error(`Release metadata differs in ${directory}.`);
  }
  const files = await releaseFiles(directory);
  if (JSON.stringify(manifest.files) !== JSON.stringify(files)) {
    const expected = new Map((manifest.files || []).map((file) => [file.path, file.sha256]));
    const actual = new Map(files.map((file) => [file.path, file.sha256]));
    const changed = [...new Set([...expected.keys(), ...actual.keys()])]
      .filter((name) => expected.get(name) !== actual.get(name));
    throw new Error(`Release fingerprint mismatch: ${changed.join(", ")}`);
  }
  return manifest;
}

if (flags.write === true) {
  const meta = await metadata(root);
  const manifest = { schemaVersion: 1, ...meta, files: await releaseFiles(root) };
  await fs.writeFile(path.join(root, manifestName), `${JSON.stringify(manifest, null, 2)}\n`);
}
const manifest = await verify(root);
if (flags.against) {
  const reference = await verify(path.resolve(flags.against));
  if (JSON.stringify(manifest) !== JSON.stringify(reference)) throw new Error("Installed plugin differs from the source release.");
}
console.log(JSON.stringify({ valid: true, root, version: manifest.version, files: manifest.files.length,
  sourceMatched: flags.against ? path.resolve(flags.against) : undefined }, null, 2));
