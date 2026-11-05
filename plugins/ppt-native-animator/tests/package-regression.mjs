import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import {
  ANALYSIS_REVISION, buildIncrementalPlanningBundle, buildModelBrief, createModelPlanTemplate,
  extractPptx, inspectPresentation, measureAnimationConcurrency, mergeModelPlanPatch,
  packPptx, parseSlideElements, sha256, simulateTeachingStates, validateExecutablePlan,
} from "../scripts/lib/core.mjs";

const exec = promisify(execFile);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const work = await fs.mkdtemp(path.join(os.tmpdir(), "ppt-package-regression-"));
const size = { width: 12192000, height: 6858000 };
const element = (id) => ({ id, type: "shape", role: "body", text: "", paragraphs: [],
  zIndex: id, x: id * 400000, y: 1500000, width: 200000, height: 200000 });
const stages = (effect = "fade") => [
  { id: "one", trigger: "after_previous", staggerMs: 0, delayMs: 0,
    items: [10, 11, 12, 13].map((id) => ({ ...element(id), shapeId: id, effect, durationMs: 400 })) },
  { id: "two", trigger: "with_previous", staggerMs: 0, delayMs: 0,
    items: [14, 15, 16, 17].map((id) => ({ ...element(id), shapeId: id, effect, durationMs: 400 })) },
];

try {
  // Real intervals, including cross-stage overlaps, stagger and click boundaries.
  const simultaneous = { slide: 1, stages: stages(), unanimated: [] };
  assert.deepEqual(measureAnimationConcurrency(simultaneous), { peakItems: 8, peakWipes: 0 });
  const performanceInspection = { slideSize: size, slides: [{ slide: 1, elements: Array.from({ length: 8 }, (_, i) => element(10 + i)) }] };
  const performancePlan = { interactionMode: "classroom-controlled", strictCoverage: true,
    performanceBudget: { maxAnimatedTargetsPerSlide: 12, maxConcurrentItemsPerStage: 5, maxConcurrentWipeItems: 2 },
    slides: [simultaneous] };
  assert.equal(validateExecutablePlan(performancePlan, performanceInspection).valid, false);
  const sequential = structuredClone(simultaneous);
  sequential.stages[1].trigger = "after_previous";
  assert.equal(measureAnimationConcurrency(sequential).peakItems, 4);
  assert.equal(validateExecutablePlan({ ...performancePlan, slides: [sequential] }, performanceInspection).valid, true);
  const wipe = { ...simultaneous, stages: stages("wipe") };
  assert.equal(measureAnimationConcurrency(wipe).peakWipes, 8);
  assert.ok(validateExecutablePlan({ ...performancePlan, slides: [wipe] }, performanceInspection).errors
    .some((error) => error.includes("simultaneous wipe effects")));
  const staggered = structuredClone(simultaneous);
  staggered.stages = [{ ...staggered.stages[0], staggerMs: 100,
    items: staggered.stages.flatMap((stage) => stage.items) }];
  assert.equal(measureAnimationConcurrency(staggered).peakItems, 4);
  assert.equal(validateExecutablePlan({ ...performancePlan, slides: [staggered] }, performanceInspection).valid, true);

  // Keep punctuation-sensitive text distinct, including comparisons in maths.
  const comparison = (id, text) => `<p:sp><p:nvSpPr><p:cNvPr id="${id}" name="Text"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="1500000"/><a:ext cx="4000000" cy="1000000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>${text}</a:t></a:r></a:p></p:txBody></p:sp>`;
  const parsed = parseSlideElements(`<p:sld><p:cSld><p:spTree>${comparison(5, "可以？")}${comparison(6, "可以。")}</p:spTree></p:cSld></p:sld>`, size);
  assert.equal(parsed.length, 2);
  assert.equal(parsed.some((entry) => entry.duplicateGroupId != null), false);

  // OfficeCLI creates a valid package with empty paragraphs and duplicated answers.
  const seed = path.join(work, "seed.pptx");
  const office = async (...args) => (await exec("officecli", args, { timeout: 60000, maxBuffer: 1024 * 1024 })).stdout;
  await office("create", seed);
  await office("add", seed, "/", "--type", "slide", "--prop", "layout=blank");
  await office("add", seed, "/slide[1]", "--type", "shape", "--prop", "id=5", "--prop", "name=Mixed",
    "--prop", "text=\\n1+1等于多少？\\n\\n答案：2", "--prop", "x=2cm", "--prop", "y=4cm",
    "--prop", "width=20cm", "--prop", "height=8cm", "--prop", "size=24", "--prop", "fill=none");
  await office("get", seed, "/slide[1]", "--depth", "1");
  await office("add", seed, "/", "--type", "slide", "--prop", "layout=blank");
  for (const [id, name, text, y] of [[6, "Q_question", "1+1等于多少？", "4cm"],
    [7, "A_answer", "答案：2", "8cm"], [8, "A_duplicate", "答案：2", "8cm"]]) {
    await office("add", seed, "/slide[2]", "--type", "shape", "--prop", `id=${id}`, "--prop", `name=${name}`,
      "--prop", `text=${text}`, "--prop", "x=2cm", "--prop", `y=${y}`, "--prop", "width=20cm",
      "--prop", "height=2cm", "--prop", "size=24", "--prop", "fill=none");
  }
  await office("get", seed, "/slide[2]", "--depth", "1");
  await office("save", seed);
  await office("close", seed);
  const directory = await extractPptx(seed);
  // Real slide order is 2,1; also exercise a non-numeric internal part name.
  const presentationPath = path.join(directory, "ppt", "presentation.xml");
  const originalPresentation = await fs.readFile(presentationPath, "utf8");
  const idTags = originalPresentation.match(/<p:sldId\b[^>]*\/>/g);
  assert.equal(idTags.length, 2);
  await fs.writeFile(presentationPath, originalPresentation.replace(idTags.join(""), [...idTags].reverse().join("")));
  await fs.rename(path.join(directory, "ppt", "slides", "slide1.xml"), path.join(directory, "ppt", "slides", "question-page.xml"));
  const oldRel = path.join(directory, "ppt", "slides", "_rels", "slide1.xml.rels");
  if (await fs.access(oldRel).then(() => true, () => false)) {
    await fs.rename(oldRel, path.join(directory, "ppt", "slides", "_rels", "question-page.xml.rels"));
  }
  for (const relative of ["ppt/_rels/presentation.xml.rels", "[Content_Types].xml"]) {
    const target = path.join(directory, relative);
    const xml = await fs.readFile(target, "utf8");
    await fs.writeFile(target, xml.replaceAll("slides/slide1.xml", "slides/question-page.xml"));
  }
  const input = path.join(work, "source.pptx");
  await packPptx(directory, input);
  await fs.rm(directory, { recursive: true, force: true });
  await office("validate", input);
  const sourceHash = await sha256(input);
  const inspection = await inspectPresentation(input);
  assert.deepEqual(inspection.slides.map((slide) => slide.file), ["slide2.xml", "question-page.xml"]);
  assert.deepEqual(inspection.slides.map((slide) => slide.slide), [1, 2]);
  assert.equal(inspection.analysisRevision, ANALYSIS_REVISION);
  const brief = buildModelBrief(inspection);
  const plan = createModelPlanTemplate(brief);
  plan.targetApplication = "wps";
  plan.deckStrategy = { rationale: "测试题目先显示，教师点击揭示答案。", effectFamilies: ["fade"],
    defaultEffect: "fade", defaultDurationMs: 400, defaultStaggerMs: 0, defaultDelayMs: 0,
    defaultGranularity: "shape", defaultTransition: "fade" };
  const question = brief.slides[0].modules.find((module) => module.memberIds.includes(6));
  const answers = brief.slides[0].modules.find((module) => module.memberIds.includes(7));
  assert.deepEqual(answers.memberIds, [7, 8]);
  const mixed = brief.slides[1].modules.find((module) => module.memberIds.includes(5));
  assert.deepEqual(mixed.paragraphs.map((paragraph) => paragraph.paragraphIndex), [1, 3]);
  plan.slides = [
    { slide: 1, stages: [
      { id: "question", trigger: "after_previous", contentRole: "question", moduleIds: [question.moduleId] },
      { id: "answer", trigger: "on_click", contentRole: "answer", moduleIds: [answers.moduleId],
        rationale: "两个重叠答案必须在教师点击后同步出现。", answersQuestionStageId: "question" },
    ] },
    { slide: 2, stages: [
      { id: "question", trigger: "after_previous", contentRole: "question", granularity: "paragraph", paragraphIds: [mixed.paragraphs[0].paragraphId] },
      { id: "answer", trigger: "on_click", contentRole: "answer", granularity: "paragraph", paragraphIds: [mixed.paragraphs[1].paragraphId],
        rationale: "题目可见后教师点击揭示同一文本框内的答案段落。", answersQuestionStageId: "question" },
    ] },
  ];
  const cues = { contract: "ppt-native-animation-teaching-cues", source: { sha256: sourceHash },
    slides: [1, 2].map((slide) => ({ slide, purpose: "学生先读题独立思考，教师点击后揭示答案。",
      teacherClickBeats: [{ stageId: "answer", reason: "待学生作答后展示答案。" }], keepStatic: [] })) };
  const modelPath = path.join(work, "model.json");
  const cuesPath = path.join(work, "cues.json");
  const structurePath = path.join(work, "structure.json");
  const executablePath = path.join(work, "executable.json");
  await Promise.all([[modelPath, plan], [cuesPath, cues], [structurePath, inspection]].map(([file, value]) => fs.writeFile(file, JSON.stringify(value))));
  const runScript = async (name, args) => {
    const result = await exec(process.execPath, [path.join(root, "scripts", name), ...args], { timeout: 120000, maxBuffer: 4 * 1024 * 1024 });
    return JSON.parse(result.stdout);
  };
  const compiled = await runScript("compile-model-plan.mjs", [input, modelPath, "--analysis", structurePath,
    "--teaching-cues", cuesPath, "--output", executablePath]);
  assert.equal(compiled.summary.animatedStages, 4);
  const executable = JSON.parse(await fs.readFile(executablePath, "utf8"));
  const duplicateStates = simulateTeachingStates(inspection.slides[0], executable.slides[0]);
  assert.ok(!duplicateStates.clickStates[0].visibleShapeIds.includes(7)
    && !duplicateStates.clickStates[0].visibleShapeIds.includes(8));
  assert.ok(duplicateStates.clickStates[1].visibleShapeIds.includes(7)
    && duplicateStates.clickStates[1].visibleShapeIds.includes(8));
  const splitDuplicate = structuredClone(executable);
  const sibling = splitDuplicate.slides[0].stages[1].items.pop();
  splitDuplicate.slides[0].stages.push({ ...splitDuplicate.slides[0].stages[1], id: "late-sibling", items: [sibling] });
  assert.ok(validateExecutablePlan(splitDuplicate, inspection, "replace").errors
    .some((error) => error.includes("overlapping duplicate")));
  const mixedStates = simulateTeachingStates(inspection.slides[1], executable.slides[1]);
  assert.deepEqual(mixedStates.clickStates.map((state) => state.visibleParagraphs.map((entry) => entry.paragraphIndex)), [[1], [1, 3]]);
  const output = path.join(work, "animated.pptx");
  const applied = await runScript("apply-animation-plan.mjs", [input, executablePath, "--original-source", input, "--output", output]);
  assert.equal(applied.published, true);
  assert.equal(applied.audit.valid, true);
  assert.equal(await sha256(input), sourceHash);
  const manifest = JSON.parse(await fs.readFile(applied.manifest, "utf8"));
  assert.equal(manifest.playbackStatus, "not-verified-in-presentation-app");
  const packaged = await extractPptx(output);
  // Inspect actual targets independently of the writer's expected-XML generator.
  const mixedXml = await fs.readFile(path.join(packaged, "ppt", "slides", "question-page.xml"), "utf8");
  assert.deepEqual([...mixedXml.matchAll(/<p:pRg st="(\d+)" end="\d+"\/>/g)].map((match) => Number(match[1])), [1, 1, 3, 3]);
  const duplicateXml = await fs.readFile(path.join(packaged, "ppt", "slides", "slide2.xml"), "utf8");
  assert.ok(/spid="7"/.test(duplicateXml) && /spid="8"/.test(duplicateXml));
  // A wrong-but-schema-valid paragraph target must fail the independent audit.
  await fs.writeFile(path.join(packaged, "ppt", "slides", "question-page.xml"), mixedXml.replaceAll('st="3" end="3"', 'st="0" end="0"'));
  const tampered = path.join(work, "tampered.pptx");
  await packPptx(packaged, tampered);
  await fs.rm(packaged, { recursive: true, force: true });
  await assert.rejects(runScript("audit-animation-result.mjs", [input, tampered, executablePath, "--original-source", input]));

  const bundle = buildIncrementalPlanningBundle(inspection, inspection, plan);
  assert.equal(bundle.template.targetApplication, "wps");
  assert.equal(mergeModelPlanPatch(inspection, inspection, plan, bundle.template).targetApplication, "wps");
  const strategyChange = structuredClone(bundle.template);
  strategyChange.deckStrategy.defaultDurationMs = 500;
  assert.throws(() => mergeModelPlanPatch(inspection, inspection, plan, strategyChange), /redesign all slides/);
  const crossPagePlan = structuredClone(plan);
  crossPagePlan.slides[1].stages[1].answersQuestionStageId = "previous-slide";
  const changedQuestion = structuredClone(inspection);
  changedQuestion.slides[0].planningFingerprint += "-changed";
  assert.deepEqual(buildIncrementalPlanningBundle(changedQuestion, inspection, crossPagePlan).brief.reuse.changedSlides, [1, 2]);
  console.log("Package regression passed: paragraph reveal, duplicate targets, real page order, WPS inheritance, concurrency and tamper rejection.");
} finally {
  await fs.rm(work, { recursive: true, force: true });
}
