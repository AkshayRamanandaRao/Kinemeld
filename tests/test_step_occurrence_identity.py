"""Source occurrence identity tests against the shipped aircraft STEP assembly."""
import importlib.util
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import step_geometry


@unittest.skipUnless(importlib.util.find_spec('OCP'), 'OCP is required for STEP transfer')
class SourceOccurrenceIdentityTests(unittest.TestCase):
    def _nested_source(self, path):
        """Write two instances of a subassembly, each containing two instances of a solid."""
        from OCP.BRep import BRep_Builder
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.STEPCAFControl import STEPCAFControl_Writer
        from OCP.TCollection import TCollection_ExtendedString
        from OCP.TDocStd import TDocStd_Document
        from OCP.TopLoc import TopLoc_Location
        from OCP.TopoDS import TopoDS_Compound
        from OCP.XCAFDoc import XCAFDoc_DocumentTool
        from OCP.gp import gp_Trsf, gp_Vec

        doc = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
        tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        builder = BRep_Builder()
        def assembly():
            compound = TopoDS_Compound()
            builder.MakeCompound(compound)
            return tool.AddShape(compound, True)
        def at(x, y):
            transform = gp_Trsf()
            transform.SetTranslation(gp_Vec(x, y, 0))
            return TopLoc_Location(transform)
        root, nested = assembly(), assembly()
        solid = tool.AddShape(BRepPrimAPI_MakeBox(10, 12, 15).Shape(), False)
        tool.AddComponent(nested, solid, at(0, 0))
        tool.AddComponent(nested, solid, at(20, 0))
        tool.AddComponent(root, nested, at(0, 0))
        tool.AddComponent(root, nested, at(0, 30))
        tool.UpdateAssemblies()
        writer = STEPCAFControl_Writer()
        self.assertTrue(writer.Transfer(doc))
        writer.Write(str(path))
        # OCCT's STEP writer repeats local NAUO Ids in different assemblies.
        # Give each source entity a distinct Id, as required by our witness.
        data = path.read_bytes()
        counter = iter(range(1, 5))
        pattern = rb"(NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*)'[^']*'"
        data, count = re.subn(pattern, lambda match: match.group(1) + ("'occ-%d'" % next(counter)).encode(), data)
        self.assertEqual(count, 4)
        path.write_bytes(data)

    def test_nested_repeated_subassemblies_have_complete_distinct_paths(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'nested.step'
            self._nested_source(path)
            parts = step_geometry._worker(path)['parts']
            source = path.read_bytes()
            # Physical # identifiers and entity declaration order are not
            # persisted as occurrence identity. Alter both, preserving links.
            rewritten = re.sub(rb'#(\d+)', lambda m: b'#' + str(int(m.group(1)) + 10000).encode(), source)
            entity = re.compile(rb'#\d+\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(.*?\)\s*;', re.S)
            records = entity.findall(rewritten)
            self.assertEqual(len(records), 4)
            replacement = iter(reversed(records))
            rewritten = entity.sub(lambda _: next(replacement), rewritten)
            self.assertNotEqual(hashlib.sha256(source).digest(), hashlib.sha256(rewritten).digest())
            path.write_bytes(rewritten)
            reordered = step_geometry._worker(path)['parts']
            duplicated = source.replace(b"'occ-1'", b"'occ-2'")
            self.assertNotEqual(source, duplicated)
            path.write_bytes(duplicated)
            ambiguous = step_geometry._worker(path)['parts']
        paths = [p['occurrenceWitness']['path'] if p['occurrenceWitness'] else None for p in parts]
        self.assertEqual(len(paths), 4)
        self.assertEqual(len(set(map(tuple, paths))), 4)
        self.assertTrue(all(len(path) == 2 for path in paths))
        self.assertEqual(len({path[0] for path in paths}), 2)
        self.assertEqual(len({path[1] for path in paths}), 2)
        self.assertGreaterEqual(sum(p['occurrenceWitness'] is None for p in ambiguous), 2)
        def positions_by_witness(occurrences):
            return {tuple(p['occurrenceWitness']['path']): tuple(round(sum(p['positions'][i::3]) / (len(p['positions']) / 3), 9) for i in range(3)) for p in occurrences}
        self.assertEqual(positions_by_witness(parts), positions_by_witness(reordered))

    def test_shipped_nose_gear_source_occurrences_have_independent_witnesses(self):
        source = ROOT / 'examples/open-aircraft-nose-gear/source-assembly.step'
        parts = step_geometry._worker(source)['parts']
        self.assertEqual(len(parts), 11)
        for index, part in enumerate(parts, 1):
            self.assertEqual(part['occurrenceWitness'], {
                'scheme': 'step-nauo-id-path/1', 'path': [f'NAUO{index}']})

    def test_duplicate_source_ids_cannot_witness_either_occurrence(self):
        source = ROOT / 'examples/open-aircraft-nose-gear/source-assembly.step'
        data = source.read_bytes()
        old = b"NEXT_ASSEMBLY_USAGE_OCCURRENCE ( 'NAUO2',"
        self.assertEqual(data.count(old), 1)
        data = data.replace(old, b"NEXT_ASSEMBLY_USAGE_OCCURRENCE ( 'NAUO1',")
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'duplicate.step'
            path.write_bytes(data)
            parts = step_geometry._worker(path)['parts']
        self.assertIsNone(parts[0]['occurrenceWitness'])
        self.assertIsNone(parts[1]['occurrenceWitness'])
        self.assertEqual(parts[2]['occurrenceWitness']['path'], ['NAUO3'])

    def test_single_part_source_has_a_verifiable_single_occurrence(self):
        part = step_geometry._worker(ROOT / 'examples/step-pendulum/pendulum.step')['parts']
        self.assertEqual(len(part), 1)
        self.assertEqual(part[0]['occurrenceWitness'], {'scheme': 'single-part/1'})


if __name__ == '__main__':
    unittest.main()
