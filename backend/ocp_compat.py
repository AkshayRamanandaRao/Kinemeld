"""OpenCascade classes whose OCP names differ between cadquery-ocp 7.9 and 8.

OCP 8 exposes NCollection sequences in ``OCP.collections`` instead of under the OCCT typedef
names. Import this module only where OCP itself is expected; ImportError means OCP is missing.
"""
try:
    from OCP.TColStd import TColStd_SequenceOfAsciiString
    from OCP.TDF import TDF_LabelSequence
except ImportError:
    from OCP.collections import Sequence_TCollection_AsciiString as TColStd_SequenceOfAsciiString
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence

__all__ = ["TColStd_SequenceOfAsciiString", "TDF_LabelSequence"]
