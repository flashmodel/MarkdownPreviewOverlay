import base64
import struct
import subprocess
import unittest
from unittest import mock

from overlay.mermaid import (
    _detect_cli_type,
    _render_png,
    find_mermaid_cli,
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
    def test_render_and_cache_merman(self, run):
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
            '/bin/merman-cli', 'render', '-', '--format', 'png',
            '--background', 'white', '--scale', '2',
            '--output', '-', '--quiet',
        ])
        larger = render_mermaid_blocks(source, '/bin/merman-cli', max_width=2000)
        self.assertIn('width="500" height="250"', larger)
        run.assert_called_once()

    @mock.patch('overlay.mermaid.subprocess.run')
    def test_render_mmdc(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, self.png, b'')
        source = '```mermaid\ngraph TD\n A --> B\n```\n'
        rendered = render_mermaid_blocks(source, '/usr/local/bin/mmdc', max_width=500)
        self.assertIn('data:image/png;base64,' + base64.b64encode(self.png).decode(), rendered)
        self.assertEqual(run.call_args.args[0], [
            '/usr/local/bin/mmdc', '-i', '-', '-o', '-', '-e', 'png',
            '-b', 'white', '-s', '2', '-q',
        ])
        self.assertEqual(run.call_args.kwargs['input'], b'graph TD\n A --> B\n')

    def test_detect_cli_type(self):
        self.assertEqual(_detect_cli_type('/usr/bin/merman-cli'), 'merman-cli')
        self.assertEqual(_detect_cli_type('C:\\Tools\\merman.exe'), 'merman-cli')
        self.assertEqual(_detect_cli_type('/usr/local/bin/mmdc'), 'mmdc')
        self.assertEqual(_detect_cli_type('C:\\npm\\mmdc.cmd'), 'mmdc')
        self.assertEqual(_detect_cli_type('/opt/homebrew/bin/mermaid-cli'), 'mmdc')

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
            self.assertEqual(
                render_mermaid_blocks(source, 'merman-cli', on_error=errors.append), source
            )
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

    @mock.patch('overlay.mermaid.shutil.which')
    def test_find_mermaid_cli_priority(self, which):
        which.side_effect = lambda cmd, path=None: (
            '/bin/mmdc' if cmd == 'mmdc' else '/bin/merman-cli'
        )
        self.assertEqual(find_mermaid_cli(), ('/bin/mmdc', 'mmdc'))

        which.side_effect = lambda cmd, path=None: (
            '/bin/merman-cli' if cmd == 'merman-cli' else None
        )
        self.assertEqual(find_mermaid_cli(), ('/bin/merman-cli', 'merman-cli'))

        which.side_effect = lambda cmd, path=None: None
        self.assertIsNone(find_mermaid_cli())

    @mock.patch('overlay.mermaid.shutil.which')
    def test_find_mermaid_cli_custom_path(self, which):
        which.side_effect = lambda cmd, path=None: (
            '/custom/bin/mmdc' if cmd == '/custom/bin/mmdc' else None
        )
        self.assertEqual(
            find_mermaid_cli('/custom/bin/mmdc'), ('/custom/bin/mmdc', 'mmdc')
        )
        self.assertIsNone(find_mermaid_cli('/invalid/path/tool'))


if __name__ == '__main__':
    unittest.main()
