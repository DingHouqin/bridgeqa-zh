"""[Static export acceptance](../specs/06_静态发布与文档.md). No network dependencies."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from export_site import export
from site_data import PROJECT, load_bundle

class StaticTest(unittest.TestCase):
    def test_export_roundtrip_and_public_files(self):
        before=(PROJECT/'data/pilot_literature_history_v0/benchmark.jsonl').read_bytes()
        with tempfile.TemporaryDirectory(prefix='pages-test-',dir=PROJECT/'workspace') as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                dest=export(Path(directory))
            manifest=json.loads((dest/'documents.json').read_text(encoding='utf-8'))
            self.assertEqual(len({d['slug'] for d in manifest['documents']}),len(manifest['documents']))
            self.assertEqual(json.loads((dest/'api/datasets/pilot_literature_history_v0/bundle.json').read_text(encoding='utf-8')),load_bundle('pilot_literature_history_v0'))
            for name in manifest['files']:
                self.assertEqual((dest/'files'/name).read_bytes(),(PROJECT/name).read_bytes())
            for doc in manifest['documents']:
                self.assertTrue((dest/'files'/doc['source']).is_file())
            self.assertFalse((dest/'.git').exists())
            self.assertFalse((dest/'files/workspace').exists())
            self.assertTrue((dest/'vendor/markdown-it.min.js').is_file())
            self.assertTrue((dest/'vendor/markdown-it-LICENSE.txt').is_file())
            # Repeat export removes obsolete publication files in the owned output.
            (dest/'obsolete.txt').write_text('old')
            with contextlib.redirect_stdout(io.StringIO()):export(dest)
            self.assertFalse((dest/'obsolete.txt').exists())
        self.assertEqual(before,(PROJECT/'data/pilot_literature_history_v0/benchmark.jsonl').read_bytes())

    def test_output_boundary_and_unowned_directory(self):
        with self.assertRaises(ValueError):export(PROJECT/'data')
        with self.assertRaises(ValueError):export(PROJECT/'workspace')
        with tempfile.TemporaryDirectory(prefix='pages-test-',dir=PROJECT/'workspace') as directory:
            dest=Path(directory);(dest/'keep.txt').write_text('keep')
            with self.assertRaises(ValueError):export(dest)
            self.assertEqual((dest/'keep.txt').read_text(),'keep')

if __name__=='__main__':unittest.main()
