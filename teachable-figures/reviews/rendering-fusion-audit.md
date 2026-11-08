# Rendering fusion review · v0.3.0

## Finding

The user's visual criticism was supported by the source. The original six complete lessons implemented teaching interactions but did not use Anatomy's geometry kit or iso-figure's projection kernel. Bundling those upstreams and listing them in provenance did not establish rendering integration.

The old chest generated the lungs, heart and airway as ellipsoids and the torso as an elliptical tube. The rocket was a small flat icon without interior construction. The garment used a flat lower panel with open strokes for pleats. Controls worked, but those representations did not meet the requested detail.

The routing table chose mostly by projection and motion complexity. “Simplest mode that makes the answer visible” lacked a subject-fidelity condition. Removing an upstream part quota was reasonable, but the combined acceptance gate did not retain recognition, structural volume and material craft as independent requirements. Earlier browser tests and reviews established behavior within the declared simplifications; they did not establish visual fidelity.

## Routing repair

[The new selection guide](../references/rendering-selection.md) records the subject reference, requested fidelity, recognizable landmarks, materials, inspection needs and actual implementation before projection is chosen. Teaching correctness and visual fidelity now have separate acceptance gates.

- **iso-figure** supplies functional isometric device graphics and state flow.
- **Anatomy** supplies crafted rigid geometry, connections, section/explosion construction and material techniques.
- **Organic anatomy** requires domain source geometry or faithful illustration. The upstream name Anatomy does not imply a medical atlas.
- **Textiles** require actual folded surfaces or cloth geometry; a mechanical primitive kit does not supply drape.

Simple requested diagrams remain valid. More detail is not a universal part count or a reason to force every subject into 3D.

## Concrete revisions

### Human chest

Two viable routes were considered: a reference-based layered medical illustration, or source anatomical meshes with a general mesh renderer. The latter preserves the requested rotation while fixing the placeholder morphology.

The page now embeds a derivative of Human Reference Atlas / HuBMAP Visible Human male skin, lung, airway and heart meshes. A native WebGL renderer uses mesh normals and a depth buffer. All source parts retain a common coordinate frame and scale. The skin is cropped to a chest study; a rendering window reveals the organs. The diaphragm remains separately authored, explicitly labeled schematic geometry.

[Provenance](../assets/hra/provenance.json) records the fixed source revision, SHA-256 hashes, cropping, vertex clustering, packing and recoloring. The data is CC BY 4.0. [Rebuild instructions](../assets/hra/README.md) accompany it. A text fallback preserves the explanatory content and structure selection when WebGL is unavailable.

### Rocket

Two viable routes were a complete bundled Raptor scene or a purpose-built generic rocket structure using Anatomy helpers. The generic route preserves the lesson's invented flight parameters without implying that a detailed real engine validates them.

The page adds an engineering study with tank cavities and end caps, skin thickness, mounting surfaces, axial assembly separation and an engine close-up. `scripts/build-rocket-visual.mjs` actually uses Anatomy surface, lathe, ring, rib, bolt-circle and tube helpers. The standalone output retains the MIT notice. Inspection state is separate from flight state; the flight function is unchanged.

### Garment

A static reference image could add texture but would not support consistent layer inspection. The chosen route is an authored sectional SVG with continuous cloth panels, fold faces/valleys, restrained satin-like lighting, hem and collar thickness, and a switchable enlarged fold section. It preserves the museum-specific overlap direction and makes reconstructed surface details explicit.

The page does not claim an exact weave, pleat count, measured pattern or cloth simulation. It does not claim that either upstream generated the garment.

## Verification and limits

All 21 browser cases and 4 model/spec checks pass. The atlas preparation and rocket visual builders were rerun. Both regenerate embedded output without a new runtime dependency. Skill validation and README asset checks are also part of the release checks.

The browser suite checks actual canvas changes for the chest window, camera and lung visibility while anatomical coordinates remain invariant. It checks the no-WebGL explanation, robe fold inspection/reset, and rocket inspection independence alongside the existing teaching cases. Desktop/mobile and light/dark screenshots were read, including opened and separated views.

The revision does not turn browser success into a visual score. Its source review and rendered close-ups provide the visual evidence. The routing evaluation table is a set of reviewed cases, not an automated model-generation benchmark. No new novice-learner study, clinical validation, physical phone GPU survey, cloth simulation or exhaustive mesh-intersection audit is claimed. The earlier full turning-dial audit concerns its unchanged configured mechanical fixture.

An independent final review read the routing, implementation, provenance and rendered desktop/mobile/theme images. Its actionable finding was undersized mobile SVG pleat captions. Those captions now use wrapping HTML at 15 CSS pixels, remain synchronized with the inspection toggle, and pass the focused clothing checks. No other blocking finding was reported.
