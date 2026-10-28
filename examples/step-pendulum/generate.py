"""Generate an original, initial-pose CAD solid for the authored pendulum."""
import math
from pathlib import Path

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec


def main():
    length_mm, width_mm, angle = 1000., 30., math.radians(-8.)
    center_x_mm = -500. * math.sin(angle)
    center_z_mm = -500. * math.cos(angle)
    shape = BRepPrimAPI_MakeBox(gp_Pnt(-width_mm/2, -width_mm/2, -length_mm/2), width_mm, width_mm, length_mm).Shape()
    transform = gp_Trsf()
    transform.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,1,0)), angle)
    transform.SetTranslationPart(gp_Vec(center_x_mm, 0, center_z_mm))
    transformed = BRepBuilderAPI_Transform(shape, transform, True).Shape()
    document = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    label = tool.AddShape(transformed, False)
    TDataStd_Name.Set_s(label, TCollection_ExtendedString("Rigid pendulum link"))
    writer = STEPCAFControl_Writer()
    if not writer.Transfer(document):
        raise RuntimeError("Failed to construct STEP document")
    output = Path(__file__).with_name("pendulum.step")
    if writer.Write(str(output)) != IFSelect_RetDone:
        raise RuntimeError("Failed to write STEP document")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
