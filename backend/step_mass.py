"""Calculate explicit-density properties of one closed STEP occurrence in SI units."""
import base64
import binascii
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import step_geometry


class StepMassError(ValueError):
    """STEP mass properties are unavailable for the supplied solid."""


def decode_witness(encoded):
    """Decode a bounded occurrence witness carried in an HTTP header."""
    if not isinstance(encoded, str) or len(encoded) > 5464:
        raise StepMassError("Invalid STEP occurrence identity header.")
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 4096:
            raise ValueError("excessive witness")
        value = json.loads(data.decode("utf-8"))
    except (binascii.Error, UnicodeError, ValueError) as exc:
        raise StepMassError("Invalid STEP occurrence identity header.") from exc
    if not valid_witness(value):
        raise StepMassError("Invalid STEP occurrence identity.")
    return value


def valid_witness(value):
    if not isinstance(value, dict): return False
    if value == {"scheme":"single-part/1"}: return True
    path = value.get("path")
    return (set(value) == {"scheme", "path"} and value.get("scheme") == "step-nauo-id-path/1"
            and isinstance(path, list) and 1 <= len(path) <= 32
            and all(isinstance(item, str) and item for item in path)
            and len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 4096)


def calculate(data, density, part_id, witness=None):
    """Return properties about the centre of mass in world coordinates without altering a model."""
    if not isinstance(data, bytes) or not 1 <= len(data) <= step_geometry.MAX_STEP_BYTES:
        raise StepMassError("STEP file must contain between 1 byte and 12 MiB.")
    if b"ISO-10303-21;" not in data[:1024].upper():
        raise StepMassError("Expected an ISO 10303-21 STEP file.")
    if type(density) not in (float, int) or not math.isfinite(density) or not 0 < density <= 1e9:
        raise StepMassError("Density must be finite and greater than zero, at most 1e9 kg/m³.")
    if not isinstance(part_id, str) or not re.fullmatch(r"part-[1-9][0-9]{0,2}", part_id) or int(part_id[5:]) > step_geometry.MAX_PARTS:
        raise StepMassError("Select a STEP occurrence ID from part-1 through part-256.")
    if witness is not None and not valid_witness(witness):
        raise StepMassError("Invalid STEP occurrence identity.")
    witness_arg = base64.b64encode(json.dumps(witness, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii") if witness is not None else ""
    with tempfile.TemporaryDirectory(prefix="mbdyn-step-mass-") as folder:
        source = Path(folder) / "source.step"
        output = Path(folder) / "mass.json"
        source.write_bytes(data)
        try:
            proc = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(source), str(output), part_id, str(density), witness_arg],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=step_geometry.TIMEOUT_SECONDS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        except subprocess.TimeoutExpired as exc:
            raise StepMassError("STEP mass-property calculation exceeded the 90-second limit.") from exc
        except OSError as exc:
            raise StepMassError("The isolated STEP mass-property worker could not be started.") from exc
        if not output.is_file() or output.stat().st_size > 65536:
            raise StepMassError("STEP mass-property worker failed or returned excessive output.")
        try:
            result = json.loads(output.read_text(encoding="utf8"))
        except (OSError, ValueError) as exc:
            raise StepMassError("STEP mass-property worker returned an unreadable result.") from exc
        if proc.returncode or "error" in result:
            raise StepMassError(result.get("error", "STEP mass-property calculation failed."))
    return {"format":"step-mass/1", "sha256":hashlib.sha256(data).hexdigest(), "partId":part_id,
            "density":density, "units":{"length":"m", "volume":"m^3", "mass":"kg", "inertia":"kg*m^2"},
            "reference":"world axes, inertia about centre of mass", **result}


def _worker(source, selected, density, expected_witness=None):
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TColStd import TColStd_SequenceOfAsciiString
        from OCP.TDF import TDF_Label, TDF_LabelSequence
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS, TopoDS_Iterator
        from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
    except ImportError as exc:
        raise StepMassError("STEP mass properties need the OpenCascade OCP Python package.") from exc
    reader=STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        raise StepMassError("OpenCascade could not read this STEP file.")
    length_units, angle_units, solid_units=(TColStd_SequenceOfAsciiString() for _ in range(3))
    reader.Reader().FileUnits(length_units, angle_units, solid_units)
    units=[length_units.Value(i).ToCString() for i in range(1,length_units.Length()+1)]
    if not units:
        raise StepMassError("The STEP file does not declare a recognizable length unit.")
    Interface_Static.SetCVal_s("xstep.cascade.unit","MM")
    document=TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    if not reader.Transfer(document):
        raise StepMassError("OpenCascade could not transfer this STEP document.")
    tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots=TDF_LabelSequence();tool.GetFreeShapes(roots)
    source_ids=step_geometry.source_occurrence_ids(reader,tool)
    count=0; chosen=None; chosen_path=None; paths=[]; triangles=0; single_root_leaf=False

    def visit(label,parent,path,depth):
        nonlocal count,chosen,chosen_path,triangles,single_root_leaf
        if depth>32: raise StepMassError("STEP assembly hierarchy exceeds 32 levels.")
        referred=TDF_Label();is_reference=XCAFDoc_ShapeTool.GetReferredShape_s(label,referred)
        target=referred if is_reference else label
        if depth==0 and roots.Length()==1:
            single_root_leaf=not is_reference and not XCAFDoc_ShapeTool.IsAssembly_s(target)
        location=parent.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label)) if is_reference else parent
        if is_reference:
            source_id=source_ids.get(step_geometry.label_entry(label))
            path=path+[source_id] if path is not None and source_id else None
        if XCAFDoc_ShapeTool.IsAssembly_s(target):
            children=TDF_LabelSequence();XCAFDoc_ShapeTool.GetComponents_s(target,children)
            for i in range(1,children.Length()+1):visit(children.Value(i),location,path,depth+1)
            return
        shape=XCAFDoc_ShapeTool.GetShape_s(target)
        if shape.IsNull(): return
        BRepMesh_IncrementalMesh(shape,0.5,False,0.3,True)
        faces=TopExp_Explorer(shape,TopAbs_FACE); has_triangles=False
        while faces.More():
            mesh=BRep_Tool.Triangulation_s(TopoDS.Face_s(faces.Current()),TopLoc_Location())
            if mesh is not None:
                triangles+=mesh.NbTriangles()
                if triangles>step_geometry.MAX_TRIANGLES: raise StepMassError("STEP file exceeds the triangle limit.")
                has_triangles=has_triangles or (mesh.NbNodes()>0 and mesh.NbTriangles()>0)
            faces.Next()
        if not has_triangles:return
        count+=1
        if count>step_geometry.MAX_PARTS: raise StepMassError("STEP file exceeds the 256-part limit.")
        paths.append(path)
        if f"part-{count}" == selected: chosen=shape.Moved(location);chosen_path=path
    for i in range(1,roots.Length()+1):visit(roots.Value(i),TopLoc_Location(),[],0)
    if chosen is None: raise StepMassError("The selected STEP occurrence was not found.")
    witness = ({"scheme":"step-nauo-id-path/1", "path":chosen_path}
               if chosen_path and paths.count(chosen_path)==1 else {"scheme":"single-part/1"} if count==1 and single_root_leaf else None)
    if not witness or count>1 and not expected_witness:
        raise StepMassError("STEP occurrence identity is missing or ambiguous; mass properties cannot be calculated safely.")
    if expected_witness is not None and witness != expected_witness:
        raise StepMassError("STEP occurrence identity does not match the selected visual part.")

    def validate_solids(shape):
        kind=shape.ShapeType()
        if kind == TopAbs_SOLID:
            if not BRepCheck_Analyzer(shape,True).IsValid():raise StepMassError("The selected solid has invalid topology.")
            shells=TopExp_Explorer(shape,TopAbs_SHELL); count_shells=0
            while shells.More():
                count_shells+=1
                if not BRep_Tool.IsClosed_s(shells.Current()):raise StepMassError("The selected solid has an open shell.")
                shells.Next()
            if not count_shells:raise StepMassError("The selected solid has no closed shells.")
            return 1
        if kind not in (TopAbs_COMPOUND,TopAbs_COMPSOLID):
            raise StepMassError("The selected occurrence contains non-solid geometry; use closed solids only.")
        children=TopoDS_Iterator(shape);number=0
        while children.More():
            number+=validate_solids(children.Value());children.Next()
            if number>256:raise StepMassError("The occurrence exceeds the 256-solid limit.")
        if not number:raise StepMassError("The selected occurrence contains no closed solids.")
        return number

    solid_count=validate_solids(chosen)
    props=GProp_GProps();BRepGProp.VolumeProperties_s(chosen,props,True,False,False)
    volume=props.Mass()*1e-9;centre=props.CentreOfMass();com=[centre.X()*1e-3,centre.Y()*1e-3,centre.Z()*1e-3]
    mat=props.MatrixOfInertia();inertia=[[mat.Value(i,j)*1e-15*density for j in range(1,4)] for i in range(1,4)]
    values=[volume,volume*density,*com,*[v for row in inertia for v in row]]
    if not all(math.isfinite(v) for v in values) or volume<=0 or max(abs(v) for v in com)>1e6:
        raise StepMassError("The selected solid has invalid, non-finite or excessively large mass properties.")
    return {"sourceLengthUnits":units,"occurrenceWitness":witness,"solidCount":solid_count,"volume":volume,"mass":volume*density,
            "centerOfMass":{"x":com[0],"y":com[1],"z":com[2]},"inertia":inertia}


if __name__ == "__main__" and len(sys.argv)==7 and sys.argv[1]=="--worker":
    try:
        result=_worker(Path(sys.argv[2]),sys.argv[4],float(sys.argv[5]),decode_witness(sys.argv[6]) if sys.argv[6] else None)
        Path(sys.argv[3]).write_text(json.dumps(result,allow_nan=False,separators=(",",":")),encoding="utf8")
    except Exception as exc:
        Path(sys.argv[3]).write_text(json.dumps({"error":str(exc)}),encoding="utf8")
        sys.exit(1)
