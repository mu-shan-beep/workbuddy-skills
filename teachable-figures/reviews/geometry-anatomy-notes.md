# Geometry and anatomy examples

These two standalone pages run from a local file without external assets, libraries or a network request. Each has native controls, prediction feedback, an explanation field, a transfer question and a lesson reset. A reset clears the learner's answers and restores the initial camera and model. The UI follows the operating system's light or dark preference. No animation runs, including under reduced motion.

The renderer rotates world-coordinate triangles around two axes, projects them orthographically, and paints them from far to near. Rotation preserves distances. These are actual depth-changing views. The anatomical cover occludes the organs when viewed from behind. The meshes are simple educational solids, and triangle centroid sorting is intended for these separated shapes. This is not a general mesh-intersection or clinical visualization engine.

## Geometry slices

- Anchor claim. For parallel slices of a right circular cone, radius is proportional to distance from the apex and area is proportional to the square of that distance.
- Model. `H = 8 cm`, `R = 4 cm`, `0 ≤ h ≤ 8 cm`, `r = R × h / H`, `A = πr²`. All dimensions are chosen teaching values.
- Mapping. The blue frustum is the retained lower cone. The gold disk is the cut surface. Dashed rays show the removed upper portion. View controls change the camera, not the dimensions.
- Misconception. Doubling the slice's distance from the apex doubles its area.
- Meaningful try. Compare `h = 2` and `h = 4`. The radius changes from `1` to `2 cm`, while the area changes from `π` to `4π cm²`.
- Satisfactory explanation. Similar triangles make radius proportional to h. Squaring the doubled radius makes area four times as large. An explanation that confuses distance from the base with distance from the apex does not meet the target.
- Transfer. At `h = 6` compared with `h = 2`, the radius triples and the area becomes nine times as large.
- Endpoints. At zero the cross-section is a point. At eight the cross-section equals the base. No oblique section or volume claim is made.

Interaction selectors are `#height`, `#trial-a`, `#trial-b`, `#yaw`, `#pitch`, `#reset`, `#check`, `#transfer-check`, and `#explanation`. Prediction radio values are `2`, `4` and `1`; transfer values are `3`, `9` and `6`. Read `#radius`, `#area`, `#summary`, `#feedback` and `#transfer-feedback`.

The exposed inspection API is `window.lesson = { state, derive, rotate, selfCheck, render }`. `state` contains `h`, `yaw` and `pitch`. `derive(h)` returns radius and area. `selfCheck()` checks zero/base areas, the fourfold area comparison, and length-preserving rotation over 25 yaw poses.

## Human anatomy

- Anchor claim. The lungs lie on either side of the heart, and the diaphragm lies below the lungs.
- Model. Fixed schematic organ meshes occupy patient-relative coordinates. Patient right is negative x, patient left is positive x, superior is positive y, and anterior is positive z. Dimensions and spacing are illustrative, without clinical units.
- Mapping. Blue ellipsoids stand for the lungs, a red ellipsoid for the heart, a small pale solid for the trachea, and a gold dome for the diaphragm. The grey torso cover is an inspection aid. Airway branches, lobes, vessels, pleura and heart chambers are omitted.
- Misconception. The heart is inside the left lung or below the diaphragm.
- Meaningful try. Open the cutaway, select the heart, switch to the side view, and inspect or hide the lungs to compare their positions. Rotate back to confirm that the viewpoint changes visibility without changing the arrangement.
- Satisfactory explanation. The heart is between the lungs. The diaphragm is below the lungs. A view from another direction does not swap the patient's left and right.
- Transfer. The diaphragm remains below the lungs when the torso is viewed from the back, even though the opaque rear cover hides the organs.
- Limits. This is an educational schematic, not an anatomical atlas, patient model, diagnostic aid, breathing simulation or blood-flow simulation. A selection marker identifies an approximate location and is not a claim that the marked organ is visible through every other surface.

Interaction selectors are `#cutaway`, `#organ`, `#yaw`, `#lungs`, `#front`, `#side`, `#pitch` (inside optional viewing details), `#reset`, `#check`, `#transfer-check`, and `#explanation`. The structure select values are `heart`, `right`, `left`, `diaphragm` and `trachea`. Prediction values are `between`, `below` and `inside`; transfer values are `below`, `swaps` and `moves`. Read `#summary`, `#selection`, `#feedback` and `#transfer-feedback`.

The inspection API is `window.lesson = { state, structures, rotate, selfCheck, render }`. `state` separates `yaw`/`pitch` from `cutaway`, `lungs` and `organ`. `selfCheck()` checks side and superior/inferior relationships, finite triangle coordinates and length-preserving rotation over 25 yaw poses.

### Authoritative sources

Read on 27 October 2026. Text is paraphrased; the artwork is original schematic geometry.

- [NHLBI, The respiratory system](https://www.nhlbi.nih.gov/health/lungs/respiratory-system) supports lungs on either side of the heart and the left lung being slightly smaller because the heart occupies some space on the left.
- [NHLBI, How your body controls breathing](https://www.nhlbi.nih.gov/health/lungs/body-controls-breathing) supports a dome-shaped diaphragm below the lungs separating the chest and abdominal cavities.
- [NHLBI, What the heart looks like](https://www.nhlbi.nih.gov/health/heart/anatomy) supports the heart's position in the chest near the lungs. No chamber or physiological model is implemented.

## Checks run during authoring

A local Playwright script drove installed Google Chrome against both actual HTML files. Both passed their inline model self-checks and rendered without page errors. Browser checks covered native arrow-key operation of the geometry slider, both comparison states, correct prediction and transfer feedback, anatomy cutaway/selection/visibility/side/front controls, ordinary typing in the explanation fields, and complete reset. Both pages had no horizontal overflow at 360 pixels with dark theme and reduced motion enabled. A 13-pose yaw sweep produced finite projected coordinates.

Stage screenshots were inspected at desktop in light theme and at 360 pixels in dark theme. Anatomy front, both side views, an oblique view and the back were inspected. Geometry front/side/oblique views were inspected. The review caught and corrected a shading bug caused by mixing screen-scaled x/y coordinates with world-space z when computing normals.

No learner study, screen-reader session, touch-device run, full mesh intersection audit or measured performance benchmark was run. These authoring checks complement the repository's repeatable browser test suite; they are not a claim that the bundled mechanical orbit audit covers these custom meshes.
