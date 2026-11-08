# Atlas chest geometry

These are derived Human Reference Atlas / HuBMAP Visible Human male reference meshes, under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The source is the [HRA 3D Reference Library](https://humanatlas.io/3d-reference-library), pinned to `hubmapconsortium/ccf-releases` revision `b036a91aaf7234f462b1249d4a5f4fb0e982f412`, models `v1.2/models/VH_M_{Skin,Lung,Heart}.glb`. Keep [LICENSE.md](LICENSE.md) and [provenance.json](provenance.json) with redistributed derivatives.

From the repository root, download the three original files into an ignored working folder and regenerate the offline lesson.

```sh
mkdir -p .audit/hra
curl -fL https://raw.githubusercontent.com/hubmapconsortium/ccf-releases/b036a91aaf7234f462b1249d4a5f4fb0e982f412/v1.2/models/VH_M_Skin.glb -o .audit/hra/skin.glb
curl -fL https://raw.githubusercontent.com/hubmapconsortium/ccf-releases/b036a91aaf7234f462b1249d4a5f4fb0e982f412/v1.2/models/VH_M_Lung.glb -o .audit/hra/lung.glb
curl -fL https://raw.githubusercontent.com/hubmapconsortium/ccf-releases/b036a91aaf7234f462b1249d4a5f4fb0e982f412/v1.2/models/VH_M_Heart.glb -o .audit/hra/heart.glb
node scripts/prepare-anatomy.mjs .audit/hra
shasum -a 256 assets/hra/chest-meshes.json
```

The preparation script rejects source SHA-256 mismatches and nonidentity node transforms. It verifies GLB version, accessor types and index limits. The resulting `chest-meshes.json` SHA-256 is `dc11d0bf46e90b6cf6d8f323bbdb8184e602927180c9b0e20b65656e567df499`. The JSON copy embedded in `examples/human-anatomy.html` has the same content, excluding the file’s final newline. No model requests occur at runtime.

The skin triangles are clipped to a bust with explicit open edges. Vertex clustering removes redundant detail; positions and normals are quantized. Source coordinates, organ positions and relative scales are preserved. The renderer uses the original normals at retained vertices and interpolates normals at crop boundaries. Teaching colors replace the original materials. The chest inspection window is a display aid. The gold diaphragm is separately authored schematic geometry, not an atlas object.

Anatomy contributes an approach to inspecting and explaining parts. It does not supply these medical meshes. WebGL depth testing handles this organic geometry because the vendored planar object projection does not model atlas topology or occlusion accurately.
