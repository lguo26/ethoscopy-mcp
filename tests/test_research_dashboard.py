"""Portable presentation checks using only synthetic source files."""
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/research_dashboard'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(v for k, v in attrs if k in ('href', 'src') and v)


@unittest.skipUnless(importlib.util.find_spec('markdown'), 'Install .[dashboard]')
class ResearchDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.output = self.root / 'site'
        shutil.copytree(EXAMPLE / 'source', self.source)

    def build(self, output=None):
        return subprocess.run(
            [sys.executable, str(EXAMPLE / 'build.py'), '--source', str(self.source),
             '--output', str(output or self.output)],
            capture_output=True, text=True,
        )

    def test_reports_links_hashes_and_figure_pairs(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        records = json.loads((self.output / 'bundle_manifest.json').read_text())
        paths = {r['source']: self.output / unquote(r['web_path']) for r in records}
        report = paths['reports/experiment.md'].read_text()
        self.assertIn('<table>', report)
        self.assertIn('<pre><code', report)
        self.assertIn('local archive', report)
        self.assertNotIn('href="private_raw.pkl"', report)
        self.assertIn('href="../reference_results.html">← Back to results',
                      paths['reports/reference/overview.md'].read_text())
        self.assertIn('assets/synthetic_curve.svg', paths)
        self.assertIn('assets/synthetic_curve.png', paths)
        self.assertIn('assets/dashboard.css', paths)
        for record in records:
            raw = (self.output / unquote(record['web_path'])).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['published_sha256'])
        for path in self.output.rglob('*.html'):
            page = path.read_text()
            self.assertIn('id="figure-viewer"', page)
            links = Links()
            links.feed(page)
            for link in links.links:
                parsed = urlsplit(link)
                if not parsed.scheme and parsed.path:
                    self.assertTrue((path.parent / unquote(parsed.path)).is_file(), (path, link))

    def test_report_links_cannot_escape_source_or_include_raw_objects(self):
        outside = self.root / 'outside.csv'
        outside.write_text('PRIVATE_SENTINEL')
        (self.source / 'reports/escape.csv').symlink_to(outside)
        (self.source / 'reports/private_raw.pkl').write_text('PRIVATE_SENTINEL')
        with (self.source / 'reports/experiment.md').open('a') as handle:
            handle.write('\n[External file](../../outside.csv)\n[Symlink](escape.csv)\n')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in self.output.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'PRIVATE_SENTINEL', path.read_bytes())
        archived = json.loads((self.output / 'archive_links.json').read_text())
        self.assertTrue(any(r['target'] == 'escape.csv' for r in archived))

    def test_output_cannot_overlap_source(self):
        for output in (self.source, self.source / 'nested', self.root):
            with self.subTest(output=output):
                result = self.build(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('must not overlap', result.stderr)


if __name__ == '__main__':
    unittest.main()
