"""Bounded, local STEP tessellation using the optional OpenCascade OCP runtime."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import subprocess
import sys
import tempfile

MAX_STEP_BYTES = 12 * 1024 * 1024
MAX_TRIANGLES = 150_000
MAX_PARTS = 256
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
TIMEOUT_SECONDS = 90


class StepError(ValueError):
    """A STEP conversion failed or exceeded a supported bound."""


def label_entry(label):
    """Return a transient XCAF label key for joining facts within one transfer."""
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def source_occurrence_ids(reader, shape_tool):
    """Map transferred labels to unique source NAUO IDs, never to model ordinals.

    This map is valid only during this transfer. IDs are source-provided; absent,
    duplicate or ambiguous identifiers are deliberately omitted.
    """
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.STEPConstruct import STEPConstruct_Tool
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence
    model = reader.Reader().StepModel()
    occurrences = []
    for index in range(1, model.NbEntities() + 1):
        entity = model.Value(index)
        if not isinstance(entity, StepRepr_NextAssemblyUsageOccurrence):
            continue
        identifier = entity.Id()
        value = identifier.ToCString() if identifier is not None else ""
        occurrences.append((entity, value))
    counts = Counter(value for _, value in occurrences)
    tool = STEPConstruct_Tool(reader.Reader().WS())
    candidates = []
    for entity, value in occurrences:
        label = STEPCAFControl_Reader.FindInstance_s(entity, shape_tool, tool, reader.GetShapeLabelMap())
        if not label.IsNull():
            candidates.append((label_entry(label), value))
    label_counts = Counter(key for key, _ in candidates)
    return {key: value for key, value in candidates
            if label_counts[key] == 1 and counts[value] == 1 and isinstance(value, str)
            and value.strip() and len(value) <= 256 and not any(ord(c) < 32 or ord(c) == 127 for c in value)}


def status():
    """Probe the same Python environment that runs isolated STEP conversion."""
    try:
        probe = subprocess.run([sys.executable, "-B", "-c", "import OCP; from OCP.STEPCAFControl import STEPCAFControl_Reader; from OCP.BRepMesh import BRepMesh_IncrementalMesh"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        if probe.returncode == 0:
            return {"available": True, "detail": "OpenCascade STEP import is available in the application's Python environment."}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {"available": False, "detail": "Install the OpenCascade OCP Python package in the application's Python environment to import STEP files."}


def convert_step(data, name="Imported STEP"):
    """Convert bytes to SI-metre occurrence meshes; source bytes remain with the caller."""
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_STEP_BYTES:
        raise StepError(f"STEP file must contain between 1 and {MAX_STEP_BYTES} bytes.")
    if not isinstance(name, str) or not 1 <= len(name) <= 200:
        raise StepError("A STEP file name of at most 200 characters is required.")
    if b"ISO-10303-21;" not in data[:1024].upper():
        raise StepError("Expected an ISO 10303-21 STEP file.")
    with tempfile.TemporaryDirectory(prefix="mbdyn-step-") as directory:
        source = Path(directory) / "source.step"
        output = Path(directory) / "mesh.json"
        source.write_bytes(data)
        try:
            proc = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(source), str(output)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=TIMEOUT_SECONDS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        except subprocess.TimeoutExpired as exc:
            raise StepError("STEP conversion exceeded the 90-second limit.") from exc
        except OSError as exc:
            raise StepError("The isolated STEP converter could not be started.") from exc
        if not output.is_file() or output.stat().st_size > MAX_OUTPUT_BYTES:
            raise StepError("STEP converter failed or its output exceeded the size limit.")
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StepError("STEP converter returned an unreadable result.") from exc
        if proc.returncode or "error" in result:
            raise StepError(result.get("error", "STEP converter process failed."))
    return {"format": "step", "name": name, "sha256": hashlib.sha256(data).hexdigest(),
            "byteLength": len(data), "units": "m", **result}


def _worker(source):
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCP.gp import gp_Vec
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDF import TDF_Label, TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS
        from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    except ImportError as exc:
        raise StepError("STEP import needs the OpenCascade OCP Python package in the app's Python environment.") from exc
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        raise StepError("OpenCascade could not read this STEP file.")
    length_units, angle_units, solid_units = (TColStd_SequenceOfAsciiString() for _ in range(3))
    reader.Reader().FileUnits(length_units, angle_units, solid_units)
    units = [length_units.Value(i).ToCString() for i in range(1, length_units.Length() + 1)]
    if not units:
        raise StepError("The STEP file does not declare a recognizable length unit.")
    # OpenCascade's STEP transfer uses millimetres internally; convert every output point to metres.
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    if not reader.Transfer(document):
        raise StepError("OpenCascade could not transfer this STEP document.")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    source_ids = source_occurrence_ids(reader, tool)
    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    # A lone tessellated leaf in an assembly does not prove that another leaf
    # was not skipped by a different importer. The whole-source fallback is
    # restricted to a single free, non-assembly, non-reference root.
    single_leaf_root = False
    if roots.Length() == 1:
        root = roots.Value(1)
        single_leaf_root = (not XCAFDoc_ShapeTool.IsAssembly_s(root)
                            and not XCAFDoc_ShapeTool.GetReferredShape_s(root, TDF_Label()))
    parts, total_triangles = [], 0

    def label_name(label, fallback):
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            value = attr.Get().ToExtString().strip()
            if value:
                return value[:160]
        return fallback

    def visit(label, parent, path, occurrence_path, depth):
        nonlocal total_triangles
        if depth > 32:
            raise StepError("STEP assembly hierarchy exceeds 32 levels.")
        referred = TDF_Label()
        is_reference = XCAFDoc_ShapeTool.GetReferredShape_s(label, referred)
        if is_reference and occurrence_path is not None:
            occurrence_id = source_ids.get(label_entry(label))
            occurrence_path = occurrence_path + [occurrence_id] if occurrence_id else None
        target = referred if is_reference else label
        location = parent.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label)) if is_reference else parent
        product_name = label_name(target, "")
        name = label_name(label, product_name or f"Part {len(parts)+1}")
        current_path = path + [name]
        if XCAFDoc_ShapeTool.IsAssembly_s(target):
            children = TDF_LabelSequence()
            XCAFDoc_ShapeTool.GetComponents_s(target, children)
            for i in range(1, children.Length()+1):
                visit(children.Value(i), location, current_path, occurrence_path, depth+1)
            return
        shape = XCAFDoc_ShapeTool.GetShape_s(target)
        if shape.IsNull():
            return
        if len(parts) >= MAX_PARTS:
            raise StepError(f"STEP file exceeds the {MAX_PARTS}-part limit.")
        BRepMesh_IncrementalMesh(shape, 0.5, False, 0.3, True)
        positions, indices, faces = [], [], []
        placement = location.Transformation()

        def metres(point):
            point = point.Transformed(placement)
            return [round(point.X()*.001, 9), round(point.Y()*.001, 9), round(point.Z()*.001, 9)]

        def direction(vector):
            vector = vector.Transformed(placement)
            return [round(vector.X(), 9), round(vector.Y(), 9), round(vector.Z(), 9)]

        def feature(face):
            # Analytic face geometry for picking joint anchors and axes; the adaptor includes the
            # face's own location, so only the assembly placement is applied here.
            surface = BRepAdaptor_Surface(face, True)
            kind = surface.GetType()
            if kind == GeomAbs_Cylinder:
                cylinder = surface.Cylinder()
                axis = cylinder.Axis()
                start, end = surface.FirstVParameter(), surface.LastVParameter()
                centre = axis.Location().Translated(gp_Vec(axis.Direction()).Multiplied((start + end) / 2))
                return {"type": "cylinder", "centre": metres(centre), "axis": direction(axis.Direction()),
                        "radius": round(cylinder.Radius()*.001, 9), "length": round(abs(end - start)*.001, 9)}
            if kind == GeomAbs_Plane:
                plane = surface.Plane()
                normal = plane.Axis().Direction()
                if face.Orientation() == TopAbs_REVERSED:
                    normal = normal.Reversed()
                return {"type": "plane", "point": metres(plane.Location()), "normal": direction(normal)}
            return None

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            first_triangle = len(indices)//3
            face_location = TopLoc_Location()
            triangulation = BRep_Tool.Triangulation_s(face, face_location)
            if triangulation is not None:
                total_triangles += triangulation.NbTriangles()
                if total_triangles > MAX_TRIANGLES:
                    raise StepError(f"STEP file exceeds the {MAX_TRIANGLES}-triangle limit.")
                transform = location.Multiplied(face_location).Transformation()
                offset = len(positions)//3
                for i in range(1, triangulation.NbNodes()+1):
                    point = triangulation.Node(i).Transformed(transform)
                    xyz = [point.X()*.001, point.Y()*.001, point.Z()*.001]
                    if not all(math.isfinite(value) and abs(value) <= 1e6 for value in xyz):
                        raise StepError("STEP contains non-finite or excessively large coordinates.")
                    positions.extend(xyz)
                for i in range(1, triangulation.NbTriangles()+1):
                    a,b,c = triangulation.Triangle(i).Get()
                    if face.Orientation() == TopAbs_REVERSED:
                        b,c = c,b
                    indices.extend([offset+a-1, offset+b-1, offset+c-1])
                count = len(indices)//3 - first_triangle
                described = feature(face) if count else None
                if described:
                    faces.append({"triangles": [first_triangle, count], **described})
            explorer.Next()
        if positions and indices:
            parts.append({"id":f"part-{len(parts)+1}", "name":name, "path":current_path,
                          "productName":product_name or None, "positions":positions, "indices":indices, "faces":faces,
                          "_occurrencePath":occurrence_path})
    for i in range(1, roots.Length()+1):
        visit(roots.Value(i), TopLoc_Location(), [], [], 0)
    if not parts:
        raise StepError("The STEP file contains no triangulatable faces.")
    paths = Counter(tuple(part['_occurrencePath']) for part in parts if part['_occurrencePath'])
    for part in parts:
        path = part.pop('_occurrencePath')
        if path and paths[tuple(path)] == 1:
            part['occurrenceWitness'] = {'scheme':'step-nauo-id-path/1', 'path':path}
        elif single_leaf_root and len(parts) == 1:
            part['occurrenceWitness'] = {'scheme':'single-part/1'}
        else:
            part['occurrenceWitness'] = None
    return {"sourceLengthUnits": units, "triangleCount": total_triangles, "parts": parts}


if __name__ == "__main__" and len(sys.argv) == 4 and sys.argv[1] == "--worker":
    try:
        result = _worker(Path(sys.argv[2]))
        Path(sys.argv[3]).write_text(json.dumps(result, allow_nan=False, separators=(",", ":")), encoding="utf-8")
    except Exception as exc:
        Path(sys.argv[3]).write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        sys.exit(1)
