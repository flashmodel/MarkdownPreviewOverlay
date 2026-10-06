import base64
import struct
import subprocess
import unittest
from unittest import mock

from overlay.mermaid import (
    _render_png,
    find_merman_cli,
    mermaid_blocks,
    render_mermaid_blocks,
)


class TestMermaidRendering(unittest.TestCase):
    def setUp(self):
        _render_png.cache_clear()
        self.png = b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\rIHDR' + struct.pack('>II', 1000, 500)

    def tearDown(self):
        _render_png.cache_clear()

    @mock.patch('overlay.mermaid.subprocess.run')
    def test_render_and_cache(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, self.png, b'')
        source = 'Before\n\n```mermaid\ngraph TD\n A --> B\n```\n\nAfter'
        rendered = render_mermaid_blocks(source, '/bin/merman-cli', max_width=400)
        self.assertIn('Before', rendered)
        self.assertIn('After', rendered)
        self.assertNotIn('```mermaid', rendered)
        self.assertIn('data:image/png;base64,' + base64.b64encode(self.png).decode(), rendered)
        self.assertIn('width="400" height="200"', rendered)
        self.assertEqual(run.call_args.kwargs['input'], b'graph TD\n A --> B\n')
        self.assertEqual(run.call_args.args[0], [
            '/bin/merman-cli', 'render', '-', '--format', 'png', '--output', '-', '--quiet',
        ])
        larger = render_mermaid_blocks(source, '/bin/merman-cli', max_width=2000)
        self.assertIn('width="1000" height="500"', larger)
        run.assert_called_once()

    def test_fence_variations(self):
        text = ('~~~mermaid\ngraph LR\n A --> B\n~~~~\n'
                '   ````mermaid\nsequenceDiagram\n```\n`````\n')
        blocks = list(mermaid_blocks(text))
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0][2], 'graph LR\n A --> B\n')
        self.assertEqual(blocks[1][2], 'sequenceDiagram\n```\n')

    @mock.patch('overlay.mermaid.subprocess.run')
    def test_other_code_and_unclosed_fences_are_untouched(self, run):
        for source in (
            '````markdown\n```mermaid\ngraph TD\n```\n````\n',
            '```python\nprint("mermaid")\n```\n',
            '```mermaid\ngraph TD\n',
            '    ```mermaid\ngraph TD\n    ```\n',
            '```mermaid-example\ngraph TD\n```\n',
        ):
            self.assertEqual(render_mermaid_blocks(source, '/bin/merman-cli'), source)
        run.assert_not_called()

    @mock.patch('overlay.mermaid.subprocess.run')
    def test_failures_preserve_source(self, run):
        source = '```mermaid\ninvalid\n```\n'
        for error in (OSError('missing'), subprocess.TimeoutExpired('merman-cli', 15)):
            run.side_effect = error
            errors = []
            self.assertEqual(render_mermaid_blocks(source, 'merman-cli', on_error=errors.append), source)
            self.assertTrue(errors)
        run.side_effect = None
        for status, output in ((1, b''), (0, b'<svg/>')):
            run.return_value = subprocess.CompletedProcess([], status, output, b'error')
            self.assertEqual(render_mermaid_blocks(source, 'merman-cli'), source)

    @mock.patch('overlay.mermaid.subprocess.run')
    def test_failure_does_not_prevent_other_diagrams(self, run):
        run.side_effect = [
            subprocess.CompletedProcess([], 1, b'', b'error'),
            subprocess.CompletedProcess([], 0, self.png, b''),
        ]
        source = '```mermaid\nbad\n```\n\n~~~mermaid\ngraph TD; A-->B\n~~~\n'
        result = render_mermaid_blocks(source, 'merman-cli')
        self.assertIn('```mermaid\nbad\n```', result)
        self.assertIn('<img ', result)
        self.assertNotIn('~~~mermaid', result)

    @mock.patch('overlay.mermaid.shutil.which', return_value=None)
    def test_missing_cli(self, which):
        self.assertIsNone(find_merman_cli())

    @mock.patch('overlay.mermaid.shutil.which', return_value='/bin/merman-cli')
    def test_cli_on_path(self, which):
        self.assertEqual(find_merman_cli(), '/bin/merman-cli')
        which.assert_called_once_with('merman-cli')


if __name__ == '__main__':
    unittest.main()
