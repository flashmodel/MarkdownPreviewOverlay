import base64
import json
import os
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

from overlay.md_render import render_markdown_tables_as_html
from overlay.math import (
    _npm_root_global,
    apply_replacements,
    clear_math_caches,
    find_math_runtime,
    math_regions,
    protect_math,
    render_math_blocks,
)


OBJECTIVE = """\
$$
\\max\\;
\\underbrace{552\\,x_K + 417\\,x_S}_{\\text{proizvodnja}}
+\\underbrace{620\\,w_{01}}_{\\text{31.01}}
+\\underbrace{2150\\,w_{04}}_{\\text{31.04}}
+\\underbrace{161\\,z^{sam} + 117\\,z^{04}}_{\\text{31.05}}
-\\underbrace{(60\\,w_{01} + 95\\,w_{04} + 60\\,w_{05})}_{\\text{fiksni troškovi}}
$$
"""

CONSTRAINTS = """\
$$
\\begin{aligned}
& x_K + x_S = 10 && \\text{cijela parcela zasijana}\\\\
& x_K,\\ x_S \\le 7{,}5 + 10\\,(1-w_{01}) && \\text{31.01: nijedna kultura iznad 75 \\%}\\\\
& 70\\cdot 10\\cdot w_{04} \\le 5\\cdot 168 && \\text{31.04: dovoljno gnoja}\\\\
& x_S \\ge 2\\,w_{05} && \\text{31.05: soja barem 20 \\%}\\\\
& z^{sam} + z^{04} \\le x_S,\\;\\; z^{sam} + z^{04} \\le 10\\,w_{05} && \\text{31.05: plaća se samo soja}\\\\
& z^{04} \\le 10\\,w_{04},\\;\\; z^{sam} \\le 10\\,(1-w_{04}) && \\text{31.05: iznos ovisi o 31.04}
\\end{aligned}
$$
"""


def _png(width=1000, height=500):
    return b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', width, height)


def _frames(items):
    parts = []
    for status, payload in items:
        parts.append(struct.pack('>II', status, len(payload)))
        parts.append(payload)
    return b''.join(parts)


class TestMathRendering(unittest.TestCase):
    def setUp(self):
        clear_math_caches()
        self.png = _png()

    def tearDown(self):
        clear_math_caches()

    def test_sample_formulas_are_extracted_intact(self):
        source = 'Notes\n\n' + OBJECTIVE + '\nThen\n\n' + CONSTRAINTS + '\n'
        regions = math_regions(source)
        self.assertEqual(len(regions), 2)
        self.assertTrue(regions[0].display)
        self.assertTrue(regions[1].display)
        self.assertIn(r'\underbrace{552\,x_K + 417\,x_S}_{\text{proizvodnja}}', regions[0].tex)
        self.assertIn(r'\text{fiksni troškovi}', regions[0].tex)
        self.assertIn(r'\begin{aligned}', regions[1].tex)
        self.assertIn(r'\text{31.05: plaća se samo soja}', regions[1].tex)
        self.assertIn(r'7{,}5', regions[1].tex)
        self.assertNotIn('$$', regions[0].tex)
        self.assertNotIn('$$', regions[1].tex)

    def test_code_inline_code_and_escaped_dollars_are_left_alone(self):
        source = (
            'Price is \\$100 and \\$20.\n\n'
            '```\n$$\nx_K$$\n```\n\n'
            '~~~python\n$x$\n~~~\n\n'
            'Use `$x_K$` in prose and $x_K$ here.\n\n'
            '```math\n$$\n\\alpha\n$$\n```\n'
        )
        regions = math_regions(source)
        self.assertEqual([region.tex for region in regions], ['x_K'])
        self.assertFalse(regions[0].display)
        protected = protect_math(source)
        self.assertIn('```\n$$\nx_K$$\n```', protected)
        self.assertIn('`$x_K$`', protected)
        self.assertIn('\\$100', protected)
        self.assertIn('```math\nx_K\n```', protected)
        self.assertNotIn('and $x_K$ here', protected)

    def test_currency_and_unclosed_dollars_are_not_math(self):
        self.assertEqual(math_regions('It costs $20 and $30 today.'), [])
        self.assertEqual(math_regions('start $x'), [])
        self.assertEqual(math_regions('$$\n\\alpha\n'), [])
        regions = math_regions('one $$a+b$$ two')
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0].tex, 'a+b')
        self.assertTrue(regions[0].display)
        indented = math_regions('   $$\nx\n$$')
        self.assertEqual(indented[0].tex, 'x')
        self.assertEqual(indented[0].start, 0)

    @mock.patch('overlay.math.subprocess.run')
    def test_render_scales_and_caches(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, _frames([(0, self.png), (0, self.png)]), b'',
        )
        source = 'Before\n\n' + OBJECTIVE + '\nAfter $x_K$\n'
        rendered = render_math_blocks(
            source, '/usr/bin/node', '/opt/modules', color='#112233', max_width=400,
        )
        self.assertIn('Before', rendered)
        self.assertIn('After', rendered)
        self.assertNotIn('$$', rendered)
        self.assertNotIn('$x_K$', rendered)
        encoded = base64.b64encode(self.png).decode()
        self.assertEqual(rendered.count('data:image/png;base64,' + encoded), 2)
        self.assertIn('class="math-display"', rendered)
        self.assertIn('class="math-inline"', rendered)
        self.assertIn('width="400" height="200"', rendered)
        self.assertIn('troškovi', rendered)
        payload = json.loads(run.call_args.kwargs['input'].decode('utf-8'))
        self.assertEqual(payload['color'], '#112233')
        self.assertEqual(payload['scale'], 2)
        self.assertEqual(len(payload['items']), 2)
        self.assertTrue(payload['items'][0]['display'])
        self.assertFalse(payload['items'][1]['display'])
        self.assertIn(r'\text{fiksni troškovi}', payload['items'][0]['tex'])
        self.assertTrue(run.call_args.args[0][1].endswith(os.path.join('math', 'tex2png.js')))
        self.assertEqual(run.call_args.args[0][2], '/opt/modules')

        again = render_math_blocks(
            source, '/usr/bin/node', '/opt/modules', color='#112233', max_width=400,
        )
        self.assertEqual(again, rendered)
        run.assert_called_once()

        wider = render_math_blocks(
            source, '/usr/bin/node', '/opt/modules', color='#112233', max_width=2000,
        )
        self.assertIn('width="500" height="250"', wider)
        run.assert_called_once()

    @mock.patch('overlay.math.subprocess.run')
    def test_failed_formula_stays_fenced_and_missing_node_does_not_raise(self, run):
        run.return_value = subprocess.CompletedProcess(
            [], 0, _frames([(1, b'TeX error'), (0, self.png)]), b'',
        )
        source = '$$\\bad$$\n\n$x$\n'
        errors = []
        rendered = render_math_blocks(source, 'node', '/modules', on_error=errors.append)
        self.assertIn('```math\n\\bad\n```', rendered)
        self.assertIn('<span class="math-inline" style="display:inline">', rendered)
        self.assertNotIn('$$', rendered)
        self.assertTrue(errors)

        run.side_effect = OSError('missing')
        clear_math_caches()
        rendered = render_math_blocks('$$\\alpha$$', 'node', '/modules', on_error=errors.append)
        self.assertIn('```math\n\\alpha\n```', rendered)

        untouched = render_math_blocks('$$\\alpha$$', None, None, on_error=errors.append)
        self.assertIn('```math', untouched)
        self.assertIn('math renderer is not available', errors)

    @mock.patch('overlay.math.subprocess.run')
    def test_render_math_blocks_deltas_and_spans(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, _frames([(0, self.png)]), b'')
        source = 'Line 0\nLine 1\n$$\nx\n$$\n'
        deltas = []
        spans = []
        rendered = render_math_blocks(source, 'node', '/modules', deltas=deltas, spans=spans)
        self.assertEqual(deltas, [(2, 250)])
        self.assertEqual(len(spans), 1)
        self.assertEqual(apply_replacements(source, spans), rendered)

    @mock.patch('overlay.math.os.name', 'nt')
    @mock.patch('overlay.math.subprocess.run')
    def test_windows_creationflags(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, _frames([(0, self.png)]), b'')
        render_math_blocks('$$x$$', 'node', '/modules')
        self.assertIn('creationflags', run.call_args.kwargs)

    def test_find_math_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            modules = os.path.join(tmp, 'node_modules')
            os.makedirs(os.path.join(modules, 'mathjax'))
            os.makedirs(os.path.join(modules, '@resvg', 'resvg-js'))
            for relative in (
                os.path.join('mathjax', 'package.json'),
                os.path.join('@resvg', 'resvg-js', 'package.json'),
            ):
                with open(os.path.join(modules, relative), 'w', encoding='utf-8') as handle:
                    handle.write('{}')
            node = os.path.join(tmp, 'node')
            with open(node, 'w', encoding='utf-8') as handle:
                handle.write('#!/bin/sh\n')
            os.chmod(node, 0o755)
            with mock.patch('overlay.math._find_executable', return_value='/usr/bin/node'):
                self.assertEqual(
                    find_math_runtime(None, tmp),
                    ('/usr/bin/node', modules),
                )
                self.assertEqual(find_math_runtime(node, modules), (node, modules))
            self.assertIsNone(find_math_runtime('/missing/node', modules))

        with mock.patch('overlay.math._find_executable', return_value=None), \
                mock.patch('overlay.math.shutil.which', return_value=None):
            self.assertIsNone(find_math_runtime(None, None))

    def test_math_images_inside_tables_stay_images(self):
        image = (
            '<span class="math-inline" style="display:inline">'
            '<img src="data:image/png;base64,AAAA" '
            'alt="x_K, x_S" width="43" height="8" style="display:inline" /></span>'
        )
        source = (
            '| Varijabla | Vrsta |\n'
            '| --- | --- |\n'
            '| {0} | real |\n'
            '| before {0} after | 0/1 |\n'
        ).format(image)
        rendered = render_markdown_tables_as_html(source, 80)
        self.assertEqual(rendered.count(image), 2)
        self.assertNotIn('&lt;span', rendered)
        self.assertNotIn('&lt;img', rendered)
        self.assertIn('white-space:normal', rendered)
        self.assertNotIn('white-space:pre', rendered)
        self.assertIn('real', rendered)
        self.assertIn('\xa0', rendered)

    @mock.patch('overlay.math.subprocess.run')
    def test_npm_root_is_cached(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, b'/opt/node_modules\n', b'')
        self.assertEqual(_npm_root_global('/usr/bin/npm'), '/opt/node_modules')
        self.assertEqual(_npm_root_global('/usr/bin/npm'), '/opt/node_modules')
        run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
