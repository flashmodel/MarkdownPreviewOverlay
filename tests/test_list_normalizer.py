#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.md_render import normalize_markdown_list_indentation


class TestListNormalizer(unittest.TestCase):
    """Test suite for normalizing 2-space or irregular list indentation."""

    def test_two_space_unordered_list(self):
        source = (
            "- **To Start a New Thread**:\n"
            "  - **Sidebar Context Menu**: Right-click\n"
            "  - **Editor Context Menu**: Right-click\n"
            "  - **Command Palette**: Palette"
        )
        expected = (
            "- **To Start a New Thread**:\n"
            "    - **Sidebar Context Menu**: Right-click\n"
            "    - **Editor Context Menu**: Right-click\n"
            "    - **Command Palette**: Palette"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_one_space_typo_not_nested(self):
        source = (
            "- Root item\n"
            " - Typo item with single space\n"
            "- Another root item"
        )
        expected = (
            "- Root item\n"
            "- Typo item with single space\n"
            "- Another root item"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_multi_level_nesting(self):
        source = (
            "- Level 0\n"
            "  - Level 1\n"
            "    - Level 2\n"
            "  - Back to Level 1\n"
            "- Back to Level 0"
        )
        expected = (
            "- Level 0\n"
            "    - Level 1\n"
            "        - Level 2\n"
            "    - Back to Level 1\n"
            "- Back to Level 0"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_already_four_space_list_unchanged(self):
        source = (
            "- Level 0\n"
            "    - Level 1\n"
            "        - Level 2"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), source)

    def test_ordered_and_task_lists(self):
        source = (
            "1. First step\n"
            "   - [ ] Subtask 1\n"
            "   - [x] Subtask 2"
        )
        expected = (
            "1. First step\n"
            "    - [ ] Subtask 1\n"
            "    - [x] Subtask 2"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_fenced_code_blocks_protected(self):
        source = (
            "- List item:\n"
            "  ```python\n"
            "  def hello():\n"
            "    return 'world'\n"
            "  ```\n"
            "  - Subitem after code"
        )
        expected = (
            "- List item:\n"
            "  ```python\n"
            "  def hello():\n"
            "    return 'world'\n"
            "  ```\n"
            "    - Subitem after code"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_indented_code_blocks_unaltered(self):
        source = (
            "This is a paragraph.\n\n"
            "    code line 1\n"
            "    code line 2"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), source)

    def test_thematic_breaks_protected(self):
        source = (
            "- Item 1\n"
            "- Item 2\n\n"
            "---\n\n"
            "- Item 3\n"
            "  - Subitem"
        )
        expected = (
            "- Item 1\n"
            "- Item 2\n\n"
            "---\n\n"
            "- Item 3\n"
            "    - Subitem"
        )
        self.assertEqual(normalize_markdown_list_indentation(source), expected)

    def test_adjacent_ul_and_ol_separated(self):
        source = (
            "- Unordered 1\n"
            "  1. Nested ordered 1\n"
            "  2. Nested ordered 2\n"
            "- Unordered 2\n\n"
            "1. Ordered 1\n"
            "  - Nested unordered A\n"
            "  - Nested unordered B\n"
            "2. Ordered 2"
        )
        sep = '<div class="markdown-preview-overlay-list-sep"></div>'
        expected = (
            "- Unordered 1\n"
            "    1. Nested ordered 1\n"
            "    2. Nested ordered 2\n"
            "- Unordered 2\n\n"
            f"{sep}\n\n"
            "1. Ordered 1\n"
            "    - Nested unordered A\n"
            "    - Nested unordered B\n"
            "2. Ordered 2"
        )
        out = normalize_markdown_list_indentation(source)
        self.assertEqual(out, expected)
        self.assertNotIn("<!--", out)

    def test_tight_and_multi_blank_list_type_switch(self):
        sep = '<div class="markdown-preview-overlay-list-sep"></div>'
        tight = "1. First\n- Second"
        tight_expected = f"1. First\n\n{sep}\n\n- Second"
        tight_out = normalize_markdown_list_indentation(tight)
        self.assertEqual(tight_out, tight_expected)
        self.assertNotIn("<!--", tight_out)

        multi_blank = "- First\n\n\n1. Second"
        multi_expected = f"- First\n\n\n{sep}\n\n1. Second"
        multi_out = normalize_markdown_list_indentation(multi_blank)
        self.assertEqual(multi_out, multi_expected)
        self.assertNotIn("<!--", multi_out)

        with_para = "- First\n\nParagraph break\n\n1. Second"
        self.assertEqual(normalize_markdown_list_indentation(with_para), with_para)

        with_heading = "- First\n\n## Section\n\n1. Second"
        self.assertEqual(normalize_markdown_list_indentation(with_heading), with_heading)

        with_hr = "- First\n\n---\n\n1. Second"
        self.assertEqual(normalize_markdown_list_indentation(with_hr), with_hr)

    def test_nested_same_level_list_type_switch(self):
        sep = '<div class="markdown-preview-overlay-list-sep"></div>'
        source = (
            "- Parent\n"
            "  - Sub UL\n\n"
            "  1. Sub OL"
        )
        expected = (
            "- Parent\n"
            "    - Sub UL\n\n"
            f"    {sep}\n\n"
            "    1. Sub OL"
        )
        out = normalize_markdown_list_indentation(source)
        self.assertEqual(out, expected)
        self.assertNotIn("<!--", out)

    def test_same_type_and_separate_parent_sublists_no_separator(self):
        same_type = "- A\n* B"
        self.assertEqual(normalize_markdown_list_indentation(same_type), same_type)

        diff_parents = (
            "- Parent 1\n"
            "  - Sub UL\n"
            "- Parent 2\n"
            "  1. Sub OL"
        )
        diff_parents_expected = (
            "- Parent 1\n"
            "    - Sub UL\n"
            "- Parent 2\n"
            "    1. Sub OL"
        )
        self.assertEqual(
            normalize_markdown_list_indentation(diff_parents),
            diff_parents_expected,
        )

    def test_root_list_interrupting_paragraph_inserts_blank_line(self):
        nested_ul = (
            "Notes:\n"
            "- A\n"
            "  - B\n"
            "    1. C\n"
            "    2. D\n"
            "- E"
        )
        nested_ul_expected = (
            "Notes:\n\n"
            "- A\n"
            "    - B\n"
            "        1. C\n"
            "        2. D\n"
            "- E"
        )
        self.assertEqual(
            normalize_markdown_list_indentation(nested_ul),
            nested_ul_expected,
        )

        ordered_after_text = "Steps:\n1. First\n2. Second"
        self.assertEqual(
            normalize_markdown_list_indentation(ordered_after_text),
            "Steps:\n\n1. First\n2. Second",
        )

        for unchanged in ("Year:\n2026. A fresh start", "Notes:\n1) First", "Notes:\n-   "):
            self.assertEqual(normalize_markdown_list_indentation(unchanged), unchanged)

        self.assertEqual(
            normalize_markdown_list_indentation("    code1\n    - code2"),
            "    code1\n    - code2",
        )
        self.assertEqual(
            normalize_markdown_list_indentation("    - code1\n    - code2"),
            "    - code1\n    - code2",
        )

    def test_dedent_after_loose_or_switched_nested_lists(self):
        sep = '<div class="markdown-preview-overlay-list-sep"></div>'

        tight_switch = "- Parent 1\n  - Sub UL\n  1. Sub OL\n- Parent 2"
        self.assertEqual(
            normalize_markdown_list_indentation(tight_switch),
            f"- Parent 1\n    - Sub UL\n\n    {sep}\n\n    1. Sub OL\n\n- Parent 2",
        )

        spaced_switch = "- Parent 1\n  - Sub UL\n\n  1. Sub OL\n- Parent 2"
        self.assertEqual(
            normalize_markdown_list_indentation(spaced_switch),
            f"- Parent 1\n    - Sub UL\n\n    {sep}\n\n    1. Sub OL\n\n- Parent 2",
        )

        ordered_parent = "1. Root OL\n  1. Sub OL\n  - Sub UL\n2. Root OL 2"
        self.assertEqual(
            normalize_markdown_list_indentation(ordered_parent),
            f"1. Root OL\n    1. Sub OL\n\n    {sep}\n\n    - Sub UL\n\n2. Root OL 2",
        )

        deep_nested = (
            "- L0\n"
            "  - L1a\n"
            "    - L2 UL\n"
            "    1. L2 OL\n"
            "  - L1b\n"
            "- L0b"
        )
        deep_expected = (
            "- L0\n"
            "    - L1a\n"
            "        - L2 UL\n\n"
            f"        {sep}\n\n"
            "        1. L2 OL\n\n"
            "    - L1b\n\n"
            "- L0b"
        )
        self.assertEqual(normalize_markdown_list_indentation(deep_nested), deep_expected)

        loose_sublist = "1. Root OL\n\n  - Sub UL\n2. Root OL 2"
        self.assertEqual(
            normalize_markdown_list_indentation(loose_sublist),
            "1. Root OL\n\n    - Sub UL\n\n2. Root OL 2",
        )

        loose_prev_sibling = "- A\n\n- B\n  - Sub B\n- C"
        self.assertEqual(
            normalize_markdown_list_indentation(loose_prev_sibling),
            "- A\n\n- B\n    - Sub B\n- C",
        )

    def test_nested_code_fence_and_fence_separates_lists(self):
        nested_fence = (
            "````markdown\n"
            "```python\n"
            "- inner\n"
            "  - keep two spaces\n"
            "```\n"
            "- still inside outer fence\n"
            "  - untouched\n"
            "````\n"
            "- after\n"
            "  - normalized"
        )
        nested_expected = (
            "````markdown\n"
            "```python\n"
            "- inner\n"
            "  - keep two spaces\n"
            "```\n"
            "- still inside outer fence\n"
            "  - untouched\n"
            "````\n\n"
            "- after\n"
            "    - normalized"
        )
        self.assertEqual(
            normalize_markdown_list_indentation(nested_fence),
            nested_expected,
        )

        inline_ticks = (
            "```code``` inline\n"
            "- item\n"
            "  - subitem"
        )
        self.assertEqual(
            normalize_markdown_list_indentation(inline_ticks),
            "```code``` inline\n\n- item\n    - subitem",
        )

        with_fence = "- First\n\n```python\nx = 1\n```\n\n1. Second"
        self.assertEqual(normalize_markdown_list_indentation(with_fence), with_fence)


if __name__ == "__main__":
    unittest.main()
