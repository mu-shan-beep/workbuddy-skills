import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  ANALYSIS_REVISION,
  applyPlan,
  buildModelBrief,
  buildIncrementalPlanningBundle,
  buildStages,
  buildTimingXml,
  buildVisualModules,
  createModelPlanTemplate,
  createPlan,
  markRepeatedElements,
  mergeModelPlanPatch,
  parseSlideElements,
  parseExistingAnimationSummary,
  reviewSemanticCoverage,
  reviewTeachingSequence,
  simulateTeachingStates,
  resolveModelPresetId,
  summarizeExecutablePlan,
  stripAnimationParts,
  validateExecutablePlan,
  validateModelPlanShape,
  validateTeachingCues,
  validatePresentation,
} from "../scripts/lib/core.mjs";

assert.equal(resolveModelPresetId({}, { preset: "model-selected" }, { type: "exercise" }), "question-answer");
assert.equal(resolveModelPresetId({}, { preset: "auto-teaching" }, { type: "story" }), "visual-story");
assert.equal(resolveModelPresetId({}, { preset: "minimal" }, { type: "story" }), "minimal");

const slideSize = { width: 12192000, height: 6858000 };
const deckStrategy = {
  rationale: "全套课件使用克制的淡入节奏，答案保留点击揭示。",
  effectFamilies: ["fade"],
  defaultEffect: "fade",
  defaultDurationMs: 420,
  defaultStaggerMs: 90,
  defaultDelayMs: 0,
  defaultGranularity: "shape",
  defaultTransition: "fade",
};
const xml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
<p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="5" name="T_标题"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="300000"/><a:ext cx="5000000" cy="700000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="4200"/><a:t>课堂练习</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="6" name="Q_题目"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="600000" y="1500000"/><a:ext cx="5000000" cy="900000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2800"/><a:t>1+1等于多少？</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="7" name="A_答案"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="600000" y="3000000"/><a:ext cx="5000000" cy="900000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2800"/><a:t>答案：2</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>`;

const elements = parseSlideElements(xml, slideSize);
assert.equal(elements.length, 3);
assert.equal(elements.find((item) => item.id === 5).role, "title");
assert.equal(elements.find((item) => item.id === 6).role, "question");
assert.equal(elements.find((item) => item.id === 7).role, "answer");

const normalizationXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr name="TextBox 10" id="10"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="400000" y="250000"/><a:ext cx="5000000" cy="700000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="3600"/><a:t>赞春与主旨总结</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="TextBox 11" id="11"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="1500000"/><a:ext cx="3000000" cy="500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>重复内容</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="TextBox 12" id="12"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="1500000"/><a:ext cx="3000000" cy="500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>重复内容</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="Freeform 13" id="13"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="6500000" y="1500000"/><a:ext cx="4200000" cy="3200000"/></a:xfrm><a:blipFill><a:blip r:embed="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></a:blipFill></p:spPr></p:sp>
<p:pic><p:nvPicPr><p:cNvPr name="Icon 14" id="14"/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></p:blipFill><p:spPr><a:xfrm><a:off x="500000" y="2600000"/><a:ext cx="450000" cy="450000"/></a:xfrm></p:spPr></p:pic>
<p:sp><p:nvSpPr><p:cNvPr name="TextBox 15" id="15"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="450000" y="3100000"/><a:ext cx="900000" cy="350000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="1600"/><a:t>图标标签</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>`;
const normalizedElements = parseSlideElements(normalizationXml, slideSize);
assert.equal(normalizedElements.filter((item) => item.text === "重复内容").length, 2);
assert.ok(buildVisualModules(normalizedElements, slideSize, 1).modules
  .some((module) => [11, 12].every((id) => module.memberIds.includes(id))));
assert.equal(normalizedElements.find((item) => item.id === 10).role, "title");
assert.equal(normalizedElements.find((item) => item.id === 13).role, "image");
assert.equal(normalizedElements.find((item) => item.id === 14).role, "image");

const thumbnailRowXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr name="Section title" id="20"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="1900000" cy="300000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>行业陷入信任危机</a:t></a:r></a:p></p:txBody></p:sp>
${[21, 22, 23, 24].map((id, index) => `<p:pic><p:nvPicPr><p:cNvPr name="Thumbnail ${id}" id="${id}"/></p:nvPicPr><p:blipFill><a:blip r:embed="rId${id}"/></p:blipFill><p:spPr><a:xfrm><a:off x="${1000000 + index * 1100000}" y="1400000"/><a:ext cx="900000" cy="900000"/></a:xfrm></p:spPr></p:pic>`).join("")}
</p:spTree></p:cSld></p:sld>`;
const thumbnailRow = parseSlideElements(thumbnailRowXml, slideSize);
assert.deepEqual(thumbnailRow.filter((item) => item.id >= 21 && item.id <= 24).map((item) => item.role), ["image", "image", "image", "image"]);

const cardXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr name="Card background" id="30"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="3000000" cy="1000000"/></a:xfrm><a:solidFill><a:srgbClr val="EEE6CB"/></a:solidFill></p:spPr></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="Card text" id="31"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1200000" y="1200000"/><a:ext cx="2500000" cy="500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>卡片文字</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>`;
const cardElements = parseSlideElements(cardXml, slideSize);
assert.equal(cardElements.find((item) => item.id === 30).role, "container");
assert.equal(cardElements.find((item) => item.id === 31).containerId, 30);
assert.ok(cardElements.find((item) => item.id === 30).zIndex < cardElements.find((item) => item.id === 31).zIndex);
const cardStages = buildStages(cardElements, {
  playback: "mixed", answerTrigger: "on_click", paragraphs: true,
  titleInitial: false, questionInitial: false, groupBody: false, maxStages: 4,
  effects: { text: "fade", image: "fade", diagram: "wipe", answer: "fade" },
  timing: { text: 300, image: 450, diagram: 350, answer: 400, delay: 120 },
}).stages;
assert.ok(cardStages.some((stage) => [30, 31].every((id) => stage.items.some((item) => item.shapeId === id))));

const translucentBackdropXml = `<?xml version="1.0"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="51" name="矩形 11"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="0" y="2210650"/><a:ext cx="12192000" cy="4168578"/></a:xfrm><a:blipFill><a:blip><a:alphaModFix amt="30000"/></a:blip></a:blipFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>
<p:sp><p:nvSpPr><p:cNvPr id="52" name="Question"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="900000" y="2700000"/><a:ext cx="6100000" cy="1100000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>读完愚公移山的故事，想一想：面对生活中不平坦的道路和重重困难，我们应该采取什么样的态度，又应当怎样行动？</a:t></a:r></a:p></p:txBody></p:sp>
<p:pic><p:nvPicPr><p:cNvPr id="53" name="愚公插图"/></p:nvPicPr><p:blipFill><a:blip/></p:blipFill><p:spPr><a:xfrm><a:off x="7100000" y="1800000"/><a:ext cx="4500000" cy="4000000"/></a:xfrm></p:spPr></p:pic>
</p:spTree></p:cSld></p:sld>`;
const backdropElements = parseSlideElements(translucentBackdropXml, slideSize);
assert.equal(backdropElements.find((item) => item.id === 51).fillType, 'image');
assert.equal(backdropElements.find((item) => item.id === 51).fillAlpha, 0.3);
assert.equal(backdropElements.find((item) => item.id === 51).role, 'background');
const backdropModules = buildVisualModules(backdropElements, slideSize, 2);
assert.ok(backdropModules.modules.some((module) => module.memberIds.includes(52)));
assert.ok(backdropModules.modules.some((module) => module.memberIds.includes(53)));
assert.ok(!backdropModules.modules.some((module) => module.memberIds.includes(51)));

const visualModules = buildVisualModules(cardElements, slideSize, 3);
assert.equal(visualModules.modules.length, 1);
assert.deepEqual(visualModules.modules[0].memberIds, [30, 31]);
assert.equal(visualModules.modules[0].moduleId, "s3-m1");

const ambiguousCardXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr name="Possible backing" id="32"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="1800000" cy="800000"/></a:xfrm><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill></p:spPr></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="Offset text" id="33"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="2200000" y="1200000"/><a:ext cx="1800000" cy="500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>关系不确定</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>`;
const ambiguousElements = parseSlideElements(ambiguousCardXml, slideSize);
const ambiguousModules = buildVisualModules(ambiguousElements, slideSize, 4);
assert.ok(ambiguousModules.reviewableModules.some((module) => module.memberIds.includes(33)
  && module.reviewReason === "ambiguous-backing-relationship"));
assert.ok(ambiguousModules.reviewableModules.some((module) => [32, 33].every((id) => module.memberIds.includes(id))));
assert.ok(!ambiguousModules.modules.some((module) => module.memberIds.includes(33)));

const foregroundMaskXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr name="Answer text" id="40"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="1000000" y="1000000"/><a:ext cx="3000000" cy="1000000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2200"/><a:t>被遮住的答案</a:t></a:r></a:p></p:txBody></p:sp>
<p:sp><p:nvSpPr><p:cNvPr name="White cover" id="41"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="900000" y="900000"/><a:ext cx="3200000" cy="1200000"/></a:xfrm><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:prstGeom prst="rect"/></p:spPr></p:sp>
</p:spTree></p:cSld></p:sld>`;
const foregroundMaskElements = parseSlideElements(foregroundMaskXml, slideSize);
assert.equal(foregroundMaskElements.find((item) => item.id === 40).zIndex, 0);
assert.equal(foregroundMaskElements.find((item) => item.id === 41).zIndex, 1);
assert.equal(foregroundMaskElements.find((item) => item.id === 41).role, "mask");
assert.deepEqual(foregroundMaskElements.find((item) => item.id === 41).overlayForIds, [40]);
assert.ok(buildVisualModules(foregroundMaskElements, slideSize, 4).staticModules.some((module) => module.semanticRole === "mask"));
const revealMaskModules = buildVisualModules(foregroundMaskElements, slideSize, 4, { revealMaskIds: [41] });
const revealMaskModule = revealMaskModules.modules.find((module) => module.animationMode === "reveal-mask");
assert.deepEqual(revealMaskModule.memberIds, [41]);
const maskedStates = simulateTeachingStates({ elements: foregroundMaskElements }, { stages: [
  { id: 'uncover', trigger: 'on_click', items: [{ shapeId: 41, effect: 'fade-out' }] },
] });
assert.equal(maskedStates.clickStates[0].visibleShapeIds.includes(40), false);
assert.equal(maskedStates.clickStates[1].visibleShapeIds.includes(40), true);
const maskedQuestionSlide = { elements: [...foregroundMaskElements,
  { id: 42, type: 'shape', role: 'question', text: '请观察答案。', x: 100, y: 500,
    width: 400, height: 50 }] };
const prematureMaskedQuestion = { slide: 4, stages: [
  { id: 'uncover', trigger: 'on_click', items: [{ shapeId: 41, effect: 'fade-out', durationMs: 300 }] },
  { id: 'question', trigger: 'with_previous', semanticRole: 'question',
    requiresVisibleShapeIds: [40], items: [{ shapeId: 42, effect: 'fade', durationMs: 300 }] },
] };
assert.match(reviewTeachingSequence(maskedQuestionSlide, prematureMaskedQuestion, slideSize).errors.join('\n'),
  /before mask 41 has revealed required shape 40/);
prematureMaskedQuestion.stages[1].trigger = 'after_previous';
assert.doesNotMatch(reviewTeachingSequence(maskedQuestionSlide, prematureMaskedQuestion, slideSize).errors.join('\n'),
  /before mask 41 has revealed required shape 40/);
assert.deepEqual(revealMaskModule.coveredIds, [40]);
assert.deepEqual(revealMaskModule.allowedEffects, ["fade-out"]);
assert.ok(revealMaskModules.staticModules.some((module) => module.memberIds.includes(40)
  && module.safetyReason === "visible-behind-reveal-mask"));

const existingTimingXml = `${xml.replace("</p:sld>", "")}<p:timing><p:tnLst><p:par><p:cTn id="1" nodeType="tmRoot"><p:childTnLst><p:seq><p:cTn id="2" nodeType="mainSeq"><p:childTnLst><p:par><p:cTn id="3" presetClass="exit" nodeType="clickEffect"><p:childTnLst><p:set><p:cBhvr><p:cTn id="4"/><p:tgtEl><p:spTgt spid="7"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="hidden"/></p:to></p:set></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing></p:sld>`;
const existingSummary = parseExistingAnimationSummary(existingTimingXml);
assert.equal(existingSummary.meaningful, true);
assert.equal(existingSummary.status, "supported");
assert.equal(existingSummary.targets[0].shapeId, 7);
assert.equal(existingSummary.targets[0].visibility, "hidden");
assert.equal(existingSummary.targets[0].isExit, true);
const secondTiming = existingTimingXml.match(/<p:timing>[\s\S]*?<\/p:timing>/)[0].replaceAll('spid="7"', 'spid="6"');
const multiTimingSummary = parseExistingAnimationSummary(existingTimingXml.replace('</p:sld>', `${secondTiming}</p:sld>`));
assert.equal(multiTimingSummary.targetCount, 2, 'all compatibility timing blocks must be inspected');

const maskRevealInspection = {
  schemaVersion: 1,
  source: { path: "/tmp/mask.pptx", extension: ".pptx", size: 1, sha256: "mask" },
  slideSize,
  slideCount: 1,
  slides: [{
    slide: 1,
    type: "exercise",
    existingAnimation: true,
    protectedMediaTiming: false,
    elements: foregroundMaskElements,
    animationSummary: {
      ...existingSummary,
      targets: [{ ...existingSummary.targets[0], shapeId: 41, isExit: true }],
    },
  }],
};
const maskRevealBrief = buildModelBrief(maskRevealInspection);
const maskRevealPlanModule = maskRevealBrief.slides[0].modules.find((module) => module.animationMode === "reveal-mask");
assert.ok(maskRevealPlanModule);
const maskRevealPlan = {
  schemaVersion: 3,
  contract: "ppt-native-animation-model-plan",
  source: { sha256: "mask" },
  mode: "teaching",
  deckStrategy,
  slides: [{
    slide: 1,
    action: "replace",
    transition: "fade",
    staticModules: [],
    stages: [{
      trigger: "on_click",
      moduleIds: [maskRevealPlanModule.moduleId],
      contentRole: "answer",
      rationale: "点击后移除原遮罩以揭示其覆盖内容。",
      answersQuestionStageId: "previous-slide",
      effect: "fade-out",
      durationMs: 420,
      staggerMs: 0,
      granularity: "shape",
    }],
  }],
};
assert.deepEqual(validateModelPlanShape(maskRevealPlan, maskRevealInspection, maskRevealBrief,
  { allowReplaceExisting: true }), []);

const modelInspection = {
  schemaVersion: 1,
  analysisRevision: ANALYSIS_REVISION,
  source: { path: "/tmp/example.pptx", extension: ".pptx", size: 1, sha256: "abc" },
  slideSize,
  slideCount: 1,
  slides: [{ slide: 1, type: "exercise", existingAnimation: false, protectedMediaTiming: false, elements }],
};
const modelBrief = buildModelBrief(modelInspection);
assert.equal(modelBrief.contract, "ppt-native-animation-model-brief");
assert.equal(modelBrief.schemaVersion, 3);
assert.equal(modelBrief.analysisMode, "structure-only");
assert.equal(modelBrief.tokenPolicy.rasterPreviews, false);
assert.ok(modelBrief.slides[0].modules.some((module) => module.semanticRole === "answer"));
const suggestedModelPlan = createModelPlanTemplate(modelBrief);
assert.equal(suggestedModelPlan.schemaVersion, 3);
assert.equal(suggestedModelPlan.mode, "classroom-controlled");
assert.equal(suggestedModelPlan.targetApplication, "unspecified");
assert.ok(Object.hasOwn(suggestedModelPlan, "deckStrategy"));
assert.equal(suggestedModelPlan.slides[0].action, undefined);
assert.equal(suggestedModelPlan.slides[0].transition, undefined);
assert.deepEqual(suggestedModelPlan.slides[0].stages, []);
const preservedBrief = buildModelBrief({
  ...modelInspection,
  slides: [{ ...modelInspection.slides[0], existingAnimation: true, animationSummary: existingSummary }],
});
assert.equal(preservedBrief.slides[0].recommendedAction, "replace");
assert.ok(preservedBrief.slides[0].modules.length > 0);
assert.ok(!Object.hasOwn(preservedBrief.slides[0].existingAnimationSummary, "targets"));
assert.equal(createModelPlanTemplate(preservedBrief).slides[0].action, undefined);
assert.equal(Object.hasOwn(createModelPlanTemplate(preservedBrief), "existingAnimations"), false);
const validModelPlan = {
  schemaVersion: 3,
  contract: "ppt-native-animation-model-plan",
  source: { sha256: "abc" },
  mode: "teaching",
  deckStrategy,
  slides: [{
    slide: 1,
    action: "design",
    transition: "fade",
    staticModules: [],
    stages: modelBrief.slides[0].modules.map((module, index) => ({
      id: `stage-${index + 1}`,
      trigger: module.semanticRole === "answer" ? "on_click" : "after_previous",
      moduleIds: [module.moduleId],
      contentRole: module.semanticRole,
      rationale: module.semanticRole === "answer" ? "该模块内容明确标注为答案。" : "",
      answersQuestionStageId: module.semanticRole === "answer"
        ? `stage-${modelBrief.slides[0].modules.findIndex((candidate) => candidate.semanticRole === "question") + 1}`
        : undefined,
      effect: "fade",
      durationMs: 420,
      staggerMs: 90,
      granularity: "shape",
    })),
  }],
};
assert.deepEqual(validateModelPlanShape(validModelPlan, modelInspection, modelBrief), []);
const teachingCues = {
  contract: "ppt-native-animation-teaching-cues",
  source: { sha256: "abc" },
  slides: [{ slide: 1, purpose: "先展示题目，学生回答后揭示答案。", teacherClickBeats: [
    { stageId: "stage-3", reason: "留出学生作答时间。" },
  ], keepStatic: [] }],
};
assert.deepEqual(validateTeachingCues(modelBrief, validModelPlan, teachingCues), []);
assert.match(validateTeachingCues(modelBrief, validModelPlan, { ...teachingCues, slides: [
  { slide: 1, purpose: "", teacherClickBeats: [] },
] }).join("\n"), /teaching purpose/);
assert.match(validateTeachingCues(modelBrief, validModelPlan, { ...teachingCues, slides: [
  { slide: 1, purpose: "完成练习", teacherClickBeats: [] },
] }).join("\n"), /missing from the teaching cues/);
const visualCueBrief = {
  source: { sha256: "visual" }, slideSize,
  slides: [{ slide: 1, mediaPolicy: "model-design", visualInspectionRequired: true,
    modules: [{ moduleId: "s1-m1", semanticRole: "image", text: "", memberIds: [20],
      bounds: { width: 5000000, height: 3000000 } }], reviewableModules: [] }],
};
const visualCuePlan = { mode: "classroom-controlled", slides: [{ slide: 1,
  stages: [{ id: "show-image", trigger: "after_previous", moduleIds: ["s1-m1"] }] }] };
const visualCues = { contract: "ppt-native-animation-teaching-cues", source: { sha256: "visual" },
  slides: [{ slide: 1, purpose: "观察建筑照片", teacherClickBeats: [], keepStatic: [], visualReviews: [] }] };
assert.match(validateTeachingCues(visualCueBrief, visualCuePlan, visualCues).join("\n"), /visual review description/);
visualCues.slides[0].visualReviews = [{ moduleId: "s1-m1", description: "雅典卫城的照片" }];
assert.deepEqual(validateTeachingCues(visualCueBrief, visualCuePlan, visualCues), []);
const baselineIncrementalInspection = {
  ...structuredClone(modelInspection),
  planningContextFingerprint: "context-1",
  slides: [{ ...structuredClone(modelInspection.slides[0]), planningFingerprint: "slide-1" }],
};
const unchangedIncrementalInspection = {
  ...structuredClone(baselineIncrementalInspection),
  source: { ...baselineIncrementalInspection.source, sha256: "def", path: "/tmp/example-edited.pptx" },
};
const unchangedBundle = buildIncrementalPlanningBundle(
  unchangedIncrementalInspection, baselineIncrementalInspection, validModelPlan,
);
assert.deepEqual(unchangedBundle.brief.reuse.reusableSlides, [1]);
assert.deepEqual(unchangedBundle.brief.reuse.changedSlides, []);
assert.equal(unchangedBundle.brief.slides.length, 0);
const unchangedMerged = mergeModelPlanPatch(unchangedIncrementalInspection, baselineIncrementalInspection,
  validModelPlan, unchangedBundle.template);
assert.equal(unchangedMerged.source.sha256, "def");
assert.deepEqual(unchangedMerged.slides[0], validModelPlan.slides[0]);
const forcedBundle = buildIncrementalPlanningBundle(
  unchangedIncrementalInspection, baselineIncrementalInspection, validModelPlan, { forceSlides: [1] },
);
assert.deepEqual(forcedBundle.brief.reuse.forcedSlides, [1]);
assert.deepEqual(forcedBundle.brief.reuse.reusableSlides, []);
assert.deepEqual(forcedBundle.brief.reuse.changedSlides, [1]);
const forcedPatch = structuredClone(forcedBundle.template);
forcedPatch.slides = [structuredClone(validModelPlan.slides[0])];
const forcedMerged = mergeModelPlanPatch(unchangedIncrementalInspection, baselineIncrementalInspection,
  validModelPlan, forcedPatch);
assert.deepEqual(forcedMerged.slides[0], validModelPlan.slides[0]);
const changedIncrementalInspection = structuredClone(unchangedIncrementalInspection);
changedIncrementalInspection.slides[0].planningFingerprint = "slide-1-edited";
const changedBundle = buildIncrementalPlanningBundle(
  changedIncrementalInspection, baselineIncrementalInspection, validModelPlan,
);
assert.deepEqual(changedBundle.brief.reuse.changedSlides, [1]);
assert.equal(changedBundle.brief.slides.length, 1);
const changedPatch = structuredClone(changedBundle.template);
changedPatch.slides = [structuredClone(validModelPlan.slides[0])];
const changedMerged = mergeModelPlanPatch(changedIncrementalInspection, baselineIncrementalInspection,
  validModelPlan, changedPatch);
assert.equal(changedMerged.slides.length, 1);
assert.equal(changedMerged.source.sha256, "def");
const inheritedStrategyPlan = structuredClone(validModelPlan);
for (const stage of inheritedStrategyPlan.slides[0].stages) {
  delete stage.effect;
  delete stage.durationMs;
  delete stage.staggerMs;
  delete stage.granularity;
}
assert.deepEqual(validateModelPlanShape(inheritedStrategyPlan, modelInspection, modelBrief), []);
const allInitialPlan = structuredClone(validModelPlan);
for (const stage of allInitialPlan.slides[0].stages) {
  stage.trigger = "initial";
  stage.rationale = "该内容需要在页面打开时作为持续参照可见。";
  delete stage.contentRole;
  delete stage.answersQuestionStageId;
}
assert.ok(validateModelPlanShape(allInitialPlan, modelInspection, modelBrief)
  .some((error) => error.includes("only initial stages")));
const lateInitialPlan = structuredClone(validModelPlan);
lateInitialPlan.slides[0].stages.at(-1).trigger = "initial";
lateInitialPlan.slides[0].stages.at(-1).rationale = "测试非法顺序。";
delete lateInitialPlan.slides[0].stages.at(-1).contentRole;
delete lateInitialPlan.slides[0].stages.at(-1).answersQuestionStageId;
assert.ok(validateModelPlanShape(lateInitialPlan, modelInspection, modelBrief)
  .some((error) => error.includes("initial after an animated stage")));
const excessiveDelayPlan = structuredClone(validModelPlan);
excessiveDelayPlan.slides[0].stages[0].delayMs = 401;
assert.ok(validateModelPlanShape(excessiveDelayPlan, modelInspection, modelBrief)
  .some((error) => error.includes("0-400ms delay")));
const tooManyEffectsPlan = structuredClone(validModelPlan);
tooManyEffectsPlan.deckStrategy.effectFamilies = ["appear", "fade", "wipe"];
assert.ok(validateModelPlanShape(tooManyEffectsPlan, modelInspection, modelBrief)
  .some((error) => error.includes("1-2 supported effects")));

const reviewInspection = {
  schemaVersion: 1,
  source: { path: "/tmp/review.pptx", extension: ".pptx", size: 1, sha256: "review" },
  slideSize,
  slideCount: 1,
  slides: [{
    slide: 1,
    type: "visual",
    existingAnimation: false,
    protectedMediaTiming: false,
    elements: [{
      id: 90, name: "Small icon", role: "decoration", sourceType: "image", type: "image",
      x: 100000, y: 100000, width: 300000, height: 300000, zIndex: 0, paragraphs: [], text: "",
    }],
  }],
};
const reviewBrief = buildModelBrief(reviewInspection);
assert.equal(reviewBrief.slides[0].modules.length, 0);
assert.equal(reviewBrief.slides[0].reviewableModules.length, 1);
const reviewModuleId = reviewBrief.slides[0].reviewableModules[0].moduleId;
const promotedReviewPlan = {
  schemaVersion: 3,
  contract: "ppt-native-animation-model-plan",
  source: { sha256: "review" },
  mode: "teaching",
  deckStrategy,
  slides: [{
    slide: 1,
    action: "design",
    transition: "fade",
    staticModules: [],
    stages: [{
      id: "supporting-icon",
      trigger: "after_previous",
      moduleIds: [reviewModuleId],
      contentRole: "image",
      promotionRationale: "该图标承担本页概念提示，而非纯装饰。",
      effect: "fade",
      durationMs: 360,
      staggerMs: 0,
      granularity: "shape",
    }],
  }],
};
assert.deepEqual(validateModelPlanShape(promotedReviewPlan, reviewInspection, reviewBrief), []);
const unjustifiedPromotionPlan = structuredClone(promotedReviewPlan);
delete unjustifiedPromotionPlan.slides[0].stages[0].promotionRationale;
assert.ok(validateModelPlanShape(unjustifiedPromotionPlan, reviewInspection, reviewBrief)
  .some((error) => error.includes("without promotionRationale")));
const unjustifiedNoTransitionPlan = structuredClone(validModelPlan);
unjustifiedNoTransitionPlan.slides[0].transition = "none";
assert.ok(validateModelPlanShape(unjustifiedNoTransitionPlan, modelInspection, modelBrief)
  .some((error) => error.includes("must use fade")));
const userApprovedNoTransitionPlan = structuredClone(unjustifiedNoTransitionPlan);
userApprovedNoTransitionPlan.slides[0].transitionRationale = "用户明确要求本页不使用翻页动画。";
assert.deepEqual(validateModelPlanShape(userApprovedNoTransitionPlan, modelInspection, modelBrief, { allowNoTransition: true }), []);
const replacePlan = structuredClone(validModelPlan);
replacePlan.slides[0].action = "replace";
assert.ok(validateModelPlanShape(replacePlan, { ...modelInspection, slides: [{ ...modelInspection.slides[0], existingAnimation: true }] }, preservedBrief)
  .some((error) => error.includes("external user authorization")));
assert.deepEqual(validateModelPlanShape(replacePlan,
  { ...modelInspection, slides: [{ ...modelInspection.slides[0], existingAnimation: true }] },
  preservedBrief, { allowReplaceExisting: true }), []);
const protectedMediaInspection = {
  ...modelInspection,
  slides: [{ ...modelInspection.slides[0], protectedMediaTiming: true }],
};
const protectedMediaBrief = buildModelBrief(protectedMediaInspection);
assert.equal(protectedMediaBrief.slides[0].mediaPolicy, "preserve-required");
assert.equal(protectedMediaBrief.slides[0].modules.length, 0);
const protectedMediaPlan = createModelPlanTemplate(protectedMediaBrief);
protectedMediaPlan.deckStrategy = deckStrategy;
assert.equal(protectedMediaPlan.slides[0].action, undefined);
assert.equal(protectedMediaPlan.slides[0].transition, undefined);
assert.deepEqual(validateModelPlanShape(protectedMediaPlan, protectedMediaInspection, protectedMediaBrief), []);
const missingSlidePlan = structuredClone(validModelPlan);
missingSlidePlan.slides = [];
assert.ok(validateModelPlanShape(missingSlidePlan, modelInspection, modelBrief)
  .some((error) => error.includes("every source slide")));
const badClickPlan = structuredClone(validModelPlan);
badClickPlan.slides[0].stages[0].trigger = "on_click";
assert.ok(validateModelPlanShape(badClickPlan, modelInspection, modelBrief).some((error) => error.includes("did not classify")));

const classroomClickPlan = structuredClone(validModelPlan);
classroomClickPlan.mode = "classroom-controlled";
classroomClickPlan.targetApplication = "wps";
classroomClickPlan.slides[0].stages[0].trigger = "on_click";
classroomClickPlan.slides[0].stages[0].contentRole = "task";
classroomClickPlan.slides[0].stages[0].rationale = "教师布置任务后，需要等待学生观察再继续。";
assert.deepEqual(validateModelPlanShape(classroomClickPlan, modelInspection, modelBrief), []);

const mixedQuestionAnswerXml = `<?xml version="1.0" encoding="utf-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree>
<p:sp><p:nvSpPr><p:cNvPr id="50" name="普通文本框"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="600000" y="1200000"/><a:ext cx="6000000" cy="1800000"/></a:xfrm><a:noFill/></p:spPr><p:txBody><a:p><a:r><a:rPr sz="2400"/><a:t>为什么要珍惜时间？</a:t></a:r></a:p><a:p><a:r><a:rPr sz="2200"/><a:t>时间一去不复返，因此应当珍惜。</a:t></a:r></a:p></p:txBody></p:sp>
</p:spTree></p:cSld></p:sld>`;
const mixedElements = parseSlideElements(mixedQuestionAnswerXml, slideSize);
const mixedInspection = {
  schemaVersion: 1,
  source: { path: "/tmp/mixed.pptx", extension: ".pptx", size: 1, sha256: "mixed" },
  slideSize,
  slideCount: 1,
  slides: [{ slide: 1, type: "exercise", existingAnimation: false, protectedMediaTiming: false, elements: mixedElements }],
};
const mixedBrief = buildModelBrief(mixedInspection);
const mixedParagraphs = mixedBrief.slides[0].modules[0].paragraphs;
assert.equal(mixedParagraphs.length, 2);
assert.equal(mixedBrief.slides[0].modules[0].semanticRoleIsHint, true);
const modelClassifiedAnswerPlan = {
  schemaVersion: 3,
  contract: "ppt-native-animation-model-plan",
  source: { sha256: "mixed" },
  mode: "teaching",
  deckStrategy,
  slides: [{
    slide: 1,
    action: "design",
    transition: "fade",
    staticModules: [],
    stages: [
      { id: "question", trigger: "after_previous", paragraphIds: [mixedParagraphs[0].paragraphId], contentRole: "question", effect: "fade", durationMs: 420, staggerMs: 0, granularity: "paragraph" },
      { id: "answer", trigger: "on_click", paragraphIds: [mixedParagraphs[1].paragraphId], contentRole: "answer", rationale: "第二段直接回答第一段提出的问题。", answersQuestionStageId: "question", effect: "fade", durationMs: 420, staggerMs: 0, granularity: "paragraph" },
    ],
  }],
};
assert.deepEqual(validateModelPlanShape(modelClassifiedAnswerPlan, mixedInspection, mixedBrief), []);

const executableValidation = validateExecutablePlan({
  strictCoverage: true,
  slides: [{
    slide: 1,
    unanimated: [],
    stages: [
      { trigger: "after_previous", items: elements.filter((item) => item.role !== "answer").map((item) => ({ shapeId: item.id })) },
      { trigger: "on_click", semanticRole: "answer", rationale: "模型判断该内容为答案。", items: [{ shapeId: 7 }] },
    ],
  }],
}, modelInspection);
assert.equal(executableValidation.valid, true, executableValidation.errors.join("\n"));

const replaceExistingValidation = validateExecutablePlan({
  strictCoverage: false,
  slides: [{
    slide: 1,
    disposition: "replace",
    unanimated: [],
    stages: [{ trigger: "after_previous", items: [{ shapeId: 5 }] }],
  }],
}, {
  ...modelInspection,
  slides: [{ ...modelInspection.slides[0], existingAnimation: true }],
}, "preserve");
assert.equal(replaceExistingValidation.valid, false);
assert.match(replaceExistingValidation.errors.join("\n"), /answer shape 7/);
const protectedMediaValidation = validateExecutablePlan({
  strictCoverage: false,
  slides: [{ slide: 1, disposition: "replace", unanimated: [], stages: [] }],
}, {
  ...modelInspection,
  slides: [{ ...modelInspection.slides[0], existingAnimation: true, protectedMediaTiming: true }],
}, "replace");
assert.equal(protectedMediaValidation.valid, false);
assert.match(protectedMediaValidation.errors.join("\n"), /protected media timing/);

const semanticReview = reviewSemanticCoverage({ modules: [
  { moduleId: 'm1', semanticRole: 'title', text: '课堂总结' },
  { moduleId: 'm2', semanticRole: 'question', text: '为什么要遵守规则？' },
  { moduleId: 'm3', semanticRole: 'body', text: '规则维护秩序' },
  { moduleId: 'm4', semanticRole: 'body', text: '规则保障自由' },
  { moduleId: 'm5', semanticRole: 'body', text: '共同维护规则' },
  { moduleId: 'm6', semanticRole: 'conclusion', text: '自觉守规' },
] }, { stages: [{ moduleIds: ['m1', 'm3'] }] });
assert.equal(semanticReview.length, 2, 'critical static content and low coverage need review warnings');
const contentPlateSlide = { elements: [
  { id: 101, type: 'group', sourceType: 'group', role: 'diagram', text: '', fillType: 'solid',
    x: 900000, y: 1600000, width: 9000000, height: 3500000, zIndex: 0 },
  { id: 102, type: 'shape', sourceType: 'shape', role: 'body', text: '请先讨论这一项课堂任务', fillType: 'none',
    x: 1700000, y: 2200000, width: 7000000, height: 600000, zIndex: 1 },
] };
const contentPlateBrief = buildModelBrief({ source: { sha256: 'plate-contract' }, slideSize,
  slideCount: 1, slides: [{ slide: 1, type: 'general', existingAnimation: false,
    protectedMediaTiming: false, elements: contentPlateSlide.elements }] });
assert.deepEqual(contentPlateBrief.slides[0].backingTimingReview,
  [{ backingModuleId: 's1-m1', contentModuleIds: ['s1-m2'] }],
  'the compact planner brief must expose cross-module plate and content timing');
const contentClickStage = { id: 'task', trigger: 'on_click', semanticRole: 'task', staggerMs: 0,
  items: [{ shapeId: 102, role: 'body', effect: 'fade', durationMs: 420, zIndex: 1 }] };
const emptyPlateReview = reviewTeachingSequence(contentPlateSlide,
  { slide: 1, stages: [contentClickStage] }, slideSize);
assert.match(emptyPlateReview.errors.join('\n'), /content backing shape 101 appears before its first text shape 102/,
  'an empty content plate must not wait through a teacher click');
const pairedPlateReview = reviewTeachingSequence(contentPlateSlide, { slide: 1, stages: [
  { ...contentClickStage, items: [
    { shapeId: 101, role: 'diagram', effect: 'fade', durationMs: 420, zIndex: 0 },
    ...contentClickStage.items,
  ] },
] }, slideSize);
assert.doesNotMatch(pairedPlateReview.errors.join('\n'), /content backing/,
  'a content plate and its text may enter on the same teacher click');
const intentionalPlateReview = reviewTeachingSequence(contentPlateSlide,
  { slide: 1, stages: [contentClickStage], approvedEarlyBackingIds: [101] }, slideSize);
assert.doesNotMatch(intentionalPlateReview.errors.join('\n'), /content backing/,
  'a documented intentional empty plate may be exempted');
const earlyBackingCuePlan = { mode: 'classroom-controlled', slides: [{ slide: 1,
  stages: [{ id: 'task', trigger: 'on_click', contentRole: 'task' }], staticModules: [
    { moduleId: 's1-m1', reason: '教师用空板框引导学生预测填写内容。' },
  ] }] };
const earlyBackingCue = { contract: 'ppt-native-animation-teaching-cues',
  source: { sha256: 'plate-contract' }, slides: [{ slide: 1, purpose: '先预测后展示任务。',
    teacherClickBeats: [{ stageId: 'task', reason: '预测后展示任务。' }], keepStatic: [],
    visualReviews: [], earlyBackingExceptions: [
      { moduleId: 's1-m1', reason: '先给学生看空白板框，邀请他们预测接下来填写的任务内容。' },
    ],
  }] };
assert.deepEqual(validateTeachingCues(contentPlateBrief, earlyBackingCuePlan, earlyBackingCue), [],
  'a detected plate can have a specific intentional early-visibility cue');
const invalidEarlyBackingCue = structuredClone(earlyBackingCue);
invalidEarlyBackingCue.slides[0].earlyBackingExceptions[0].reason = '装饰';
assert.match(validateTeachingCues(contentPlateBrief, earlyBackingCuePlan, invalidEarlyBackingCue).join('\n'),
  /early backing exception/, 'a generic decoration label must not bypass the timing guard');
invalidEarlyBackingCue.slides[0].earlyBackingExceptions[0].reason = '该元素是装饰或版式辅助，保持常显。';
assert.match(validateTeachingCues(contentPlateBrief, earlyBackingCuePlan, invalidEarlyBackingCue).join('\n'),
  /early backing exception/, 'a long generic static label must not bypass the timing guard');
const pageBackgroundReview = reviewTeachingSequence({ elements: [
  { ...contentPlateSlide.elements[0], type: 'image', role: 'background' },
  contentPlateSlide.elements[1],
] }, { slide: 1, stages: [contentClickStage] }, slideSize);
assert.doesNotMatch(pageBackgroundReview.errors.join('\n'), /content backing/,
  'a true page background is not a delayed content plate');
const nestedPlateReview = reviewTeachingSequence({ elements: [
  { ...contentPlateSlide.elements[0], id: 100, type: 'shape', role: 'container', x: 800000,
    y: 1500000, width: 9500000, height: 3700000, zIndex: 0 },
  { ...contentPlateSlide.elements[0], id: 101, type: 'shape', role: 'container', zIndex: 1 },
  { ...contentPlateSlide.elements[1], zIndex: 2, containerId: 101 },
] }, { slide: 1, stages: [{ ...contentClickStage, items: [
  { shapeId: 101, role: 'container', effect: 'fade', durationMs: 420, zIndex: 1 },
  { shapeId: 102, role: 'body', effect: 'fade', durationMs: 420, zIndex: 2 },
] }] }, slideSize);
assert.doesNotMatch(nestedPlateReview.errors.join('\n'), /content backing/,
  'an outer decorative panel may remain static when the nearer content plate arrives with text');
assert.deepEqual(reviewSemanticCoverage({ modules: [
  { moduleId: 'm1', semanticRole: 'title', text: '稻壳儿PPT模板使用说明' },
  { moduleId: 'm2', semanticRole: 'body', text: '素材授权条款与字体说明' },
] }, { stages: [] }), [], 'template instructions may remain static without classroom coverage warnings');

const lessonSlide = {
  elements: [
    { id: 17, type: 'group', role: 'diagram', text: '1节干电池电压为1.5 V', x: 0, y: 200, width: 300, height: 100 },
    { id: 18, type: 'group', role: 'diagram', text: '2节干电池电压为3 V', x: 300, y: 200, width: 300, height: 100 },
    { id: 19, type: 'group', role: 'diagram', text: '3节干电池电压为4.5 V', x: 600, y: 200, width: 300, height: 100 },
    { id: 45, type: 'shape', role: 'body', text: '串联电池组两端电压等于各节电池电压之和', x: 100, y: 720, width: 750, height: 65 },
    { id: 16, type: 'shape', role: 'section-title', text: 'U=1.5 V×n', x: 350, y: 860, width: 300, height: 60 },
  ],
  animationSummary: { targets: [{ shapeId: 45 }, { shapeId: 16 }] },
};
const lessonSize = { width: 1000, height: 1000 };
const stagesFor = (ids) => ids.map((shapeId) => ({ trigger: 'after_previous', items: [{ shapeId }] }));
const prematureConclusion = reviewTeachingSequence(lessonSlide, {
  slide: 10, stages: stagesFor([17, 18, 19]),
}, lessonSize);
assert.equal(prematureConclusion.errors.length, 2, prematureConclusion.errors.join('\n'));
const orderedConclusion = reviewTeachingSequence(lessonSlide, {
  slide: 10, stages: stagesFor([17, 18, 19, 45, 16]),
}, lessonSize);
assert.equal(orderedConclusion.errors.length, 0, orderedConclusion.errors.join('\n'));
assert.match(reviewTeachingSequence(lessonSlide, {
  slide: 10, stages: stagesFor([17, 18, 45, 16, 19]),
}, lessonSize).errors.join('\n'), /before or with its evidence/);
const exampleSlide = { elements: [
  { id: 1, type: 'shape', role: 'question', text: '例1：电压是多少？', x: 50, y: 100, width: 500, height: 80 },
  { id: 2, type: 'shape', role: 'answer', text: '答案：D', x: 50, y: 300, width: 300, height: 80 },
  { id: 3, type: 'shape', role: 'analysis', text: '【解析】先读电压表，再计算。', x: 50, y: 500, width: 650, height: 80 },
] };
assert.match(reviewTeachingSequence(exampleSlide, { slide: 11, stages: stagesFor([1, 2]) }, lessonSize).errors.join('\n'), /analysis shape 3/);
assert.equal(reviewTeachingSequence(exampleSlide, { slide: 11, stages: [
  ...stagesFor([1]), { trigger: 'on_click', items: [{ shapeId: 2 }] }, ...stagesFor([3]),
] }, lessonSize).errors.length, 0);
assert.match(reviewTeachingSequence(exampleSlide, { slide: 11, stages: stagesFor([1, 3, 2]) }, lessonSize).errors.join('\n'), /before or with the answer/);
const agendaSlide = { elements: [
  { id: 1, type: 'shape', role: 'conclusion', text: '总结与归纳', x: 100, y: 600, width: 350, height: 70 },
  { id: 2, type: 'group', role: 'diagram', text: '《目录》 数学课', x: 100, y: 100, width: 800, height: 600 },
] };
assert.deepEqual(reviewTeachingSequence(agendaSlide, { slide: 2, stages: stagesFor([2]) }, lessonSize), { errors: [], warnings: [] });
const pairedSlide = { elements: [
  { id: 1, type: 'image', role: 'image', text: '', x: 100, y: 100, width: 400, height: 300 },
  { id: 2, type: 'shape', role: 'section-title', text: '雅典卫城', x: 100, y: 410, width: 400, height: 50 },
] };
assert.match(reviewTeachingSequence(pairedSlide, { slide: 10, stages: stagesFor([2]) }, lessonSize).errors.join('\n'), /image shape 1 is static/);
const visualQuestionSlide = { elements: [
  { id: 1, type: 'shape', role: 'question', text: 'Is it a jeep or a car?', x: 500, y: 100, width: 400, height: 80 },
  { id: 2, type: 'image', role: 'image', text: '', x: 80, y: 230, width: 220, height: 130 },
  { id: 3, type: 'shape', role: 'answer', text: 'That is a jeep.', x: 500, y: 400, width: 400, height: 80 },
] };
const visualQuestionBrief = buildModelBrief({
  source: { sha256: 'visual-question' }, slideSize: lessonSize, slideCount: 1,
  slides: [{ slide: 1, type: 'general', existingAnimation: false, protectedMediaTiming: false,
    elements: visualQuestionSlide.elements.map((element, index) => ({ ...element, zIndex: index, paragraphs: [] })) }],
});
assert.equal(visualQuestionBrief.slides[0].visualInspectionRequired, true,
  'a small but question-critical image must receive selected visual review');
assert.deepEqual(visualQuestionBrief.slides[0].visualQuestionDependencies,
  [{ questionModuleId: 's1-m1', requiredVisualModuleIds: ['s1-m2'] }]);
assert.deepEqual(visualQuestionBrief.slides[0].visualQuestionReview,
  [{ questionModuleId: 's1-m1', candidateVisualModuleIds: ['s1-m2'] }]);
const visualModelPlan = {
  schemaVersion: 3, contract: 'ppt-native-animation-model-plan', source: { sha256: 'visual-question' },
  mode: 'classroom-controlled', deckStrategy,
  slides: [{ slide: 1, stages: visualQuestionBrief.slides[0].modules.map((module, index) => ({
    id: ['question', 'picture', 'answer'][index],
    trigger: module.semanticRole === 'answer' ? 'on_click' : 'after_previous',
    moduleIds: [module.moduleId], contentRole: module.semanticRole,
    rationale: module.semanticRole === 'answer' ? '先让学生回答。' : '',
    answersQuestionStageId: module.semanticRole === 'answer' ? 'question' : undefined,
  })) }],
};
const visualInspection = {
  source: { sha256: 'visual-question' }, slideSize: lessonSize, slideCount: 1,
  slides: [{ slide: 1, type: 'general', existingAnimation: false, protectedMediaTiming: false,
    elements: visualQuestionSlide.elements.map((element, index) => ({ ...element, zIndex: index, paragraphs: [] })) }],
};
assert.match(validateModelPlanShape(visualModelPlan, visualInspection, visualQuestionBrief).join('\n'),
  /must classify its relationship/);
visualModelPlan.slides[0].stages[0].visualDependency = { kind: 'independent', reason: '这只是装饰图。' };
assert.match(validateModelPlanShape(visualModelPlan, visualInspection, visualQuestionBrief).join('\n'),
  /cannot mark its required picture independent/);
visualModelPlan.slides[0].stages[0].visualDependency = { kind: 'requires-visible', moduleIds: ['s1-m2'] };
assert.doesNotMatch(validateModelPlanShape(visualModelPlan, visualInspection, visualQuestionBrief).join('\n'),
  /visualDependency|relationship|required picture/);
visualModelPlan.slides[0].stages[0].visualDependency = { kind: 'blind-prediction', reason: '先让学生猜，再出示图片。' };
const blindCues = { contract: 'ppt-native-animation-teaching-cues',
  source: { sha256: 'visual-question' }, slides: [{ slide: 1, purpose: '先猜后验证。',
    teacherClickBeats: [{ stageId: 'answer', reason: '讨论后公布。' }], keepStatic: [],
    visualReviews: [{ moduleId: 's1-m2', description: '吉普车图片。' }],
    deferredVisualQuestions: [{ stageId: 'question', reason: '先让学生凭生活经验预测。' }],
  }] };
assert.deepEqual(validateTeachingCues(visualQuestionBrief, visualModelPlan, blindCues), []);
const unapprovedBlindCues = structuredClone(blindCues);
unapprovedBlindCues.slides[0].deferredVisualQuestions = [];
assert.match(validateTeachingCues(visualQuestionBrief, visualModelPlan, unapprovedBlindCues).join('\n'),
  /needs a deferredVisualQuestions teaching cue/);
const visualQuestionPlan = { slide: 5, stages: [
  { id: 'question', trigger: 'on_click', items: [{ shapeId: 1 }] },
  { id: 'picture', trigger: 'on_click', items: [{ shapeId: 2 }] },
  { id: 'answer', trigger: 'on_click', items: [{ shapeId: 3 }] },
] };
assert.match(reviewTeachingSequence(visualQuestionSlide, visualQuestionPlan, lessonSize).errors.join('\n'), /visual question shape 1 appears before its required image 2/);
const simultaneousVisualPlan = structuredClone(visualQuestionPlan);
simultaneousVisualPlan.stages[0].items.push({ shapeId: 2 });
simultaneousVisualPlan.stages[0].staggerMs = 0;
simultaneousVisualPlan.stages.splice(1, 1);
assert.equal(reviewTeachingSequence(visualQuestionSlide, simultaneousVisualPlan, lessonSize).errors.length, 0);
const approvedPredictionPlan = { ...visualQuestionPlan, approvedDeferredVisualQuestionStageIds: ['question'] };
assert.equal(reviewTeachingSequence(visualQuestionSlide, approvedPredictionPlan, lessonSize).errors.length, 0);
const explicitPrerequisitePlan = { slide: 5, stages: [
  { id: 'instruction', trigger: 'on_click', requiresVisibleShapeIds: [2], items: [{ shapeId: 1 }] },
  { id: 'picture', trigger: 'on_click', items: [{ shapeId: 2 }] },
  { id: 'answer', trigger: 'on_click', items: [{ shapeId: 3 }] },
] };
assert.match(reviewTeachingSequence(visualQuestionSlide, explicitPrerequisitePlan, lessonSize).errors.join('\n'), /prerequisite is visible/);
const withPreviousVisualPlan = structuredClone(visualQuestionPlan);
withPreviousVisualPlan.stages[1].trigger = 'with_previous';
assert.equal(reviewTeachingSequence(visualQuestionSlide, withPreviousVisualPlan, lessonSize).errors.length, 0);
const visualStates = simulateTeachingStates(visualQuestionSlide, visualQuestionPlan);
assert.deepEqual(visualStates.clickStates.map((state) => state.clickIndex), [0, 1, 2, 3]);
assert.equal(visualStates.clickStates[1].visibleShapeIds.includes(2), false);
assert.equal(visualStates.clickStates[2].visibleShapeIds.includes(2), true);
const staggeredVisualPlan = { slide: 5, stages: [{ id: 'question', trigger: 'on_click',
  semanticRole: 'question', staggerMs: 120, requiresVisibleShapeIds: [2], items: [
    { shapeId: 1, role: 'question', moduleId: 'question', zIndex: 0, durationMs: 300 },
    { shapeId: 2, role: 'image', moduleId: 'picture', zIndex: 1, durationMs: 300 },
  ] }] };
assert.match(reviewTeachingSequence(visualQuestionSlide, staggeredVisualPlan, lessonSize).errors.join('\n'),
  /starts before required shape 2 because of stagger or delay/);
const legacyStaggeredVisualPlan = structuredClone(staggeredVisualPlan);
delete legacyStaggeredVisualPlan.stages[0].requiresVisibleShapeIds;
assert.match(reviewTeachingSequence(visualQuestionSlide, legacyStaggeredVisualPlan, lessonSize).errors.join('\n'),
  /visual question shape 1 starts before required image 2 because of stagger or delay/);
staggeredVisualPlan.stages[0].staggerMs = 0;
assert.doesNotMatch(reviewTeachingSequence(visualQuestionSlide, staggeredVisualPlan, lessonSize).errors.join('\n'),
  /stagger or delay/);
const sameBeatAnswer = { slide: 5, stages: [
  { id: 'question', trigger: 'on_click', semanticRole: 'question', items: [{ shapeId: 1 }] },
  { id: 'answer', trigger: 'with_previous', semanticRole: 'answer', items: [{ shapeId: 3 }] },
] };
assert.match(reviewTeachingSequence(visualQuestionSlide, sameBeatAnswer, lessonSize).errors.join('\n'),
  /same teaching beat/);
const cardSlide = { elements: [
  { id: 1, type: 'group', role: 'diagram', text: '第一个建议：先发现实际问题', x: 50, y: 100, width: 250, height: 200 },
  { id: 2, type: 'group', role: 'diagram', text: '第二个建议：再讨论不同方案', x: 350, y: 100, width: 250, height: 200 },
  { id: 3, type: 'group', role: 'diagram', text: '第三个建议：最后形成规则', x: 650, y: 100, width: 250, height: 200 },
] };
assert.match(reviewTeachingSequence(cardSlide, { slide: 4, stages: stagesFor([1, 2]) }, lessonSize).errors.join('\n'), /card shape 3/);
assert.match(reviewTeachingSequence({ elements }, { slide: 1, stages: [
  { trigger: 'on_click', items: [{ shapeId: 6 }, { shapeId: 7 }] },
] }, slideSize).errors.join('\n'), /question and its answer together/);
const groupedConclusionXml = `<?xml version="1.0" encoding="utf-8"?><p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="80" name="Result"/></p:nvSpPr><p:spPr><a:xfrm><a:off x="500000" y="5000000"/><a:ext cx="4000000" cy="500000"/></a:xfrm></p:spPr><p:txBody><a:p><a:r><a:t>结 论</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>`;
assert.equal(parseSlideElements(groupedConclusionXml, slideSize)[0].role, 'conclusion');

const repeatedSlides = [
  { elements: [{ id: 21, text: "调研", role: "body", x: 500000, y: 6400000, width: 400000, height: 200000 }] },
  { elements: [{ id: 22, text: "调研", role: "body", x: 505000, y: 6402000, width: 398000, height: 201000 }] },
];
markRepeatedElements(repeatedSlides, slideSize);
assert.equal(repeatedSlides[0].elements[0].role, "repeat");
assert.equal(repeatedSlides[1].elements[0].role, "repeat");

const semanticStages = buildStages(elements, {
  playback: "mixed",
  answerTrigger: "on_click",
  paragraphs: true,
  titleInitial: false,
  questionInitial: false,
  groupBody: false,
  maxStages: 6,
  effects: { text: "fade", image: "fade", diagram: "wipe", answer: "fade" },
  timing: { text: 300, image: 450, diagram: 350, answer: 400, delay: 120 },
}).stages;
assert.equal(semanticStages.find((stage) => stage.items.some((item) => item.role === "title")).trigger, "after_previous");
assert.equal(semanticStages.find((stage) => stage.items.some((item) => item.role === "question")).trigger, "after_previous");
assert.equal(semanticStages.find((stage) => stage.items.some((item) => item.role === "answer")).trigger, "on_click");
assert.ok(semanticStages.filter((stage) => stage.trigger === "on_click").every((stage) => stage.items.every((item) => item.role === "answer")));

const classroomStages = buildStages(elements, {
  playback: "teacher-controlled",
  answerTrigger: "on_click",
  clickTeachingBeats: true,
  paragraphs: true,
  titleInitial: false,
  questionInitial: false,
  groupBody: false,
  maxStages: 6,
  effects: { text: "fade", image: "fade", diagram: "fade", answer: "fade" },
  timing: { text: 300, image: 380, diagram: 350, answer: 380, delay: 60 },
}).stages;
assert.equal(classroomStages[0].trigger, "after_previous");
assert.ok(classroomStages.slice(1).some((stage) => stage.trigger === "on_click"));

const performanceInspection = structuredClone(modelInspection);
const performancePlan = {
  interactionMode: "classroom-controlled",
  performanceBudget: {
    maxAnimatedTargetsPerSlide: 2,
    maxConcurrentItemsPerStage: 2,
    maxConcurrentWipeItems: 1,
    maxLargeWipeAreaRatio: 0.3,
  },
  strictCoverage: false,
  slides: [{
    slide: 1,
    stages: [{
      trigger: "on_click",
      semanticRole: "task",
      rationale: "课堂任务等待教师控制。",
      staggerMs: 0,
      items: elements.map((item) => ({ ...item, shapeId: item.id, effect: "fade", durationMs: 420 })),
    }],
    unanimated: [],
  }],
};
const performanceValidation = validateExecutablePlan(performancePlan, performanceInspection);
assert.ok(performanceValidation.errors.some((error) => error.includes("animated targets")));
assert.ok(performanceValidation.errors.some((error) => error.includes("items together")));

const largeWipePlan = {
  performanceBudget: {
    maxAnimatedTargetsPerSlide: 4,
    maxConcurrentItemsPerStage: 4,
    maxConcurrentWipeItems: 2,
    maxLargeWipeAreaRatio: 0.3,
  },
  strictCoverage: false,
  slides: [{
    slide: 1,
    stages: [{
      trigger: "after_previous",
      items: [{ shapeId: 5, role: "title", effect: "wipe", x: 0, y: 0, width: slideSize.width, height: slideSize.height }],
    }],
    unanimated: [],
  }],
};
assert.ok(validateExecutablePlan(largeWipePlan, performanceInspection).errors
  .some((error) => error.includes("uses wipe over")));

const timing = buildTimingXml({
  stages: [
    { id: "initial", trigger: "initial", items: [{ shapeId: 6 }] },
    { id: "answer", trigger: "on_click", items: [{ shapeId: 7, effect: "fade", durationMs: 400, direction: "left" }] },
  ],
});
assert.match(timing, /spid="7"/);
assert.match(timing, /nodeType="clickEffect"/);
assert.match(timing, /<p:cond delay="indefinite"\/><p:cond evt="onBegin" delay="0"><p:tn val="2"\/><\/p:cond>/);
assert.match(timing, /grpId="3" nodeType="clickEffect"/);
assert.match(timing, /dur="400" fill="hold"/);
assert.doesNotMatch(timing, /spid="6"/);
const timingSummary = summarizeExecutablePlan({
  slides: [{
    slide: 1,
    stages: [
      { trigger: "initial", items: [{ shapeId: 6 }] },
      { trigger: "after_previous", items: [{ shapeId: 7 }] },
      { trigger: "on_click", semanticRole: "answer", items: [{ shapeId: 8 }] },
    ],
  }],
}, [{ slide: 1, status: "animated" }]);
assert.deepEqual({
  plannedStages: timingSummary.plannedStages,
  initialVisibleStages: timingSummary.initialVisibleStages,
  animatedStages: timingSummary.animatedStages,
  autoStages: timingSummary.autoStages,
  clickAnswerStages: timingSummary.clickAnswerStages,
  animatedTargets: timingSummary.animatedTargets,
}, {
  plannedStages: 3,
  initialVisibleStages: 1,
  animatedStages: 2,
  autoStages: 1,
  clickAnswerStages: 1,
  animatedTargets: 2,
});
const sequentialTiming = buildTimingXml({
  stages: [
    { trigger: "after_previous", delayMs: 0, staggerMs: 0, items: [{ shapeId: 5, effect: "fade", durationMs: 400, zIndex: 0 }] },
    { trigger: "after_previous", delayMs: 120, staggerMs: 0, items: [{ shapeId: 6, effect: "fade", durationMs: 360, zIndex: 1 }] },
  ],
});
assert.match(sequentialTiming, /delay="520"/);
const simultaneousTiming = buildTimingXml({
  stages: [
    { trigger: "after_previous", delayMs: 0, staggerMs: 0, items: [{ shapeId: 5, effect: "fade", durationMs: 400, zIndex: 0 }] },
    { trigger: "with_previous", delayMs: 0, staggerMs: 0, items: [{ shapeId: 6, effect: "fade", durationMs: 360, zIndex: 1 }] },
  ],
});
assert.equal((simultaneousTiming.match(/<p:cond delay="0"\/>/g) || []).length >= 4, true);
const maskExitTiming = buildTimingXml({
  stages: [{ trigger: "on_click", items: [{ shapeId: 41, effect: "fade-out", durationMs: 420, zIndex: 1 }] }],
});
assert.match(maskExitTiming, /presetClass="exit"/);
assert.match(maskExitTiming, /transition="out" filter="fade"/);
assert.doesNotMatch(maskExitTiming, /val="visible"/);
const paragraphTiming = buildTimingXml({
  stages: [{ trigger: "after_previous", items: [{ shapeId: 6, paragraphIndex: 0, effect: "fade", durationMs: 360, direction: "left", zIndex: 0 }] }],
});
assert.match(paragraphTiming, /animBg="0"/);
assert.doesNotMatch(paragraphTiming, /animBg="1"/);
assert.equal(
  stripAnimationParts(`<p:sld><p:cSld/><p:transition spd="fast"><p:fade/></p:transition>${timing}</p:sld>`),
  "<p:sld><p:cSld/></p:sld>",
);

if (process.env.PPT_TEST_FILE) {
  const source = path.resolve(process.env.PPT_TEST_FILE);
  const work = await fs.mkdtemp(path.join(os.tmpdir(), "ppt-native-animator-test-"));
  const plan = await createPlan(source, "auto-teaching");
  assert.ok(plan.slides.length > 0);
  const output = path.join(work, `test-output${path.extname(source)}`);
  await applyPlan(source, plan, output, "replace");
  const validation = await validatePresentation(output);
  assert.equal(validation.valid, true, validation.errors.join("\n"));
  await fs.rm(work, { recursive: true, force: true });
}

console.log("All tests passed.");
