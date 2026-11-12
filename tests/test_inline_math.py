#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.inline_math import latex_to_unicode, render_inline_math


class TestInlineMath(unittest.TestCase):
    """Test suite for inline LaTeX to Unicode conversion and markdown rendering."""

    def test_relational_operators(self):
        self.assertEqual(latex_to_unicode(r"\ge 2"), "≥ 2")
        self.assertEqual(latex_to_unicode(r"x \le 10"), "x ≤ 10")
        self.assertEqual(latex_to_unicode(r"a \ne b"), "a ≠ b")
        self.assertEqual(latex_to_unicode(r"\pi \approx 3.14"), "π ≈ 3.14")
        self.assertEqual(latex_to_unicode(r"\pm 5\%"), "± 5%")

    def test_greek_letters(self):
        self.assertEqual(latex_to_unicode(r"\alpha + \beta = \gamma"), "α + β = γ")
        self.assertEqual(latex_to_unicode(r"\Delta x \to 0"), "Δ x → 0")
        self.assertEqual(latex_to_unicode(r"\lambda, \mu, \sigma, \omega"), "λ, μ, σ, ω")

    def test_superscripts_and_subscripts(self):
        self.assertEqual(latex_to_unicode(r"O(n^2)"), "O(n²)")
        self.assertEqual(latex_to_unicode(r"x_1 + x_2 = x_i"), "x₁ + x₂ = xᵢ")
        self.assertEqual(latex_to_unicode(r"2^{10}"), "2¹⁰")
        self.assertEqual(latex_to_unicode(r"a_{max}"), "aₘₐₓ")

    def test_fractions_and_roots(self):
        self.assertEqual(latex_to_unicode(r"\frac{1}{2}"), "½")
        self.assertEqual(latex_to_unicode(r"\frac{3}{4}"), "¾")
        self.assertEqual(latex_to_unicode(r"\frac{a}{b}"), "a/b")
        self.assertEqual(latex_to_unicode(r"\frac{x + 1}{y - 1}"), "(x + 1)/(y - 1)")
        self.assertEqual(latex_to_unicode(r"\frac{x + y}{2}"), "(x + y)/2")
        self.assertEqual(latex_to_unicode(r"\frac{1}{x + y}"), "1/(x + y)")
        self.assertEqual(latex_to_unicode(r"(\frac{1}{2} + \frac{1}{4}) \times 2"), "(½ + ¼) × 2")
        self.assertEqual(latex_to_unicode(r"[\frac{a + b}{c}]^2"), "[(a + b)/c]²")
        self.assertEqual(latex_to_unicode(r"\frac{1}{1 + \frac{1}{2}}"), "1/(1 + ½)")
        self.assertEqual(latex_to_unicode(r"\sqrt{x^2 + 1}"), "√(x² + 1)")

    def test_sets_and_logic(self):
        self.assertEqual(latex_to_unicode(r"x \in \mathbb{R}"), "x ∈ ℝ")
        self.assertEqual(latex_to_unicode(r"\forall x \in S, \exists y"), "∀ x ∈ S, ∃ y")
        self.assertEqual(latex_to_unicode(r"A \cap B \subseteq C"), "A ∩ B ⊆ C")

    def test_code_spans_and_blocks_protected(self):
        md = (
            "Inline `$code$` and ```\necho $VAR\n``` should not change, "
            "but $\ge 2$ should."
        )
        res = render_inline_math(md)
        self.assertIn("`$code$`", res)
        self.assertIn("echo $VAR", res)
        self.assertIn('<span class="markdown-preview-overlay-math">≥ 2</span>', res)

    def test_currency_and_escaped_dollars(self):
        md = "Costs $50 and $20, or \\$100 total."
        self.assertEqual(render_inline_math(md), md)

    def test_block_math_protected(self):
        md = "$$\n\\int_0^\\infty f(x) dx\n$$\n\nInline: $\\alpha = 1$"
        res = render_inline_math(md)
        self.assertIn("$$\n\\int_0^\\infty f(x) dx\n$$", res)
        self.assertIn('<span class="markdown-preview-overlay-math">α = 1</span>', res)


if __name__ == "__main__":
    unittest.main()
