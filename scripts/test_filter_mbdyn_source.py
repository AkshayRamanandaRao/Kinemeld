import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import filter_mbdyn_source as filtered


class FilteredSourceTests(unittest.TestCase):
    def fixture(self, root, omit=None):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w', format=tarfile.GNU_FORMAT) as archive:
            for name in sorted(filtered.REMOVED | {'mbdyn-1.7.3/README', 'mbdyn-1.7.3/libraries/liby12/Makefile.in'}):
                if name == omit:
                    continue
                data = ('unchanged original ' + name).encode()
                member = tarfile.TarInfo(name)
                member.size, member.mtime = len(data), 123456
                archive.addfile(member, io.BytesIO(data))
        original = root / 'upstream.tar.gz'
        original.write_bytes(gzip.compress(raw.getvalue(), mtime=0))
        # Build the expected byte-exact tar from original member offsets.
        with tarfile.open(fileobj=io.BytesIO(raw.getvalue())) as archive:
            expected = b''.join(raw.getvalue()[m.offset:m.offset_data + (m.size + 511) // 512 * 512]
                                for m in archive if m.name not in filtered.REMOVED) + b'\0' * 1024
        return original, expected

    def test_filter_is_deterministic_and_preserves_all_retained_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, expected = self.fixture(root)
            output, metadata = root / 'source.tar', root / 'transform.json'
            with patch.object(filtered, 'UPSTREAM_SHA', hashlib.sha256(original.read_bytes()).hexdigest()), \
                 patch.object(filtered, 'FILTERED_SHA', hashlib.sha256(expected).hexdigest()):
                filtered.transform(original, output, metadata)
                first = output.read_bytes()
                filtered.transform(original, output, metadata)
            self.assertEqual(first, expected)
            self.assertEqual(first, output.read_bytes())
            report = json.loads(metadata.read_text())
            self.assertEqual({entry['path'] for entry in report['removed']}, filtered.REMOVED)
            with tarfile.open(output) as archive:
                self.assertEqual(set(archive.getnames()), {'mbdyn-1.7.3/README', 'mbdyn-1.7.3/libraries/liby12/Makefile.in'})

    def test_changed_upstream_missing_y12_or_changed_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, _ = self.fixture(root)
            with self.assertRaisesRegex(ValueError, 'upstream archive'):
                filtered.transform(original, root / 'out.tar', root / 'manifest.json')
            with patch.object(filtered, 'UPSTREAM_SHA', hashlib.sha256(original.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'Filtered'):
                    filtered.transform(original, root / 'out.tar', root / 'manifest.json')
            original, _ = self.fixture(root, next(iter(filtered.REMOVED)))
            with patch.object(filtered, 'UPSTREAM_SHA', hashlib.sha256(original.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'exact reviewed'):
                    filtered.transform(original, root / 'out.tar', root / 'manifest.json')


if __name__ == '__main__':
    unittest.main()
