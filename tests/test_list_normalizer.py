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


if __name__ == "__main__":
    unittest.main()
