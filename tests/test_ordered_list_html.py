#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.md_render import render_ordered_lists_as_html


def _num(label):
    return f'<span class="markdown-preview-overlay-ol-num">{label}</span>'


class TestOrderedListHtml(unittest.TestCase):
    """Verify miniHTML structural rewriting for <ol>/<li> lists."""

    def test_basic_nested_and_preserved_attributes(self):
        src = (
            '<ol id="steps" class="custom markdown-preview-overlay-ol" start="2" type="a">\n'
            '<li id="i1" class="task" value="5">Outer\n'
            '<ul>\n<li>Bullet A</li>\n'
            '<li>Bullet B\n<ol>\n<li>Deep 1</li>\n<li>Deep 2</li>\n</ol>\n</li>\n'
            '</ul>\n</li>\n'
            '<li>Outer next</li>\n'
            '</ol>'
        )
        out = render_ordered_lists_as_html(src)
        self.assertNotIn("<ol", out)
        self.assertNotIn("<li id=", out)
        self.assertIn('<div class="markdown-preview-overlay-ol custom" id="steps">', out)
        self.assertIn(
            f'<div class="markdown-preview-overlay-li task" id="i1">{_num("e.")} Outer',
            out,
        )
        self.assertIn("<ul>\n<li>Bullet A</li>", out)
        self.assertIn(f'<div class="markdown-preview-overlay-li">{_num("1.")} Deep 1</div>', out)
        self.assertIn(f'<div class="markdown-preview-overlay-li">{_num("2.")} Deep 2</div>', out)
        self.assertIn(
            f'<div class="markdown-preview-overlay-li">{_num("f.")} Outer next</div>',
            out,
        )

    def test_marker_placement_wrappers_inline_block_and_empty(self):
        src = (
            "<ol>\n"
            "<li>\n<p>First para</p>\n<p>Second para</p>\n</li>\n"
            "<li><h3>Heading</h3><p>Body</p></li>\n"
            "<li><strong>Bold</strong> &amp; &#60;tag&#62;</li>\n"
            "<li>&mdash; Entity</li>\n"
            "<li><pre><code>x = 1</code></pre></li>\n"
            "<li></li>\n"
            "</ol>"
        )
        out = render_ordered_lists_as_html(src)
        self.assertIn(f"<p>{_num('1.')} First para</p>", out)
        self.assertIn("<p>Second para</p>", out)
        self.assertIn(f"<h3>{_num('2.')} Heading</h3><p>Body</p>", out)
        self.assertIn(f"{_num('3.')} <strong>Bold</strong> &amp; &#60;tag&#62;", out)
        self.assertIn(f"{_num('4.')} &mdash; Entity", out)
        self.assertIn(f"{_num('5.')} <pre><code>x = 1</code></pre>", out)
        self.assertIn(f"{_num('6.')}</div>", out)


if __name__ == "__main__":
    unittest.main()
