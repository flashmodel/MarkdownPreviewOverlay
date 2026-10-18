#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.md_render import (
    inject_copy_links,
    render_markdown_tables_as_html,
    resolve_markdown_image_paths,
)


class TestCodeBlockCopyLinks(unittest.TestCase):
    """Test suite for code block copy link injection."""

    def test_fenced_block_copies_raw_code(self):
        md = "Intro\n```python\nprint('a')\n\nx = 1\n```\nAfter"
        res, texts = inject_copy_links(md)
        self.assertEqual(texts, ["print('a')\n\nx = 1"])
        self.assertIn('href="overlay:copy:0"', res)
        # Copy link is its own paragraph, placed before the untouched fence
        self.assertIn('Intro\n\n<a class="markdown-preview-overlay-copy-code" href="overlay:copy:0">⧉ Copy</a>\n\n```python', res)
        self.assertTrue(res.endswith("```python\nprint('a')\n\nx = 1\n```\nAfter"))

    def test_tilde_and_longer_fences(self):
        md = "~~~\na\n~~~\n\n````\n```\nnested\n```\n````"
        _, texts = inject_copy_links(md)
        self.assertEqual(texts, ["a", "```\nnested\n```"])

    def test_unclosed_fence_runs_to_end(self):
        md = "```\nline 1\nline 2"
        res, texts = inject_copy_links(md)
        self.assertEqual(texts, ["line 1\nline 2"])
        self.assertTrue(res.endswith("```\nline 1\nline 2"))

    def test_fence_inside_list_keeps_indentation(self):
        md = "- item\n\n    ```\n    code\n      more\n    ```"
        res, texts = inject_copy_links(md)
        self.assertEqual(texts, ["code\n  more"])
        self.assertIn('\n    <a class="markdown-preview-overlay-copy-code"', res)

    def test_indented_code_block(self):
        md = "Para\n\n    def f():\n        return 1\n\nNext"
        _, texts = inject_copy_links(md)
        self.assertEqual(texts, ["def f():\n    return 1"])

    def test_list_continuation_is_not_code(self):
        md = "- item\n\n    continuation `x`"
        _, texts = inject_copy_links(md, code_blocks=True, inline_code=False)
        self.assertEqual(texts, [])

    def test_code_blocks_disabled(self):
        md = "```\ncode\n```"
        res, texts = inject_copy_links(md, code_blocks=False)
        self.assertEqual((res, texts), (md, []))


class TestInlineCodeCopyLinks(unittest.TestCase):
    """Test suite for inline code copy link injection."""

    def test_inline_code_wrapped_and_encoded(self):
        res, texts = inject_copy_links("Run `a*b* http://x` now")
        self.assertEqual(texts, ["a*b* http://x"])
        self.assertIn(
            '<a class="markdown-preview-overlay-copy-inline" href="overlay:copy:0">'
            '<code>a&#42;b&#42; http&#58;&#47;&#47;x</code></a>', res)
        self.assertTrue(res.startswith("Run ") and res.endswith(" now"))

    def test_html_special_chars_survive_mdpopups_unescape(self):
        # mdpopups unescapes every entity except &amp; &lt; &gt; &nbsp;
        # (RE_BAD_ENTITIES); a raw <tag> left behind breaks minihtml.
        import html
        import re
        res, texts = inject_copy_links("Use `<tag> & co` here")
        self.assertEqual(texts, ["<tag> & co"])
        self.assertIn('<code>&lt;tag&gt; &amp; co</code>', res)
        bad_entities = re.compile(r'(&(?!amp;|lt;|gt;|nbsp;)(?:\w+;|#\d+;))')
        unescaped = bad_entities.sub(lambda m: html.unescape(m.group(1)), res)
        self.assertNotIn('<tag>', unescaped)

    def test_double_backticks_and_padding(self):
        _, texts = inject_copy_links("Use `` a`b `` and `c`")
        self.assertEqual(texts, ["a`b", "c"])

    def test_escaped_backtick_ignored(self):
        md = r"Not \`code\` here"
        self.assertEqual(inject_copy_links(md), (md, []))

    def test_not_wrapped_in_fence_table_or_link(self):
        md = (
            "```\n`inside`\n```\n\n"
            "| a | b |\n| --- | --- |\n| `cell` | 1 |\n\n"
            "[`linked`](http://example.com) and `free`"
        )
        res, texts = inject_copy_links(md, code_blocks=False)
        self.assertEqual(texts, ["free"])
        self.assertIn("```\n`inside`\n```", res)
        self.assertIn("| `cell` | 1 |", res)
        self.assertIn("[`linked`](http://example.com)", res)

    def test_inline_code_in_heading(self):
        _, texts = inject_copy_links("## The `cmd` option")
        self.assertEqual(texts, ["cmd"])


class TestParagraphCopyLinks(unittest.TestCase):
    """Test suite for paragraph, list item and blockquote copy links."""

    def test_paragraphs_off_by_default(self):
        md = "Just text.\n\nMore text."
        self.assertEqual(inject_copy_links(md), (md, []))

    def test_paragraph_link_appended(self):
        md = "Line one\nline two\n\nSecond"
        res, texts = inject_copy_links(md, paragraphs=True)
        self.assertEqual(texts, ["Line one\nline two", "Second"])
        self.assertIn(
            'line two <a class="markdown-preview-overlay-copy-para" href="overlay:copy:0">⧉</a>', res)

    def test_list_items_and_blockquotes(self):
        md = "- first\n- second\n  wrapped\n1. third\n\n> quoted\n> more"
        _, texts = inject_copy_links(md, paragraphs=True)
        self.assertEqual(texts, ["first", "second\nwrapped", "third", "quoted\nmore"])

    def test_headings_hr_and_setext_skipped(self):
        md = "# Title\n\nSetext\n======\n\n---\n\nBody"
        _, texts = inject_copy_links(md, paragraphs=True)
        self.assertEqual(texts, ["Body"])

    def test_paragraph_with_inline_code(self):
        res, texts = inject_copy_links("Use `x` here", paragraphs=True)
        self.assertEqual(texts, ["x", "Use `x` here"])
        self.assertTrue(res.endswith('</code></a> here <a class="markdown-preview-overlay-copy-para" href="overlay:copy:1">⧉</a>'))

    def test_html_blocks_untouched(self):
        md = "<div>\n`raw` text\n</div>"
        self.assertEqual(inject_copy_links(md, paragraphs=True), (md, []))


class TestCopyLinkPipeline(unittest.TestCase):
    """Test that copy links do not break image and table preprocessing."""

    def test_all_disabled_is_identity(self):
        md = "Text `x`\n\n```\ncode\n```"
        self.assertEqual(
            inject_copy_links(md, code_blocks=False, paragraphs=False, inline_code=False),
            (md, []))

    def test_tables_and_images_survive(self):
        readme = os.path.join(PARENT_DIR, "README.md")
        md = (
            "![Shot](screenshot.gif)\n\n"
            "| a | b |\n| --- | --- |\n| `x` | **y** |\n\n"
            "Text `code`"
        )
        md = resolve_markdown_image_paths(md, readme, max_width=800)
        md, texts = inject_copy_links(md, paragraphs=True)
        res = render_markdown_tables_as_html(md, 80)
        self.assertIn('<img src="file://', res)
        self.assertIn('<div class="table">', res)
        self.assertIn('<code>x</code>', res)
        self.assertEqual(texts, ["code", "Text `code`"])


if __name__ == "__main__":
    unittest.main()
