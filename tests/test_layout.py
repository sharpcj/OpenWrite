"""Workspace layout tiers: deliverables at root, process and workflow below."""
import json
from pathlib import Path
import tempfile
import unittest

import layout


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='openwrite-layout-')
        self.addCleanup(self.tmp.cleanup)
        self.article = Path(self.tmp.name).resolve() / 'piece'
        self.article.mkdir(parents=True)

    def test_tiers_and_write_side_creates_dirs(self):
        self.assertEqual(layout.path(self.article, 'draft.md'),
                         self.article / 'process' / 'draft.md')
        self.assertEqual(layout.path(self.article, 'workflow.json'),
                         self.article / 'workflow' / 'workflow.json')
        self.assertEqual(layout.path(self.article, 'cover.png'), self.article / 'cover.png')
        self.assertTrue((self.article / 'process').is_dir())
        self.assertTrue((self.article / 'workflow').is_dir())

    def test_existing_reads_legacy_flat_without_side_effects(self):
        (self.article / 'workflow.json').write_text('{}', encoding='utf-8')
        self.assertEqual(layout.existing(self.article, 'workflow.json'),
                         self.article / 'workflow.json')
        self.assertFalse((self.article / 'workflow').exists())

    def test_migrate_moves_flat_files_and_unreferenced_images(self):
        for name in ('draft.md', 'workflow.json', 'cover-base.png', 'raw source.png'):
            (self.article / name).write_text('x', encoding='utf-8')
        (self.article / 'cover.png').write_text('x', encoding='utf-8')
        (self.article / 'c1.png').write_text('x', encoding='utf-8')
        layout.path(self.article, 'image-requests.json').write_text(json.dumps({
            'version': 1, 'images': [{'id': 'cover', 'role': 'cover', 'output': 'cover.png'},
                                     {'id': 'c1', 'role': 'content', 'output': 'c1.png'}]}),
            encoding='utf-8')
        moved = layout.migrate(self.article)
        self.assertIn('draft.md', moved)
        self.assertIn('workflow.json', moved)
        self.assertIn('cover-base.png', moved)
        self.assertIn('raw source.png', moved)
        self.assertTrue((self.article / 'process' / 'cover-base.png').is_file())
        self.assertTrue((self.article / 'process' / 'raw source.png').is_file())
        self.assertTrue((self.article / 'cover.png').is_file())  # 交付件留根目录
        self.assertTrue((self.article / 'c1.png').is_file())
        self.assertEqual(layout.migrate(self.article), [])  # 幂等


if __name__ == '__main__':
    unittest.main()