import { STLLoader } from "./vendor/STLLoader.js";

/** Reference-only import budgets; check File.size before reading a selected file. */
export const REFERENCE_LIMITS = Object.freeze({
  maxSourceBytes: 12 * 1024 * 1024,
  maxTriangles: 200000,
  maxProjectJsonChars: 16 * 1024 * 1024 + 1024,
  maxAbsCoordinateMeters: 1e6,
});

const resources = new WeakSet();
const disposed = new WeakSet();
const FLOAT32_MAX = 3.4028234663852886e38;
const NUMBER = "([+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][+-]?\\d+)?)";
const vertexPattern = new RegExp(`^vertex\\s+${NUMBER}\\s+${NUMBER}\\s+${NUMBER}$`, "i");
const normalPattern = new RegExp(`^facet\\s+normal\\s+${NUMBER}\\s+${NUMBER}\\s+${NUMBER}$`, "i");

function scaleFor(unit) {
  if (!["mm", "m", "in"].includes(unit)) throw new Error("Choose STL source units explicitly: mm, m or in.");
  return unit === "mm" ? 0.001 : unit === "in" ? 0.0254 : 1;
}

function bytesOf(input) {
  const bytes = input instanceof ArrayBuffer ? new Uint8Array(input) : input;
  if (!(bytes instanceof Uint8Array)) throw new Error("STL input must be an ArrayBuffer or Uint8Array.");
  if (bytes.byteLength === 0 || bytes.byteLength > REFERENCE_LIMITS.maxSourceBytes) {
    throw new Error("STL source must contain 1 byte to 12 MiB.");
  }
  return bytes;
}

function checkedNumbers(values) {
  if (!values.every((value) => Number.isFinite(value) && Math.abs(value) <= FLOAT32_MAX)) {
    throw new Error("STL contains non-finite or unrepresentable numeric values.");
  }
  return values;
}

function checkTriangle(vertices, scale) {
  // Match the actual Float32 loader buffer followed by the unit conversion.
  const points = vertices.map((point) => point.map((value) => Math.fround(Math.fround(value) * scale)));
  if (points.flat().some((value) => !Number.isFinite(value) || Math.abs(value) > REFERENCE_LIMITS.maxAbsCoordinateMeters)) {
    throw new Error("STL coordinates exceed the supported ±1,000,000 m reference-view range.");
  }
  const a = points[1].map((value, i) => value - points[0][i]);
  const b = points[2].map((value, i) => value - points[0][i]);
  const cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const longestSquared = Math.max(a.reduce((sum, value) => sum + value * value, 0), b.reduce((sum, value) => sum + value * value, 0));
  if (Math.hypot(...cross) <= longestSquared * 1e-12) {
    throw new Error("STL contains a degenerate triangle or vertices that collapse at display precision.");
  }
}

function* asciiLines(text) {
  let start = 0;
  for (let end = 0; end <= text.length; end++) {
    if (end - start > 1024) throw new Error("ASCII STL line exceeds 1024 characters.");
    if (end === text.length || text[end] === "\n" || text[end] === "\r") {
      const line = text.slice(start, end).trim();
      if (line) yield line;
      if (text[end] === "\r" && text[end + 1] === "\n") end++;
      start = end + 1;
    }
  }
}

function walkAscii(bytes, scale, emit) {
  for (const byte of bytes) {
    if (byte > 126 || (byte < 32 && ![9, 10, 13].includes(byte))) throw new Error("STL is neither exact-length binary nor valid ASCII text.");
  }
  const text = new TextDecoder("ascii").decode(bytes);
  let state = "solid", count = 0, solidStart = 0, points = [], normal;
  for (const line of asciiLines(text)) {
    if (state === "solid") {
      if (!/^solid(?:\s.*)?$/i.test(line)) throw new Error("ASCII STL must start with a solid declaration.");
      solidStart = count;
      state = "facet";
    } else if (state === "facet") {
      if (/^endsolid(?:\s.*)?$/i.test(line)) {
        if (count === solidStart) throw new Error("STL solid contains no triangles.");
        state = "solid";
        continue;
      }
      const match = normalPattern.exec(line);
      if (!match) throw new Error("ASCII STL expects a facet normal or endsolid.");
      if (++count > REFERENCE_LIMITS.maxTriangles) throw new Error("STL exceeds the 200,000-triangle limit.");
      normal = checkedNumbers(match.slice(1).map(Number));
      points = [];
      state = "outer";
    } else if (state === "outer") {
      if (!/^outer\s+loop$/i.test(line)) throw new Error("ASCII STL expects outer loop.");
      state = "vertex";
    } else if (state === "vertex") {
      const match = vertexPattern.exec(line);
      if (!match) throw new Error("ASCII STL facets require exactly three finite vertices.");
      points.push(checkedNumbers(match.slice(1).map(Number)));
      if (points.length === 3) state = "endloop";
    } else if (state === "endloop") {
      if (line.toLowerCase() !== "endloop") throw new Error("ASCII STL expects endloop after three vertices.");
      state = "endfacet";
    } else {
      if (line.toLowerCase() !== "endfacet") throw new Error("ASCII STL expects endfacet.");
      checkTriangle(points, scale);
      emit?.(normal, points, count - 1);
      state = "facet";
    }
  }
  if (state !== "solid" || count === 0) throw new Error("ASCII STL is incomplete or contains no complete solids.");
  return count;
}

/** Validate all facets and budgets before allocating any Three.js geometry. */
export function validateStl(input, { unit } = {}) {
  const bytes = bytesOf(input);
  const scale = scaleFor(unit);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength >= 84) {
    const count = view.getUint32(80, true);
    if (84 + count * 50 === bytes.byteLength) {
      if (count === 0 || count > REFERENCE_LIMITS.maxTriangles) throw new Error("Binary STL requires 1 to 200,000 triangles.");
      for (let index = 0; index < count; index++) {
        const start = 84 + index * 50;
        checkedNumbers([0, 4, 8].map((offset) => view.getFloat32(start + offset, true)));
        const points = [12, 24, 36].map((offset) => checkedNumbers([0, 4, 8].map((axis) => view.getFloat32(start + offset + axis, true))));
        checkTriangle(points, scale);
      }
      return { encoding: "binary", triangleCount: count, byteLength: bytes.byteLength, unit, scale };
    }
  }
  return { encoding: "ascii", triangleCount: walkAscii(bytes, scale), byteLength: bytes.byteLength, unit, scale };
}

function loaderBytes(bytes, checked) {
  if (checked.encoding === "binary") return bytes.buffer;
  // Canonical binary avoids STLLoader's permissive ASCII regex and header-name ambiguity.
  const buffer = new ArrayBuffer(84 + checked.triangleCount * 50);
  const view = new DataView(buffer);
  view.setUint32(80, checked.triangleCount, true);
  walkAscii(bytes, checked.scale, (normal, points, index) => {
    [...normal, ...points.flat()].forEach((value, i) => view.setFloat32(84 + index * 50 + i * 4, value, true));
  });
  return buffer;
}

function fileName(name) {
  if (typeof name !== "string" || name.length > 512 || /[\x00-\x1f\x7f]/.test(name)) throw new Error("Supply a plain STL filename.");
  const clean = name.split(/[\\/]/).pop().trim();
  if (!clean || clean.length > 128) throw new Error("STL filename must contain 1 to 128 characters.");
  return clean;
}

function base64(bytes) {
  const chunks = [];
  for (let start = 0; start < bytes.length; start += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(start, start + 0x8000)));
  }
  return btoa(chunks.join(""));
}

async function digest(bytes) {
  if (!globalThis.crypto?.subtle) return null;
  try {
    const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return null;
  }
}

/** Import source bytes into a disposable, meter-scaled visual reference geometry. */
export async function importReferenceGeometry(input, { name, unit } = {}) {
  const filename = fileName(name);
  const bytes = new Uint8Array(bytesOf(input));
  const checked = validateStl(bytes, { unit });
  const sha256 = await digest(bytes);
  let geometry;
  try {
    geometry = new STLLoader().parse(loaderBytes(bytes, checked));
    if (geometry.getAttribute("position")?.count !== checked.triangleCount * 3) throw new Error("STL loader returned an unexpected vertex count.");
    geometry.scale(checked.scale, checked.scale, checked.scale);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    const metadata = Object.freeze({ schemaVersion: 1, format: "stl", name: filename, unit, data: base64(bytes), sha256,
      byteLength: bytes.byteLength, triangleCount: checked.triangleCount });
    const resource = Object.freeze({ geometry, metadata, dispose() { disposeReferenceGeometry(resource); } });
    resources.add(resource);
    return resource;
  } catch (error) {
    geometry?.dispose();
    throw error;
  }
}

/** Persist only the exact original bytes and explicit source units, never Three.js objects. */
export function serializeReferenceGeometry(resource) {
  if (!resources.has(resource)) throw new Error("Serialize an imported reference-geometry resource.");
  const text = JSON.stringify(resource.metadata);
  if (text.length > REFERENCE_LIMITS.maxProjectJsonChars) throw new Error("Reference geometry exceeds the project JSON budget.");
  return text;
}

/** Restore bounded metadata, revalidate every facet, and verify a saved digest when present. */
export async function restoreReferenceGeometry(value) {
  if (typeof value === "string") {
    if (value.length > REFERENCE_LIMITS.maxProjectJsonChars) throw new Error("Reference geometry exceeds the project JSON budget.");
    value = JSON.parse(value);
  }
  const keys = ["schemaVersion", "format", "name", "unit", "data", "sha256", "byteLength", "triangleCount"];
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some((key) => !keys.includes(key)) ||
      value.schemaVersion !== 1 || value.format !== "stl") throw new Error("Unsupported reference-geometry metadata.");
  fileName(value.name);
  scaleFor(value.unit);
  const encoded = value.data;
  if (typeof encoded !== "string" || encoded.length === 0 || encoded.length > 4 * Math.ceil(REFERENCE_LIMITS.maxSourceBytes / 3) ||
      encoded.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) throw new Error("Invalid or oversized STL base64 data.");
  if (!Number.isInteger(value.byteLength) || value.byteLength < 1 || value.byteLength > REFERENCE_LIMITS.maxSourceBytes ||
      !Number.isInteger(value.triangleCount) || value.triangleCount < 1 || value.triangleCount > REFERENCE_LIMITS.maxTriangles ||
      (value.sha256 !== null && !/^[a-f0-9]{64}$/.test(value.sha256))) throw new Error("Invalid reference-geometry counts or digest.");
  const decodedLength = encoded.length / 4 * 3 - (encoded.endsWith("==") ? 2 : encoded.endsWith("=") ? 1 : 0);
  if (decodedLength !== value.byteLength) throw new Error("STL byte count does not match the stored data.");
  const decoded = atob(encoded);
  const bytes = Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  if (base64(bytes) !== encoded) throw new Error("STL base64 must use canonical padding.");
  if (value.sha256 !== null) {
    const actual = await digest(bytes);
    if (actual === null) throw new Error("SHA-256 verification is unavailable for this saved reference; use a secure browser context.");
    if (actual !== value.sha256) throw new Error("STL source hash does not match the saved reference.");
  }
  const resource = await importReferenceGeometry(bytes, { name: value.name, unit: value.unit });
  if (resource.metadata.triangleCount !== value.triangleCount) {
    resource.dispose();
    throw new Error("STL triangle count does not match the saved reference.");
  }
  return resource;
}

/** Release the owned BufferGeometry once; callers separately remove meshes and dispose materials. */
export function disposeReferenceGeometry(resource) {
  if (!resource || !resources.has(resource) || disposed.has(resource)) return;
  disposed.add(resource);
  resource.geometry.dispose();
}
