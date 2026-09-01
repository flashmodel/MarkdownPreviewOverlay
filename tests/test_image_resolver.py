#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.md_render import get_image_size, resolve_markdown_image_paths


class TestImageResolver(unittest.TestCase):
    """Test suite for image dimension parsing and markdown/HTML path resolution."""

    def setUp(self):
        self.readme_path = os.path.join(PARENT_DIR, "README.md")
        self.gif_path = os.path.join(PARENT_DIR, "screenshot.gif")

    def test_get_image_size(self):
        # 1. Header parsing on local image (screenshot.gif is 2102x1440)
        self.assertEqual(get_image_size(self.gif_path), (2102, 1440))
        # 2. Non-existent file returns None safely
        self.assertIsNone(get_image_size("/non/existent/image.png"))

    def test_markdown_image_resolution_and_scaling(self):
        # 1. Oversized image (> max_width) scales down with proportional height
        md = "![Screenshot](screenshot.gif)"
        res = resolve_markdown_image_paths(md, self.readme_path, max_width=800)
        self.assertIn('<img src="file://', res)
        self.assertIn('width="800" height="548"', res)

        # 2. Image under max_width stays in original Markdown syntax
        res_small = resolve_markdown_image_paths(md, self.readme_path, max_width=3000)
        self.assertTrue(res_small.startswith("![Screenshot](file://"))

        # 3. Remote URLs and code blocks remain protected/untouched
        remote = "![Remote](https://example.com/logo.png)"
        self.assertEqual(resolve_markdown_image_paths(remote, self.readme_path, max_width=800), remote)

        code = "```\n![Code](screenshot.gif)\n```"
        self.assertEqual(resolve_markdown_image_paths(code, self.readme_path, max_width=800), code)

    def test_html_image_resolution_and_proportional_height(self):
        # 1. Pixel width without height: auto-derives height (2102x1440 -> width 200, height 137)
        tag = '<img src="screenshot.gif" alt="Demo" width="200" />'
        res = resolve_markdown_image_paths(tag, self.readme_path, max_width=900)
        self.assertIn('src="file://', res)
        self.assertIn('width="200" height="137"', res)

        # 2. Percentage width: converts to viewport pixels and derives proportional height
        pct_tag = '<img src="screenshot.gif" width="50%" />'
        res_pct = resolve_markdown_image_paths(pct_tag, self.readme_path, max_width=900)
        self.assertIn('width="450" height="308"', res_pct)


    def test_special_schemes_and_file_uris(self):
        # 1. Existing file:// URI still resolves and scales down
        file_uri = f"file://{self.gif_path}"
        md = f"![Local]({file_uri})"
        res = resolve_markdown_image_paths(md, self.readme_path, max_width=800)
        self.assertIn('<img src="file://', res)
        self.assertIn('width="800" height="548"', res)

        # 2. res: and data: schemes remain untouched
        res_uri = "![Icon](res://Packages/Theme/icon.png)"
        self.assertEqual(resolve_markdown_image_paths(res_uri, self.readme_path, max_width=800), res_uri)

        data_uri = "![Inline](data:image/png;base64,iVBORw0KGgo=)"
        self.assertEqual(resolve_markdown_image_paths(data_uri, self.readme_path, max_width=800), data_uri)

    def test_windows_and_space_path_resolution(self):
        from overlay.md_render import MarkdownImageResolver
        resolver = MarkdownImageResolver(r"C:\workspace\docs\readme.md")

        # Windows drive paths without file: prefix
        uri, abs_path = resolver.resolve_path(r"C:\workspace\docs\images\pic.png")
        self.assertEqual(abs_path.replace('\\', '/'), "C:/workspace/docs/images/pic.png")
        self.assertEqual(uri, "file://C:/workspace/docs/images/pic.png")

        # Windows file:/// URLs with 3 slashes
        uri3, abs_path3 = resolver.resolve_path("file:///C:/workspace/docs/images/pic.png")
        self.assertEqual(abs_path3.replace('\\', '/'), "C:/workspace/docs/images/pic.png")
        self.assertEqual(uri3, "file://C:/workspace/docs/images/pic.png")

        # Space in markdown image path formatting
        md_space = "![Space](screenshot.gif)"
        res_space = resolve_markdown_image_paths(md_space, self.readme_path, max_width=3000)
        self.assertTrue(res_space.startswith("![Space]("))


if __name__ == "__main__":
    unittest.main()
