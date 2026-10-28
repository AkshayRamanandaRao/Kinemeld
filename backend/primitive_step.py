"""Create small, bounded STEP solids in an isolated OpenCascade worker."""
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import polygon_profile
import revolution_profile

MAX_STEP_BYTES = 12 * 1024 * 1024
TIMEOUT_SECONDS = 45
SHAPES = {"brick": ("x", "y", "z"), "cylinder": ("radius", "length"),
          "sphere": ("radius",), "ellipsoid": ("x", "y", "z"),
          "regular-extrusion": ("radius", "length", "sides"),
          "polygon-extrusion": ("vertices", "length"), "revolution": ("vertices",)}


class PrimitiveError(ValueError):
    """A primitive definition or OpenCascade operation is invalid."""


def validate(spec):
    """Validate dimensions in metres and an explicit planar or Euler123 body pose."""
    if not isinstance(spec, dict) or set(spec) != {"shape", "dimensions", "pose"}:
        raise PrimitiveError("Supply shape, dimensions and pose only.")
    shape = spec["shape"]
    if not isinstance(shape, str) or shape not in SHAPES:
        raise PrimitiveError("Choose a supported primitive or polygon extrusion.")
    dimensions, pose = spec["dimensions"], spec["pose"]
    if not isinstance(dimensions, dict) or set(dimensions) != set(SHAPES[shape]):
        raise PrimitiveError("Supply exactly the dimensions required by the selected solid.")
    if not isinstance(pose, dict) or set(pose) not in ({"x", "z", "angleDeg"}, {"x", "y", "z", "rx", "ry", "rz"}):
        raise PrimitiveError("Supply a planar x, z, angleDeg or spatial x, y, z, rx, ry, rz pose.")
    def finite(value):
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    for key,value in dimensions.items():
        if key == 'vertices':
            try:
                if shape == 'revolution':revolution_profile.profile(value)
                else:polygon_profile.validate(value)
            except ValueError as exc:raise PrimitiveError(str(exc)) from exc
            continue
        if key == 'sides':
            if type(value) is not int or not 3 <= value <= 64:
                raise PrimitiveError("A regular extrusion requires an integer from 3 to 64 sides.")
            continue
        if not finite(value) or not 0 < value <= 1000:
            raise PrimitiveError("Solid dimensions must be finite and greater than zero, up to 1,000 m.")
    position=("x", "z") if "angleDeg" in pose else ("x", "y", "z")
    angles=("angleDeg",) if "angleDeg" in pose else ("rx", "ry", "rz")
    if any(not finite(pose[key]) or abs(pose[key]) > 1000 for key in position):
        raise PrimitiveError("Body centre coordinates must be finite and within ±1,000 m.")
    if any(not finite(pose[key]) or abs(pose[key]) > 360 for key in angles):
        raise PrimitiveError("Body angles must be finite and within ±360 degrees.")


def generate_step(spec):
    """Return STEP bytes for a validated primitive in its initial body pose."""
    validate(spec)
    with tempfile.TemporaryDirectory(prefix="mbdyn-primitive-") as directory:
        root = Path(directory)
        source, output, status = root / "primitive.json", root / "primitive.step", root / "status.json"
        source.write_text(json.dumps(spec, allow_nan=False), encoding="utf-8")
        try:
            process = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(source), str(output), str(status)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     timeout=TIMEOUT_SECONDS, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        except subprocess.TimeoutExpired as exc:
            raise PrimitiveError("Primitive STEP generation timed out after 45 seconds.") from exc
        except OSError as exc:
            raise PrimitiveError("Could not start the isolated primitive STEP generator.") from exc
        if process.returncode != 0:
            try:
                detail = json.loads(status.read_text(encoding="utf-8"))["error"]
            except (OSError, ValueError, KeyError, TypeError):
                detail = "OpenCascade primitive generation failed."
            raise PrimitiveError(str(detail))
        if not output.is_file() or not 0 < output.stat().st_size <= MAX_STEP_BYTES:
            raise PrimitiveError("Primitive STEP output is missing or exceeds 12 MiB.")
        data = output.read_bytes()
        if b"ISO-10303-21;" not in data[:1024].upper():
            raise PrimitiveError("OpenCascade did not produce a valid STEP envelope.")
        return data


def _worker(spec, output):
    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform, BRepBuilderAPI_Transform, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeSphere, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDataStd import TDataStd_Name
        from OCP.TDocStd import TDocStd_Document
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_GTrsf, gp_Pnt, gp_Trsf, gp_Vec
    except ImportError as exc:
        raise PrimitiveError("Primitive STEP generation needs the OpenCascade OCP Python package.") from exc
    validate(spec)
    shape, d, pose = spec["shape"], spec["dimensions"], spec["pose"]
    if shape == "brick":
        x,y,z=(1000*d[key] for key in ("x", "y", "z"))
        solid = BRepPrimAPI_MakeBox(gp_Pnt(-x/2,-y/2,-z/2),x,y,z).Shape()
    elif shape == "cylinder":
        r,length=1000*d["radius"],1000*d["length"]
        solid = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0,0,-length/2),gp_Dir(0,0,1)),r,length).Shape()
    elif shape == "sphere":
        solid = BRepPrimAPI_MakeSphere(gp_Pnt(0,0,0),1000*d["radius"]).Shape()
    elif shape in ("regular-extrusion", "polygon-extrusion"):
        length=1000*d['length']
        polygon=BRepBuilderAPI_MakePolygon()
        if shape == 'regular-extrusion':
            r,n=1000*d['radius'],d['sides'];points=[(r*math.cos(2*math.pi*i/n),r*math.sin(2*math.pi*i/n)) for i in range(n)]
        else:
            cx,cy=polygon_profile.validate(d['vertices']);points=[(1000*(p['x']-cx),1000*(p['y']-cy)) for p in d['vertices']]
        for x,y in points:polygon.Add(gp_Pnt(x,y,-length/2))
        polygon.Close()
        solid=BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(),gp_Vec(0,0,length)).Shape()
    elif shape == 'revolution':
        props=revolution_profile.profile(d['vertices']);polygon=BRepBuilderAPI_MakePolygon()
        for point in d['vertices']:polygon.Add(gp_Pnt(1000*point['x'],0,1000*(point['y']-props['z'])))
        polygon.Close();face=BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
        solid=BRepPrimAPI_MakeRevol(face,gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),2*math.pi,True).Shape()
        if solid.IsNull() or not BRepCheck_Analyzer(solid,True).IsValid():raise PrimitiveError('The revolution profile did not produce a valid solid.')
    else:
        solid = BRepPrimAPI_MakeSphere(gp_Pnt(0,0,0),1000).Shape()
        scaling = gp_GTrsf()
        for index,key in enumerate(("x","y","z"),1):
            scaling.SetValue(index,index,d[key])
        solid = BRepBuilderAPI_GTransform(solid,scaling,True).Shape()
    # Euler123 matches MBDyn and the STEP playback binding: Rx * Ry * Rz.
    rx,ry,rz=(0.,math.radians(pose["angleDeg"]),0.) if "angleDeg" in pose else tuple(math.radians(pose[k]) for k in ("rx","ry","rz"))
    cx,sx=math.cos(rx),math.sin(rx);cy,sy=math.cos(ry),math.sin(ry);cz,sz=math.cos(rz),math.sin(rz)
    rotation=((cy*cz,-cy*sz,sy),(cx*sz+sx*sy*cz,cx*cz-sx*sy*sz,-sx*cy),(sx*sz-cx*sy*cz,sx*cz+cx*sy*sz,cx*cy))
    x,y,z=1000*pose["x"],1000*pose.get("y",0.),1000*pose["z"]
    transform=gp_Trsf()
    transform.SetValues(rotation[0][0],rotation[0][1],rotation[0][2],x,rotation[1][0],rotation[1][1],rotation[1][2],y,rotation[2][0],rotation[2][1],rotation[2][2],z)
    placed=BRepBuilderAPI_Transform(solid,transform,True).Shape()
    if placed.IsNull():
        raise PrimitiveError("OpenCascade did not construct a solid for these dimensions.")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    document=TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    label=XCAFDoc_DocumentTool.ShapeTool_s(document.Main()).AddShape(placed,False)
    TDataStd_Name.Set_s(label,TCollection_ExtendedString(f"Generated {shape}"))
    writer=STEPCAFControl_Writer()
    if not writer.Transfer(document) or writer.Write(str(output)) != IFSelect_RetDone:
        raise PrimitiveError("OpenCascade could not export the primitive to STEP.")


if __name__ == "__main__" and len(sys.argv) == 5 and sys.argv[1] == "--worker":
    try:
        _worker(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")), Path(sys.argv[3]))
    except Exception as exc:
        Path(sys.argv[4]).write_text(json.dumps({"error": str(exc)}), encoding="utf-8")
        sys.exit(1)
