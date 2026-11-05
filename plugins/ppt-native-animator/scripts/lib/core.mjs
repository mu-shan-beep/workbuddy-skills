import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const schemaValidationCache = new Map();
export const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const ANALYSIS_REVISION = 8;

// Only high-confidence observation prompts are inferred here. Other teaching
// dependencies are authored explicitly through requiresVisibleModuleIds.
function asksAboutVisiblePicture(value) {
  const text = String(value || "").replace(/\s+/g, " ");
  return /\b(?:is (?:it|this|that) an? .{1,70} or an? |what (?:is|are) (?:this|that|these|those)|look at (?:the|this)|what can you see|which (?:picture|image))\b/i.test(text)
    || /(?:看图|图中|图片中|画面中|观察这|这(?:是|辆|个).{0,20}还是)/.test(text);
}

async function validateOpenXmlSchema(filePath) {
  const stat = await fs.stat(filePath);
  const cacheKey = `${filePath}:${stat.size}:${stat.mtimeMs}`;
  if (schemaValidationCache.has(cacheKey)) return schemaValidationCache.get(cacheKey);
  let result;
  try {
    await execFileAsync("officecli", ["validate", filePath], { timeout: 60000, maxBuffer: 1024 * 1024 });
    result = { valid: true, errors: [] };
  } catch (error) {
    const detail = String(error.stdout || error.stderr || error.message || "unknown validation error").trim();
    result = { valid: false, errors: [error.code === "ENOENT"
      ? "OfficeCLI is required for strict OpenXML schema validation but was not found."
      : `OfficeCLI OpenXML schema validation failed: ${detail}`] };
  }
  schemaValidationCache.set(cacheKey, result);
  return result;
}

export function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      positional.push(token);
      continue;
    }
    const key = token.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      flags[key] = next;
      i += 1;
    } else {
      flags[key] = true;
    }
  }
  return { positional, flags };
}

export async function sha256(filePath) {
  const data = await fs.readFile(filePath);
  return createHash("sha256").update(data).digest("hex");
}

export async function extractPptx(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (![".pptx", ".pptm", ".ppsx", ".potx"].includes(ext)) {
    throw new Error(`Unsupported package ${ext || "(no extension)"}. Convert legacy .ppt to .pptx first.`);
  }
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "ppt-native-animator-"));
  try {
    await execFileAsync("unzip", ["-qq", path.resolve(filePath), "-d", tempDir]);
    await fs.access(path.join(tempDir, "ppt", "presentation.xml"));
    return tempDir;
  } catch (error) {
    await fs.rm(tempDir, { recursive: true, force: true });
    const header = await fs.readFile(filePath).then((data) => data.subarray(0, 4).toString("hex")).catch(() => "");
    const hint = header.startsWith("504b")
      ? "The file starts like an OOXML package but its ZIP directory is missing; it is probably incomplete or corrupted. Download/export it again."
      : "The file is not a valid OOXML PowerPoint package. Convert legacy .ppt files to .pptx first.";
    throw new Error(`Unable to extract PowerPoint package. ${hint}`);
  }
}

export async function packPptx(tempDir, outputPath) {
  const absolute = path.resolve(outputPath);
  try {
    await fs.access(absolute);
    throw new Error(`Refusing to overwrite existing output: ${absolute}`);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  await fs.mkdir(path.dirname(absolute), { recursive: true });
  await execFileAsync("zip", ["-qr", absolute, "."], { cwd: tempDir });
  return absolute;
}

export async function cleanupTemp(tempDir) {
  await fs.rm(tempDir, { recursive: true, force: true });
}

function decodeXml(value = "") {
  return value
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", "\"")
    .replaceAll("&apos;", "'")
    .replaceAll("&amp;", "&");
}

function hashParts(parts) {
  const hash = createHash("sha256");
  for (const part of parts) hash.update(part);
  return hash.digest("hex");
}

function xmlAttributes(tag) {
  return Object.fromEntries([...tag.matchAll(/([\w:.-]+)\s*=\s*(["'])([\s\S]*?)\2/g)]
    .map((match) => [match[1], decodeXml(match[3])]));
}

/** Resolve audience page order independently of internal slide filenames. */
async function presentationSlideOrder(packageDir, presentationXml) {
  const rels = await fs.readFile(path.join(packageDir, "ppt", "_rels", "presentation.xml.rels"), "utf8");
  const relationships = new Map([...rels.matchAll(/<Relationship\b[^>]*\/?\s*>/g)]
    .map((match) => xmlAttributes(match[0])).map((attrs) => [attrs.Id, attrs]));
  const list = presentationXml.match(/<p:sldIdLst(?:\s[^>]*)?>([\s\S]*?)<\/p:sldIdLst>/)?.[1] || "";
  const ordered = [];
  const seen = new Set();
  for (const match of list.matchAll(/<p:sldId\b[^>]*\/?\s*>/g)) {
    const attrs = xmlAttributes(match[0]);
    const relationship = relationships.get(attrs["r:id"]);
    if (!relationship || relationship.TargetMode === "External" || !/\/slide$/.test(relationship.Type || "")) {
      throw new Error(`Invalid slide relationship ${attrs["r:id"] || "(missing)"}.`);
    }
    const target = relationship.Target.startsWith("/")
      ? path.posix.normalize(relationship.Target.slice(1))
      : path.posix.normalize(path.posix.join("ppt", relationship.Target));
    const file = path.posix.relative("ppt/slides", target);
    if (!target.startsWith("ppt/slides/") || file.includes("/") || !file.endsWith(".xml") || seen.has(target)) {
      throw new Error(`Invalid or repeated slide part ${target}.`);
    }
    seen.add(target);
    await fs.access(path.join(packageDir, target));
    ordered.push({ slide: ordered.length + 1, file, relationshipId: attrs["r:id"], slideId: attrs.id });
  }
  if (!ordered.length) throw new Error("No referenced slides found in presentation.xml.");
  return ordered;
}

async function hashDirectoryTree(rootDir, relativeDirs) {
  const entries = [];
  const visit = async (relativePath) => {
    const absolutePath = path.join(rootDir, relativePath);
    let children;
    try {
      children = await fs.readdir(absolutePath, { withFileTypes: true });
    } catch {
      return;
    }
    for (const child of children) {
      const childRelative = path.join(relativePath, child.name);
      if (child.isDirectory()) await visit(childRelative);
      else entries.push([childRelative.split(path.sep).join("/"), await fs.readFile(path.join(rootDir, childRelative))]);
    }
  };
  for (const relativeDir of relativeDirs) await visit(relativeDir);
  entries.sort(([a], [b]) => a.localeCompare(b));
  return hashParts(entries.flatMap(([name, data]) => [name, data]));
}

async function slidePlanningFingerprint(packageDir, slideName, slideXml) {
  const slideDir = path.join(packageDir, "ppt", "slides");
  const relsPath = path.join(slideDir, "_rels", `${slideName}.rels`);
  const parts = [slideXml];
  try {
    const relsXml = await fs.readFile(relsPath, "utf8");
    parts.push(relsXml);
    const targets = [...relsXml.matchAll(/<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*>/g)]
      .map((match) => decodeXml(match[1]))
      .filter((target) => !/^[a-z]+:/i.test(target));
    for (const target of [...new Set(targets)].sort()) {
      const targetPath = path.resolve(slideDir, target);
      if (!targetPath.startsWith(`${packageDir}${path.sep}`)) continue;
      try {
        parts.push(target, await fs.readFile(targetPath));
      } catch {
        parts.push(target, "missing");
      }
    }
  } catch {
    parts.push("no-slide-relationships");
  }
  return hashParts(parts);
}

function matchNumber(text, pattern, fallback = 0) {
  const match = text.match(pattern);
  return match ? Number(match[1]) : fallback;
}

function parseParagraphs(block) {
  const paragraphs = [];
  // Empty paragraphs still occupy OOXML pRg indices. Never compact this array.
  for (const match of block.matchAll(/<a:p\b[^>]*\/>|<a:p(?:\s[^>]*)?>([\s\S]*?)<\/a:p>/g)) {
    const runs = [...(match[1] || "").matchAll(/<a:t(?:\s[^>]*)?>([\s\S]*?)<\/a:t>/g)].map((item) => decodeXml(item[1]));
    const text = runs.join("").trim();
    paragraphs.push(text);
  }
  return paragraphs;
}

function parseFill(block, type) {
  // Only inspect the shape properties. Text run colors also use a:solidFill;
  // treating those as a shape fill caused transparent text boxes to be
  // misclassified as opaque cards.
  const properties = block.match(/<p:spPr(?:\s[^>]*)?>([\s\S]*?)<\/p:spPr>/)?.[1]
    ?? block.match(/<p:grpSpPr(?:\s[^>]*)?>([\s\S]*?)<\/p:grpSpPr>/)?.[1]
    ?? "";
  const solid = properties.match(/<a:solidFill(?:\s[^>]*)?>([\s\S]*?)<\/a:solidFill>/)?.[1] ?? "";
  const color = solid.match(/<a:srgbClr\s+[^>]*val="([0-9A-Fa-f]{6})"/)?.[1]?.toUpperCase()
    ?? solid.match(/<a:schemeClr\s+[^>]*val="([^"]+)"/)?.[1]
    ?? null;
  const alphaValue = solid.match(/<a:alpha\s+[^>]*val="(\d+)"/)?.[1];
  const blipAlphaValue = properties.match(/<a:alphaModFix\s+[^>]*amt="(\d+)"/)?.[1];
  const alpha = (alphaValue == null ? 1 : Math.max(0, Math.min(1, Number(alphaValue) / 100000)))
    * (blipAlphaValue == null ? 1 : Math.max(0, Math.min(1, Number(blipAlphaValue) / 100000)));
  // A line's <a:noFill/> must not override an image fill in the same spPr.
  const fillType = type === "image" || /<(?:a|p):blipFill(?:\s|>)/.test(properties)
    || /<p:blipFill(?:\s|>)/.test(block) ? "image"
    : solid ? "solid" : /<a:gradFill(?:\s|>)/.test(properties) ? "gradient"
      : "none";
  const isWhiteLike = typeof color === "string" && /^[0-9A-F]{6}$/.test(color)
    ? [0, 2, 4].map((index) => Number.parseInt(color.slice(index, index + 2), 16)).every((channel) => channel >= 232)
    : false;
  return { fillType, fillColor: color, fillAlpha: alpha, isWhiteLike };
}

function extractTopLevelSlideBlocks(xml) {
  const tree = xml.match(/<p:spTree(?:\s[^>]*)?>([\s\S]*?)<\/p:spTree>/)?.[1] ?? "";
  const tags = /<\/?p:(?:sp|pic|graphicFrame|cxnSp|grpSp)\b[^>]*>/g;
  const stack = [];
  const blocks = [];
  let start = -1;
  let rootTag = "";
  for (const match of tree.matchAll(tags)) {
    const token = match[0];
    const closing = token.startsWith("</");
    const selfClosing = token.endsWith("/>");
    const tag = token.match(/^<\/?(p:[A-Za-z]+)/)?.[1] ?? "";
    if (!closing) {
      if (!stack.length) {
        start = match.index;
        rootTag = tag;
      }
      if (!selfClosing) stack.push(tag);
      else if (!stack.length && start >= 0) {
        blocks.push({ tag: rootTag, xml: tree.slice(start, match.index + token.length) });
        start = -1;
      }
    } else if (stack.length) {
      stack.pop();
      if (!stack.length && start >= 0) {
        blocks.push({ tag: rootTag, xml: tree.slice(start, match.index + token.length) });
        start = -1;
      }
    }
  }
  return blocks;
}

function parseBlock(block, type, zIndex = 0) {
  const nv = block.match(/<p:cNvPr\s+([^>]*)>/);
  if (!nv) return null;
  const idMatch = nv[1].match(/\bid="(\d+)"/);
  const nameMatch = nv[1].match(/\bname="([^"]*)"/);
  if (!idMatch) return null;
  const paragraphs = parseParagraphs(block);
  const allSizes = [...block.matchAll(/\ssz="(\d+)"/g)].map((m) => Number(m[1]));
  const hasBlipFill = /<(?:a|p):blipFill(?:\s|>)/.test(block);
  const hidden = /\bhidden="(?:1|true)"/.test(nv[1]) || /<a:alpha\s+val="0"\s*\/>/.test(block);
  const fill = parseFill(block, type);
  return {
    id: Number(idMatch[1]),
    name: decodeXml(nameMatch?.[1] ?? ""),
    type: type === "group" ? "group" : hasBlipFill && !paragraphs.some(Boolean) ? "image" : type,
    sourceType: type,
    hasBlipFill,
    hidden,
    zIndex,
    sourceOrder: zIndex,
    parentGroupId: null,
    groupPath: [],
    paragraphs,
    text: paragraphs.join("\n").trim(),
    fontSize: allSizes.length ? Math.max(...allSizes) : 0,
    x: matchNumber(block, /<a:off\s+[^>]*x="(-?\d+)"/),
    y: matchNumber(block, /<a:off\s+[^>]*y="(-?\d+)"/),
    width: matchNumber(block, /<a:ext\s+[^>]*cx="(\d+)"/),
    height: matchNumber(block, /<a:ext\s+[^>]*cy="(\d+)"/),
    rotation: matchNumber(block, /<a:xfrm\s+[^>]*rot="(-?\d+)"/),
    shapeType: block.match(/<a:prstGeom\s+[^>]*prst="([^"]+)"/)?.[1] ?? null,
    childCount: type === "group" ? extractTopLevelSlideBlocks(`<p:spTree>${block}</p:spTree>`).length : 0,
    ...fill,
  };
}

export function parseSlideElements(xml, slideSize) {
  const typeByTag = new Map([
    ["p:sp", "shape"], ["p:pic", "image"], ["p:graphicFrame", "graphic"],
    ["p:cxnSp", "connector"], ["p:grpSp", "group"],
  ]);
  const elements = extractTopLevelSlideBlocks(xml)
    .map((entry, index) => parseBlock(entry.xml, typeByTag.get(entry.tag) ?? "shape", index))
    .filter((item) => item && item.id > 1);
  const visible = elements.filter((item) => !item.hidden
    && item.width > 0 && item.height > 0
    && item.x + item.width > 0 && item.y + item.height > 0
    && item.x < slideSize.width && item.y < slideSize.height);
  const maxFont = Math.max(0, ...visible.map((item) => item.fontSize));
  for (const item of visible) {
    item.role = classifyRole(item, { ...slideSize, maxFont });
    item.areaRatio = slideSize.width && slideSize.height
      ? (item.width * item.height) / (slideSize.width * slideSize.height)
      : 0;
  }
  const multipleChoiceQuestion = visible.some((item) => /[?？]/.test(item.text)
    && /(?:A[．.、]\s*.+B[．.、]|B[．.、]\s*.+C[．.、])/s.test(item.text));
  if (multipleChoiceQuestion) {
    for (const item of visible) {
      if (/^[A-DＡ-Ｄ]$/i.test(item.text.trim()) && item.areaRatio < 0.035) item.role = "answer";
    }
  }
  return normalizeElements(visible, slideSize);
}

function normalizedText(value = "") {
  return value.replace(/[\s\u00a0]+/g, "").replace(/[，。；：、,.!?！？“”‘’"'（）()【】\[\]]/g, "").toLowerCase();
}

function intersectionArea(a, b) {
  const width = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const height = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  return width * height;
}

function overlapRatio(a, b) {
  const intersection = intersectionArea(a, b);
  const smaller = Math.max(1, Math.min(a.width * a.height, b.width * b.height));
  return intersection / smaller;
}

function centerInside(inner, outer) {
  const cx = inner.x + inner.width / 2;
  const cy = inner.y + inner.height / 2;
  return cx >= outer.x && cx <= outer.x + outer.width && cy >= outer.y && cy <= outer.y + outer.height;
}

/** Find the nearest visible plate carrying each readable text object. */
function contentBackingPairs(elements, slideSize) {
  const slideArea = Math.max(1, slideSize.width * slideSize.height);
  const pairs = [];
  for (const content of elements) {
    if (String(content.text || "").replace(/\s+/g, "").length < 8) continue;
    if (["background", "decoration", "repeat", "page-number"].includes(content.role)) continue;
    const contentArea = Math.max(1, content.width * content.height);
    const candidates = elements.filter((backing) => {
      if (backing.id === content.id || backing.text || backing.zIndex >= content.zIndex) return false;
      const backingArea = backing.width * backing.height;
      const areaRatio = backingArea / slideArea;
      if (areaRatio < 0.035 || areaRatio > 0.72 || backingArea < contentArea * 1.05) return false;
      if (backing.role !== "container" && !(backing.type === "group" && backing.fillType === "solid")) return false;
      return intersectionArea(backing, content) / contentArea >= 0.82;
    });
    if (!candidates.length) continue;
    const direct = candidates.find((backing) => backing.id === content.containerId);
    const nearest = direct || candidates.sort((a, b) => a.width * a.height - b.width * b.height)[0];
    pairs.push({ backingId: nearest.id, contentId: content.id });
  }
  return pairs;
}

function normalizeElements(elements, slideSize) {
  const kept = [];
  for (const item of elements) {
    const textKey = String(item.text || "").replace(/[\s\u00a0]+/g, "");
    const duplicateIndex = textKey ? kept.findIndex((candidate) => String(candidate.text || "").replace(/[\s\u00a0]+/g, "") === textKey
      && overlapRatio(item, candidate) >= 0.68) : -1;
    if (duplicateIndex >= 0) {
      const candidate = kept[duplicateIndex];
      // Retain every real shape and animate overlapping copies atomically.
      // Dropping a duplicate here leaves its original visible in the PPTX.
      item.duplicateGroupId = candidate.duplicateGroupId ?? candidate.id;
      candidate.duplicateGroupId = item.duplicateGroupId;
    }
    kept.push(item);
  }
  for (const item of kept.filter((entry) => entry.duplicateGroupId != null)) {
    const siblings = kept.filter((entry) => entry.duplicateGroupId === item.duplicateGroupId);
    const role = ["answer", "question", "analysis", "conclusion"].find((value) => siblings.some((entry) => entry.role === value));
    if (role) for (const sibling of siblings) sibling.role = role;
  }

  // Small pictures are often meaningful icons or thumbnails. Keep them animatable
  // when a nearby text label describes them; isolated small pictures remain decoration.
  for (const item of kept) {
    if (item.type !== "image" || item.role !== "decoration") continue;
    if (item.y < slideSize.height * 0.2 && item.width / Math.max(1, item.height) > 3.2) continue;
    const nearbyLabel = kept.some((candidate) => {
      if (!candidate.text || candidate === item || ["decoration", "page-number"].includes(candidate.role)) return false;
      const gaps = gapBetween(itemBounds(item), itemBounds(candidate));
      const horizontalOverlap = axisOverlap(item.x, item.width, candidate.x, candidate.width);
      const verticalOverlap = axisOverlap(item.y, item.height, candidate.y, candidate.height);
      return (horizontalOverlap >= 0.45 && gaps.vertical <= slideSize.height * 0.045)
        || (verticalOverlap >= 0.45 && gaps.horizontal <= slideSize.width * 0.025);
    });
    if (nearbyLabel) item.role = "image";
  }

  // A caption may span only the first items in a row of equal-sized thumbnails.
  // Once one thumbnail is known to be content, promote its aligned siblings too,
  // so a visual series is animated as a complete set instead of being cut in half.
  let promotedSibling = true;
  while (promotedSibling) {
    promotedSibling = false;
    for (const item of kept) {
      if (item.type !== "image" || item.role !== "decoration") continue;
      const sibling = kept.find((candidate) => {
        if (candidate.type !== "image" || candidate.role !== "image") return false;
        const widthRatio = Math.min(item.width, candidate.width) / Math.max(1, Math.max(item.width, candidate.width));
        const heightRatio = Math.min(item.height, candidate.height) / Math.max(1, Math.max(item.height, candidate.height));
        const verticalOverlap = axisOverlap(item.y, item.height, candidate.y, candidate.height);
        const gaps = gapBetween(itemBounds(item), itemBounds(candidate));
        return widthRatio >= 0.78 && heightRatio >= 0.78 && verticalOverlap >= 0.72
          && gaps.horizontal <= slideSize.width * 0.035;
      });
      if (sibling) {
        item.role = "image";
        promotedSibling = true;
      }
    }
  }

  const graphics = kept.filter((item) => item.type === "graphic" && item.areaRatio > 0.08);
  const filtered = kept.filter((item) => item.type === "graphic"
    || !item.text
    || !graphics.some((graphic) => centerInside(item, graphic) && overlapRatio(item, graphic) > 0.35));
  const containers = filtered.filter((item) => item.role === "image"
      || (!item.text && item.sourceType === "shape" && item.fillType !== "none"
        && item.fillAlpha > 0.05 && item.areaRatio > 0.004 && item.areaRatio < 0.45))
    .map((image) => ({
      image,
      children: filtered.filter((item) => item.text && centerInside(item, image)
        && image.zIndex < item.zIndex && overlapRatio(item, image) >= 0.5),
    }))
    .filter(({ children }) => children.length >= 1)
    .sort((a, b) => a.image.width * a.image.height - b.image.width * b.image.height);
  for (const { image, children } of containers) {
    image.role = "container";
    image.containerId = image.id;
    image.backingForIds = children.map((child) => child.id);
    for (const child of children) if (child.containerId == null) child.containerId = image.id;
  }
  // A filled rectangle above text is not a backing plate. It is usually a mask,
  // answer cover, or other foreground overlay and must never receive a normal
  // entrance animation independently from the covered content.
  for (const overlay of filtered) {
    if (overlay.text || overlay.role === "container" || overlay.sourceType !== "shape"
      || overlay.fillType === "none" || overlay.fillAlpha <= 0.05) continue;
    const covered = filtered.filter((item) => item.text && overlay.zIndex > item.zIndex
      && centerInside(item, overlay) && overlapRatio(item, overlay) >= 0.55);
    if (!covered.length) continue;
    overlay.role = "mask";
    overlay.overlayForIds = covered.map((item) => item.id);
  }
  // If a text object overlaps a separate filled shape behind it but the
  // relationship is not strong enough to prove a container binding, do not
  // guess. Mark the text as relationship-ambiguous so the planner keeps it
  // static together with the already-static backing candidate.
  for (const item of filtered) {
    if (!item.text || item.containerId != null) continue;
    const ambiguousBackingIds = filtered.filter((candidate) => candidate !== item
      && !candidate.text
      && candidate.sourceType === "shape"
      && candidate.fillType !== "none"
      && candidate.fillAlpha > 0.05
      && candidate.areaRatio > 0.004
      && candidate.areaRatio < 0.45
      && candidate.zIndex < item.zIndex
      && overlapRatio(item, candidate) >= 0.2).map((candidate) => candidate.id);
    if (ambiguousBackingIds.length) item.ambiguousBackingIds = ambiguousBackingIds;
  }
  return filtered;
}

function classifyRole(item, context) {
  const name = item.name.toUpperCase();
  const text = item.text.trim();
  const areaRatio = context.width && context.height ? (item.width * item.height) / (context.width * context.height) : 0;
  if (/^(NOANIM_|BG_|DEC_)/.test(name) || /(BACKGROUND|背景|装饰|LOGO)/i.test(item.name)) return "decoration";
  if (/^ST_/.test(name) || /副标题/.test(item.name)) return "subtitle";
  if (/^T_/.test(name) || /(主标题|标题)/.test(item.name)) return "title";
  if (/^Q_/.test(name)) return "question";
  if (/^A_/.test(name)) return "answer";
  if (/^H_/.test(name)) return "hint";
  if (/^E_/.test(name)) return "analysis";
  if (/^C_/.test(name)) return "conclusion";
  if (/^S\d+_/.test(name)) return "step";
  if ((item.type === "image" || item.hasBlipFill) && areaRatio > 0.68) return "background";
  if (item.type === "image" && item.sourceType === "shape" && item.fillAlpha < 0.5
    && item.width >= context.width * 0.9 && areaRatio > 0.45) return "background";
  if ((item.type === "image" || item.hasBlipFill) && areaRatio < 0.025) return "decoration";
  if (/(^|[\s【（(])(答案|参考答案|正确答案|解：|解:)/.test(text)) return "answer";
  if (/(^|[\s【（(])(提示|思路)/.test(text)) return "hint";
  if (/(易错|解析|点拨|注意)/.test(text)) return "analysis";
  if (/(结\s*论|小\s*结|^总\s*结(?:[:：\s]|$))/.test(text)) return "conclusion";
  if (/(^|[\s【（(])(例题|练习|问题|思考|任务)(?:[\d一二三四五六七八九十.:：、\s]|$)/.test(text)
    || /[?？]\s*$/.test(text)) return "question";
  if (text && item.x < context.width * 0.4 && item.y < context.height * 0.18 && item.fontSize >= context.maxFont * 0.45 && text.length <= 100) return "title";
  if (text && item.x < context.width * 0.4 && item.y < context.height * 0.24 && item.fontSize >= context.maxFont * 0.32 && text.length <= 120) return "subtitle";
  if (/(^|\s)(第[\u4e00-十\d]+步|步骤[\u4e00-十\d]*|[①②③④⑤⑥⑦⑧⑨])/.test(text)) return "step";
  if (text.length <= 18 && item.fontSize >= context.maxFont * 0.36) return "section-title";
  if (/(页码|PAGE)/i.test(item.name)
    || (/^\d{1,3}$/.test(text) && item.y > context.height * 0.9
      && (item.x < context.width * 0.06 || item.x > context.width * 0.9))) return "page-number";
  if (item.type === "graphic" || item.type === "group" || item.type === "connector") return "diagram";
  if (item.type === "image") return "image";
  if (!text) return "decoration";
  return "body";
}

export function parseExistingAnimationSummary(xml) {
  const timing = slideTiming(xml);
  if (!timing) return {
    hasTiming: false, meaningful: false, status: "none", targetCount: 0,
    targets: [], hasMedia: false, hasBuilds: false,
  };
  const hasMedia = /<p:(?:audio|video|cmd)(?:\s|>)/.test(timing);
  const hasBuilds = /<p:bld(?:P|Dgm|OleChart)(?:\s|>)/.test(timing);
  const targets = [];
  const seen = new Set();
  const effectPatterns = [
    ["effect", /<p:animEffect\b[\s\S]*?<\/p:animEffect>/g],
    ["motion", /<p:animMotion\b[\s\S]*?<\/p:animMotion>/g],
    ["property", /<p:anim(?:\s|>)[\s\S]*?<\/p:anim>/g],
    ["set", /<p:set\b[\s\S]*?<\/p:set>/g],
    ["command", /<p:cmd\b[\s\S]*?<\/p:cmd>/g],
  ];
  for (const [kind, pattern] of effectPatterns) {
    for (const match of timing.matchAll(pattern)) {
      const block = match[0];
      for (const target of block.matchAll(/<p:spTgt\s+[^>]*spid="(\d+)"[^>]*>(?:[\s\S]*?<\/p:spTgt>)?|<p:spTgt\s+[^>]*spid="(\d+)"[^>]*\/>/g)) {
        const shapeId = Number(target[1] ?? target[2]);
        const paragraph = block.match(/<p:pRg\s+[^>]*st="(\d+)"[^>]*end="(\d+)"/);
        const prefix = timing.slice(Math.max(0, match.index - 1200), match.index);
        const nodeTypes = [...prefix.matchAll(/nodeType="([^"]+)"/g)];
        const nodeType = nodeTypes.at(-1)?.[1] ?? "unknown";
        const transition = block.match(/transition="([^"]+)"/)?.[1] ?? null;
        const filter = block.match(/filter="([^"]+)"/)?.[1] ?? null;
        const visibility = block.match(/<p:strVal\s+[^>]*val="([^"]+)"/)?.[1] ?? null;
        const key = `${shapeId}:${kind}:${paragraph?.[1] ?? "all"}:${transition ?? ""}:${visibility ?? ""}`;
        if (seen.has(key)) continue;
        seen.add(key);
        targets.push({
          shapeId,
          kind,
          order: match.index,
          nodeType,
          trigger: nodeType === "clickEffect" ? "on_click"
            : nodeType === "withEffect" ? "with_previous"
              : nodeType === "afterEffect" ? "after_previous" : "unknown",
          transition,
          filter,
          visibility,
          paragraphStart: paragraph ? Number(paragraph[1]) : null,
          paragraphEnd: paragraph ? Number(paragraph[2]) : null,
          isExit: transition === "out" || visibility === "hidden" || /presetClass="exit"/.test(prefix.slice(-500)),
        });
      }
    }
  }
  targets.sort((a, b) => a.order - b.order);
  targets.forEach((target, index) => { target.order = index + 1; });
  const rawTargetIds = [...timing.matchAll(/<p:spTgt\s+[^>]*spid="(\d+)"/g)].map((match) => Number(match[1]));
  const meaningful = targets.length > 0 || rawTargetIds.length > 0 || hasMedia || hasBuilds
    || /presetClass=|<p:(?:anim|animEffect|animMotion|set)(?:\s|>)/.test(timing);
  const summarizedIds = new Set(targets.map((target) => target.shapeId));
  const fullyMapped = rawTargetIds.every((id) => summarizedIds.has(id));
  return {
    hasTiming: true,
    meaningful,
    status: !meaningful ? "empty" : targets.length && fullyMapped ? "supported" : "partial",
    targetCount: new Set(rawTargetIds).size,
    targets,
    hasMedia,
    hasBuilds,
  };
}

function hasMeaningfulTiming(xml) {
  return parseExistingAnimationSummary(xml).meaningful;
}

function hasProtectedMediaTiming(xml) {
  const timing = slideTiming(xml);
  return /<p:(?:audio|video|cmd)(?:\s|>)/.test(timing) || /ppaction:\/\/media/.test(xml);
}

function assessAnimationSafety(summary, elements) {
  if (!summary.meaningful) return { ...summary, safety: "none", unsafeReasons: [] };
  if (summary.hasMedia) return { ...summary, safety: "protected-media", unsafeReasons: [] };
  const elementById = new Map(elements.map((element) => [element.id, element]));
  const reasons = new Set();
  if (summary.status !== "supported") reasons.add("partially-understood-timing");
  if (summary.hasBuilds || summary.targets.some((target) => target.paragraphStart != null)) reasons.add("paragraph-build");
  if (summary.targets.some((target) => ["property", "motion"].includes(target.kind))) reasons.add("position-or-property-animation");
  if (summary.targets.some((target) => target.filter && !/^(?:fade|wipe\()/i.test(target.filter))) reasons.add("compatibility-sensitive-effect");
  if (summary.targets.some((target) => target.trigger === "on_click"
    && elementById.get(target.shapeId)?.role !== "answer")) reasons.add("non-answer-click");
  return {
    ...summary,
    safety: reasons.size ? "unsafe" : "safe",
    unsafeReasons: [...reasons],
  };
}

function inferSlideType(elements, slideNumber) {
  const roles = new Set(elements.map((item) => item.role));
  const textLength = elements.reduce((sum, item) => sum + item.text.length, 0);
  const imageArea = elements.filter((item) => item.role === "image").reduce((sum, item) => sum + item.areaRatio, 0);
  if (roles.has("question") && (roles.has("answer") || roles.has("analysis") || roles.has("hint"))) return "exercise";
  if (roles.has("diagram") || elements.filter((item) => item.role === "step").length >= 2) return "process";
  if (roles.has("conclusion") && roles.has("diagram")) return "data";
  if (textLength > 220 || elements.some((item) => item.paragraphs.length >= 4)) return "text";
  if (slideNumber === 1) return "cover";
  if (imageArea > 0.38) return "story";
  if (elements.filter((item) => !["decoration", "repeat", "background", "container", "page-number"].includes(item.role)).length <= 3) return "cover";
  return "general";
}

export function markRepeatedElements(slides, slideSize) {
  if (slides.length < 2) return;
  for (let slideIndex = 0; slideIndex < slides.length; slideIndex += 1) {
    for (const item of slides[slideIndex].elements) {
      const key = normalizedText(item.text);
      if (!key || ["title", "question", "answer"].includes(item.role)) continue;
      const repeatedElsewhere = slides.some((slide, otherIndex) => otherIndex !== slideIndex
        && slide.elements.some((candidate) => normalizedText(candidate.text) === key
          && Math.abs(candidate.x - item.x) <= slideSize.width * 0.018
          && Math.abs(candidate.y - item.y) <= slideSize.height * 0.018
          && Math.abs(candidate.width - item.width) <= slideSize.width * 0.025
          && Math.abs(candidate.height - item.height) <= slideSize.height * 0.025));
      if (repeatedElsewhere) item.role = "repeat";
    }
  }
}

function routePreset(slideType) {
  return {
    exercise: "question-answer",
    process: "process-diagram",
    data: "data-analysis",
    text: "text-reading",
    story: "visual-story",
    cover: "minimal",
    general: "classroom-step",
  }[slideType] ?? "minimal";
}

export async function loadPreset(id) {
  const file = path.join(PLUGIN_ROOT, "config", `${id}.json`);
  return JSON.parse(await fs.readFile(file, "utf8"));
}

function itemFromElement(element, preset, paragraphIndex = null) {
  const kind = element.role === "answer" ? "answer"
    : element.type === "image" ? "image"
      : ["diagram", "step"].includes(element.role) ? "diagram" : "text";
  return {
    shapeId: element.id,
    name: element.name,
    role: element.role,
    text: paragraphIndex == null ? element.text : element.paragraphs[paragraphIndex],
    paragraphIndex,
    x: element.x,
    y: element.y,
    width: element.width,
    height: element.height,
    fontSize: element.fontSize,
    zIndex: element.zIndex,
    fillType: element.fillType,
    fillColor: element.fillColor,
    isWhiteLike: element.isWhiteLike,
    overlayForIds: element.overlayForIds ?? [],
    backingForIds: element.backingForIds ?? [],
    containerId: element.containerId ?? null,
    effect: preset.effects[kind] ?? "appear",
    durationMs: preset.timing[kind] ?? preset.timing.text,
    direction: element.width >= element.height ? "left" : "up",
  };
}

function expandElement(element, preset) {
  if (preset.paragraphs && ["body", "step", "analysis"].includes(element.role) && element.paragraphs.length > 1) {
    return element.paragraphs.flatMap((text, index) => text ? [itemFromElement(element, preset, index)] : []);
  }
  return [itemFromElement(element, preset)];
}

export function buildStages(elements, preset) {
  const excludedRoles = new Set(["background", "decoration", "repeat", "page-number", "mask"]);
  const unanimated = elements.filter((item) => excludedRoles.has(item.role)).map((item) => ({ shapeId: item.id, name: item.name, role: item.role }));
  const initial = [];
  const candidates = [];
  const startsInitial = (element) => (preset.titleInitial && ["title", "subtitle"].includes(element.role))
    || (preset.questionInitial && element.role === "question");
  for (const element of elements) {
    if (excludedRoles.has(element.role)) continue;
    const containerStartsInitial = element.role === "container"
      && elements.some((child) => child.containerId === element.id && child.id !== element.id && startsInitial(child));
    if (startsInitial(element) || containerStartsInitial) {
      initial.push({ shapeId: element.id, name: element.name, role: element.role, text: element.text });
    } else {
      candidates.push(...expandElement(element, preset));
    }
  }

  const stages = [];
  if (initial.length) stages.push({ id: "initial", trigger: "initial", items: initial });
  const inferredSize = {
    width: Math.max(1, ...elements.map((item) => item.x + item.width)),
    height: Math.max(1, ...elements.map((item) => item.y + item.height)),
  };
  const slideSize = preset.slideSize || inferredSize;
  const maxStages = Math.max(1, Number(preset.maxStages) || candidates.length || 1);
  const appendGroups = (groups, prefix, trigger) => groups.forEach((group, index) => {
    const resolvedTrigger = typeof trigger === "function" ? trigger(index, group) : trigger;
    stages.push({
      id: `${prefix}-${index + 1}`,
      label: group.label,
      trigger: resolvedTrigger,
      delayMs: preset.timing.delay,
      items: group.items,
    });
  });

  const answers = candidates.filter((item) => item.role === "answer");
  const afterAnswer = answers.length
    ? candidates.filter((item) => ["analysis", "conclusion"].includes(item.role))
    : [];
  const beforeAnswer = candidates.filter((item) => item.role !== "answer" && !afterAnswer.includes(item));
  const answerTrigger = preset.answerTrigger || (preset.playback === "auto" ? "after_previous" : "on_click");

  const teachingBeatTrigger = (index) => preset.clickTeachingBeats === true && index > 0
    ? "on_click" : "after_previous";

  if (!answers.length) {
    appendGroups(spatialGroups(beforeAnswer, slideSize, preset.groupBody ? 1 : maxStages), "auto", teachingBeatTrigger);
    return { stages, unanimated };
  }

  const afterCount = afterAnswer.length ? Math.min(2, Math.max(1, maxStages - 2)) : 0;
  const beforeCount = Math.max(1, maxStages - 1 - afterCount);
  appendGroups(spatialGroups(beforeAnswer, slideSize, preset.groupBody ? 1 : beforeCount), "auto", teachingBeatTrigger);
  appendGroups([{ label: "答案", items: answers }], "answer", answerTrigger);
  appendGroups(spatialGroups(afterAnswer, slideSize, afterCount), "follow", "after_previous");
  return { stages, unanimated };
}

function itemBounds(item) {
  return { x: item.x, y: item.y, width: item.width, height: item.height };
}

function gapBetween(a, b) {
  const horizontal = Math.max(0, Math.max(a.x, b.x) - Math.min(a.x + a.width, b.x + b.width));
  const vertical = Math.max(0, Math.max(a.y, b.y) - Math.min(a.y + a.height, b.y + b.height));
  return { horizontal, vertical };
}

function axisOverlap(aStart, aSize, bStart, bSize) {
  const overlap = Math.max(0, Math.min(aStart + aSize, bStart + bSize) - Math.max(aStart, bStart));
  return overlap / Math.max(1, Math.min(aSize, bSize));
}

function unionBounds(items) {
  const left = Math.min(...items.map((item) => item.x));
  const top = Math.min(...items.map((item) => item.y));
  const right = Math.max(...items.map((item) => item.x + item.width));
  const bottom = Math.max(...items.map((item) => item.y + item.height));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function clusterModules(items, slideSize) {
  if (!items.length) return [];
  const parent = items.map((_, index) => index);
  const find = (index) => parent[index] === index ? index : (parent[index] = find(parent[index]));
  const unite = (a, b) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[rootB] = rootA;
  };
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = itemBounds(items[i]);
      const b = itemBounds(items[j]);
      if (items[i].shapeId === items[j].shapeId) {
        unite(i, j);
        continue;
      }
      if (items[i].containerId != null && items[i].containerId === items[j].containerId) {
        unite(i, j);
        continue;
      }
      if (items[i].shapeId === items[j].containerId || items[j].shapeId === items[i].containerId) {
        unite(i, j);
        continue;
      }
      const gaps = gapBetween(a, b);
      const horizontalOverlap = axisOverlap(a.x, a.width, b.x, b.width);
      const hasImage = items[i].role === "image" || items[j].role === "image";
      const sameColumn = horizontalOverlap >= (hasImage ? 0.62 : 0.42)
        && gaps.vertical <= slideSize.height * (hasImage ? 0.025 : 0.045);
      const oneImageOneText = (items[i].role === "image") !== (items[j].role === "image");
      const verticalOverlap = axisOverlap(a.y, a.height, b.y, b.height);
      const sameRowImageLabel = oneImageOneText && verticalOverlap >= 0.48
        && gaps.horizontal <= slideSize.width * 0.03;
      if (sameColumn || sameRowImageLabel) unite(i, j);
    }
  }
  const grouped = new Map();
  items.forEach((item, index) => {
    const root = find(index);
    if (!grouped.has(root)) grouped.set(root, []);
    grouped.get(root).push(item);
  });
  return [...grouped.values()];
}

function collectSectionGroups(items, slideSize) {
  const anchors = items.filter((item) => item.role === "section-title" && !/^\s*\d/.test(item.text));
  if (!anchors.length) return { groups: [], remaining: items };
  const assigned = new Map(anchors.map((anchor) => [anchor, [anchor]]));
  const claimed = new Set(anchors);
  for (const item of items) {
    if (claimed.has(item)) continue;
    const cx = item.x + item.width / 2;
    const candidates = anchors.map((anchor) => {
      const regionWidth = Math.max(anchor.width, slideSize.width * 0.34);
      const left = anchor.x - slideSize.width * 0.018;
      const right = anchor.x + regionWidth + slideSize.width * 0.018;
      const nextY = Math.min(slideSize.height + 1, ...anchors
        .filter((other) => other !== anchor && other.y > anchor.y + slideSize.height * 0.035
          && Math.abs(other.x - anchor.x) <= slideSize.width * 0.08)
        .map((other) => other.y));
      if (cx < left || cx > right || item.y < anchor.y - slideSize.height * 0.025 || item.y >= nextY) return null;
      return { anchor, score: Math.abs(item.y - anchor.y) / slideSize.height + Math.abs(cx - (left + right) / 2) / slideSize.width };
    }).filter(Boolean).sort((a, b) => a.score - b.score);
    if (candidates.length) {
      assigned.get(candidates[0].anchor).push(item);
      claimed.add(item);
    }
  }
  const groups = [...assigned.entries()]
    .map(([anchor, sectionItems]) => ({ label: anchor.text || "内容模块", items: sectionItems }))
    .filter((group) => group.items.length > 1);
  const groupedItems = new Set(groups.flatMap((group) => group.items));
  return { groups, remaining: items.filter((item) => !groupedItems.has(item)) };
}

function spatialGroups(items, slideSize, maxGroups) {
  if (!items.length || maxGroups <= 0) return [];
  const header = items.filter((item) => ["title", "subtitle"].includes(item.role) && item.y < slideSize.height * 0.34);
  const footer = items.filter((item) => !header.includes(item)
    && (/课堂提示|演讲提示|备注|^关键词[:：]/.test(item.text)
      || (item.y > slideSize.height * 0.9 && item.width > slideSize.width * 0.4)));
  const middle = items.filter((item) => !header.includes(item) && !footer.includes(item));
  const sections = collectSectionGroups(middle, slideSize);
  let groups = [
    ...(header.length ? [{ label: "标题区", items: header }] : []),
    ...clusterModules(sections.remaining, slideSize).map((module) => ({ label: "内容模块", items: module })),
    ...sections.groups,
    ...(footer.length ? [{ label: "页脚提示", items: footer }] : []),
  ];
  groups.sort((a, b) => {
    const boxA = unionBounds(a.items);
    const boxB = unionBounds(b.items);
    const aHeader = a.label === "标题区" ? -1 : a.label === "页脚提示" ? 1 : 0;
    const bHeader = b.label === "标题区" ? -1 : b.label === "页脚提示" ? 1 : 0;
    if (aHeader !== bHeader) return aHeader - bHeader;
    const rowTolerance = slideSize.height * 0.055;
    return Math.abs(boxA.y - boxB.y) <= rowTolerance ? boxA.x - boxB.x : boxA.y - boxB.y;
  });
  while (groups.length > maxGroups) {
    let bestIndex = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < groups.length - 1; index += 1) {
      if (groups[index].label === "标题区" || groups[index + 1].label === "页脚提示") continue;
      const a = unionBounds(groups[index].items);
      const b = unionBounds(groups[index + 1].items);
      const gaps = gapBetween(a, b);
      const distance = gaps.horizontal / slideSize.width + gaps.vertical / slideSize.height;
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    groups.splice(bestIndex, 2, {
      label: "合并模块",
      items: [...groups[bestIndex].items, ...groups[bestIndex + 1].items],
    });
  }
  return groups;
}

function compactText(value = "", limit = 320) {
  const compact = String(value).replace(/[\s\u00a0]+/g, " ").trim();
  return compact.length <= limit ? compact : `${compact.slice(0, limit)}…`;
}

function semanticRoleForModule(items) {
  const roles = new Set(items.map((item) => item.role));
  for (const role of ["answer", "question", "analysis", "conclusion", "step", "title", "subtitle", "section-title", "diagram", "image", "body"]) {
    if (roles.has(role)) return role;
  }
  return items[0]?.role ?? "content";
}

function visualAtomicGroups(items, slideSize) {
  if (!items.length) return [];
  const parent = items.map((_, index) => index);
  const find = (index) => parent[index] === index ? index : (parent[index] = find(parent[index]));
  const unite = (a, b) => {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[rootB] = rootA;
  };
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = items[i];
      const b = items[j];
      if (a.duplicateGroupId != null && a.duplicateGroupId === b.duplicateGroupId) {
        unite(i, j);
        continue;
      }
      if (a.containerId != null && a.containerId === b.containerId) {
        unite(i, j);
        continue;
      }
      if (a.shapeId === b.containerId || b.shapeId === a.containerId) {
        unite(i, j);
        continue;
      }
      const boundsA = itemBounds(a);
      const boundsB = itemBounds(b);
      const gaps = gapBetween(boundsA, boundsB);
      const verticalOverlap = axisOverlap(a.y, a.height, b.y, b.height);
      const horizontalOverlap = axisOverlap(a.x, a.width, b.x, b.width);
      const aImage = a.role === "image";
      const bImage = b.role === "image";
      if (aImage && bImage) {
        const widthRatio = Math.min(a.width, b.width) / Math.max(1, Math.max(a.width, b.width));
        const heightRatio = Math.min(a.height, b.height) / Math.max(1, Math.max(a.height, b.height));
        if (widthRatio >= 0.78 && heightRatio >= 0.78 && verticalOverlap >= 0.72
          && gaps.horizontal <= slideSize.width * 0.035) unite(i, j);
        continue;
      }
      if (aImage !== bImage) {
        const image = aImage ? a : b;
        const label = aImage ? b : a;
        const imageArea = image.width * image.height / Math.max(1, slideSize.width * slideSize.height);
        // Long teaching paragraphs beside a large illustration are not icon
        // labels. Binding them would force the question, image and later text
        // into one unbreakable animation stage.
        const sideLabel = imageArea <= 0.08 || (String(label.text || "").length <= 18
          && label.height <= image.height * 0.5);
        const sameRowCaption = sideLabel && verticalOverlap >= 0.48
          && gaps.horizontal <= slideSize.width * 0.03;
        const stackedCaption = horizontalOverlap >= 0.55 && gaps.vertical <= slideSize.height * 0.025;
        if (sameRowCaption || stackedCaption) unite(i, j);
      }
    }
  }
  const groups = new Map();
  items.forEach((item, index) => {
    const root = find(index);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(item);
  });
  return [...groups.values()];
}

/**
 * Convert raw slide elements into stable visual modules for model planning.
 * Cards, image-caption pairs and other visually bound objects animate together.
 */
export function buildVisualModules(elements, slideSize, slideNumber = 1, options = {}) {
  const lockedStaticRoles = new Set(["background", "page-number", "mask"]);
  const revealMaskIds = new Set(options.revealMaskIds || []);
  const activeRevealMasks = elements.filter((item) => item.role === "mask" && revealMaskIds.has(item.id));
  const revealCoveredIds = new Set(activeRevealMasks.flatMap((item) => item.overlayForIds || []));
  const uncertain = elements.filter((item) => item.ambiguousBackingIds?.length);
  const uncertainIds = new Set(uncertain.flatMap((item) => [item.id, ...(item.ambiguousBackingIds || [])]));
  const explicitlyLockedDecoration = (item) => ["decoration", "repeat"].includes(item.role)
    && /(?:^|[_\s-])(BG|BACKGROUND|DEC|DECORATION|LOGO|页码|背景|装饰)(?:$|[_\s-])/i.test(item.name || "");
  const reviewableIds = new Set(elements
    .filter((item) => (item.role === "decoration" || item.role === "repeat") && !explicitlyLockedDecoration(item))
    .map((item) => item.id));
  for (const id of uncertainIds) reviewableIds.add(id);
  const eligible = elements.filter((item) => !lockedStaticRoles.has(item.role)
    && !explicitlyLockedDecoration(item) && !reviewableIds.has(item.id) && !revealCoveredIds.has(item.id));
  const groupedItems = eligible.map((item) => ({ ...item, shapeId: item.id }));
  // Answers must never be fused with their question merely because the two are
  // close together. Otherwise the whole card would incorrectly wait for a click.
  const ordinaryItems = groupedItems.filter((item) => item.role !== "answer");
  const answerItems = groupedItems.filter((item) => item.role === "answer");
  const groups = [ordinaryItems, answerItems]
    .flatMap((items) => visualAtomicGroups(items, slideSize).map((moduleItems) => ({ label: "视觉模块", items: moduleItems })))
    .sort((a, b) => {
      const boxA = unionBounds(a.items);
      const boxB = unionBounds(b.items);
      return Math.abs(boxA.y - boxB.y) <= slideSize.height * 0.055 ? boxA.x - boxB.x : boxA.y - boxB.y;
    });
  const modules = groups.map((group, index) => {
    const moduleId = `s${slideNumber}-m${index + 1}`;
    const semanticRole = semanticRoleForModule(group.items);
    const allParagraphs = group.items.flatMap((item) => (item.paragraphs || []).map((text, paragraphIndex) => ({
      paragraphId: `${moduleId}-e${item.shapeId}-p${paragraphIndex + 1}`,
      shapeId: item.shapeId,
      paragraphIndex,
      text: compactText(text),
    })).filter((paragraph) => paragraph.text.trim()));
    const paragraphs = allParagraphs.length > 1 ? allParagraphs : [];
    return {
      moduleId,
      label: group.label || "内容模块",
      semanticRole,
      semanticRoleIsHint: true,
      memberIds: [...new Set(group.items.map((item) => item.shapeId))],
      memberZOrder: [...new Set(group.items.map((item) => item.shapeId))]
        .sort((a, b) => (group.items.find((item) => item.shapeId === a)?.zIndex ?? 0)
          - (group.items.find((item) => item.shapeId === b)?.zIndex ?? 0)),
      backingIds: group.items.filter((item) => item.role === "container").map((item) => item.shapeId),
      containsWhiteBacking: group.items.some((item) => item.role === "container" && item.isWhiteLike),
      animationConstraints: {
        paragraphAnimationSafe: group.items.every((item) => !item.text
          || (item.fillType === "none" && item.sourceType === "shape" && item.type === "shape")),
        paragraphSelectionSafe: paragraphs.length > 0
          && group.items.filter((item) => item.text).every((item) => item.fillType === "none"
            && item.sourceType === "shape" && item.type === "shape"),
        preserveMemberZOrder: true,
        animateAtomically: group.items.length > 1,
      },
      paragraphs,
      // Keep a short preview even for compound tables/groups. Their paragraphs
      // remain available for precise planning, while the preview makes a
      // grouped conclusion or data image visible in the compact slide brief.
      text: compactText(group.items.map((item) => item.text).filter(Boolean).join(" ｜ "), paragraphs.length ? 96 : 160),
      bounds: unionBounds(group.items),
      confidence: group.items.length > 1 || !["body", "image"].includes(semanticRole) ? "high" : "medium",
    };
  });
  for (const mask of activeRevealMasks) {
    const covered = elements.filter((item) => (mask.overlayForIds || []).includes(item.id));
    modules.push({
      moduleId: `s${slideNumber}-m${modules.length + 1}`,
      label: "遮罩揭示",
      semanticRole: semanticRoleForModule(covered),
      semanticRoleIsHint: true,
      animationMode: "reveal-mask",
      allowedEffects: ["fade-out"],
      memberIds: [mask.id],
      memberZOrder: [mask.id],
      backingIds: [],
      coveredIds: covered.map((item) => item.id),
      text: compactText(covered.map((item) => item.text).filter(Boolean).join(" ｜ ")),
      bounds: itemBounds(mask),
      confidence: "high",
      animationConstraints: {
        paragraphAnimationSafe: false,
        paragraphSelectionSafe: false,
        preserveMemberZOrder: true,
        animateAtomically: true,
      },
      paragraphs: [],
    });
  }
  const ambiguousOwnerById = new Map(uncertain.flatMap((item) => (item.ambiguousBackingIds || [])
    .map((backingId) => [backingId, item.id])));
  const reviewableItems = elements.filter((item) => reviewableIds.has(item.id)).map((item) => ({
    ...item,
    containerId: ambiguousOwnerById.get(item.id) ?? item.containerId,
  }));
  const reviewableGroups = visualAtomicGroups(reviewableItems.map((item) => ({ ...item, shapeId: item.id })), slideSize);
  const reviewableModules = reviewableGroups.map((items, index) => ({
    moduleId: `s${slideNumber}-review-${index + 1}`,
    label: "待模型复核的视觉模块",
    semanticRole: semanticRoleForModule(items),
    semanticRoleIsHint: true,
    memberIds: [...new Set(items.map((item) => item.shapeId))],
    memberZOrder: [...new Set(items.map((item) => item.shapeId))]
      .sort((a, b) => (items.find((item) => item.shapeId === a)?.zIndex ?? 0)
        - (items.find((item) => item.shapeId === b)?.zIndex ?? 0)),
    backingIds: items.filter((item) => item.role === "container").map((item) => item.shapeId),
    text: compactText(items.map((item) => item.text).filter(Boolean).join(" ｜ ")),
    bounds: unionBounds(items),
    confidence: "low",
    defaultDisposition: "static",
    reviewReason: items.some((item) => uncertainIds.has(item.id))
      ? "ambiguous-backing-relationship" : "possible-decoration-or-repeated-element",
    promotionRequiresRationale: true,
    animationConstraints: {
      paragraphAnimationSafe: false,
      paragraphSelectionSafe: false,
      preserveMemberZOrder: true,
      animateAtomically: true,
    },
    paragraphs: [],
  }));
  const staticItems = elements.filter((item) => (lockedStaticRoles.has(item.role) && !revealMaskIds.has(item.id))
    || explicitlyLockedDecoration(item) || revealCoveredIds.has(item.id));
  const staticModules = staticItems.map((item, index) => ({
    moduleId: `s${slideNumber}-static-${index + 1}`,
    label: item.role,
    semanticRole: item.role,
    memberIds: [item.id],
    text: compactText(item.text),
    bounds: itemBounds(item),
    confidence: "high",
    defaultDisposition: "static",
    safetyReason: revealCoveredIds.has(item.id) ? "visible-behind-reveal-mask" : undefined,
  }));
  return { modules, reviewableModules, staticModules };
}

/** Build the compact, token-conscious contract handed to the language model. */
export function buildModelBrief(inspection) {
  const slides = inspection.slides.map((slide) => {
      const revealMaskIds = slide.animationSummary?.targets
        ?.filter((target) => target.isExit
          && slide.elements.some((element) => element.id === target.shapeId && element.role === "mask"))
        .map((target) => target.shapeId) || [];
      const mediaPolicy = slide.protectedMediaTiming ? "preserve-required" : "model-design";
      const visualModules = mediaPolicy === "preserve-required"
        ? { modules: [], reviewableModules: [], staticModules: [] }
        : buildVisualModules(slide.elements, inspection.slideSize, slide.slide, { revealMaskIds });
      const { modules, reviewableModules, staticModules } = visualModules;
      const moduleForShape = new Map([...modules, ...reviewableModules]
        .flatMap((module) => module.memberIds.map((id) => [id, module.moduleId])));
      const backingTimingByModule = new Map();
      for (const { backingId, contentId } of contentBackingPairs(slide.elements, inspection.slideSize)) {
        const backingModuleId = moduleForShape.get(backingId);
        const contentModuleId = moduleForShape.get(contentId);
        if (!backingModuleId || !contentModuleId || backingModuleId === contentModuleId) continue;
        if (!backingTimingByModule.has(backingModuleId)) backingTimingByModule.set(backingModuleId, new Set());
        backingTimingByModule.get(backingModuleId).add(contentModuleId);
      }
      const backingTimingReview = [...backingTimingByModule]
        .map(([backingModuleId, contentModuleIds]) => ({ backingModuleId,
          contentModuleIds: [...contentModuleIds] }));
      const textlessVisuals = modules.filter((module) => module.semanticRole === "image" && !module.text);
      const slideArea = Math.max(1, inspection.slideSize.width * inspection.slideSize.height);
      const questionModules = modules.filter((module) => module.semanticRole === "question"
        || /[?？]\s*$/.test(String(module.text || "").trim())
        || /^(?:思考|问题|讨论|任务)[：:]/.test(String(module.text || "").trim()));
      const visualQuestionModules = questionModules.filter((module) => asksAboutVisiblePicture(module.text));
      const observationImages = textlessVisuals.filter((module) => module.bounds.width * module.bounds.height / slideArea >= 0.01);
      const visualQuestionDependencies = observationImages.length === 1
        ? visualQuestionModules.map((question) => ({ questionModuleId: question.moduleId,
          requiredVisualModuleIds: [observationImages[0].moduleId] })) : [];
      const candidateTeachingVisuals = [...modules, ...reviewableModules].filter((module) =>
        ["image", "diagram", "graphic"].includes(module.semanticRole)
        && module.bounds.width * module.bounds.height / slideArea >= 0.015
        && module.bounds.width * module.bounds.height / slideArea <= 0.65);
      const visualQuestionReview = questionModules
        .map((question) => ({
          questionModuleId: question.moduleId,
          candidateVisualModuleIds: candidateTeachingVisuals
            .filter((visual) => visual.moduleId !== question.moduleId).map((visual) => visual.moduleId),
        })).filter((entry) => entry.candidateVisualModuleIds.length > 0);
      const visualReviewModuleIds = textlessVisuals.filter((module) => {
        const ratio = module.bounds.width * module.bounds.height / slideArea;
        return ratio > 0.03 || (visualQuestionModules.length > 0 && ratio >= 0.01)
          || visualQuestionReview.some((entry) => entry.candidateVisualModuleIds.includes(module.moduleId));
      }).map((module) => module.moduleId);
      for (const visual of textlessVisuals) {
        const captions = modules.filter((candidate) => candidate !== visual && candidate.text
          && ["section-title", "subtitle", "body"].includes(candidate.semanticRole)
          && candidate.bounds.y >= visual.bounds.y + visual.bounds.height * 0.65
          && candidate.bounds.y - (visual.bounds.y + visual.bounds.height) < inspection.slideSize.height * 0.1
          && candidate.bounds.x < visual.bounds.x + visual.bounds.width
          && candidate.bounds.x + candidate.bounds.width > visual.bounds.x);
        visual.nearbyCaptionModuleIds = captions.map((caption) => caption.moduleId);
        visual.nearbyCaptionTexts = captions.map((caption) => compactText(caption.text, 48));
      }
      const existingTargets = slide.animationSummary?.targets || [];
      const effectKinds = [...new Set(existingTargets.map((target) => target.kind))];
      const triggerCounts = Object.fromEntries([...new Set(existingTargets.map((target) => target.trigger))]
        .map((trigger) => [trigger, existingTargets.filter((target) => target.trigger === trigger).length]));
      return {
        slide: slide.slide,
        detectedType: slide.type,
        existingAnimation: slide.existingAnimation,
        recommendedAction: mediaPolicy === "preserve-required" ? "preserve"
          : slide.existingAnimation ? "replace" : "design",
        existingAnimationSummary: slide.existingAnimation ? {
          status: slide.animationSummary.status,
          safety: slide.animationSummary.safety,
          unsafeReasons: slide.animationSummary.unsafeReasons,
          targetCount: slide.animationSummary.targetCount,
          hasMedia: slide.animationSummary.hasMedia,
          hasBuilds: slide.animationSummary.hasBuilds,
          effectKinds,
          triggerCounts,
        } : null,
        protectedMediaTiming: slide.protectedMediaTiming,
        mediaPolicy,
        visualInspectionRequired: visualReviewModuleIds.length > 0 || visualQuestionReview.length > 0,
        visualReviewModuleIds,
        visualQuestionDependencies,
        visualQuestionReview,
        backingTimingReview,
        contentOmittedReason: mediaPolicy === "preserve-required" ? "protected-media-timing" : undefined,
        revealMaskCount: revealMaskIds.length,
        modules,
        reviewableModules,
        staticModules,
        elementCount: slide.elements.length,
        elements: [],
      };
    });
  const typeDistribution = Object.fromEntries([...new Set(slides.map((slide) => slide.detectedType))]
    .map((type) => [type, slides.filter((slide) => slide.detectedType === type).length]));
  const semanticRoleDistribution = {};
  for (const module of slides.flatMap((slide) => [...slide.modules, ...slide.reviewableModules])) {
    semanticRoleDistribution[module.semanticRole] = (semanticRoleDistribution[module.semanticRole] || 0) + 1;
  }
  return {
    schemaVersion: 3,
    contract: "ppt-native-animation-model-brief",
    analysisMode: "structure-only",
    tokenPolicy: {
      rasterPreviews: false,
      selectedRiskPagePreviews: true,
      compactTextOnly: true,
      rawElementsOmitted: true,
      existingAnimationTargetsAggregated: true,
      strategyDefaultsWithPerStageOverrides: true,
    },
    source: inspection.source,
    slideSize: inspection.slideSize,
    slideCount: inspection.slideCount,
    deckProfile: {
      typeDistribution,
      semanticRoleDistribution,
      existingAnimationSlides: slides.filter((slide) => slide.existingAnimation).length,
      protectedMediaSlides: slides.filter((slide) => slide.mediaPolicy === "preserve-required").length,
      reviewableModuleCount: slides.reduce((sum, slide) => sum + slide.reviewableModules.length, 0),
    },
    performanceProfiles: {
      classroomWps: performanceBudgetFor("wps", "classroom-controlled"),
      classroomPowerPoint: performanceBudgetFor("powerpoint", "classroom-controlled"),
      microcourseWps: performanceBudgetFor("wps", "microcourse-auto"),
      microcoursePowerPoint: performanceBudgetFor("powerpoint", "microcourse-auto"),
    },
    rules: {
      planDeckStrategyBeforeSlides: true,
      stageFieldsInheritDeckStrategyUnlessOverridden: true,
      classroomDefaultMode: "classroom-controlled",
      classroomTeachingBeatsMayUseOnClick: true,
      ordinaryContentWithinATeachingBeat: "with_previous",
      answerTrigger: "on_click",
      microcourseOrdinaryContentTrigger: "after_previous",
      animateVisualModulesTogether: true,
      requireEveryAnimatableModuleToBeAssigned: true,
      reviewableModulesRemainStaticUnlessModelPromotesWithRationale: true,
      sourceSemanticRolesAreHints: true,
      modelMayClassifyParagraphsByMeaning: true,
      onClickRequiresPedagogicalRoleAndRationale: true,
      defaultSlideTransition: "fade",
      noTransitionOnlyForProtectedMediaOrExplicitUserOverride: true,
      everySourceSlideMustBePlanned: true,
      protectedMediaSlidesMustBePreserved: true,
      textlessContentImagesRequireVisualReview: true,
      visualQuestionRequiresPictureAtOrBeforeQuestion: true,
      questionVisualRelationshipMustBeClassified: true,
      declaredStagePrerequisitesMustBeVisible: true,
      authorizationIsExternalToModelPlan: true,
      revealMasksUseFadeOut: true,
    },
    slides,
  };
}

export function createModelPlanTemplate(brief) {
  return {
    schemaVersion: 3,
    contract: "ppt-native-animation-model-plan",
    source: { sha256: brief.source.sha256 },
    mode: "classroom-controlled",
    targetApplication: "unspecified",
    preset: "auto-teaching",
    deckStrategy: {
      rationale: "",
      effectFamilies: [],
      defaultEffect: null,
      defaultDurationMs: null,
      defaultStaggerMs: null,
      defaultDelayMs: null,
      defaultGranularity: "shape",
      defaultTransition: "fade",
    },
    slides: brief.slides.map((slide) => ({
      slide: slide.slide,
      stages: [],
    })),
  };
}

/** Require a saved classroom intent for every planned page and click pause. */
export function validateTeachingCues(brief, modelPlan, cues) {
  const errors = [];
  if (cues?.contract !== "ppt-native-animation-teaching-cues"
    || cues?.source?.sha256 !== brief?.source?.sha256) {
    errors.push("Teaching cues are missing or refer to a different PowerPoint source.");
    return errors;
  }
  const bySlide = new Map((cues.slides || []).map((entry) => [entry.slide, entry]));
  const plans = new Map((modelPlan.slides || []).map((entry) => [entry.slide, entry]));
  for (const slide of brief.slides || []) {
    if (slide.mediaPolicy === "preserve-required") continue;
    const plan = plans.get(slide.slide);
    const cue = bySlide.get(slide.slide);
    if (!cue || !String(cue.purpose || "").trim()) {
      errors.push(`Slide ${slide.slide} needs a teaching purpose in the cues file.`);
      continue;
    }
    const stageById = new Map((plan?.stages || []).map((stage, index) => [stage.id || `stage-${index + 1}`, stage]));
    const clickBeats = new Map();
    for (const beat of cue.teacherClickBeats || []) {
      const id = String(beat?.stageId || "").trim();
      const reason = String(beat?.reason || "").trim();
      if (!id || !reason) {
        errors.push(`Slide ${slide.slide} has a teacher click beat without a stageId and reason.`);
      } else if (clickBeats.has(id)) {
        errors.push(`Slide ${slide.slide} repeats teacher click beat ${id}.`);
      } else {
        clickBeats.set(id, reason);
        if (stageById.get(id)?.trigger !== "on_click") {
          errors.push(`Slide ${slide.slide} teaching cue ${id} must reference an on_click stage.`);
        }
      }
    }
    for (const [id, stage] of stageById) {
      if (stage.trigger === "on_click" && !clickBeats.has(id)) {
        errors.push(`Slide ${slide.slide} click stage ${id} is missing from the teaching cues.`);
      }
    }
    for (const exception of cue.deferredVisualQuestions || []) {
      const id = String(exception?.stageId || "").trim();
      const stage = stageById.get(id);
      if (!id || !String(exception?.reason || "").trim()
        || !stage || stage.contentRole !== "question"
        || stage.visualDependency?.kind !== "blind-prediction") {
        errors.push(`Slide ${slide.slide} deferred visual question needs a question stageId and classroom reason.`);
      }
    }
    const approvedPredictions = new Set((cue.deferredVisualQuestions || []).map((entry) => entry.stageId));
    for (const [id, stage] of stageById) {
      if (stage.visualDependency?.kind === "blind-prediction" && !approvedPredictions.has(id)) {
        errors.push(`Slide ${slide.slide} blind-prediction stage ${id} needs a deferredVisualQuestions teaching cue.`);
      }
    }
    const hasReveal = slide.modules.some((module) => ["answer", "conclusion"].includes(module.semanticRole));
    if (modelPlan.mode === "classroom-controlled" && hasReveal
      && slide.modules.length >= 3 && ![...stageById.values()].some((stage) => stage.trigger === "on_click")) {
      errors.push(`Slide ${slide.slide} contains an answer or conclusion but has no teacher-controlled reveal.`);
    }
    const keepStatic = new Set((cue.keepStatic || []).map((entry) => entry.moduleId));
    const eligibleEarlyBackings = new Set((slide.backingTimingReview || [])
      .map((entry) => entry.backingModuleId));
    const earlyBackingIds = new Set();
    for (const exception of cue.earlyBackingExceptions || []) {
      const id = String(exception?.moduleId || "").trim();
      const reason = String(exception?.reason || "").trim();
      const classroomAction = /学生|同学|教师|老师|预测|观察|思考|讨论|辨认|描述|提问|作答|填写|teacher|student|predict|observe|discuss/i;
      if (!eligibleEarlyBackings.has(id) || reason.length < 12
        || !classroomAction.test(reason) || earlyBackingIds.has(id)) {
        errors.push(`Slide ${slide.slide} early backing exception needs a detected backing module and a specific classroom reason.`);
      }
      earlyBackingIds.add(id);
    }
    if (slide.visualInspectionRequired) {
      const reviewed = new Map((cue.visualReviews || []).map((entry) => [entry.moduleId, entry]));
      const ids = new Set(slide.visualReviewModuleIds || slide.modules.filter((entry) => entry.semanticRole === "image" && !entry.text
        && entry.bounds.width * entry.bounds.height
          > brief.slideSize.width * brief.slideSize.height * 0.03).map((entry) => entry.moduleId));
      for (const module of slide.modules.filter((entry) => ids.has(entry.moduleId))) {
        if (!String(reviewed.get(module.moduleId)?.description || "").trim()) {
          errors.push(`Slide ${slide.slide} image module ${module.moduleId} needs a visual review description.`);
        }
      }
    }
    for (const entry of plan?.staticModules || []) {
      const id = typeof entry === "string" ? entry : entry.moduleId;
      const module = slide.modules.find((candidate) => candidate.moduleId === id);
      if (!module) continue;
      const meaningful = module.text?.length >= 8 || module.semanticRole === "image";
      if (meaningful && !keepStatic.has(id)) {
        errors.push(`Slide ${slide.slide} static content module ${id} needs an explicit keepStatic teaching cue.`);
      }
    }
    for (const entry of cue.keepStatic || []) {
      if (!String(entry?.moduleId || "").trim() || !String(entry?.reason || "").trim()) {
        errors.push(`Slide ${slide.slide} keepStatic entries need moduleId and classroom reason.`);
      }
    }
  }
  for (const number of bySlide.keys()) {
    if (!brief.slides.some((slide) => slide.slide === number)) errors.push(`Unknown teaching cue slide ${number}.`);
  }
  return errors;
}

export function buildIncrementalPlanningBundle(currentInspection, baselineInspection, baselinePlan, options = {}) {
  if (currentInspection?.analysisRevision !== ANALYSIS_REVISION) {
    throw new Error("Current structure analysis is from an older parser. Re-analyze the source before incremental planning.");
  }
  if (baselinePlan?.schemaVersion !== 3 || baselinePlan?.contract !== "ppt-native-animation-model-plan") {
    throw new Error("Baseline model plan must use schemaVersion 3.");
  }
  if (baselinePlan?.source?.sha256 !== baselineInspection?.source?.sha256) {
    throw new Error("Baseline plan and baseline structure hashes do not match.");
  }
  const currentBrief = buildModelBrief(currentInspection);
  const baselineBySlide = new Map((baselineInspection.slides || []).map((slide) => [slide.slide, slide]));
  const baselinePlanBySlide = new Map((baselinePlan.slides || []).map((slide) => [slide.slide, slide]));
  const currentSlideNumbers = new Set((currentInspection.slides || []).map((slide) => slide.slide));
  const forcedSlides = [...new Set((options.forceSlides || []).map(Number))].sort((a, b) => a - b);
  const unknownForcedSlides = forcedSlides.filter((slide) => !Number.isInteger(slide) || !currentSlideNumbers.has(slide));
  if (unknownForcedSlides.length) {
    throw new Error(`Requested redesign slides do not exist: ${unknownForcedSlides.join(", ")}`);
  }
  const forced = new Set(forcedSlides);
  const sameContext = baselineInspection?.analysisRevision === ANALYSIS_REVISION
    && Boolean(currentInspection.planningContextFingerprint)
    && currentInspection.planningContextFingerprint === baselineInspection.planningContextFingerprint;
  const reusableSlides = [];
  const changedSlides = [];
  for (const slide of currentInspection.slides || []) {
    const baselineSlide = baselineBySlide.get(slide.slide);
    const dependsOnPrevious = (baselinePlanBySlide.get(slide.slide)?.stages || [])
      .some((stage) => stage.answersQuestionStageId === "previous-slide");
    const predecessorUnchanged = !dependsOnPrevious || (slide.slide > 1
      && currentInspection.slides.find((entry) => entry.slide === slide.slide - 1)?.planningFingerprint
        === baselineBySlide.get(slide.slide - 1)?.planningFingerprint);
    const reusable = !forced.has(slide.slide) && sameContext
      && predecessorUnchanged
      && Boolean(slide.planningFingerprint)
      && slide.planningFingerprint === baselineSlide?.planningFingerprint
      && baselinePlanBySlide.has(slide.slide);
    (reusable ? reusableSlides : changedSlides).push(slide.slide);
  }
  const patchBrief = {
    schemaVersion: 1,
    contract: "ppt-native-animation-model-brief-patch",
    analysisMode: "structure-only-incremental",
    source: currentInspection.source,
    baseSource: { sha256: baselineInspection.source.sha256 },
    deckProfile: currentBrief.deckProfile,
    tokenPolicy: currentBrief.tokenPolicy,
    rules: currentBrief.rules,
    reuse: {
      planningContextUnchanged: sameContext,
      forcedSlides,
      reusableSlides,
      changedSlides,
    },
    slides: currentBrief.slides.filter((slide) => changedSlides.includes(slide.slide)),
  };
  const patchTemplate = {
    schemaVersion: 1,
    contract: "ppt-native-animation-model-plan-patch",
    source: { sha256: currentInspection.source.sha256 },
    baseSource: { sha256: baselineInspection.source.sha256 },
    mode: baselinePlan.mode,
    targetApplication: baselinePlan.targetApplication || "unspecified",
    preset: baselinePlan.preset,
    deckStrategy: structuredClone(baselinePlan.deckStrategy),
    redesignSlides: forcedSlides,
    slides: patchBrief.slides.map((slide) => ({ slide: slide.slide, stages: [] })),
  };
  return { brief: patchBrief, template: patchTemplate };
}

export function mergeModelPlanPatch(currentInspection, baselineInspection, baselinePlan, patchPlan, options = {}) {
  const forceSlides = options.forceSlides?.length ? options.forceSlides : patchPlan?.redesignSlides || [];
  const { brief } = buildIncrementalPlanningBundle(currentInspection, baselineInspection, baselinePlan, { forceSlides });
  if (patchPlan?.schemaVersion !== 1 || patchPlan?.contract !== "ppt-native-animation-model-plan-patch") {
    throw new Error("Incremental patch must use schemaVersion 1 and contract ppt-native-animation-model-plan-patch.");
  }
  if (patchPlan?.source?.sha256 !== currentInspection.source.sha256
    || patchPlan?.baseSource?.sha256 !== baselineInspection.source.sha256) {
    throw new Error("Incremental patch source hashes do not match the current and baseline structures.");
  }
  const changed = new Set(brief.reuse.changedSlides);
  if (brief.reuse.reusableSlides.length && (
    (patchPlan.mode && patchPlan.mode !== baselinePlan.mode)
    || (patchPlan.preset && patchPlan.preset !== baselinePlan.preset)
    || (patchPlan.deckStrategy && JSON.stringify(patchPlan.deckStrategy) !== JSON.stringify(baselinePlan.deckStrategy)))) {
    throw new Error("Deck-wide mode, preset or strategy changed; redesign all slides before merging inherited stage defaults.");
  }
  if (new Set((patchPlan.slides || []).map((slide) => slide.slide)).size !== (patchPlan.slides || []).length) {
    throw new Error("Incremental patch contains duplicate slide entries.");
  }
  const patchBySlide = new Map((patchPlan.slides || []).map((slide) => [slide.slide, slide]));
  const baselineBySlide = new Map((baselinePlan.slides || []).map((slide) => [slide.slide, slide]));
  for (const slide of patchPlan.slides || []) {
    if (!changed.has(slide.slide)) throw new Error(`Slide ${slide.slide} is unchanged and must not be redesigned in the incremental patch.`);
  }
  const slides = currentInspection.slides.map((slide) => {
    if (changed.has(slide.slide)) {
      const replacement = patchBySlide.get(slide.slide);
      if (!replacement) throw new Error(`Changed slide ${slide.slide} is missing from the incremental patch.`);
      return structuredClone(replacement);
    }
    const reused = baselineBySlide.get(slide.slide);
    if (!reused) throw new Error(`Reusable slide ${slide.slide} is missing from the baseline plan.`);
    return structuredClone(reused);
  });
  return {
    ...structuredClone(baselinePlan),
    schemaVersion: 3,
    contract: "ppt-native-animation-model-plan",
    source: { sha256: currentInspection.source.sha256 },
    mode: patchPlan.mode || baselinePlan.mode,
    targetApplication: patchPlan.targetApplication || baselinePlan.targetApplication || "unspecified",
    preset: patchPlan.preset || baselinePlan.preset,
    deckStrategy: structuredClone(patchPlan.deckStrategy || baselinePlan.deckStrategy),
    slides,
  };
}

export async function inspectPresentation(inputPath) {
  const absolute = path.resolve(inputPath);
  const tempDir = await extractPptx(absolute);
  try {
    const presentationXml = await fs.readFile(path.join(tempDir, "ppt", "presentation.xml"), "utf8");
    const sizeMatch = presentationXml.match(/<p:sldSz\s+[^>]*cx="(\d+)"[^>]*cy="(\d+)"/);
    const slideSize = {
      width: sizeMatch ? Number(sizeMatch[1]) : 12192000,
      height: sizeMatch ? Number(sizeMatch[2]) : 6858000,
    };
    const slideDir = path.join(tempDir, "ppt", "slides");
    const sharedContext = await hashDirectoryTree(tempDir, [
      "ppt/theme",
      "ppt/slideMasters",
      "ppt/slideLayouts",
    ]);
    const planningContextFingerprint = hashParts([sharedContext, JSON.stringify(slideSize)]);
    const orderedSlides = await presentationSlideOrder(tempDir, presentationXml);
    const slides = [];
    for (const { slide: number, file: name, relationshipId, slideId } of orderedSlides) {
      const xml = await fs.readFile(path.join(slideDir, name), "utf8");
      const elements = parseSlideElements(xml, slideSize);
      const animationSummary = assessAnimationSafety(parseExistingAnimationSummary(xml), elements);
      slides.push({
        slide: number,
        file: name,
        relationshipId,
        slideId,
        existingAnimation: animationSummary.meaningful,
        animationSummary,
        protectedMediaTiming: hasProtectedMediaTiming(xml),
        planningFingerprint: await slidePlanningFingerprint(tempDir, name, xml),
        elements,
      });
    }
    markRepeatedElements(slides, slideSize);
    for (const slide of slides) slide.type = inferSlideType(slide.elements, slide.slide);
    const stat = await fs.stat(absolute);
    return {
      schemaVersion: 1,
      analysisRevision: ANALYSIS_REVISION,
      source: { path: absolute, extension: path.extname(absolute).toLowerCase(), size: stat.size, sha256: await sha256(absolute) },
      slideSize,
      slideCount: slides.length,
      planningContextFingerprint,
      slides,
    };
  } finally {
    await cleanupTemp(tempDir);
  }
}

export async function createPlan(inputPath, requestedPreset = "auto-teaching") {
  const inspection = await inspectPresentation(inputPath);
  const slides = [];
  for (const slide of inspection.slides) {
    const presetId = requestedPreset === "auto-teaching" ? routePreset(slide.type) : requestedPreset;
    const preset = await loadPreset(presetId);
    const fallback = slide.protectedMediaTiming
      ? null : buildStages(slide.elements, { ...preset, slideSize: inspection.slideSize });
    const { stages, unanimated } = slide.protectedMediaTiming
      ? { stages: [], unanimated: slide.elements.map((element) => ({ shapeId: element.id, role: "protected-media" })) }
      : fallback;
    slides.push({
      slide: slide.slide,
      detectedType: slide.type,
      preset: preset.id,
      presetLabel: preset.label,
      existingAnimation: slide.existingAnimation,
      protectedMediaTiming: slide.protectedMediaTiming,
      transition: { type: slide.protectedMediaTiming ? "preserve" : "fade", durationMs: preset.timing.transition },
      stages,
      unanimated,
      disposition: slide.protectedMediaTiming ? "preserve" : undefined,
      warnings: [
        ...(slide.existingAnimation ? ["已检测到现有视觉动画；模型工作流会在明确计划后替换，本地回退流程仍需显式选择 replace。"] : []),
        ...(slide.protectedMediaTiming ? ["本页含音频或视频播放时序；整页保留原有动画与媒体播放。"] : []),
      ],
    });
  }
  return {
    schemaVersion: 1,
    planningMode: "deterministic-fallback",
    fallbackPlan: true,
    deliveryReady: false,
    createdAt: new Date().toISOString(),
    source: inspection.source,
    slideSize: inspection.slideSize,
    requestedPreset,
    defaultExistingPolicy: "preserve",
    performanceBudget: {
      maxAnimatedTargetsPerSlide: 18,
      maxConcurrentItemsPerStage: 8,
      maxConcurrentWipeItems: 3,
      maxLargeWipeAreaRatio: 0.35,
    },
    slides,
  };
}

export function validateModelPlanShape(modelPlan, inspection, brief, authorization = {}) {
  const errors = [];
  const deckEffects = new Set();
  if (modelPlan?.schemaVersion !== 3 || modelPlan?.contract !== "ppt-native-animation-model-plan") {
    errors.push("Model plan must use schemaVersion 3 and contract ppt-native-animation-model-plan.");
  }
  if (modelPlan?.source?.sha256 !== inspection.source.sha256) {
    errors.push("The model plan source hash does not match the PowerPoint file. Re-analyze the source.");
  }
  if (!Array.isArray(modelPlan?.slides)) errors.push("Model plan slides must be an array.");
  if (Object.hasOwn(modelPlan || {}, "existingAnimations")
    || Object.hasOwn(modelPlan || {}, "transitionPolicy")
    || Object.hasOwn(modelPlan || {}, "authorization")) {
    errors.push("User authorization must be supplied externally by the compiler command, not declared inside the model plan.");
  }
  if (!["classroom-controlled", "teaching", "microcourse-auto"].includes(modelPlan?.mode)) {
    errors.push("Model plan mode must be classroom-controlled, teaching, or microcourse-auto.");
  }
  if (modelPlan?.mode === "microcourse-auto" && authorization.allowUnattended !== true) {
    errors.push("Microcourse-auto mode requires external user authorization.");
  }
  if (!["unspecified", "wps", "powerpoint"].includes(modelPlan?.targetApplication || "unspecified")) {
    errors.push("targetApplication must be unspecified, wps, or powerpoint.");
  }
  const strategy = modelPlan?.deckStrategy;
  const allowedEffects = new Set(["appear", "fade", "wipe"]);
  const effectFamilies = Array.isArray(strategy?.effectFamilies) ? [...new Set(strategy.effectFamilies)] : [];
  if (!strategy || !String(strategy.rationale || "").trim()) {
    errors.push("deckStrategy needs a concise model-authored rationale.");
  }
  if (effectFamilies.length < 1 || effectFamilies.length > 2 || effectFamilies.some((effect) => !allowedEffects.has(effect))) {
    errors.push("deckStrategy.effectFamilies must contain 1-2 supported effects: appear, fade, or wipe.");
  }
  if (!effectFamilies.includes(strategy?.defaultEffect)) {
    errors.push("deckStrategy.defaultEffect must be one of effectFamilies.");
  }
  if (!Number.isFinite(Number(strategy?.defaultDurationMs))
    || Number(strategy.defaultDurationMs) < 250 || Number(strategy.defaultDurationMs) > 650) {
    errors.push("deckStrategy.defaultDurationMs must be 250-650ms.");
  }
  if (!Number.isFinite(Number(strategy?.defaultStaggerMs))
    || Number(strategy.defaultStaggerMs) < 0 || Number(strategy.defaultStaggerMs) > 180) {
    errors.push("deckStrategy.defaultStaggerMs must be 0-180ms.");
  }
  if (!Number.isFinite(Number(strategy?.defaultDelayMs ?? 0))
    || Number(strategy?.defaultDelayMs ?? 0) < 0 || Number(strategy?.defaultDelayMs ?? 0) > 400) {
    errors.push("deckStrategy.defaultDelayMs must be 0-400ms.");
  }
  if (!['shape', 'paragraph'].includes(strategy?.defaultGranularity)) {
    errors.push("deckStrategy.defaultGranularity must be shape or paragraph.");
  }
  if (strategy?.defaultTransition !== "fade") {
    errors.push("deckStrategy.defaultTransition must be fade; exceptions belong on individual slides with authorization.");
  }
  if (errors.length) return errors;
  const plannedSlides = new Map();
  for (const slidePlan of modelPlan.slides) {
    if (!Number.isInteger(slidePlan.slide) || !brief.slides.some((slide) => slide.slide === slidePlan.slide)) {
      errors.push(`Unknown slide ${slidePlan.slide}.`);
      continue;
    }
    if (plannedSlides.has(slidePlan.slide)) errors.push(`Slide ${slidePlan.slide} appears more than once.`);
    plannedSlides.set(slidePlan.slide, slidePlan);
  }
  for (const slide of brief.slides) {
    const slidePlan = plannedSlides.get(slide.slide);
    if (!slidePlan) {
      errors.push(`Slide ${slide.slide} is missing from the model plan; every source slide must be present even when it has no animatable modules.`);
      continue;
    }
    const effectiveAction = slidePlan.action ?? slide.recommendedAction;
    const effectiveTransition = slidePlan.transition
      ?? (slide.mediaPolicy === "preserve-required" ? "preserve" : strategy.defaultTransition);
    if (slide.mediaPolicy === "preserve-required") {
      if (effectiveAction !== "preserve") {
        errors.push(`Slide ${slide.slide} contains protected media timing and must use action preserve.`);
      }
      if (effectiveTransition !== "preserve") {
        errors.push(`Slide ${slide.slide} contains protected media timing and must preserve its source transition.`);
      }
      if ((slidePlan.stages || []).length || (slidePlan.staticModules || []).length) {
        errors.push(`Slide ${slide.slide} is media-protected and must not contain model-authored stages or static assignments.`);
      }
      continue;
    }
    if (slide.existingAnimation && effectiveAction !== "replace") {
      errors.push(`Slide ${slide.slide} has existing visual animation and must be redesigned with action replace.`);
      continue;
    }
    if (slide.existingAnimation && effectiveAction === "replace"
      && authorization.allowReplaceExisting !== true) {
      errors.push(`Slide ${slide.slide} replaces existing animation without external user authorization.`);
    }
    if (!slide.existingAnimation && effectiveAction !== "design") {
      errors.push(`Slide ${slide.slide} has no existing visual animation and must use action design.`);
      continue;
    }
    if (!["fade", "none"].includes(effectiveTransition)) {
      errors.push(`Slide ${slide.slide} needs a model-selected fade or none transition.`);
    }
    if (effectiveTransition === "none") {
      const rationale = String(slidePlan.transitionRationale || "").trim();
      const userApprovedNone = authorization.allowNoTransition === true;
      if (!rationale) {
        errors.push(`Slide ${slide.slide} uses no transition without a transitionRationale.`);
      }
      if (!slide.protectedMediaTiming && !userApprovedNone) {
        errors.push(`Slide ${slide.slide} must use fade unless protected media timing makes it unsafe or the user explicitly approved no transition.`);
      }
    }
    const reviewableModuleIds = new Set((slide.reviewableModules || []).map((module) => module.moduleId));
    const moduleById = new Map([...(slide.modules || []), ...(slide.reviewableModules || [])]
      .map((module) => [module.moduleId, module]));
    const paragraphById = new Map(slide.modules.flatMap((module) => (module.paragraphs || [])
      .map((paragraph) => [paragraph.paragraphId, { ...paragraph, moduleId: module.moduleId }])));
    const usedWholeModules = new Set();
    const usedParagraphs = new Set();
    const intentionallyStatic = new Set((slidePlan.staticModules || []).map((entry) => typeof entry === "string" ? entry : entry.moduleId));
    for (const entry of slidePlan.staticModules || []) {
      const moduleId = typeof entry === "string" ? entry : entry.moduleId;
      const reason = typeof entry === "string" ? "" : String(entry.reason || "").trim();
      if (!moduleById.has(moduleId)) errors.push(`Slide ${slide.slide} marks unknown module ${moduleId} as static.`);
      if (!reason) errors.push(`Slide ${slide.slide} static module ${moduleId} needs a reason.`);
    }
    if (!Array.isArray(slidePlan.stages)) {
      errors.push(`Slide ${slide.slide} stages must be an array.`);
      continue;
    }
    const maxStages = slide.detectedType === "text" ? 8 : 6;
    if (slidePlan.stages.length > maxStages) {
      errors.push(`Slide ${slide.slide} has ${slidePlan.stages.length} stages; combine related content into at most ${maxStages} teaching beats.`);
    }
    const stageIds = new Set(slidePlan.stages.map((stage, index) => stage.id || `stage-${index + 1}`));
    let sawAnimatedStage = false;
    for (const [stageIndex, stage] of slidePlan.stages.entries()) {
      const effectiveEffect = stage.effect ?? strategy.defaultEffect;
      const effectiveDurationMs = stage.durationMs ?? strategy.defaultDurationMs;
      const effectiveStaggerMs = stage.staggerMs ?? strategy.defaultStaggerMs;
      const effectiveDelayMs = stage.delayMs ?? strategy.defaultDelayMs ?? 0;
      const effectiveGranularity = stage.granularity ?? strategy.defaultGranularity;
      if (!["initial", "after_previous", "with_previous", "on_click"].includes(stage.trigger)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} has invalid trigger ${stage.trigger}.`);
      }
      if (stage.trigger === "initial") {
        if (sawAnimatedStage) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} is initial after an animated stage; initial stages must be contiguous at the start.`);
        }
        if (["teaching", "classroom-controlled"].includes(modelPlan.mode) && !String(stage.rationale || "").trim()) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} uses initial visibility without a rationale.`);
        }
      } else {
        sawAnimatedStage = true;
      }
      const moduleIds = Array.isArray(stage.moduleIds) ? stage.moduleIds : [];
      const paragraphIds = Array.isArray(stage.paragraphIds) ? stage.paragraphIds : [];
      if (stage.requiresVisibleModuleIds !== undefined
        && (!Array.isArray(stage.requiresVisibleModuleIds)
          || stage.requiresVisibleModuleIds.some((id) => !moduleById.has(id)))) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} has unknown visible prerequisite modules.`);
      }
      const selectedIds = new Set([...moduleIds, ...paragraphIds
        .map((id) => paragraphById.get(id)?.moduleId).filter(Boolean)]);
      const relevantQuestions = (slide.visualQuestionReview || [])
        .filter((entry) => selectedIds.has(entry.questionModuleId));
      if (relevantQuestions.length) {
        const decision = stage.visualDependency;
        const kind = decision?.kind;
        const candidates = new Set(relevantQuestions.flatMap((entry) => entry.candidateVisualModuleIds));
        const required = decision?.moduleIds;
        if (!["requires-visible", "independent", "blind-prediction"].includes(kind)) {
          errors.push(`Slide ${slide.slide} question stage ${stage.id || stageIndex + 1} must classify its relationship to the page's visual material.`);
        } else if (kind === "requires-visible"
          && (!Array.isArray(required) || !required.length
            || required.some((id) => !candidates.has(id)))) {
          errors.push(`Slide ${slide.slide} question stage ${stage.id || stageIndex + 1} needs valid visualDependency.moduleIds.`);
        } else if (kind !== "requires-visible" && !String(decision.reason || "").trim()) {
          errors.push(`Slide ${slide.slide} question stage ${stage.id || stageIndex + 1} needs a reason for ${kind}.`);
        }
        const certainVisuals = (slide.visualQuestionDependencies || [])
          .filter((entry) => selectedIds.has(entry.questionModuleId))
          .flatMap((entry) => entry.requiredVisualModuleIds);
        if (certainVisuals.length && kind === "independent") {
          errors.push(`Slide ${slide.slide} observation question stage ${stage.id || stageIndex + 1} cannot mark its required picture independent; use requires-visible or an approved blind prediction.`);
        }
        if (certainVisuals.length && kind === "requires-visible"
          && certainVisuals.some((id) => !required.includes(id))) {
          errors.push(`Slide ${slide.slide} observation question stage ${stage.id || stageIndex + 1} omits its required picture.`);
        }
      }
      if (!moduleIds.length && !paragraphIds.length) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} has no moduleIds or paragraphIds.`);
        continue;
      }
      const paragraphModules = paragraphIds
        .map((paragraphId) => paragraphById.get(paragraphId)?.moduleId)
        .filter(Boolean);
      const stageModules = [...new Set([...moduleIds, ...paragraphModules])]
        .map((moduleId) => moduleById.get(moduleId)).filter(Boolean);
      const revealModes = new Set(stageModules.map((module) => module.animationMode || "entrance"));
      if (revealModes.size > 1) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} mixes reveal-mask and entrance modules.`);
      }
      const revealMaskStage = revealModes.size === 1 && revealModes.has("reveal-mask");
      if (revealMaskStage ? effectiveEffect !== "fade-out" : !effectFamilies.includes(effectiveEffect)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a model-selected effect.`);
      }
      if (effectiveEffect && effectiveEffect !== "fade-out") deckEffects.add(effectiveEffect);
      if (!Number.isFinite(Number(effectiveDurationMs)) || Number(effectiveDurationMs) < 250 || Number(effectiveDurationMs) > 650) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a 250-650ms model-selected duration.`);
      }
      if (!Number.isFinite(Number(effectiveStaggerMs)) || Number(effectiveStaggerMs) < 0 || Number(effectiveStaggerMs) > 180) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a 0-180ms model-selected stagger.`);
      }
      if (!Number.isFinite(Number(effectiveDelayMs)) || Number(effectiveDelayMs) < 0 || Number(effectiveDelayMs) > 400) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a 0-400ms delay.`);
      }
      if (!["shape", "paragraph"].includes(effectiveGranularity)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs model-selected shape or paragraph granularity.`);
      }
      if (revealMaskStage && effectiveGranularity !== "shape") {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} reveal-mask animation must use shape granularity.`);
      }
      if (paragraphIds.length && effectiveGranularity !== "paragraph") {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} selects paragraphs but does not use paragraph granularity.`);
      }
      if (paragraphIds.length
        && stageModules.some((module) => !module.animationConstraints?.paragraphSelectionSafe)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} selects paragraphs from an unsafe filled text module.`);
      }
      if (!paragraphIds.length && effectiveGranularity === "paragraph"
        && stageModules.some((module) => !module.animationConstraints?.paragraphAnimationSafe)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} uses paragraph animation on an unsafe filled text module.`);
      }
      for (const moduleId of moduleIds) {
        if (!moduleById.has(moduleId)) errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} references unknown module ${moduleId}.`);
        if (usedWholeModules.has(moduleId)) errors.push(`Slide ${slide.slide} module ${moduleId} is assigned more than once.`);
        if ((moduleById.get(moduleId)?.paragraphs || []).some((paragraph) => usedParagraphs.has(paragraph.paragraphId))) {
          errors.push(`Slide ${slide.slide} module ${moduleId} is assigned both as a whole module and by paragraph.`);
        }
        usedWholeModules.add(moduleId);
        if (reviewableModuleIds.has(moduleId) && !String(stage.promotionRationale || "").trim()) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} promotes reviewable module ${moduleId} without promotionRationale.`);
        }
      }
      for (const paragraphId of paragraphIds) {
        const paragraph = paragraphById.get(paragraphId);
        if (!paragraph) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} references unknown paragraph ${paragraphId}.`);
          continue;
        }
        if (usedWholeModules.has(paragraph.moduleId)) {
          errors.push(`Slide ${slide.slide} module ${paragraph.moduleId} is assigned both as a whole module and by paragraph.`);
        }
        if (usedParagraphs.has(paragraphId)) errors.push(`Slide ${slide.slide} paragraph ${paragraphId} is assigned more than once.`);
        usedParagraphs.add(paragraphId);
      }
      const contentRole = String(stage.contentRole || "").trim();
      if (stage.trigger === "initial" && ["question", "answer"].includes(contentRole)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} cannot keep ${contentRole} visible initially in teaching mode.`);
      }
      const classroomClickRoles = new Set(["question", "task", "discussion", "evidence", "answer", "conclusion", "teacher-cue"]);
      if (stage.trigger === "on_click" && modelPlan.mode !== "classroom-controlled" && contentRole !== "answer") {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} waits for a click but the model did not classify it as answer.`);
      }
      if (stage.trigger === "on_click" && modelPlan.mode === "classroom-controlled" && !classroomClickRoles.has(contentRole)) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a classroom click role: question, task, discussion, evidence, answer, conclusion, or teacher-cue.`);
      }
      if (stage.trigger === "on_click" && !String(stage.rationale || "").trim()) {
        errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs a model rationale for the click pause.`);
      }
      if (stage.trigger === "on_click" && contentRole === "answer") {
        const questionRef = String(stage.answersQuestionStageId || "").trim();
        if (!questionRef) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} needs answersQuestionStageId linking the answer to its question.`);
        } else if (questionRef !== "previous-slide" && !stageIds.has(questionRef)) {
          errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} references unknown question stage ${questionRef}.`);
        } else if (questionRef !== "previous-slide") {
          const referencedIndex = slidePlan.stages.findIndex((candidate, index) => (candidate.id || `stage-${index + 1}`) === questionRef);
          if (referencedIndex >= stageIndex || String(slidePlan.stages[referencedIndex]?.contentRole || "") !== "question") {
            errors.push(`Slide ${slide.slide} stage ${stageIndex + 1} must reference an earlier question stage.`);
          }
        }
      }
      if (stage.trigger !== "on_click" && contentRole === "answer"
        && !(modelPlan.mode === "microcourse-auto" && authorization.allowUnattended === true)) {
        errors.push(`Slide ${slide.slide} model-classified answer must use on_click outside microcourse-auto mode.`);
      }
    }
    if (slidePlan.stages.length && slidePlan.stages.every((stage) => stage.trigger === "initial")) {
      errors.push(`Slide ${slide.slide} contains only initial stages and would produce no element animation; use after_previous or mark the modules static.`);
    }
    for (const module of slide.modules) {
      const paragraphCovered = (module.paragraphs || []).length > 0
        && module.paragraphs.every((paragraph) => usedParagraphs.has(paragraph.paragraphId));
      if (!usedWholeModules.has(module.moduleId) && !paragraphCovered && !intentionallyStatic.has(module.moduleId)) {
        errors.push(`Slide ${slide.slide} module ${module.moduleId} is not assigned or explicitly static.`);
      }
    }
  }
  if (deckEffects.size > 2) {
    errors.push(`The deck uses ${deckEffects.size} entrance effect families (${[...deckEffects].join(", ")}); keep at most 2 for consistency.`);
  }
  return errors;
}

/** Compile a model-authored module plan into the deterministic executable plan. */
export function resolveModelPresetId(modelSlide, modelPlan, sourceSlide) {
  const topLevelPreset = modelPlan.preset;
  const concreteTopLevelPreset = topLevelPreset
    && !["auto-teaching", "model-selected"].includes(topLevelPreset)
    ? topLevelPreset : null;
  return modelSlide.preset || concreteTopLevelPreset || routePreset(sourceSlide.type);
}

export function reviewSemanticCoverage(briefSlide, modelSlide) {
  const modules = briefSlide.modules || [];
  // A template's licence/instruction slide is deliberately left unanimated.
  // It must not be reported as missing classroom content coverage.
  if (modules.some((module) => /模板使用说明|母版说明/.test(String(module.text || "")))) return [];
  const paragraphModules = new Map(modules.flatMap((module) => (module.paragraphs || [])
    .map((paragraph) => [paragraph.paragraphId, module.moduleId])));
  const stagedIds = new Set((modelSlide.stages || []).flatMap((stage) => [
    ...(stage.moduleIds || []),
    ...(stage.paragraphIds || []).map((id) => paragraphModules.get(id)).filter(Boolean),
  ]));
  const meaningful = modules.filter((module) => {
    const text = String(module.text || (module.paragraphs || []).map((item) => item.text || "").join(" ")).trim();
    return (text.length >= 2 || module.semanticRole === "image")
      && !/单击此处|点击输入|稻壳儿PPT模板|字体说明|版权声明/.test(text);
  });
  const unstaged = meaningful.filter((module) => !stagedIds.has(module.moduleId));
  const warnings = [];
  const critical = unstaged.filter((module) => ["question", "answer", "analysis", "conclusion"].includes(module.semanticRole));
  if (critical.length) {
    warnings.push(`Question, answer, analysis, or conclusion modules remain static: ${critical.map((module) => module.moduleId).join(", ")}. Check the classroom reveal order.`);
  }
  if (meaningful.length >= 6 && unstaged.length >= 3 && unstaged.length / meaningful.length >= 0.35) {
    warnings.push(`${unstaged.length} of ${meaningful.length} readable content modules remain static. Review coverage: ${unstaged.slice(0, 8).map((module) => module.moduleId).join(", ")}.`);
  }
  return warnings;
}

/** Mirror the writer's stage and stagger timing for prerequisite checks. */
function calculateItemStarts(slidePlan) {
  const byShape = new Map();
  const byStage = [];
  let clickIndex = 0;
  let previousStart = 0;
  let previousEnd = 0;
  let started = false;
  for (const [index, stage] of (slidePlan.stages || []).entries()) {
    if (stage.trigger === "initial") {
      byStage.push({ clickIndex: 0, startMs: 0 });
      continue;
    }
    if (stage.trigger === "on_click") {
      clickIndex += 1;
      previousStart = 0;
      previousEnd = 0;
      started = false;
    }
    const delay = Math.max(0, Number(stage.delayMs ?? 0));
    const startMs = !started ? delay : stage.trigger === "with_previous"
      ? previousStart + delay : previousEnd + delay;
    started = true;
    const stagger = Math.max(0, Math.min(180, Number(stage.staggerMs ?? 90)));
    const offsets = new Map();
    let nextOffset = 0;
    let endMs = startMs;
    const orderedItems = [...(stage.items || [])].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
    for (const item of orderedItems) {
      const moduleKey = item.moduleId ?? item.containerId ?? `shape-${item.shapeId}`;
      if (!offsets.has(moduleKey)) { offsets.set(moduleKey, nextOffset); nextOffset += stagger; }
      const itemStartMs = startMs + offsets.get(moduleKey)
        + (Number.isInteger(item.paragraphIndex) ? item.paragraphIndex * stagger : 0);
      const entry = { clickIndex, startMs: itemStartMs, stageIndex: index,
        durationMs: Math.max(0, Number(item.durationMs) || 0), effect: item.effect };
      if (!byShape.has(item.shapeId)) byShape.set(item.shapeId, []);
      byShape.get(item.shapeId).push(entry);
      endMs = Math.max(endMs, itemStartMs + Math.max(0, Number(item.durationMs) || 0));
    }
    byStage.push({ clickIndex, startMs });
    previousStart = startMs;
    previousEnd = Math.max(previousEnd, endMs);
  }
  return { byShape, byStage };
}

/** Measure overlaps across stages on the same teacher-click timeline. */
export function measureAnimationConcurrency(slidePlan) {
  const starts = calculateItemStarts(slidePlan);
  const clicks = new Map();
  for (const entries of starts.byShape.values()) {
    for (const entry of entries) {
      if (!clicks.has(entry.clickIndex)) clicks.set(entry.clickIndex, []);
      const wipe = entry.effect === "wipe" ? 1 : 0;
      const events = clicks.get(entry.clickIndex);
      events.push({ time: entry.startMs, delta: 1, wipe });
      events.push({ time: entry.startMs + Math.max(1, entry.durationMs), delta: -1, wipe: -wipe });
    }
  }
  let peakItems = 0;
  let peakWipes = 0;
  for (const events of clicks.values()) {
    let items = 0;
    let wipes = 0;
    // Ending at t and starting at t is sequential, not simultaneous.
    events.sort((a, b) => a.time - b.time || a.delta - b.delta);
    for (const event of events) {
      items += event.delta;
      wipes += event.wipe;
      peakItems = Math.max(peakItems, items);
      peakWipes = Math.max(peakWipes, wipes);
    }
  }
  return { peakItems, peakWipes };
}

// Teaching checks must distinguish paragraphs sharing one physical text box.
// This projection exists only for review; the writer still targets original IDs.
function paragraphReviewProjection(sourceSlide, slidePlan) {
  const paragraphShapes = new Set((slidePlan.stages || []).flatMap((stage) => (stage.items || [])
    .filter((item) => Number.isInteger(item.paragraphIndex)).map((item) => item.shapeId)));
  if (!paragraphShapes.size) return null;
  const key = (id, index) => `${id}:paragraph-${index + 1}`;
  const units = new Map();
  const elements = (sourceSlide.elements || []).flatMap((element) => {
    if (!paragraphShapes.has(element.id)) return [{ ...element }];
    const paragraphs = (element.paragraphs || []).flatMap((text, index) => {
      if (!String(text || "").trim()) return [];
      const assignedStage = (slidePlan.stages || []).find((stage) => (stage.items || [])
        .some((item) => item.shapeId === element.id && item.paragraphIndex === index));
      let role = assignedStage?.semanticRole || "body";
      if (/^(?:答案|参考答案|正确答案)[：:]/.test(text.trim())) role = "answer";
      else if (/[?？]/.test(text)) role = "question";
      else if (/^(?:【解析】|解析[：:])/.test(text.trim())) role = "analysis";
      else if (/^(?:结论|小结|总结)[：:]/.test(text.trim())) role = "conclusion";
      return [{ ...element, id: key(element.id, index), paragraphs: [], text, role,
        originalShapeId: element.id, originalParagraphIndex: index }];
    });
    units.set(element.id, paragraphs.map((paragraph) => paragraph.id));
    return paragraphs;
  });
  const expandId = (id) => units.get(id) || [id];
  for (const element of elements) {
    if (element.overlayForIds) element.overlayForIds = element.overlayForIds.flatMap(expandId);
    if (element.backingForIds) element.backingForIds = element.backingForIds.flatMap(expandId);
  }
  const stages = (slidePlan.stages || []).map((stage) => ({
    ...stage,
    requiresVisibleShapeIds: (stage.requiresVisibleShapeIds || []).flatMap(expandId),
    items: (stage.items || []).flatMap((item) => {
      if (!paragraphShapes.has(item.shapeId)) return [{ ...item }];
      const ids = Number.isInteger(item.paragraphIndex) ? [key(item.shapeId, item.paragraphIndex)] : expandId(item.shapeId);
      return ids.map((id) => {
        const projected = { ...item, shapeId: id };
        delete projected.paragraphIndex;
        return projected;
      });
    }),
  }));
  return {
    sourceSlide: { ...sourceSlide, elements },
    slidePlan: { ...slidePlan, stages,
      approvedStaticVisualIds: (slidePlan.approvedStaticVisualIds || []).flatMap(expandId),
      approvedEarlyBackingIds: (slidePlan.approvedEarlyBackingIds || []).flatMap(expandId) },
  };
}

/** Simulate the settled classroom view after each teaching beat and teacher click. */
export function simulateTeachingStates(sourceSlide, slidePlan) {
  const stages = slidePlan.stages || [];
  const entranceKeys = new Map();
  const keyFor = (item) => `${item.shapeId}:${Number.isInteger(item.paragraphIndex) ? item.paragraphIndex : "all"}`;
  for (const stage of stages) {
    for (const item of stage.items || []) {
      const key = keyFor(item);
      if (stage.trigger !== "initial" && item.effect !== "fade-out") {
        if (!entranceKeys.has(item.shapeId)) entranceKeys.set(item.shapeId, new Set());
        entranceKeys.get(item.shapeId).add(key);
      }
    }
  }
  const revealed = new Set();
  const exited = new Set();
  const snapshot = (beat, clickIndex, stageIds = []) => {
    const coveredShapeIds = new Set((sourceSlide.elements || [])
      .filter((element) => element.role === "mask" && !exited.has(element.id))
      .flatMap((element) => element.overlayForIds || []));
    const fullyVisibleShapeIds = [];
    const visibleShapeIds = [];
    const visibleParagraphs = [];
    for (const element of sourceSlide.elements || []) {
      const entrances = entranceKeys.get(element.id);
      const clear = !exited.has(element.id) && !coveredShapeIds.has(element.id);
      const paragraphs = (element.paragraphs || []).flatMap((text, paragraphIndex) => text ? [{ shapeId: element.id, paragraphIndex }] : []);
      const visible = paragraphs.filter((paragraph) => {
        const paragraphKey = keyFor(paragraph);
        return clear && (!entrances || (entrances.has(`${element.id}:all`)
          ? revealed.has(`${element.id}:all`) : !entrances.has(paragraphKey) || revealed.has(paragraphKey)));
      });
      visibleParagraphs.push(...visible);
      const fullyVisible = clear && (paragraphs.length ? visible.length === paragraphs.length
        : !entrances || [...entrances].every((key) => revealed.has(key)));
      if (fullyVisible) fullyVisibleShapeIds.push(element.id);
      // A partly revealed text box can already show unanimated paragraphs.
      if (fullyVisible || visible.length || (clear
        && entrances && [...entrances].some((key) => revealed.has(key)))) {
        visibleShapeIds.push(element.id);
      }
    }
    return { beat, clickIndex, stageIds, visibleShapeIds, fullyVisibleShapeIds, visibleParagraphs };
  };
  const beats = [];
  const clickStates = [];
  const stageBeatIndexes = [];
  let beat = -1;
  let clickIndex = 0;
  const pending = [];
  const flushBeat = () => {
    if (!pending.length) return;
    const state = snapshot(beat, clickIndex, pending.map((entry) => entry.id));
    beats.push(state);
    pending.length = 0;
  };
  const flushClick = () => {
    const state = snapshot(beat, clickIndex);
    if (clickStates.at(-1)?.clickIndex === clickIndex) clickStates[clickStates.length - 1] = state;
    else clickStates.push(state);
  };
  for (const [index, stage] of stages.entries()) {
    if (index === 0 || stage.trigger !== "with_previous") {
      flushBeat();
      if (stage.trigger === "on_click") { flushClick(); clickIndex += 1; }
      beat += 1;
    }
    stageBeatIndexes.push(beat);
    pending.push({ id: stage.id || `stage-${index + 1}` });
    for (const item of stage.items || []) {
      if (item.effect === "fade-out") exited.add(item.shapeId);
      else revealed.add(keyFor(item));
    }
  }
  flushBeat();
  flushClick();
  return { beats, clickStates, stageBeatIndexes };
}

/** Check the classroom meaning of an executable sequence, not just target IDs. */
export function reviewTeachingSequence(sourceSlide, slidePlan, slideSize, interactionMode = "classroom-controlled") {
  const projected = paragraphReviewProjection(sourceSlide, slidePlan);
  if (projected) return reviewTeachingSequence(projected.sourceSlide, projected.slidePlan, slideSize, interactionMode);
  const errors = [];
  const warnings = [];
  const elements = sourceSlide.elements || [];
  // Template licences and agendas describe the deck rather than teach the
  // current concept; words such as "summary" there are navigation labels.
  if (elements.some((element) => /(?:模板使用说明|母版说明|《目录》|课程目录)/i.test(String(element.text || "")))) {
    return { errors, warnings };
  }
  const height = Math.max(1, Number(slideSize?.height) || 1);
  const area = Math.max(1, Number(slideSize?.width) || 1) * height;
  const stages = slidePlan.stages || [];
  const placeholderCount = elements.filter((element) => /(?:单击此处输入|点击输入|在此输入正文)/.test(element.text)).length;
  if (placeholderCount && interactionMode === "classroom-controlled") {
    errors.push(`Slide ${slidePlan.slide} still contains ${placeholderCount} unfinished teaching placeholder(s).`);
  }
  const substantive = elements.filter((element) => !["decoration", "background", "repeat", "page-number"].includes(element.role)
    && (element.text.length >= 8 || element.width * element.height / area >= 0.04));
  if (!stages.some((stage) => stage.trigger !== "initial") && substantive.length >= 3) {
    warnings.push(`Slide ${slidePlan.slide} has several teaching elements but no element animation; check its static teaching cue.`);
  }
  const stageByShape = new Map();
  const approvedStaticVisuals = new Set(slidePlan.approvedStaticVisualIds || []);
  const approvedDeferredVisualQuestions = new Set(slidePlan.approvedDeferredVisualQuestionStageIds || []);
  const simulation = simulateTeachingStates(sourceSlide, slidePlan);
  const itemStarts = calculateItemStarts(slidePlan);
  const stageBeats = simulation.stageBeatIndexes;
  stages.forEach((stage, index) => {
    for (const item of stage.items || []) {
      if (!stageByShape.has(item.shapeId)) stageByShape.set(item.shapeId,
        { index, beat: stageBeats[index], id: stage.id || `stage-${index + 1}`, trigger: stage.trigger });
    }
  });
  for (const [index, stage] of stages.entries()) {
    for (const requiredId of stage.requiresVisibleShapeIds || []) {
      const state = simulation.beats[stageBeats[index]];
      if (!state?.fullyVisibleShapeIds.includes(requiredId)) {
        errors.push(`Slide ${slidePlan.slide} stage ${stage.id || index + 1} uses shape ${requiredId} before that prerequisite is visible.`);
        continue;
      }
      const requiredStarts = itemStarts.byShape.get(requiredId) || [];
      const dependentItems = stage.semanticRole === "question"
        && (stage.items || []).some((item) => item.role === "question")
        ? stage.items.filter((item) => item.role === "question") : stage.items || [];
      const dependentStarts = dependentItems.flatMap((item) => itemStarts.byShape.get(item.shapeId)
        ?.filter((entry) => entry.stageIndex === index) || []);
      const dependentStart = Math.min(...dependentStarts.map((entry) => entry.startMs));
      const requiredStart = Math.max(...requiredStarts.map((entry) => entry.startMs));
      const requiredClick = Math.max(...requiredStarts.map((entry) => entry.clickIndex));
      const dependentClick = itemStarts.byStage[index]?.clickIndex ?? 0;
      if (requiredStarts.length && dependentStarts.length && requiredClick === dependentClick
        && requiredStart > dependentStart) {
        errors.push(`Slide ${slidePlan.slide} stage ${stage.id || index + 1} starts before required shape ${requiredId} because of stagger or delay.`);
      }
      for (const mask of elements.filter((element) => element.role === "mask"
        && (element.overlayForIds || []).includes(requiredId))) {
        const maskExit = (itemStarts.byShape.get(mask.id) || []).find((entry) => entry.effect === "fade-out");
        if (maskExit && dependentStarts.length && maskExit.clickIndex === dependentClick
          && dependentStart < maskExit.startMs + maskExit.durationMs) {
          errors.push(`Slide ${slidePlan.slide} stage ${stage.id || index + 1} starts before mask ${mask.id} has revealed required shape ${requiredId}.`);
        }
      }
    }
  }
  const visibleAtStart = (element) => !stageByShape.has(element.id)
    || stageByShape.get(element.id).trigger === "initial";
  const firstAppearance = (shapeId) => {
    const starts = itemStarts.byShape.get(shapeId) || [];
    if (!starts.length) return { clickIndex: 0, startMs: 0 };
    return starts.reduce((first, current) => current.clickIndex < first.clickIndex
      || (current.clickIndex === first.clickIndex && current.startMs < first.startMs)
      ? current : first);
  };
  const carriedTextByBacking = new Map();
  for (const { backingId, contentId } of contentBackingPairs(elements, slideSize)) {
    if (!carriedTextByBacking.has(backingId)) carriedTextByBacking.set(backingId, []);
    carriedTextByBacking.get(backingId).push(contentId);
  }
  const approvedEarlyBackings = new Set(slidePlan.approvedEarlyBackingIds || []);
  for (const [backingId, contentIds] of carriedTextByBacking) {
    const backing = firstAppearance(backingId);
    const firstContent = contentIds.map((shapeId) => ({ shapeId, ...firstAppearance(shapeId) }))
      .sort((a, b) => a.clickIndex - b.clickIndex || a.startMs - b.startMs)[0];
    if (!firstContent) continue;
    const earlyByClick = backing.clickIndex < firstContent.clickIndex;
    const earlyWithinClick = backing.clickIndex === firstContent.clickIndex
      && firstContent.startMs - backing.startMs > 120;
    const late = backing.clickIndex > firstContent.clickIndex
      || (backing.clickIndex === firstContent.clickIndex
        && backing.startMs - firstContent.startMs > 120);
    if ((earlyByClick || earlyWithinClick) && !approvedEarlyBackings.has(backingId)) {
      errors.push(`Slide ${slidePlan.slide} content backing shape ${backingId} appears before its first text shape ${firstContent.shapeId}; reveal the plate with its content or document an intentional early-backing teaching beat.`);
    } else if (late) {
      errors.push(`Slide ${slidePlan.slide} content backing shape ${backingId} appears after its first text shape ${firstContent.shapeId}.`);
    }
  }
  const plainText = (element) => String(element.text || "").replace(/\s+/g, "").trim();
  const isExplicitConclusion = (element) => element.role === "conclusion"
    || /(?:结论|小结|总结)/.test(plainText(element));
  const isAnalysis = (element) => element.role === "analysis"
    || /(?:【解析】|^解析[:：])/.test(String(element.text || "").trim());
  const isVisualEvidence = (element) => ["graphic", "group", "image"].includes(element.type)
    || element.role === "diagram";
  const questionPresent = elements.some((element) => element.role === "question"
    || /(?:[?？]|例\s*\d+|练习)/.test(String(element.text || "")));
  const questions = elements.filter((element) => element.role === "question"
    || /[?？]/.test(String(element.text || "")));
  const observationImages = elements.filter((element) => element.type === "image"
    && element.role === "image" && element.width * element.height / area >= 0.01
    && element.width * element.height / area <= 0.65);
  if (observationImages.length === 1) {
    const image = observationImages[0];
    const imageStage = stageByShape.get(image.id);
    for (const question of questions.filter((element) => asksAboutVisiblePicture(element.text))) {
      const questionStage = stageByShape.get(question.id);
      const questionBeat = questionStage?.beat ?? -1;
      if (imageStage && imageStage.trigger !== "initial" && imageStage.beat > questionBeat
        && !approvedDeferredVisualQuestions.has(questionStage?.id)) {
        errors.push(`Slide ${slidePlan.slide} visual question shape ${question.id} appears before its required image ${image.id}; show the image no later than the question or document a teacher-approved blind prediction.`);
      } else if (imageStage && questionStage && !approvedDeferredVisualQuestions.has(questionStage.id)
        && !(stages[questionStage.index]?.requiresVisibleShapeIds || []).includes(image.id)) {
        const imageStart = itemStarts.byShape.get(image.id)?.[0];
        const questionStart = itemStarts.byShape.get(question.id)?.[0];
        if (imageStart && questionStart && imageStart.clickIndex === questionStart.clickIndex
          && imageStart.startMs > questionStart.startMs) {
          errors.push(`Slide ${slidePlan.slide} visual question shape ${question.id} starts before required image ${image.id} because of stagger or delay.`);
        }
      }
    }
  }
  const answerCandidates = elements.filter((element) => element.role === "answer"
    || /^\s*(?:答案|参考答案|正确答案)[:：]/.test(String(element.text || ""))
    || (questions.length === 1 && element.id !== questions[0].id
      && element.y >= questions[0].y
      && /[?？]/.test(questions[0].text)
      && /[A-Za-z]{4,}/.test(element.text)
      && !/[?？]/.test(element.text)
      && [...questions[0].text.toLowerCase().matchAll(/[a-z]{4,}/g)]
        .some((match) => element.text.toLowerCase().includes(match[0]))));
  const answerStageIndexes = answerCandidates
    .map((element) => stageByShape.get(element.id)?.index).filter(Number.isInteger);
  const questionBeats = stages.flatMap((stage, index) => stage.semanticRole === "question" ? [stageBeats[index]] : []);
  const answerBeats = stages.flatMap((stage, index) => stage.semanticRole === "answer" ? [stageBeats[index]] : []);
  if (questionBeats.some((questionBeat) => answerBeats.includes(questionBeat))) {
    errors.push(`Slide ${slidePlan.slide} reveals a model-classified question and answer in the same teaching beat.`);
  }
  if (questionBeats.length && answerBeats.some((answerBeat) => answerBeat < Math.min(...questionBeats))) {
    errors.push(`Slide ${slidePlan.slide} reveals a model-classified answer before its question.`);
  }
  if (questionPresent && interactionMode !== "microcourse-auto") {
    const questionIds = new Set(questions.map((element) => element.id));
    const answerIds = new Set(answerCandidates.map((element) => element.id));
    for (const [index, stage] of stages.entries()) {
      const ids = new Set((stage.items || []).map((item) => item.shapeId));
      if ([...ids].some((id) => questionIds.has(id)) && [...ids].some((id) => answerIds.has(id))) {
        errors.push(`Slide ${slidePlan.slide} stage ${index + 1} reveals a question and its answer together.`);
      }
    }
    for (const element of answerCandidates) {
      const stage = stageByShape.get(element.id);
      if (!stage || stage.trigger === "initial") {
        errors.push(`Slide ${slidePlan.slide} answer shape ${element.id} is visible before a teacher reveal.`);
      } else if (stage.trigger !== "on_click") {
        errors.push(`Slide ${slidePlan.slide} answer shape ${element.id} does not have a teacher click.`);
      }
    }
  }
  const conclusions = elements.filter((element) => {
    const text = plainText(element);
    if (!text || /[?？]$/.test(text)) return false;
    const evidenceAbove = elements.some((other) => other.id !== element.id
      && isVisualEvidence(other) && !isExplicitConclusion(other)
      && (plainText(other).length >= 4 || other.type === "graphic")
      && other.y + other.height * 0.5 < element.y
      && other.width * other.height / area >= 0.02);
    if (!evidenceAbove) return false;
    if (isExplicitConclusion(element)) return true;
    const lowerStatement = element.y > height * 0.6 && text.length >= 14
      && /(?:等于|可得|规律|由此|因此|说明)/.test(text);
    return lowerStatement;
  });
  const conclusionIds = new Set(conclusions.map((element) => element.id));
  const explicitEvidenceBeats = stages.flatMap((stage, index) => stage.semanticRole === "evidence"
    ? [stageBeats[index]] : []);
  const explicitConclusionBeats = stages.flatMap((stage, index) => stage.semanticRole === "conclusion"
    ? [stageBeats[index]] : []);
  if (explicitEvidenceBeats.length && explicitConclusionBeats.some((value) => value <= Math.max(...explicitEvidenceBeats))) {
    errors.push(`Slide ${slidePlan.slide} reveals a model-classified conclusion before or with its evidence.`);
  }
  const formulae = elements.filter((element) => !conclusionIds.has(element.id)
    && element.y > height * 0.75
    && /^[A-Za-zΑ-Ωα-ω]\s*[=＝]/.test(String(element.text || "").trim())
    && conclusions.some((conclusion) => conclusion.y < element.y));
  for (const element of [...conclusions, ...formulae]) {
    const stage = stageByShape.get(element.id);
    if (visibleAtStart(element)) {
      errors.push(`Slide ${slidePlan.slide} conclusion or derived formula shape ${element.id} is visible before the evidence.`);
      continue;
    }
    const earlierEvidenceStages = elements.filter((other) => other.id !== element.id
      && isVisualEvidence(other) && !conclusionIds.has(other.id)
      && (plainText(other).length >= 4 || other.type === "graphic")
      && other.y + other.height * 0.5 < element.y)
      .map((other) => stageByShape.get(other.id)?.index).filter(Number.isInteger);
    if (earlierEvidenceStages.length && stage.index <= Math.max(...earlierEvidenceStages)) {
      errors.push(`Slide ${slidePlan.slide} conclusion or formula shape ${element.id} appears before or with its evidence.`);
    }
  }
  if (questionPresent) {
    for (const element of elements.filter(isAnalysis)) {
      const stage = stageByShape.get(element.id);
      if (visibleAtStart(element)) {
        errors.push(`Slide ${slidePlan.slide} analysis shape ${element.id} is visible before the class works through the question.`);
      } else if (answerStageIndexes.length && stage.index <= Math.max(...answerStageIndexes)) {
        errors.push(`Slide ${slidePlan.slide} analysis shape ${element.id} appears before or with the answer.`);
      }
    }
  }
  const oldTargets = new Set((sourceSlide.animationSummary?.targets || []).map((target) => target.shapeId));
  const contentImages = elements.filter((element) => element.type === "image"
    && element.role !== "background" && element.width * element.height / area >= 0.04
    && element.width * element.height / area <= 0.65);
  for (const image of contentImages) {
    if (!visibleAtStart(image)) continue;
    const caption = elements.find((candidate) => candidate.text && candidate.id !== image.id
      && ["section-title", "subtitle", "body"].includes(candidate.role)
      && stageByShape.has(candidate.id)
      && candidate.y >= image.y + image.height * 0.72
      && candidate.y - (image.y + image.height) < height * 0.08
      && Math.abs((candidate.x + candidate.width / 2) - (image.x + image.width / 2)) < image.width * 0.38);
    if (caption && !approvedStaticVisuals.has(image.id)) {
      errors.push(`Slide ${slidePlan.slide} image shape ${image.id} is static while caption ${caption.id} is revealed separately.`);
    }
  }
  const cards = elements.filter((element) => element.type === "group"
    && plainText(element).length >= 12
    && element.width * element.height / area >= 0.04
    && element.width * element.height / area <= 0.3);
  for (const card of cards.filter(visibleAtStart)) {
    const matching = cards.filter((other) => other.id !== card.id
      && Math.min(other.width, card.width) / Math.max(other.width, card.width) >= 0.68
      && Math.min(other.height, card.height) / Math.max(other.height, card.height) >= 0.68);
    if (!approvedStaticVisuals.has(card.id) && matching.filter((other) => !visibleAtStart(other)).length >= 2) {
      errors.push(`Slide ${slidePlan.slide} card shape ${card.id} is visible before two matching teaching cards.`);
    }
  }
  for (const element of elements) {
    if (!visibleAtStart(element) || conclusionIds.has(element.id) || isAnalysis(element)
      || approvedStaticVisuals.has(element.id)) continue;
    const ratio = element.width * element.height / area;
    if (sourceSlide.type !== "cover" && isVisualEvidence(element) && ratio >= 0.035 && ratio <= 0.65
      && element.y > height * 0.16 && element.y < height * 0.9
      && (plainText(element).length >= 8 || oldTargets.has(element.id))) {
      const message = `Slide ${slidePlan.slide} content visual shape ${element.id} remains visible from the start without a teaching cue.`;
      if (plainText(element).length >= 8) errors.push(message);
      else warnings.push(message);
    }
    if (oldTargets.has(element.id) && ["image", "graphic", "group"].includes(element.type)
      && ratio >= 0.025 && element.role !== "background" && !approvedStaticVisuals.has(element.id)) {
      const message = `Slide ${slidePlan.slide} formerly animated content visual ${element.id} is now static without a teaching cue.`;
      if (element.type === "image" || (plainText(element).length >= 4 && ratio >= 0.035)) errors.push(message);
      else warnings.push(message);
    }
  }
  return { errors, warnings };
}

export async function compileModelPlan(inputPath, modelPlan, authorization = {}, options = {}) {
  let inspection = options.inspection ? structuredClone(options.inspection) : null;
  if (inspection) {
    if (inspection.analysisRevision !== ANALYSIS_REVISION) {
      throw new Error("Saved structure analysis is from an older parser. Re-analyze the source.");
    }
    const absolute = path.resolve(inputPath);
    const currentHash = await sha256(absolute);
    if (inspection?.source?.sha256 !== currentHash) {
      throw new Error("Cached analysis does not match the PowerPoint file. Re-analyze the source.");
    }
    const stat = await fs.stat(absolute);
    inspection.source = {
      ...inspection.source,
      path: absolute,
      extension: path.extname(absolute).toLowerCase(),
      size: stat.size,
    };
  } else {
    inspection = await inspectPresentation(inputPath);
  }
  const brief = buildModelBrief(inspection);
  const errors = validateModelPlanShape(modelPlan, inspection, brief, authorization);
  if (errors.length) throw new Error(`Invalid model animation plan:\n- ${errors.join("\n- ")}`);
  const inspectionBySlide = new Map(inspection.slides.map((slide) => [slide.slide, slide]));
  const briefBySlide = new Map(brief.slides.map((slide) => [slide.slide, slide]));
  const modelBySlide = new Map(modelPlan.slides.map((slide) => [slide.slide, slide]));
  const strategy = modelPlan.deckStrategy;
  const slides = [];
  for (const sourceSlide of inspection.slides) {
    const modelSlide = modelBySlide.get(sourceSlide.slide);
    if (!modelSlide) continue;
    const briefSlide = briefBySlide.get(sourceSlide.slide);
    const allBriefModules = [...(briefSlide.modules || []), ...(briefSlide.reviewableModules || [])];
    const moduleById = new Map(allBriefModules.map((module) => [module.moduleId, module]));
    const elementById = new Map(inspectionBySlide.get(sourceSlide.slide).elements.map((element) => [element.id, element]));
    const paragraphById = new Map(allBriefModules.flatMap((module) => (module.paragraphs || [])
      .map((paragraph) => [paragraph.paragraphId, { ...paragraph, moduleId: module.moduleId }])));
    const firstParagraphStageByModule = new Map();
    modelSlide.stages.forEach((stage, stageIndex) => {
      for (const paragraphId of stage.paragraphIds || []) {
        const moduleId = paragraphById.get(paragraphId)?.moduleId;
        if (moduleId && !firstParagraphStageByModule.has(moduleId)) firstParagraphStageByModule.set(moduleId, stageIndex);
      }
    });
    const presetId = resolveModelPresetId(modelSlide, modelPlan, sourceSlide);
    const preset = await loadPreset(presetId);
    const stages = modelSlide.stages.map((stage, index) => {
      const effect = stage.effect ?? strategy.defaultEffect;
      const durationMs = Number(stage.durationMs ?? strategy.defaultDurationMs);
      const staggerMs = Number(stage.staggerMs ?? strategy.defaultStaggerMs);
      const delayMs = Number(stage.delayMs ?? strategy.defaultDelayMs ?? 0);
      const granularity = stage.granularity ?? strategy.defaultGranularity;
      const stagePreset = { ...preset, paragraphs: granularity === "paragraph" };
      const wholeModuleIds = stage.moduleIds || [];
      const paragraphRefs = (stage.paragraphIds || []).map((paragraphId) => paragraphById.get(paragraphId));
      const selectedModuleIds = [...new Set([...wholeModuleIds, ...paragraphRefs.map((paragraph) => paragraph.moduleId)])];
      const selectedModules = selectedModuleIds.map((moduleId) => moduleById.get(moduleId));
      const inferredRole = semanticRoleForModule(selectedModules.map((module) => ({ role: module.semanticRole })));
      const semanticRole = String(stage.contentRole || inferredRole);
      const wholeItems = wholeModuleIds.flatMap((moduleId) => {
        const module = moduleById.get(moduleId);
        return module.memberIds.flatMap((id) => {
        const element = elementById.get(id);
        if (!element) return [];
        return expandElement(element, stagePreset).map((item) => ({
          ...item,
          effect,
          durationMs,
          direction: stage.direction || item.direction,
          moduleId: module.moduleId,
        }));
        });
      });
      const paragraphItems = paragraphRefs.map((paragraph) => {
        const element = elementById.get(paragraph.shapeId);
        const item = itemFromElement(element, stagePreset, paragraph.paragraphIndex);
        return {
          ...item,
          role: semanticRole,
          effect,
          durationMs,
          direction: stage.direction || item.direction,
          moduleId: paragraph.moduleId,
          paragraphId: paragraph.paragraphId,
        };
      });
      const accompanyingItems = selectedModuleIds.flatMap((moduleId) => {
        if (firstParagraphStageByModule.get(moduleId) !== index || wholeModuleIds.includes(moduleId)) return [];
        const module = moduleById.get(moduleId);
        return module.memberIds.flatMap((id) => {
          const element = elementById.get(id);
          if (!element || element.text) return [];
          const item = itemFromElement(element, stagePreset);
          return [{
            ...item,
            effect,
            durationMs,
            direction: stage.direction || item.direction,
            moduleId,
          }];
        });
      });
      const items = [...wholeItems, ...paragraphItems, ...accompanyingItems]
        .sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0)
          || (a.paragraphIndex ?? -1) - (b.paragraphIndex ?? -1));
      return {
        id: stage.id || `model-${index + 1}`,
        label: stage.label || selectedModules.map((module) => module.label).join(" + "),
        trigger: stage.trigger,
        semanticRole,
        delayMs: Math.max(0, delayMs),
        staggerMs,
        granularity,
        moduleIds: selectedModuleIds,
        paragraphIds: stage.paragraphIds || [],
        rationale: stage.rationale || "",
        answersQuestionStageId: stage.answersQuestionStageId || "",
        promotionRationale: stage.promotionRationale || "",
        requiresVisibleShapeIds: [...new Set([...(stage.requiresVisibleModuleIds || []),
          ...(stage.visualDependency?.kind === "requires-visible" ? stage.visualDependency.moduleIds || [] : [])])]
          .flatMap((moduleId) => moduleById.get(moduleId)?.memberIds || []),
        items,
      };
    });
    const staticEntries = modelSlide.staticModules || [];
    const explicitStaticIds = staticEntries.flatMap((entry) => {
      const module = moduleById.get(typeof entry === "string" ? entry : entry.moduleId);
      return module?.memberIds ?? [];
    });
    const usedModuleIds = new Set(stages.flatMap((stage) => stage.moduleIds || []));
    const defaultReviewableStaticIds = (briefSlide.reviewableModules || [])
      .filter((module) => !usedModuleIds.has(module.moduleId))
      .flatMap((module) => module.memberIds);
    slides.push({
      slide: sourceSlide.slide,
      file: sourceSlide.file,
      detectedType: sourceSlide.type,
      preset: preset.id,
      presetLabel: preset.label,
      existingAnimation: sourceSlide.existingAnimation,
      animationSummary: sourceSlide.animationSummary,
      protectedMediaTiming: sourceSlide.protectedMediaTiming,
      transition: {
        type: modelSlide.transition
          ?? (briefSlide.mediaPolicy === "preserve-required" ? "preserve" : strategy.defaultTransition),
        durationMs: preset.timing.transition,
      },
      stages,
      unanimated: [
        ...briefSlide.staticModules.flatMap((module) => module.memberIds.map((shapeId) => ({ shapeId, role: module.semanticRole }))),
        ...defaultReviewableStaticIds.map((shapeId) => ({ shapeId, role: "reviewable-static" })),
        ...explicitStaticIds.map((shapeId) => ({ shapeId, role: "model-static" })),
      ],
      warnings: reviewSemanticCoverage(briefSlide, modelSlide),
      disposition: modelSlide.action ?? briefSlide.recommendedAction,
    });
  }
  return {
    schemaVersion: 1,
    planningMode: "model-v3-strategy-delta",
    interactionMode: modelPlan.mode,
    strictCoverage: true,
    createdAt: new Date().toISOString(),
    source: inspection.source,
    slideSize: inspection.slideSize,
    requestedPreset: modelPlan.preset || "model-selected",
    modelStrategy: modelPlan.deckStrategy,
    targetApplication: modelPlan.targetApplication || "unspecified",
    performanceBudget: performanceBudgetFor(modelPlan.targetApplication || "unspecified", modelPlan.mode),
    defaultExistingPolicy: "replace",
    authorization: {
      replaceExisting: authorization.allowReplaceExisting === true,
      noTransition: authorization.allowNoTransition === true,
      unattended: authorization.allowUnattended === true,
    },
    slides,
  };
}

function performanceBudgetFor(targetApplication = "unspecified", mode = "classroom-controlled") {
  if (mode === "microcourse-auto") {
    return {
      maxAnimatedTargetsPerSlide: targetApplication === "wps" ? 14 : 18,
      maxConcurrentItemsPerStage: targetApplication === "wps" ? 5 : 7,
      maxConcurrentWipeItems: targetApplication === "wps" ? 2 : 3,
      maxLargeWipeAreaRatio: 0.35,
    };
  }
  return {
    maxAnimatedTargetsPerSlide: targetApplication === "powerpoint" ? 16 : 12,
    maxConcurrentItemsPerStage: targetApplication === "powerpoint" ? 6 : 5,
    maxConcurrentWipeItems: targetApplication === "powerpoint" ? 3 : 2,
    maxLargeWipeAreaRatio: 0.3,
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;");
}

export function renderPlanHtml(plan) {
  const slides = plan.slides.map((slide) => {
    const animatedStages = slide.stages.filter((stage) => stage.trigger !== "initial");
    const stages = slide.stages.map((stage, stageIndex) => {
      const items = stage.items.map((item) => `<li><strong>${escapeHtml(item.role)}</strong> ${escapeHtml(item.text || item.name || `#${item.shapeId}`)}${item.effect ? ` <span>${escapeHtml(item.effect)} / ${item.durationMs}ms</span>` : ""}</li>`).join("");
      const displayIndex = stage.trigger === "initial" ? "初始" : animatedStages.indexOf(stage) + 1;
      return `<section class="stage ${stage.trigger === "on_click" ? "click" : "auto"}"><h4>${displayIndex} · ${escapeHtml(stage.label || stage.id)} · ${escapeHtml(stage.trigger)}</h4><ul>${items}</ul></section>`;
    }).join("");
    const overlays = animatedStages.map((stage, index) => {
      const drawable = stage.items.filter((item) => Number.isFinite(item.x) && Number.isFinite(item.y) && item.width > 0 && item.height > 0);
      if (!drawable.length) return "";
      const box = unionBounds(drawable);
      const left = box.x / plan.slideSize.width * 100;
      const top = box.y / plan.slideSize.height * 100;
      const width = Math.max(2.5, box.width / plan.slideSize.width * 100);
      const height = Math.max(4, box.height / plan.slideSize.height * 100);
      const mode = stage.trigger === "on_click" ? "click" : "auto";
      return `<div class="overlay ${mode}" style="left:${left.toFixed(3)}%;top:${top.toFixed(3)}%;width:${width.toFixed(3)}%;height:${height.toFixed(3)}%"><b>${index + 1}</b></div>`;
    }).join("");
    const structureMap = `<div class="structure-map">结构坐标示意</div>`;
    const warnings = slide.warnings.length ? `<div class="warning">${slide.warnings.map(escapeHtml).join("<br>")}</div>` : "";
    return `<article><h2>第 ${slide.slide} 页</h2><p><b>类型：</b>${escapeHtml(slide.detectedType)}　<b>预设：</b>${escapeHtml(slide.presetLabel)}　<b>原动画：</b>${slide.existingAnimation ? "有" : "无"}</p>${warnings}<div class="review"><div class="canvas">${structureMap}${overlays}</div><div class="stages">${stages}</div></div></article>`;
  }).join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PPT 动画方案</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif;max-width:1280px;margin:32px auto;padding:0 20px;color:#172033;background:#f7f8fb}header,article{background:white;border:1px solid #e2e6ef;border-radius:14px;padding:20px 24px;margin:16px 0}h1,h2,h4{margin:0 0 12px}h2{color:#173f86}.review{display:grid;grid-template-columns:minmax(420px,1.15fr) minmax(340px,.85fr);gap:22px;align-items:start}.canvas{position:relative;background:#eef1f6;aspect-ratio:${plan.slideSize.width}/${plan.slideSize.height};overflow:hidden;border-radius:10px;border:1px solid #cfd6e4}.structure-map{display:grid;height:100%;place-items:center;color:#778197}.overlay{position:absolute;border:3px solid rgba(20,145,90,.9);background:rgba(20,145,90,.1);box-sizing:border-box;border-radius:7px;pointer-events:none}.overlay.click{border-color:#ef7b21;background:rgba(239,123,33,.12)}.overlay b{position:absolute;left:-3px;top:-27px;color:white;background:#14915a;border-radius:99px;min-width:24px;height:24px;display:grid;place-items:center;font-size:13px}.overlay.click b{background:#ef7b21}.stage{border-left:4px solid #14915a;padding:9px 0 9px 14px;margin:10px 0}.stage.click{border-color:#ef7b21}.stage span{color:#697386}.stage ul{margin:6px 0;padding-left:20px}.warning{background:#fff5d8;border-radius:8px;padding:10px 12px;color:#745000;margin-bottom:14px}li{margin:5px 0}@media(max-width:900px){.review{grid-template-columns:1fr}}</style></head><body><header><h1>PPT 原生动画方案</h1><p>${escapeHtml(plan.source.path)}</p><p>请求预设：${escapeHtml(plan.requestedPreset)}，共 ${plan.slides.length} 页。绿色为自动播放，橙色为教师点击控制的教学节点。</p></header>${slides}</body></html>`;
}

export function summarizeExecutablePlan(plan, results = []) {
  const slides = Array.isArray(plan?.slides) ? plan.slides : [];
  const stages = slides.flatMap((slide) => slide.stages || []);
  const animatedStages = stages.filter((stage) => stage.trigger !== "initial" && (stage.items || []).length);
  const statusCounts = results.reduce((counts, result) => {
    counts[result.status] = (counts[result.status] || 0) + 1;
    return counts;
  }, {});
  return {
    slides: slides.length,
    plannedStages: stages.length,
    initialVisibleStages: stages.filter((stage) => stage.trigger === "initial").length,
    animatedStages: animatedStages.length,
    autoStages: animatedStages.filter((stage) => ["after_previous", "with_previous"].includes(stage.trigger)).length,
    clickStages: animatedStages.filter((stage) => stage.trigger === "on_click").length,
    clickAnswerStages: animatedStages.filter((stage) => stage.trigger === "on_click" && stage.semanticRole === "answer").length,
    clickTeachingStages: animatedStages.filter((stage) => stage.trigger === "on_click" && stage.semanticRole !== "answer").length,
    animatedTargets: animatedStages.reduce((sum, stage) => sum + (stage.items || []).length, 0),
    animatedSlides: slides.filter((slide) => (slide.stages || []).some((stage) => stage.trigger !== "initial" && (stage.items || []).length)).length,
    transitionOnlySlides: results.filter((result) => result.status === "transition-only").length,
    semanticReviewWarnings: slides.reduce((sum, slide) => sum + (slide.warnings || []).length, 0),
    semanticReviewSlides: slides.filter((slide) => (slide.warnings || []).length).map((slide) => slide.slide),
    statusCounts,
  };
}

function xmlTarget(item) {
  if (Number.isInteger(item.paragraphIndex)) {
    return `<p:spTgt spid="${item.shapeId}"><p:txEl><p:pRg st="${item.paragraphIndex}" end="${item.paragraphIndex}"/></p:txEl></p:spTgt>`;
  }
  return `<p:spTgt spid="${item.shapeId}"/>`;
}

function normalizeEffect(effect) {
  return ["appear", "fade", "wipe", "fade-out"].includes(effect) ? effect : "fade";
}

function buildEffectXml(item, nodeType, delayMs, groupId, nextId) {
  const effect = normalizeEffect(item.effect);
  const exitEffect = effect === "fade-out";
  const presetId = effect === "appear" ? 1 : ["fade", "fade-out"].includes(effect) ? 10 : 22;
  const subtype = effect === "wipe" ? ({ left: 8, up: 1, right: 2, down: 4 }[item.direction] ?? 8) : 0;
  const effectId = nextId();
  const setId = nextId();
  const target = xmlTarget(item);
  let extra = "";
  if (["fade", "fade-out"].includes(effect)) {
    extra = `<p:animEffect transition="${exitEffect ? "out" : "in"}" filter="fade"><p:cBhvr><p:cTn id="${nextId()}" dur="${item.durationMs}" accel="18000" decel="22000"/><p:tgtEl>${target}</p:tgtEl></p:cBhvr></p:animEffect>`;
  } else if (effect === "wipe") {
    const direction = ["left", "up", "right", "down"].includes(item.direction) ? item.direction : "left";
    extra = `<p:animEffect transition="in" filter="wipe(${direction})"><p:cBhvr><p:cTn id="${nextId()}" dur="${item.durationMs}" accel="16000" decel="24000"/><p:tgtEl>${target}</p:tgtEl></p:cBhvr></p:animEffect>`;
  }
  const visibilitySet = exitEffect ? "" : `<p:set><p:cBhvr><p:cTn id="${setId}" dur="${item.durationMs}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn><p:tgtEl>${target}</p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>`;
  return `<p:par><p:cTn id="${effectId}" presetID="${presetId}" presetClass="${exitEffect ? "exit" : "entr"}" presetSubtype="${subtype}" fill="hold" grpId="${groupId}" nodeType="${nodeType}" accel="18000" decel="22000"><p:stCondLst><p:cond delay="${delayMs}"/></p:stCondLst><p:childTnLst>${visibilitySet}${extra}</p:childTnLst></p:cTn></p:par>`;
}

function buildTimingParts(slidePlan, startId = 1) {
  const animatedStages = slidePlan.stages.filter((stage) => stage.trigger !== "initial" && stage.items.length);
  if (!animatedStages.length) return { sequence: "", builds: "" };
  let id = startId;
  const nextId = () => ++id;
  const sequenceId = nextId();
  const groups = [];
  for (const stage of animatedStages) {
    if (stage.trigger === "on_click" || !groups.length) {
      groups.push({ trigger: stage.trigger, stages: [stage] });
    } else {
      groups.at(-1).stages.push(stage);
    }
  }
  const stageXml = groups.map((group) => {
    const outerId = nextId();
    const innerId = nextId();
    let previousStageStart = 0;
    let previousStageEnd = 0;
    let effectIndex = 0;
    const effects = group.stages.map((stage, stageIndex) => {
      const stageDelay = Math.max(0, Number(stage.delayMs ?? 0));
      const stageStart = stageIndex === 0 ? stageDelay
        : stage.trigger === "with_previous" ? previousStageStart + stageDelay
          : previousStageEnd + stageDelay;
      const orderedItems = [...stage.items].sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0));
      const staggerMs = Math.max(0, Math.min(180, Number(stage.staggerMs ?? 90)));
      const moduleOffsets = new Map();
      let nextModuleOffset = 0;
      let stageEnd = stageStart;
      const stageEffects = orderedItems.map((item) => {
        const moduleKey = item.moduleId ?? item.containerId ?? `shape-${item.shapeId}`;
        if (!moduleOffsets.has(moduleKey)) {
          moduleOffsets.set(moduleKey, nextModuleOffset);
          nextModuleOffset += staggerMs;
        }
        const paragraphOffset = Number.isInteger(item.paragraphIndex) ? item.paragraphIndex * staggerMs : 0;
        const nodeType = effectIndex === 0 && group.trigger === "on_click" ? "clickEffect" : "withEffect";
        effectIndex += 1;
        const itemStart = stageStart + moduleOffsets.get(moduleKey) + paragraphOffset;
        stageEnd = Math.max(stageEnd, itemStart + Math.max(0, Number(item.durationMs) || 0));
        return buildEffectXml(item, nodeType, itemStart, outerId, nextId);
      }).join("");
      previousStageStart = stageStart;
      previousStageEnd = Math.max(previousStageEnd, stageEnd);
      return stageEffects;
    }).join("");
    return `<p:par><p:cTn id="${outerId}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="${sequenceId}"/></p:cond></p:stCondLst><p:childTnLst><p:par><p:cTn id="${innerId}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>${effects}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>`;
  }).join("");
  const paragraphShapeIds = [...new Set(animatedStages.flatMap((stage) => stage.items)
    .filter((item) => Number.isInteger(item.paragraphIndex)).map((item) => item.shapeId))];
  const builds = paragraphShapeIds.length
    ? `<p:bldLst>${paragraphShapeIds.map((shapeId) => `<p:bldP spid="${shapeId}" grpId="0" bldLvl="0" animBg="0"/>`).join("")}</p:bldLst>`
    : "";
  const sequence = `<p:seq concurrent="1" nextAc="seek"><p:cTn id="${sequenceId}" dur="indefinite" nodeType="mainSeq"><p:childTnLst>${stageXml}</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>`;
  return { sequence, builds };
}

export function buildTimingXml(slidePlan) {
  const { sequence, builds } = buildTimingParts(slidePlan, 1);
  if (!sequence) return "";
  return `<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>${sequence}</p:childTnLst></p:cTn></p:par></p:tnLst>${builds}</p:timing>`;
}

function removeTiming(xml) {
  return xml.replace(/<p:timing(?:\s[^>]*)?>[\s\S]*?<\/p:timing>/g, "");
}

function insertBeforeSlideEnd(xml, fragment) {
  const cSldEnd = xml.lastIndexOf("</p:cSld>");
  const extIndex = xml.lastIndexOf("<p:extLst");
  if (extIndex > cSldEnd) return `${xml.slice(0, extIndex)}${fragment}${xml.slice(extIndex)}`;
  return xml.replace("</p:sld>", `${fragment}</p:sld>`);
}

function applySlideTransition(xml, transitionType) {
  if (!["fade", "none"].includes(transitionType)) return xml;
  const withoutTransition = xml
    .replace(/<p:transition(?:\s[^>]*)?>[\s\S]*?<\/p:transition>/g, "")
    .replace(/<p:transition(?:\s[^>]*)?\/>/g, "");
  if (transitionType === "none") return withoutTransition;
  const fragment = `<p:transition spd="fast"><p:fade/></p:transition>`;
  const timingIndex = withoutTransition.indexOf("<p:timing");
  if (timingIndex >= 0) {
    return `${withoutTransition.slice(0, timingIndex)}${fragment}${withoutTransition.slice(timingIndex)}`;
  }
  return insertBeforeSlideEnd(withoutTransition, fragment);
}

export function validateExecutablePlan(plan, inspection, existingPolicy = "preserve") {
  const errors = [];
  const warnings = [];
  const inspectionBySlide = new Map(inspection.slides.map((slide) => [slide.slide, slide]));
  const plannedSlides = new Set((plan.slides || []).map((slide) => slide.slide));
  if (plannedSlides.size !== (plan.slides || []).length) errors.push("Executable plan contains duplicate slide entries.");
  for (const sourceSlide of inspection.slides) {
    if (!plannedSlides.has(sourceSlide.slide)) errors.push(`Slide ${sourceSlide.slide} is missing from the executable plan.`);
  }
  for (const slidePlan of plan.slides || []) {
    const sourceSlide = inspectionBySlide.get(slidePlan.slide);
    if (!sourceSlide) {
      errors.push(`Slide ${slidePlan.slide} does not exist in the source.`);
      continue;
    }
    const modelReplaces = slidePlan.disposition === "replace";
    if (sourceSlide.protectedMediaTiming && slidePlan.disposition !== "preserve") {
      errors.push(`Slide ${slidePlan.slide} contains protected media timing and must be preserved without changes.`);
      continue;
    }
    const preservedExisting = sourceSlide.existingAnimation && existingPolicy !== "replace" && !modelReplaces;
    if (slidePlan.disposition === "preserve" || preservedExisting) {
      if (!sourceSlide.existingAnimation && !sourceSlide.protectedMediaTiming) {
        errors.push(`Slide ${slidePlan.slide} is marked preserve but has no meaningful existing animation.`);
      } else {
        warnings.push(`Slide ${slidePlan.slide} contains existing animation and will be preserved.`);
      }
      continue;
    }
    const elementById = new Map(sourceSlide.elements.map((element) => [element.id, element]));
    const animatedStages = (slidePlan.stages || []).filter((stage) => stage.trigger !== "initial");
    const animatedItems = animatedStages.flatMap((stage) => stage.items || []);
    const budget = plan.performanceBudget || {};
    const maxTargets = Number(budget.maxAnimatedTargetsPerSlide ?? 18);
    const maxConcurrent = Number(budget.maxConcurrentItemsPerStage ?? 8);
    const maxConcurrentWipe = Number(budget.maxConcurrentWipeItems ?? 3);
    const maxLargeWipeAreaRatio = Number(budget.maxLargeWipeAreaRatio ?? 0.35);
    if (animatedItems.length > maxTargets) {
      errors.push(`Slide ${slidePlan.slide} has ${animatedItems.length} animated targets; reduce it to at most ${maxTargets} for reliable playback.`);
    }
    const concurrency = measureAnimationConcurrency(slidePlan);
    if (concurrency.peakItems > maxConcurrent) {
      errors.push(`Slide ${slidePlan.slide} animates ${concurrency.peakItems} items together across overlapping stages; reduce it to at most ${maxConcurrent}.`);
    }
    if (concurrency.peakWipes > maxConcurrentWipe) {
      errors.push(`Slide ${slidePlan.slide} uses ${concurrency.peakWipes} simultaneous wipe effects across overlapping stages; reduce it to at most ${maxConcurrentWipe}.`);
    }
    for (const [stageIndex, stage] of animatedStages.entries()) {
      const items = stage.items || [];
      const wipeItems = items.filter((item) => item.effect === "wipe");
      for (const item of wipeItems) {
        const area = Math.max(0, Number(item.width) || 0) * Math.max(0, Number(item.height) || 0);
        const slideArea = Math.max(1, Number(inspection.slideSize?.width) || 1) * Math.max(1, Number(inspection.slideSize?.height) || 1);
        if (area / slideArea > maxLargeWipeAreaRatio) {
          errors.push(`Slide ${slidePlan.slide} shape ${item.shapeId} uses wipe over ${Math.round(area / slideArea * 100)}% of the slide; use fade or keep it static.`);
        }
      }
    }
    const used = new Set();
    const animatedShapeIds = new Set();
    const initialShapeIds = new Set();
    const visibleBeforeStage = new Set();
    for (const [stageIndex, stage] of (slidePlan.stages || []).entries()) {
      if (!["initial", "after_previous", "with_previous", "on_click"].includes(stage.trigger)) {
        errors.push(`Slide ${slidePlan.slide} stage ${stageIndex + 1} has invalid trigger ${stage.trigger}.`);
      }
      const stageShapeIds = new Set();
      for (const item of stage.items || []) {
        const element = elementById.get(item.shapeId);
        if (!element) {
          errors.push(`Slide ${slidePlan.slide} targets missing shape ${item.shapeId}.`);
          continue;
        }
        if (element.role === "mask" && item.effect !== "fade-out") {
          errors.push(`Slide ${slidePlan.slide} foreground mask ${item.shapeId} may only use the protected fade-out reveal effect.`);
        }
        stageShapeIds.add(item.shapeId);
        const key = `${item.shapeId}:${Number.isInteger(item.paragraphIndex) ? item.paragraphIndex : "all"}`;
        if (used.has(key)) errors.push(`Slide ${slidePlan.slide} repeats animation target ${key}.`);
        if (Number.isInteger(item.paragraphIndex)) {
          if (item.paragraphIndex < 0 || item.paragraphIndex >= (element.paragraphs || []).length
            || !String(element.paragraphs[item.paragraphIndex] || "").trim()) {
            errors.push(`Slide ${slidePlan.slide} targets invalid or empty paragraph ${key}.`);
          }
          if (used.has(`${item.shapeId}:all`)) errors.push(`Slide ${slidePlan.slide} mixes whole-shape and paragraph targets for ${item.shapeId}.`);
        } else if ([...used].some((entry) => entry.startsWith(`${item.shapeId}:`))) {
          errors.push(`Slide ${slidePlan.slide} mixes whole-shape and paragraph targets for ${item.shapeId}.`);
        }
        used.add(key);
        if (stage.trigger === "initial") initialShapeIds.add(item.shapeId);
        else animatedShapeIds.add(item.shapeId);
      }
      const classroomClickRoles = new Set(["question", "task", "discussion", "evidence", "answer", "conclusion", "teacher-cue"]);
      if (stage.trigger === "on_click" && plan.interactionMode !== "classroom-controlled"
        && stage.semanticRole && stage.semanticRole !== "answer") {
        errors.push(`Slide ${slidePlan.slide} stage ${stageIndex + 1} has non-answer click semantics.`);
      }
      if (stage.trigger === "on_click" && plan.interactionMode === "classroom-controlled"
        && !classroomClickRoles.has(stage.semanticRole)) {
        errors.push(`Slide ${slidePlan.slide} stage ${stageIndex + 1} has unsupported classroom click semantics ${stage.semanticRole}.`);
      }
      if (stage.trigger === "on_click" && !String(stage.rationale || "").trim()) {
        errors.push(`Slide ${slidePlan.slide} stage ${stageIndex + 1} has no model rationale for answer reveal.`);
      }
      for (const shapeId of stageShapeIds) {
        const element = elementById.get(shapeId);
        if (element?.containerId != null && !stageShapeIds.has(element.containerId) && !visibleBeforeStage.has(element.containerId)) {
          errors.push(`Slide ${slidePlan.slide} shape ${shapeId} is separated from its visual container ${element.containerId}.`);
        }
      }
      for (const shapeId of stageShapeIds) visibleBeforeStage.add(shapeId);
    }
    if (plan.strictCoverage) {
      const explicitStatic = new Set((slidePlan.unanimated || []).map((item) => item.shapeId));
      const required = sourceSlide.elements.filter((element) => !["background", "decoration", "repeat", "page-number", "mask"].includes(element.role));
      for (const element of required) {
        if (!animatedShapeIds.has(element.id) && !initialShapeIds.has(element.id) && !explicitStatic.has(element.id)) {
          errors.push(`Slide ${slidePlan.slide} leaves animatable shape ${element.id} (${element.role}) uncovered.`);
        }
      }
      const stagedParagraphs = new Set((slidePlan.stages || []).flatMap((stage) => (stage.items || [])
        .filter((item) => Number.isInteger(item.paragraphIndex)).map((item) => item.shapeId)));
      for (const element of required.filter((entry) => stagedParagraphs.has(entry.id))) {
        (element.paragraphs || []).forEach((text, index) => {
          if (text && !used.has(`${element.id}:${index}`) && !explicitStatic.has(element.id)) {
            errors.push(`Slide ${slidePlan.slide} leaves paragraph ${element.id}:${index} uncovered.`);
          }
        });
      }
    }
    const duplicates = new Map();
    for (const element of sourceSlide.elements.filter((entry) => entry.duplicateGroupId != null)) {
      const signature = (slidePlan.stages || []).flatMap((stage, index) => (stage.items || [])
        .filter((item) => item.shapeId === element.id)
        .map((item) => [index, item.paragraphIndex ?? "all", item.effect, item.durationMs]));
      const encoded = JSON.stringify(signature);
      if (duplicates.has(element.duplicateGroupId) && duplicates.get(element.duplicateGroupId) !== encoded) {
        errors.push(`Slide ${slidePlan.slide} separates overlapping duplicate shape ${element.id} from its visual module.`);
      }
      duplicates.set(element.duplicateGroupId, encoded);
    }
    const teachingReview = reviewTeachingSequence(sourceSlide, slidePlan, inspection.slideSize, plan.interactionMode);
    errors.push(...teachingReview.errors);
    warnings.push(...teachingReview.warnings);
  }
  return { valid: errors.length === 0, errors, warnings };
}

export async function applyPlan(inputPath, plan, outputPath, existingPolicy = "preserve") {
  const absoluteInput = path.resolve(inputPath);
  if (await sha256(absoluteInput) !== plan.source.sha256) {
    throw new Error("The source file has changed since the plan was generated. Create a new plan before applying animations.");
  }
  if (!["preserve", "skip", "replace"].includes(existingPolicy)) throw new Error(`Unknown existing-animation policy: ${existingPolicy}`);
  const inspection = await inspectPresentation(absoluteInput);
  const planValidation = validateExecutablePlan(plan, inspection, existingPolicy);
  if (!planValidation.valid) throw new Error(`Invalid executable animation plan:\n- ${planValidation.errors.join("\n- ")}`);
  const tempDir = await extractPptx(absoluteInput);
  const results = [];
  try {
    for (const slidePlan of plan.slides) {
      const sourceSlide = inspection.slides.find((slide) => slide.slide === slidePlan.slide);
      const slidePath = path.join(tempDir, "ppt", "slides", sourceSlide.file);
      let xml = await fs.readFile(slidePath, "utf8");
      const meaningful = hasMeaningfulTiming(xml);
      const protectedMedia = hasProtectedMediaTiming(xml);
      const modelReplaces = slidePlan.disposition === "replace";
      if (slidePlan.disposition === "preserve") {
        results.push({ slide: slidePlan.slide, status: protectedMedia ? "preserved-protected-media" : "preserved-existing-animation" });
        continue;
      }
      if (meaningful && existingPolicy !== "replace" && !modelReplaces) {
        results.push({ slide: slidePlan.slide, status: "skipped-existing-animation" });
        continue;
      }
      if (meaningful && protectedMedia && modelReplaces) {
        results.push({ slide: slidePlan.slide, status: "skipped-protected-mixed-media" });
        continue;
      }
      // Replacement also applies to transition-only pages. Clear every timing
      // branch, including compatibility alternatives, before writing the plan.
      xml = removeTiming(xml);
      xml = applySlideTransition(xml, slidePlan.transition?.type);
      const timing = buildTimingXml(slidePlan);
      if (!timing) {
        await fs.writeFile(slidePath, xml, "utf8");
        const plannedStages = slidePlan.stages?.length || 0;
        const initialVisibleStages = (slidePlan.stages || []).filter((stage) => stage.trigger === "initial").length;
        const reason = plannedStages > 0 && initialVisibleStages === plannedStages
          ? "all-planned-content-was-initial"
          : "no-animated-stages";
        results.push({
          slide: slidePlan.slide,
          status: slidePlan.transition?.type ? "transition-only" : "no-animation-needed",
          reason,
          plannedStages,
          animatedStages: 0,
        });
        continue;
      }
      xml = insertBeforeSlideEnd(xml, timing);
      await fs.writeFile(slidePath, xml, "utf8");
      results.push({ slide: slidePlan.slide, status: protectedMedia ? "animated-preserved-media" : meaningful ? "replaced" : "animated" });
    }
    const output = await packPptx(tempDir, outputPath);
    return { output, results, summary: summarizeExecutablePlan(plan, results), planValidation };
  } finally {
    await cleanupTemp(tempDir);
  }
}

export async function validatePresentation(filePath) {
  const absolute = path.resolve(filePath);
  await execFileAsync("unzip", ["-tqq", absolute]);
  const tempDir = await extractPptx(absolute);
  const errors = [];
  const warnings = [];
  try {
    const slideDir = path.join(tempDir, "ppt", "slides");
    const names = (await fs.readdir(slideDir)).filter((name) => /\.xml$/.test(name));
    const presentationXml = await fs.readFile(path.join(tempDir, "ppt", "presentation.xml"), "utf8");
    let orderedSlides = [];
    try { orderedSlides = await presentationSlideOrder(tempDir, presentationXml); }
    catch (error) { errors.push(error.message); }
    for (const name of names) {
      const xml = await fs.readFile(path.join(slideDir, name), "utf8");
      const shapeIds = new Set([...xml.matchAll(/<p:cNvPr\s+[^>]*id="(\d+)"/g)].map((m) => Number(m[1])));
      const targets = [...xml.matchAll(/<p:spTgt\b[^>]*\bspid="(\d+)"/g)].map((m) => Number(m[1]));
      for (const target of targets) if (!shapeIds.has(target)) errors.push(`${name}: animation target ${target} does not exist`);
      const timing = xml.match(/<p:timing(?:\s[^>]*)?>[\s\S]*?<\/p:timing>/)?.[0];
      if (timing) {
        const timingIndex = xml.indexOf(timing);
        const cSldEnd = xml.lastIndexOf("</p:cSld>");
        if (timingIndex < cSldEnd) errors.push(`${name}: timing is nested inside slide content instead of being a slide-level element`);
        const hasVisualAnimation = /<p:(?:animEffect|animMotion|anim|set)(?:\s|>)/.test(timing);
        if (hasVisualAnimation && !/<p:cTn\s+[^>]*nodeType="mainSeq"/.test(timing)) {
          errors.push(`${name}: targeted animation timing has no main sequence`);
        }
        const ids = [...timing.matchAll(/<p:cTn\s+[^>]*id="(\d+)"/g)].map((m) => Number(m[1]));
        const duplicate = ids.find((value, index) => ids.indexOf(value) !== index);
        if (duplicate != null) errors.push(`${name}: duplicate timing node id ${duplicate}`);
      }
    }
    if (!names.length) errors.push("No slide XML files found");
    const schemaValidation = await validateOpenXmlSchema(absolute);
    errors.push(...schemaValidation.errors);
    return { valid: errors.length === 0, file: absolute, slideCount: orderedSlides.length, errors, warnings };
  } finally {
    await cleanupTemp(tempDir);
  }
}

export function stripAnimationParts(xml) {
  return xml
    .replace(/<p:timing(?:\s[^>]*)?>[\s\S]*?<\/p:timing>/g, "")
    .replace(/<p:transition(?:\s[^>]*)?>[\s\S]*?<\/p:transition>/g, "")
    .replace(/<p:transition(?:\s[^>]*)?\/>/g, "");
}

function slideShapeTree(xml) {
  return xml.match(/<p:spTree(?:\s[^>]*)?>[\s\S]*?<\/p:spTree>/)?.[0] ?? "";
}

function slideTiming(xml) {
  return [...xml.matchAll(/<p:timing(?:\s[^>]*)?>[\s\S]*?<\/p:timing>/g)]
    .map((match) => match[0]).join("");
}

async function collectPackageHashes(rootDir, relativeDir = "", output = new Map()) {
  const absoluteDir = path.join(rootDir, relativeDir);
  for (const entry of await fs.readdir(absoluteDir, { withFileTypes: true })) {
    const relativePath = path.posix.join(relativeDir.split(path.sep).join(path.posix.sep), entry.name);
    if (entry.isDirectory()) {
      await collectPackageHashes(rootDir, relativePath, output);
    } else if (!/^ppt\/slides\/[^/]+\.xml$/.test(relativePath)) {
      output.set(relativePath, await sha256(path.join(rootDir, relativePath)));
    }
  }
  return output;
}

function timingTargetIds(xml) {
  const timing = slideTiming(xml);
  return new Set([...timing.matchAll(/<p:spTgt\b[^>]*\bspid="(\d+)"/g)].map((match) => Number(match[1])));
}

/**
 * Fast, zero-preview source/output guard used on every apply. It checks only
 * immutable package parts and slide content, leaving semantic coverage and
 * playback diagnosis to the opt-in full auditor.
 */
export async function validateStructuralIntegrity(sourcePath, outputPath) {
  const source = path.resolve(sourcePath);
  const output = path.resolve(outputPath);
  const errors = [];
  const sourceDir = await extractPptx(source);
  const outputDir = await extractPptx(output);
  try {
    const [sourceFiles, outputFiles] = await Promise.all([
      collectPackageHashes(sourceDir),
      collectPackageHashes(outputDir),
    ]);
    for (const packagePath of new Set([...sourceFiles.keys(), ...outputFiles.keys()])) {
      if (!sourceFiles.has(packagePath)) errors.push(`Unexpected package part added: ${packagePath}`);
      else if (!outputFiles.has(packagePath)) errors.push(`Source package part missing: ${packagePath}`);
      else if (sourceFiles.get(packagePath) !== outputFiles.get(packagePath)) {
        errors.push(`Non-slide package part changed: ${packagePath}`);
      }
    }
    const slideDir = path.join(sourceDir, "ppt", "slides");
    const sourceSlides = (await fs.readdir(slideDir)).filter((name) => /\.xml$/.test(name)).sort();
    const outputSlides = (await fs.readdir(path.join(outputDir, "ppt", "slides")))
      .filter((name) => /\.xml$/.test(name)).sort();
    if (sourceSlides.join("\n") !== outputSlides.join("\n")) errors.push("Slide XML file set changed.");
    for (const name of sourceSlides.filter((candidate) => outputSlides.includes(candidate))) {
      const [sourceXml, outputXml] = await Promise.all([
        fs.readFile(path.join(sourceDir, "ppt", "slides", name), "utf8"),
        fs.readFile(path.join(outputDir, "ppt", "slides", name), "utf8"),
      ]);
      if (stripAnimationParts(sourceXml) !== stripAnimationParts(outputXml)) {
        errors.push(`${name}: content changed outside animation or transition XML.`);
      }
      if (slideShapeTree(sourceXml) !== slideShapeTree(outputXml)) {
        errors.push(`${name}: shape order, geometry, grouping, or styling changed.`);
      }
    }
    return { valid: errors.length === 0, source, output, slideCount: sourceSlides.length, errors };
  } finally {
    await Promise.all([cleanupTemp(sourceDir), cleanupTemp(outputDir)]);
  }
}

/** Compare a finished file with the actual customer source, even after a repair copy was used. */
export async function auditOriginalMediaPreservation(originalPath, outputPath) {
  const original = path.resolve(originalPath);
  const output = path.resolve(outputPath);
  const errors = [];
  const protectedSlides = [];
  const originalDir = await extractPptx(original);
  const outputDir = await extractPptx(output);
  try {
    const originalMedia = path.join(originalDir, "ppt", "media");
    const outputMedia = path.join(outputDir, "ppt", "media");
    const mediaNames = await fs.readdir(originalMedia).catch(() => []);
    const finishedNames = await fs.readdir(outputMedia).catch(() => []);
    if (mediaNames.sort().join("\n") !== finishedNames.sort().join("\n")) {
      errors.push("Media files differ from the original PowerPoint.");
    }
    for (const name of mediaNames.filter((item) => finishedNames.includes(item))) {
      if (await sha256(path.join(originalMedia, name)) !== await sha256(path.join(outputMedia, name))) {
        errors.push(`Original media file changed: ${name}`);
      }
    }
    const slideDir = path.join(originalDir, "ppt", "slides");
    const originalPresentation = await fs.readFile(path.join(originalDir, "ppt", "presentation.xml"), "utf8");
    for (const { slide, file: name } of await presentationSlideOrder(originalDir, originalPresentation)) {
      const sourceXml = await fs.readFile(path.join(slideDir, name), "utf8");
      if (!hasProtectedMediaTiming(sourceXml)) continue;
      protectedSlides.push(slide);
      const finishedXml = await fs.readFile(path.join(outputDir, "ppt", "slides", name), "utf8").catch(() => "");
      if (slideTiming(sourceXml) !== slideTiming(finishedXml)) {
        errors.push(`Slide ${slide} video/audio playback timeline differs from the original.`);
      }
      const rel = path.join("ppt", "slides", "_rels", `${name}.rels`);
      const originalRels = await fs.readFile(path.join(originalDir, rel), "utf8").catch(() => "");
      const finishedRels = await fs.readFile(path.join(outputDir, rel), "utf8").catch(() => "");
      if (originalRels !== finishedRels) errors.push(`Slide ${slide} media relationships differ from the original.`);
    }
    return { valid: errors.length === 0, original, output, protectedSlides, errors };
  } finally {
    await Promise.all([cleanupTemp(originalDir), cleanupTemp(outputDir)]);
  }
}

/**
 * Audit a generated deck against its source and executable plan. This checks
 * package preservation, unchanged slide content, animation target coverage and
 * structural OOXML validity without opening PowerPoint.
 */
export async function auditAnimationResult(sourcePath, outputPath, plan, existingPolicy = "preserve") {
  const source = path.resolve(sourcePath);
  const output = path.resolve(outputPath);
  const errors = [];
  const warnings = [];
  if (plan?.planningMode === "model-v3-strategy-delta") {
    if (plan.planningEvidence?.workflow !== "model-authored-with-teaching-cues") {
      errors.push("The model plan has no saved teaching-cue provenance.");
    } else {
      for (const evidence of [plan.planningEvidence.modelPlan, plan.planningEvidence.teachingCues]) {
        if (!evidence?.path || await sha256(evidence.path).catch(() => null) !== evidence.sha256) {
          errors.push("Saved model plan or teaching cues are missing or changed since compilation.");
        }
      }
    }
  } else {
    warnings.push("This is a deterministic test plan; no model-authored teaching sequence is proven.");
  }
  const validation = await validatePresentation(output);
  errors.push(...validation.errors);
  warnings.push(...validation.warnings);
  if (!['preserve', 'skip', 'replace'].includes(existingPolicy)) {
    errors.push(`Unknown existing-animation policy: ${existingPolicy}`);
  }
  const sourceInspection = await inspectPresentation(source);
  if (sourceInspection.source.sha256 !== plan?.source?.sha256) {
    errors.push("The plan source hash does not match the audited source file.");
  }
  const planValidation = validateExecutablePlan(plan, sourceInspection, existingPolicy);
  errors.push(...planValidation.errors);
  warnings.push(...planValidation.warnings);
  for (const slidePlan of plan.slides || []) {
    for (const warning of slidePlan.warnings || []) warnings.push(`Slide ${slidePlan.slide}: ${warning}`);
  }

  const sourceDir = await extractPptx(source);
  const outputDir = await extractPptx(output);
  const slideReports = [];
  try {
    const sourceFiles = await collectPackageHashes(sourceDir);
    const outputFiles = await collectPackageHashes(outputDir);
    const packagePaths = new Set([...sourceFiles.keys(), ...outputFiles.keys()]);
    for (const packagePath of packagePaths) {
      if (!sourceFiles.has(packagePath)) errors.push(`Unexpected package part added: ${packagePath}`);
      else if (!outputFiles.has(packagePath)) errors.push(`Source package part missing: ${packagePath}`);
      else if (sourceFiles.get(packagePath) !== outputFiles.get(packagePath)) {
        errors.push(`Non-slide package part changed: ${packagePath}`);
      }
    }

    const sourceSlides = new Map(sourceInspection.slides.map((slide) => [slide.slide, slide]));
    for (const slidePlan of plan.slides || []) {
      const slideNo = slidePlan.slide;
      const sourceSlide = sourceSlides.get(slideNo);
      const sourceXmlPath = path.join(sourceDir, "ppt", "slides", sourceSlide.file);
      const outputXmlPath = path.join(outputDir, "ppt", "slides", sourceSlide.file);
      const [sourceXml, outputXml] = await Promise.all([
        fs.readFile(sourceXmlPath, "utf8"),
        fs.readFile(outputXmlPath, "utf8"),
      ]);
      if (stripAnimationParts(sourceXml) !== stripAnimationParts(outputXml)) {
        errors.push(`Slide ${slideNo} content changed outside animation or transition XML.`);
      }
      if (slideShapeTree(sourceXml) !== slideShapeTree(outputXml)) {
        errors.push(`Slide ${slideNo} shape order, geometry, grouping, or styling changed.`);
      }
      const modelReplaces = slidePlan.disposition === "replace";
      const preservedByPlan = slidePlan.disposition === "preserve";
      const skippedExisting = sourceSlide?.existingAnimation && existingPolicy !== "replace" && !modelReplaces;
      const skippedMixedMedia = sourceSlide?.existingAnimation && sourceSlide?.protectedMediaTiming && modelReplaces;
      const expectedIds = new Set((slidePlan.stages || [])
        .filter((stage) => stage.trigger !== "initial")
        .flatMap((stage) => stage.items || [])
        .map((item) => item.shapeId));
      const actualIds = timingTargetIds(outputXml);
      if ((preservedByPlan || skippedExisting) && slideTiming(sourceXml) !== slideTiming(outputXml)) {
        errors.push(`Slide ${slideNo} existing animation timing changed under preserve policy.`);
      }
      const timingMatchesPlan = preservedByPlan || skippedExisting || skippedMixedMedia
        || slideTiming(outputXml) === buildTimingXml(slidePlan);
      if (!timingMatchesPlan) {
        errors.push(`Slide ${slideNo} animation timing or click order differs from the executable plan.`);
      }
      const missingIds = preservedByPlan || skippedExisting || skippedMixedMedia
        ? [] : [...expectedIds].filter((shapeId) => !actualIds.has(shapeId));
      const extraIds = preservedByPlan || skippedExisting || skippedMixedMedia
        ? [] : [...actualIds].filter((shapeId) => !expectedIds.has(shapeId));
      const teachingReview = preservedByPlan || skippedExisting || skippedMixedMedia
        ? { errors: [], warnings: [] }
        : reviewTeachingSequence(sourceSlide, slidePlan, sourceInspection.slideSize, plan.interactionMode);
      const playbackStates = preservedByPlan || skippedExisting || skippedMixedMedia
        ? [] : simulateTeachingStates(sourceSlide, slidePlan).clickStates.map((state) => ({
          click: state.clickIndex,
          visibleShapeIds: state.visibleShapeIds,
          fullyVisibleShapeIds: state.fullyVisibleShapeIds,
          visibleParagraphs: state.visibleParagraphs,
        }));
      for (const shapeId of missingIds) errors.push(`Slide ${slideNo} is missing planned animation target ${shapeId}.`);
      for (const shapeId of extraIds) errors.push(`Slide ${slideNo} retains unplanned animation target ${shapeId}.`);
      const status = preservedByPlan ? "preserved-by-plan"
        : skippedExisting ? "preserved-existing"
        : skippedMixedMedia ? "preserved-mixed-media"
          : missingIds.length || extraIds.length || !timingMatchesPlan ? "incomplete"
            : teachingReview.errors.length ? "teaching-sequence-issue" : "covered";
      slideReports.push({
        slide: slideNo,
        status,
        expectedTargets: expectedIds.size,
        actualTargets: actualIds.size,
        missingTargets: missingIds,
        extraTargets: extraIds,
        timingMatchesPlan,
        teachingErrors: teachingReview.errors,
        teachingWarnings: teachingReview.warnings,
        playbackStates,
      });
    }
  } finally {
    await Promise.all([cleanupTemp(sourceDir), cleanupTemp(outputDir)]);
  }
  return {
    valid: errors.length === 0,
    source,
    output,
    existingPolicy,
    slideCount: validation.slideCount,
    packageValidation: validation,
    slides: slideReports,
    errors: [...new Set(errors)],
    warnings: [...new Set(warnings)],
  };
}
