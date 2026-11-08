# Human Reference Atlas mesh attribution

The derived mesh data in `chest-meshes.json`, and the copy embedded in `examples/human-anatomy.html`, are adapted from the Human Reference Atlas / HuBMAP consortium Visible Human male reference objects.

The HRA [3D Reference Library](https://humanatlas.io/3d-reference-library) licenses its reference objects under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/). The license allows sharing and adaptation with attribution, a license link and indication of changes. No endorsement by the source creators is implied.

The pinned upstream revision, individual source file URLs, original SHA-256 hashes, derivative SHA-256 hash, mesh names and transformations are recorded in [provenance.json](provenance.json).

Changes include cropping the skin to a bust, reducing vertex density, quantizing data and replacing teaching colors. All meshes retain the same source coordinate frame and scale. The display window removes body surface fragments for inspection. The gold diaphragm is separately authored schematic geometry and is not an HRA reference object.

Rebuild with `node scripts/prepare-anatomy.mjs /path/to/source-glbs`. That folder must contain the pinned files renamed `skin.glb`, `lung.glb` and `heart.glb`. The script writes the derivative data and embeds it into the offline lesson. Keep this notice with redistributed mesh derivatives.
