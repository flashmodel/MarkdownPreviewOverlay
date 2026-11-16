#!/usr/bin/env python3
import os
import sys
import unittest

PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from overlay.inline_math import latex_to_unicode, render_inline_math
from overlay.md_render import render_markdown_tables_as_html


class TestInlineMath(unittest.TestCase):
    """Test suite for inline LaTeX to Unicode conversion and markdown rendering."""

    def test_relational_operators(self):
        self.assertEqual(latex_to_unicode(r"\ge 2"), "≥ 2")
        self.assertEqual(latex_to_unicode(r"x \le 10"), "x ≤ 10")
        self.assertEqual(latex_to_unicode(r"a \ne b"), "a ≠ b")
        self.assertEqual(latex_to_unicode(r"\pi \approx 3.14"), "π ≈ 3.14")
        self.assertEqual(latex_to_unicode(r"\pm 5\%"), "± 5%")
        self.assertEqual(latex_to_unicode(r"a \ll b \gg c"), "a ≪ b ≫ c")

    def test_greek_letters(self):
        self.assertEqual(latex_to_unicode(r"\alpha + \beta = \gamma"), "α + β = γ")
        self.assertEqual(latex_to_unicode(r"\Delta x \to 0"), "Δ x → 0")
        self.assertEqual(latex_to_unicode(r"\lambda, \mu, \sigma, \omega"), "λ, μ, σ, ω")
        self.assertEqual(latex_to_unicode(r"\Omega, \Theta, \Phi"), "Ω, Θ, Φ")

    def test_superscripts_and_subscripts(self):
        self.assertEqual(latex_to_unicode(r"O(n^2)"), "O(n²)")
        self.assertEqual(latex_to_unicode(r"x_1 + x_2 = x_i"), "x₁ + x₂ = xᵢ")
        self.assertEqual(latex_to_unicode(r"2^{10}"), "2¹⁰")
        self.assertEqual(latex_to_unicode(r"a_{max}"), "aₘₐₓ")
        self.assertEqual(latex_to_unicode(r"x_{total}"), "xₜₒₜₐₗ")
        self.assertEqual(latex_to_unicode(r"x^{a + b}"), "x<sup>a + b</sup>")
        self.assertEqual(latex_to_unicode(r"x_{bad}"), "x<sub>bad</sub>")
        self.assertEqual(latex_to_unicode(r"x^{a + b}", html_tags=False), "x^(a + b)")
        self.assertEqual(latex_to_unicode(r"x_{bad}", html_tags=False), "x_(bad)")

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
        self.assertEqual(latex_to_unicode(r"\sqrt[3]{8}"), "³√(8)")

    def test_sets_and_logic(self):
        self.assertEqual(latex_to_unicode(r"x \in \mathbb{R}"), "x ∈ ℝ")
        self.assertEqual(latex_to_unicode(r"\forall x \in S, \exists y"), "∀ x ∈ S, ∃ y")
        self.assertEqual(latex_to_unicode(r"A \cap B \subseteq C"), "A ∩ B ⊆ C")
        self.assertEqual(latex_to_unicode(r"P \implies Q \iff R"), "P ⇒ Q ⇔ R")

    def test_escaped_characters_and_sizing(self):
        self.assertEqual(latex_to_unicode(r"\% \& \$ \_"), "% & $ _")
        self.assertEqual(latex_to_unicode(r"\{a, b\}"), "{a, b}")
        self.assertEqual(latex_to_unicode(r"\|x\|"), "∥x∥")
        self.assertEqual(latex_to_unicode(r"(\frac{1}{2})"), "(½)")
        self.assertEqual(latex_to_unicode(r"\text{count} \le 5"), "count ≤ 5")
        self.assertEqual(latex_to_unicode(r"\log_2(n) + \sin(\theta)"), "log₂(n) + sin(θ)")

    def test_combining_accents(self):
        self.assertEqual(latex_to_unicode(r"\hat{y}"), "ŷ")
        self.assertEqual(latex_to_unicode(r"\hat y"), "ŷ")
        self.assertEqual(latex_to_unicode(r"\widehat{y}"), "ŷ")
        self.assertEqual(latex_to_unicode(r"\bar{x}"), "x̄")
        self.assertEqual(latex_to_unicode(r"\vec{w}"), "w⃗")
        self.assertEqual(latex_to_unicode(r"\dot{x} + \ddot{x}"), "ẋ + ẍ")
        self.assertEqual(latex_to_unicode(r"\tilde{x}"), "x̃")
        self.assertEqual(latex_to_unicode(r"\hat{\theta}_0"), "θ̂₀")
        self.assertEqual(latex_to_unicode(r"\hat{y}_i"), "ŷᵢ")
        self.assertEqual(latex_to_unicode(r"\vec{w}^T"), "w⃗ᵀ")

    def test_script_and_calligraphy(self):
        self.assertEqual(latex_to_unicode(r"\mathcal{L}"), "ℒ")
        self.assertEqual(latex_to_unicode(r"\mathcal L"), "ℒ")
        self.assertEqual(latex_to_unicode(r"\mathcal{D}"), "𝒟")
        self.assertEqual(latex_to_unicode(r"\mathcal{N}(\mu, \sigma^2)"), "𝒩(μ, σ²)")
        self.assertEqual(latex_to_unicode(r"\mathcal{H}"), "ℋ")

    def test_delimiters_and_advanced_operators(self):
        self.assertEqual(latex_to_unicode(r"\langle x, y \rangle"), "⟨ x, y ⟩")
        self.assertEqual(latex_to_unicode(r"\Vert x \Vert"), "‖ x ‖")
        self.assertEqual(
            latex_to_unicode(r"\lfloor x \rfloor \le \lceil x \rceil"),
            "⌊ x ⌋ ≤ ⌈ x ⌉"
        )
        self.assertEqual(latex_to_unicode(r"\hbar \omega"), "ℏ ω")
        self.assertEqual(latex_to_unicode(r"A \odot B \oplus C \otimes D"), "A ⊙ B ⊕ C ⊗ D")
        self.assertEqual(latex_to_unicode(r"\top \bot"), "⊤ ⊥")

    def test_parentheses_delimiters(self):
        md = (
            r"The loss \( \mathcal{L} \) and prediction "
            r"\( \hat{y} = \mathbf{w}^T \mathbf{x} + b \)"
        )
        res = render_inline_math(md)
        self.assertIn('<span class="markdown-preview-overlay-math">ℒ</span>', res)
        self.assertIn('<span class="markdown-preview-overlay-math">ŷ = wᵀ x + b</span>', res)

    def test_code_spans_and_blocks_protected(self):
        md = (
            "Inline `$code$` and ```\necho $VAR\n``` and <code>$HTML</code> should not change, "
            "but $\\ge 2$ should."
        )
        res = render_inline_math(md)
        self.assertIn("`$code$`", res)
        self.assertIn("echo $VAR", res)
        self.assertIn("<code>$HTML</code>", res)
        self.assertIn('<span class="markdown-preview-overlay-math">≥ 2</span>', res)

    def test_currency_and_escaped_dollars(self):
        md = "Costs $50 and $20, or \\$100 total."
        self.assertEqual(render_inline_math(md), md)

        md_bold = "**$65.76**, experiencing a sharp decline of **$29.77 (-31.16%)**"
        self.assertEqual(render_inline_math(md_bold), md_bold)

    def test_single_line_block_math(self):
        self.assertEqual(
            render_inline_math(r"$$ E = mc^2 $$"),
            '<span class="markdown-preview-overlay-math">E = mc²</span>'
        )

        md = (
            r"$$\text{Foundry Valuation} = 190 \text{ billion USD (base revenue)} "
            r"\times 3.5 = \mathbf{665 \text{ billion ~ 700 billion USD}}$$"
        )
        self.assertEqual(
            render_inline_math(md),
            '<span class="markdown-preview-overlay-math">'
            'Foundry Valuation = 190 billion USD (base revenue) '
            '× 3.5 = 665 billion ~ 700 billion USD'
            '</span>'
        )

        dcf = (
            r"$$\text{DCF Value} = \frac{100 \text{ billion}}{9\% - 3\%} "
            r"\approx \mathbf{2,400 \text{ billion ~ 2,600 billion}}$$"
        )
        self.assertEqual(
            render_inline_math(dcf),
            '<span class="markdown-preview-overlay-math">'
            'DCF Value = (100 billion)/(9% - 3%) ≈ 2,400 billion ~ 2,600 billion'
            '</span>'
        )

        multi = r"$$x = 1$$ and $$y = 2$$"
        self.assertEqual(
            render_inline_math(multi),
            '<span class="markdown-preview-overlay-math">x = 1</span> and '
            '<span class="markdown-preview-overlay-math">y = 2</span>'
        )

    def test_multiline_block_math_protected(self):
        md = "$$\n\\int_0^\\infty f(x) dx\n$$\n\nInline: $\\alpha = 1$"
        res = render_inline_math(md)
        self.assertIn("$$\n\\int_0^\\infty f(x) dx\n$$", res)
        self.assertIn('<span class="markdown-preview-overlay-math">α = 1</span>', res)

        edge = "$$x = 1$$\n$$\n\\int_0^\\infty f(x) dx\n$$"
        res_edge = render_inline_math(edge)
        self.assertIn('<span class="markdown-preview-overlay-math">x = 1</span>\n', res_edge)
        self.assertIn("$$\n\\int_0^\\infty f(x) dx\n$$", res_edge)

    def test_html_escaping_in_math_span(self):
        res = render_inline_math(r"$a < b$ and $x^{a < b}$ and $p \& q$")
        self.assertIn('<span class="markdown-preview-overlay-math">a &lt; b</span>', res)
        self.assertIn(
            '<span class="markdown-preview-overlay-math">x<sup>a &lt; b</sup></span>',
            res
        )
        self.assertIn('<span class="markdown-preview-overlay-math">p &amp; q</span>', res)


class TestHtmlTableMathIntegration(unittest.TestCase):
    """Test inline math integration inside HtmlTableRenderer and preview pipeline."""

    def test_table_cells_render_math_before_alignment(self):
        md = (
            "| Algorithm | Time | Space |\n"
            "|---|---|---|\n"
            "| Binary Search | $O(\\log n)$ | $O(1)$ |\n"
            "| Merge Sort | $O(n \\log n)$ | $O(n)$ |\n"
            "| Limit | $\\lim_{n \\to \\infty} \\frac{1}{n} = 0$ | $\\hat{y}_i$ |\n"
        )
        table_html = render_markdown_tables_as_html(md, max_width=100)
        final = render_inline_math(table_html)

        self.assertIn("O(log n)", final)
        self.assertIn("O(n log n)", final)
        self.assertIn("lim_(n → ∞) 1/n = 0", final)
        self.assertIn("ŷᵢ", final)
        self.assertNotIn("$O(", final)
        self.assertNotIn('<span class="markdown-preview-overlay-math">', final)

    def test_table_code_and_escaped_dollars_protected(self):
        md = (
            "| Token | Example |\n"
            "|---|---|\n"
            "| Code | `$var$` |\n"
            "| Literal | \\$foo\\$ |\n"
            "| Math | $x \\le y$ |\n"
        )
        table_html = render_markdown_tables_as_html(md, max_width=100)
        final = render_inline_math(table_html)

        self.assertIn("<code>$var$</code>", final)
        self.assertIn("$foo$", final)
        self.assertIn("x ≤ y", final)
        self.assertNotIn('<span class="markdown-preview-overlay-math">', final)


if __name__ == "__main__":
    unittest.main()
