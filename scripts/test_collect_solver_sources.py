import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import collect_solver_sources as collector


class SourceCollectionTests(unittest.TestCase):
    def test_cygwin_matching_source_uses_installed_version(self):
        index = ('@ libgcc1\nversion: 14.4.0-1\nsource: x86_64/gcc-14.tar.zst 12 abc\n'
                 '[test]\nversion: 16.2.0-1\nsource: src/gcc-16.tar.zst 99 def\n'
                 '@ other\nversion: 1\n')
        self.assertEqual(collector.cygwin_entry(index, 'libgcc1', '14.4.0-1')['source'],
                         'x86_64/gcc-14.tar.zst 12 abc')
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            collector.cygwin_entry(index, 'libgcc1', '14.3.0-1')
        with self.assertRaisesRegex(ValueError, 'absent'):
            collector.cygwin_entry(index, 'unknown', '1')

    def test_download_rejects_changed_cached_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'source.tar.xz'
            path.write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                collector.download('https://example.org/source.tar.xz', path, '0' * 64)
            with self.assertRaisesRegex(ValueError, 'HTTPS'):
                collector.download('http://example.org/source.tar.xz', path)

    def test_actual_source_headers_preserve_permission_and_copyright(self):
        source = b'/* Copyright original author.\n Permission to copy and distribute. */\n#include <stdio.h>\n'
        text = collector.leading_comments(source)
        self.assertIn('Permission to copy', text)
        self.assertNotIn('#include', text)

    def test_unknown_cygwin_dependency_stops_before_source_substitution(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            import lzma
            index = work / 'cygwin-setup.xz'
            index.write_bytes(lzma.compress(b'@ irrelevant\n'))
            with patch.object(collector, 'download', return_value=index):
                with self.assertRaisesRegex(ValueError, 'Unreviewed'):
                    collector.collect_cygwin(work, work, {'bin/unknown.dll': '/usr/bin/unknown.dll'})

    def test_quadmath_is_not_classified_as_gcc_exception(self):
        from prepare_solver_sources import NAMES, LICENSES
        self.assertTrue(NAMES['quadmath'].fullmatch('libquadmath.so.0'))
        self.assertTrue(NAMES['quadmath'].fullmatch('cygquadmath-0.dll'))
        self.assertFalse(NAMES['gcc-runtime'].fullmatch('libquadmath.0.dylib'))
        self.assertEqual(LICENSES['quadmath'], 'LGPL-2.1-or-later')


if __name__ == '__main__':
    unittest.main()
