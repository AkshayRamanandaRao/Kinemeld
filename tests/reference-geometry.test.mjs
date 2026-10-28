import assert from "node:assert/strict";
import { test } from "node:test";
import {
  REFERENCE_LIMITS,
  validateStl,
  importReferenceGeometry,
  serializeReferenceGeometry,
  restoreReferenceGeometry,
  disposeReferenceGeometry,
} from "../frontend/reference-geometry.js";

const triangle = [[0, 0, 0], [1, 0, 0], [0, 1, 0]];
const text = (vertices = triangle) => `solid reference
facet normal 0 0 0
outer loop
${vertices.map((point) => `vertex ${point.join(" ")}`).join("\n")}
endloop
endfacet
endsolid reference
`;
const ascii = (value = text()) => new TextEncoder().encode(value);

function binary(vertices = triangle, header = "binary reference") {
  const buffer = new ArrayBuffer(134);
  const bytes = new Uint8Array(buffer);
  bytes.set(new TextEncoder().encode(header));
  const view = new DataView(buffer);
  view.setUint32(80, 1, true);
  vertices.flat().forEach((value, index) => view.setFloat32(96 + index * 4, value, true));
  return bytes;
}

test("binary and ASCII honor explicit mm, m and inch scale without moving the origin", async () => {
  for (const input of [binary(), ascii()]) {
    for (const [unit, expected] of [["m", 1], ["mm", .001], ["in", .0254]]) {
      const result = await importReferenceGeometry(input, { name: "plate.stl", unit });
      assert.equal(result.metadata.triangleCount, 1);
      assert.equal(result.metadata.unit, unit);
      assert.equal(result.geometry.getAttribute("position").getX(1), Math.fround(expected));
      assert.equal(result.geometry.boundingBox.min.x, 0);
      assert.equal(result.geometry.getAttribute("normal").getZ(0), 1);
      result.dispose();
    }
  }
  const offset = await importReferenceGeometry(binary([[10, 20, 30], [11, 20, 30], [10, 21, 30]]), { name: "offset.stl", unit: "m" });
  assert.deepEqual(offset.geometry.boundingBox.min.toArray(), [10, 20, 30]);
  offset.dispose();
  assert.throws(() => validateStl(binary()), /units explicitly/);
  assert.throws(() => validateStl(binary(), { unit: "cm" }), /units explicitly/);
});

test("binary detection handles solid-prefixed headers and byte-offset views", async () => {
  const input = binary(triangle, "solid this is still binary");
  const storage = new Uint8Array(input.length + 11);
  storage.set(input, 7);
  const view = storage.subarray(7, 7 + input.length);
  assert.equal(validateStl(view, { unit: "m" }).encoding, "binary");
  const resource = await importReferenceGeometry(view, { name: "binary.stl", unit: "m" });
  assert.equal(resource.metadata.byteLength, 134);
  assert.deepEqual(new Uint8Array(Buffer.from(resource.metadata.data, "base64")), input);
  resource.dispose();
});

test("ASCII grammar accepts scientific numbers and multiple complete solids, rejects malformed facets", async () => {
  const valid = ascii(`  ${text().toUpperCase().replace("VERTEX 1 0 0", "VERTEX 1e+0 0.0 +0")}${text()}`);
  assert.equal(validateStl(valid, { unit: "m" }).triangleCount, 2);
  const resource = await importReferenceGeometry(valid, { name: "multi.stl", unit: "m" });
  assert.equal(resource.geometry.getAttribute("position").count, 6);
  resource.dispose();
  for (const invalid of [text().replace("endfacet", ""), text().replace("endloop", "vertex 0 0 1\nendloop"),
    text().replace("outer loop", "loop"), text() + "unexpected data", "solid empty\nendsolid empty\n",
    text().replace("vertex 1", "vertex NaN"), text().replace("vertex 1", "vertex 1e999"),
    text().replace("solid reference", "solid emoji🙂"), "solid " + "x".repeat(1025) + "\n" + text()]) {
    assert.throws(() => validateStl(ascii(invalid), { unit: "m" }));
  }
});

test("reject malformed binary, oversized counts and nonfinite or degenerate triangles", () => {
  for (const input of [binary().subarray(0, 133), new Uint8Array([...binary(), 0]), new Uint8Array(84),
    binary([[0, 0, 0], [1, 0, 0], [2, 0, 0]]), binary([[0, 0, 0], [Infinity, 0, 0], [0, 1, 0]]),
    binary([[1e6, 0, 0], [1e6 + .001, 0, 0], [1e6, 1, 0]])]) {
    assert.throws(() => validateStl(input, { unit: "m" }));
  }
  const normalNaN = binary();
  new DataView(normalNaN.buffer).setFloat32(84, NaN, true);
  assert.throws(() => validateStl(normalNaN, { unit: "m" }), /non-finite/);
  const count = REFERENCE_LIMITS.maxTriangles + 1;
  const tooMany = new Uint8Array(84 + count * 50);
  new DataView(tooMany.buffer).setUint32(80, count, true);
  assert.throws(() => validateStl(tooMany, { unit: "m" }), /200,000/);
  assert.throws(() => validateStl(new Uint8Array(REFERENCE_LIMITS.maxSourceBytes + 1), { unit: "m" }), /12 MiB/);
  assert.throws(() => validateStl(binary([[0, 0, 0], [2e6, 0, 0], [0, 1, 0]]), { unit: "m" }), /range/);
});

test("project round trip retains exact source bytes and selected units; dispose is idempotent", async () => {
  const input = ascii();
  const resource = await importReferenceGeometry(input, { name: "C:\\selected\\fixture.stl", unit: "in" });
  input.fill(0);
  assert.equal(resource.metadata.name, "fixture.stl");
  assert.equal(Object.isFrozen(resource.metadata), true);
  const saved = serializeReferenceGeometry(resource);
  const restored = await restoreReferenceGeometry(saved);
  assert.equal(serializeReferenceGeometry(restored), saved);
  assert.deepEqual(restored.geometry.getAttribute("position").array, resource.geometry.getAttribute("position").array);
  assert.equal(restored.metadata.sha256?.length, globalThis.crypto?.subtle ? 64 : undefined);
  let disposals = 0;
  resource.geometry.addEventListener("dispose", () => disposals++);
  resource.dispose();
  disposeReferenceGeometry(resource);
  assert.equal(disposals, 1);
  assert.equal(serializeReferenceGeometry(resource), saved);
  restored.dispose();
});

test("restore rejects corrupted hashes, count lies, unit overrides and oversized JSON/base64", async () => {
  const resource = await importReferenceGeometry(binary(), { name: "test.stl", unit: "mm" });
  const value = JSON.parse(serializeReferenceGeometry(resource));
  for (const changed of [{ ...value, sha256: "0".repeat(64) }, { ...value, triangleCount: 2 }, { ...value, byteLength: 1 },
    { ...value, unit: "automatic" }, { ...value, data: value.data + "%%%%" }, { ...value, url: "https://example.com/file.stl" },
    { ...value, data: "A".repeat(4 * Math.ceil(REFERENCE_LIMITS.maxSourceBytes / 3) + 4) }]) {
    await assert.rejects(() => restoreReferenceGeometry(changed));
  }
  await assert.rejects(() => restoreReferenceGeometry(" ".repeat(REFERENCE_LIMITS.maxProjectJsonChars + 1)), /JSON budget/);
  await assert.rejects(() => importReferenceGeometry(binary(), { name: "bad\0.stl", unit: "m" }), /filename/);
  resource.dispose();
});
