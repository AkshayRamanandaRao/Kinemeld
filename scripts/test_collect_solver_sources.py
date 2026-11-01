import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import struct
import tarfile
import io
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

    def test_changed_cygwin_copy_is_rejected_before_package_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            import lzma
            index = work / 'cygwin-setup.xz'
            index.write_bytes(lzma.compress(b'@ libgcc1\n'))
            (work / 'bin').mkdir()
            (work / 'bin/cyggcc_s-seh-1.dll').write_bytes(b'changed DLL')
            original = work / 'original.dll'
            original.write_bytes(b'original DLL')
            with patch.object(collector, 'download', return_value=index), patch.object(collector, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'differs from its installed owner'):
                    collector.collect_cygwin(work, work, {'bin/cyggcc_s-seh-1.dll': str(original)})
                run.assert_not_called()

    def test_quadmath_is_not_classified_as_gcc_exception(self):
        from prepare_solver_sources import NAMES, LICENSES
        self.assertTrue(NAMES['quadmath'].fullmatch('libquadmath.so.0'))
        self.assertTrue(NAMES['quadmath'].fullmatch('cygquadmath-0.dll'))
        self.assertFalse(NAMES['gcc-runtime'].fullmatch('libquadmath.0.dylib'))
        self.assertEqual(LICENSES['quadmath'], 'LGPL-2.1-or-later')

    def test_macho_identity_ignores_load_paths_and_rejects_changed_code(self):
        # One UUID and one __TEXT,__text section, followed by code and signing data.
        header = bytearray(32)
        struct.pack_into('<IIIIIIII', header, 0, 0xfeedfacf, 0x100000c, 0, 6, 2, 176, 0, 0)
        uuid = struct.pack('<II', 0x1b, 24) + b'1234567890abcdef'
        segment = bytearray(152)
        struct.pack_into('<II', segment, 0, 0x19, 152)
        struct.pack_into('<I', segment, 64, 1)
        segment[72:78] = b'__text'
        segment[88:94] = b'__TEXT'
        struct.pack_into('<QI', segment, 112, 4, 208)
        data = header + uuid + segment + b'CODE' + b'signature'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'runtime.dylib'
            path.write_bytes(data)
            identity = collector.macho_identity(path)
            data[-4:] = b'edit'
            path.write_bytes(data)
            self.assertEqual(identity, collector.macho_identity(path))
            data[208] ^= 1
            path.write_bytes(data)
            self.assertNotEqual(identity, collector.macho_identity(path))
            # Homebrew's libgcc may be a one-slice universal container while
            # other GCC libraries are thin Mach-O files.
            thin = path.read_bytes()
            fat = struct.pack('>IIIIIII', 0xcafebabe, 1, 0x100000c, 0, 4096, len(thin), 12)
            path.write_bytes(fat + b'\0' * (4096 - len(fat)) + thin)
            self.assertEqual(collector.macho_identity(path), collector.macho_identity(path, thin))

    def test_homebrew_cannot_substitute_an_unreviewed_local_keg(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'INSTALL_RECEIPT.json').write_text('{"source":{"tap_git_head":"not-a-commit"}}')
            info = {'formulae': [{'installed': [{'version': '1.0', 'built_as_bottle': False}]}]}
            api = root / 'api.json'
            api.write_text('{"versions":{"stable":"1.0"}}')
            with patch.object(collector, 'run', side_effect=[json.dumps(info), str(root)]), \
                 patch.object(collector, 'download', return_value=api):
                with self.assertRaisesRegex(ValueError, 'official bottle'):
                    collector.collect_homebrew(root, root, {})

    def test_homebrew_accepts_exact_bottle_recipe_and_rejects_modified_recipe(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prefix = root / 'gcc/16.2.0'
            (prefix / '.brew').mkdir(parents=True)
            installed = prefix / '.brew/gcc.rb'
            installed.write_bytes(b'class Gcc < Formula\n  # exact pre-bottling recipe\nend\n')
            tap = root / 'tap-gcc.rb'
            tap.write_bytes(b'class Gcc < Formula\n  bottle do\n    rebuild 1\n  end\nend\n')
            bottle = root / 'gcc.bottle.tar.gz'
            with tarfile.open(bottle, 'w:gz') as archive:
                member = tarfile.TarInfo('gcc/16.2.0/.brew/gcc.rb')
                member.size = installed.stat().st_size
                archive.addfile(member, io.BytesIO(installed.read_bytes()))
            api = {'bottle': {'stable': {'rebuild': 1, 'files': {'arm64_sequoia': {
                'sha256': collector.digest(bottle), 'url': 'https://ghcr.io/verified-bottle'}}}}}
            with patch.object(collector, 'run', return_value=str(bottle)):
                recipe, evidence, metadata = collector.verify_homebrew_bottle(api, root, prefix, {}, installed, tap)
                self.assertEqual(recipe.read_bytes(), installed.read_bytes())
                self.assertEqual(json.loads(evidence.read_text())['rebuild'], 1)
                installed.write_bytes(b'class Gcc < Formula\n  # unknown local modifications\nend\n')
                with self.assertRaisesRegex(ValueError, 'both verified bottle and tap'):
                    collector.verify_homebrew_bottle(api, root, prefix, {}, installed, tap)
                api['bottle']['stable']['files']['arm64_sequoia']['sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'official API SHA-256'):
                    collector.verify_homebrew_bottle(api, root, prefix, {}, installed, tap)


if __name__ == '__main__':
    unittest.main()
