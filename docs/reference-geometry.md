# Legacy saved STL references

New geometry imports use STEP. This page documents compatibility for STL
references already embedded in older saved projects; there is no new STL
import control in the current interface.

STL imports provide a visual reference in the scene. They do not create MBDyn
bodies, joints, contact surfaces, finite-element meshes, materials or inertias.
An STL surface also does not establish that an object is watertight, manifold,
dimensionally correct or suitable for analysis.

The workbench initially places the reference **beside** the mechanism for clarity;
this is a display offset and does not register it to a body or change its saved
source coordinates. Choose **Isolate STL** to frame the reference alone. Saving a
desktop project retains its source bytes, chosen unit and digest; reopening
revalidates them before replacing the current workspace.

The optional [NASA Mars 2020 wheel](../examples/reference/README.md) is an
attributed, pinned visual-reference example; its file is ignored by Git and can
be downloaded separately. It does not become a simulated wheel or contact model.

Older projects store an explicitly chosen source unit: **millimeters (`mm`), meters (`m`) or inches
(`in`)**. STL does not declare units. Restoration never infers units from a
filename, bounding box or existing mechanism. It scales the display coordinates
to meters using respectively `0.001`, `1` or `0.0254`, preserving the original
coordinate origin. A curated asset may have a documented unit selection in its
provenance; that does not supply an automatic rule for arbitrary files.

## Legacy restoration and rendering

The browser and native viewer share `frontend/reference-geometry.js`:

```js
import {
  REFERENCE_LIMITS,
  importReferenceGeometry,
  serializeReferenceGeometry,
  restoreReferenceGeometry,
} from "./reference-geometry.js";

// Check before File.arrayBuffer(), so an oversized file is never read in full.
if (file.size > REFERENCE_LIMITS.maxSourceBytes) throw new Error("STL exceeds 12 MiB");
const reference = await importReferenceGeometry(await file.arrayBuffer(), {
  name: file.name,
  unit: "mm", // selected by the user
});

const material = new THREE.MeshStandardMaterial({
  color: 0x829aab,
  side: THREE.DoubleSide,
  transparent: true,
  opacity: 0.45,
});
const mesh = new THREE.Mesh(reference.geometry, material);
scene.add(mesh);

// Save separately from the mechanical model sent to the solver API.
const saved = serializeReferenceGeometry(reference);
const restored = await restoreReferenceGeometry(saved);

scene.remove(mesh);
material.dispose();
reference.dispose();
restored.dispose();
```

`importReferenceGeometry` accepts `ArrayBuffer` or `Uint8Array`, including a view
with a nonzero byte offset. It returns `{geometry, metadata, dispose()}`.
The `geometry` is a non-indexed Three.js `BufferGeometry` in meters, with
recomputed vertex normals, bounding box and bounding sphere. Mesh/material
creation, selection, visibility and camera fitting belong to the caller.

The resource owns its geometry. Call `dispose()` when replacing or removing it;
it is idempotent. Remove every mesh using that geometry from the scene and
dispose caller-owned materials separately. Metadata can still be saved after
geometry disposal. No network request or solver operation occurs during import.

## Input checks and budgets

Limits apply **per reference**, not to the sum of multiple references in a scene:

| Limit | Value |
| --- | --- |
| Original source bytes | 12 MiB |
| Triangles | 1–200,000 |
| Stored reference JSON | 16 MiB + 1024 characters |
| Absolute displayed coordinate | 1,000,000 m per axis |
| ASCII line length | 1024 characters |
| Display filename | 128 characters; directory components removed |

The caller should also bound the number or total memory of simultaneously
active references. Source bytes are copied, validated and hashed before the
Three.js loader allocates geometry arrays. Binary STL must have an exact
84-byte header/count plus 50 bytes per declared triangle; truncated and trailing
data are rejected. A binary header beginning with `solid` is handled correctly.

ASCII accepts complete `solid` blocks, exactly three vertices per facet,
scientific notation, case-insensitive keywords, blank lines, and LF/CRLF/CR line
endings. It rejects comments, non-ASCII encodings, missing delimiters, extra
vertices, empty solids and trailing unrelated text. The validated ASCII mesh is
converted to bounded canonical binary before calling the loader, avoiding its
more permissive ASCII parsing behavior. The original input bytes are preserved.

Every normal and vertex must be finite and representable as Float32. Triangles
must remain nondegenerate after the actual display precision and unit conversion.
A cross-product magnitude at or below `1e-12` times the larger squared edge
length is rejected. This is a display-safety check, not a mesh-quality assessment.
Zero supplied normals are allowed and replaced with normals from vertex winding.

The loader is an unchanged copy of
`three@0.186.1/examples/jsm/loaders/STLLoader.js`; Three.js retains its existing
MIT notice. The application calls its local `parse` method only.

## Project persistence and integrity

`serializeReferenceGeometry(resource)` returns a bounded JSON string containing:

```json
{
  "schemaVersion": 1,
  "format": "stl",
  "name": "reference.stl",
  "unit": "mm",
  "data": "<canonical base64 of the original source bytes>",
  "sha256": "<64 lowercase hexadecimal characters, or null>",
  "byteLength": 134,
  "triangleCount": 1
}
```

The frozen metadata is also available as `resource.metadata` for embedding in
an existing project JSON object. Store it in view/project state, outside the
mechanical model payload sent to the solver API. A maximum-size reference is
larger than that API's 64-KiB request limit. The project loader should bound the
whole project file before parsing it; this module bounds its own JSON string
before parsing and its base64 field before decoding.

`restoreReferenceGeometry(metadataOrJson)` checks the schema, fields, counts,
base64 padding, unit and every facet again. It compares the saved SHA-256 with
the source bytes when present. Browser Web Crypto is used where available;
new imports have `sha256:null` otherwise. Restoring a saved non-null digest
requires working Web Crypto, rather than silently claiming it was checked.
Hashes detect accidental content changes; they do not authenticate a model's
author, licensing or engineering accuracy. Changing the explicit unit changes
display scale and is not a change to the hashed STL bytes.

## Verification

```sh
node --test tests/reference-geometry.test.mjs
```

Six focused tests cover ASCII/binary parsing, `solid`-prefixed binary headers,
byte-offset inputs, meter/millimeter/inch scale, preserved origins, malformed and
non-finite facets, precision collapse, size/count caps, exact source persistence,
digest mismatch, count mismatch and idempotent disposal.

The local NASA Mars 2020 wheel reference was also imported and round-tripped:
45,328 triangles, source SHA-256
`6318740c1ce44b5d4deb85866dd2a2cef9195197019553c78f0c439ab737c4ad`.
With its explicitly selected inch scale, its displayed dimensions are about
`0.127001 × 0.126998 × 0.074550 m`. This checks file import, scale and persistence;
it does not validate the wheel's dimensions against physical flight hardware.
