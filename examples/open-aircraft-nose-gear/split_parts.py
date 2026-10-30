"""Write each occurrence of the original nose-gear assembly to its own STEP file.

The source assembly (`source-assembly.step`) is read with OpenCascade exactly as Kinemeld's
importer reads it. Every occurrence is written, with its STEP product name, to `parts/` in
millimetres. Its assembly placement is applied and the whole gear is translated by the same
offset as the kinematic example, so the axle centre lies 0.35 m above the origin. The
geometry is otherwise unchanged. Run from the repository root:

    python examples/open-aircraft-nose-gear/split_parts.py
"""
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from ocp_compat import TDF_LabelSequence  # noqa: E402

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform  # noqa: E402
from OCP.Interface import Interface_Static  # noqa: E402
from OCP.IFSelect import IFSelect_RetDone  # noqa: E402
from OCP.STEPCAFControl import STEPCAFControl_Reader  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.StepBasic import StepBasic_Product  # noqa: E402
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString  # noqa: E402
from OCP.TDataStd import TDataStd_Name  # noqa: E402
from OCP.TDF import TDF_Label  # noqa: E402
from OCP.TDocStd import TDocStd_Document  # noqa: E402
from OCP.TopLoc import TopLoc_Location  # noqa: E402
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool  # noqa: E402
from OCP.gp import gp_Trsf, gp_Vec  # noqa: E402

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source-assembly.step"
SHA = "b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575"
# Same translation as examples/open-aircraft-nose-kinematics/generate.py, in millimetres.
SHIFT = (-1362.4089479151387, -140.4889931316861, -676.3863684055106)
# File name for each occurrence, in source order (NAUO1-NAUO11).
FILES = ["01-piston", "02-shaft", "03-strut", "04-upper-link", "05-wheel-hub", "06-lower-link",
         "07-upper-pin-bolt", "08-scissor-pin-bolt", "09-lower-pin-bolt", "10-wheel-left", "11-wheel-right"]


def name(label):
    attribute = TDataStd_Name()
    return attribute.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else ""


def occurrences():
    """(product name, placed shape) for every leaf occurrence, in the importer's order."""
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.ReadFile(str(SOURCE))
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    reader.Transfer(document)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    found = []

    def visit(label, parent):
        referred = TDF_Label()
        is_reference = XCAFDoc_ShapeTool.GetReferredShape_s(label, referred)
        target = referred if is_reference else label
        location = parent.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label)) if is_reference else parent
        if XCAFDoc_ShapeTool.IsAssembly_s(target):
            children = TDF_LabelSequence()
            XCAFDoc_ShapeTool.GetComponents_s(target, children)
            for i in range(1, children.Length() + 1):
                visit(children.Value(i), location)
            return
        found.append((name(target), XCAFDoc_ShapeTool.GetShape_s(target).Moved(location)))

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        visit(roots.Value(i), TopLoc_Location())
    return found


def write(shape, product, path):
    shift = gp_Trsf()
    shift.SetTranslation(gp_Vec(*SHIFT))
    placed = BRepBuilderAPI_Transform(shape, shift, True).Shape()
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    # A part made of several solids stays one product rather than an assembly of solids.
    Interface_Static.SetIVal_s("write.step.assembly", 0)
    writer = STEPControl_Writer()
    if writer.Transfer(placed, STEPControl_AsIs) != IFSelect_RetDone:
        raise RuntimeError(f"Could not transfer {path.name}")
    # One product per file, carrying the source product name.
    model = writer.Model()
    for index in range(1, model.NbEntities() + 1):
        entity = model.Value(index)
        if isinstance(entity, StepBasic_Product):
            entity.SetName(TCollection_HAsciiString(product))
            entity.SetId(TCollection_HAsciiString(product))
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"Could not write {path.name}")


def main():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SHA:
        raise ValueError("Source STEP hash mismatch")
    parts = occurrences()
    if len(parts) != len(FILES):
        raise ValueError(f"Expected {len(FILES)} occurrences, found {len(parts)}")
    out = HERE / "parts"
    out.mkdir(exist_ok=True)
    for (product, shape), stem in zip(parts, FILES):
        write(shape, product, out / f"{stem}.step")
        print(f"{stem}.step  {product}")


if __name__ == "__main__":
    main()
