"""Custom Markdown rendering, transformations, and miniHTML formatting."""

import html
import re
import unicodedata


class HtmlTableRenderer:
    """Helper to render Markdown tables as minihtml block elements with CJK support."""

    _HTML_LINE_BREAK_RE = re.compile(r'<br\s*/?\s*>', re.IGNORECASE)
    _EXPLICIT_LINE_BREAK = '\n'

    def __init__(self, max_width=100):
        self.max_width = max_width

    def char_width(self, char):
        if unicodedata.combining(char):
            return 0
        if unicodedata.east_asian_width(char) in ('W', 'F'):
            return 2
        return 1

    def str_width(self, text):
        return sum(self.char_width(c) for c in text)

    def _wrap_cell(self, text, width):
        text = text.strip()
        if not text:
            return [""]

        lines = []
        while text:
            display_width = 0
            end = 0
            for end, char in enumerate(text, 1):
                char_width = self.char_width(char)
                if display_width + char_width > width:
                    end -= 1
                    break
                display_width += char_width
            else:
                lines.append(text)
                break

            if end == 0:
                end = 1

            candidate = text[:end]
            whitespace_breaks = [
                i for i, char in enumerate(candidate) if char.isspace()
            ]
            if whitespace_breaks and whitespace_breaks[-1] > 0:
                end = whitespace_breaks[-1]
                candidate = text[:end]

            lines.append(candidate.rstrip())
            text = text[end:].lstrip()

        return lines

    def _fit_column_widths(self, natural_widths, max_table_width):
        column_count = len(natural_widths)
        fixed_width = 2 * column_count
        available = max_table_width - fixed_width
        minimum_width = 3

        if available < minimum_width * column_count:
            return [minimum_width] * column_count
        if sum(natural_widths) <= available:
            return natural_widths

        low, high = minimum_width, max(natural_widths)
        while low < high:
            cap = (low + high + 1) // 2
            required = sum(max(minimum_width, min(width, cap))
                           for width in natural_widths)
            if required <= available:
                low = cap
            else:
                high = cap - 1

        widths = [max(minimum_width, min(width, low))
                  for width in natural_widths]
        remaining = available - sum(widths)
        for i, natural_width in enumerate(natural_widths):
            if remaining == 0:
                break
            extra = min(natural_width - widths[i], remaining)
            widths[i] += extra
            remaining -= extra
        return widths

    def _split_table_row(self, line):
        text = line.strip()
        cells = []
        current = []
        code_fence = 0
        i = 0
        while i < len(text):
            char = text[i]
            if char == '\\' and i + 1 < len(text):
                current.append(char)
                current.append(text[i + 1])
                i += 2
                continue
            if char == '`':
                run_end = i + 1
                while run_end < len(text) and text[run_end] == '`':
                    run_end += 1
                run_length = run_end - i
                if code_fence == 0:
                    code_fence = run_length
                elif code_fence == run_length:
                    code_fence = 0
                current.extend(text[i:run_end])
                i = run_end
                continue
            if char == '|' and code_fence == 0:
                cells.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
            i += 1
        cells.append(''.join(current).strip())

        if text.startswith('|') and cells and cells[0] == "":
            cells.pop(0)
        if text.endswith('|') and cells and cells[-1] == "":
            cells.pop()
        return cells

    def parse_table(self, lines):
        if not lines:
            return None
        rows = [self._split_table_row(line) for line in lines]
        if not rows:
            return None

        max_cols = max(len(row) for row in rows)
        for row in rows:
            while len(row) < max_cols:
                row.append("")

        separator_idx = -1
        alignments = []
        for i, row in enumerate(rows):
            row_aligns = []
            for cell in row:
                if not re.match(r'^:?-+:?$', cell):
                    break
                if cell.startswith(':') and cell.endswith(':'):
                    row_aligns.append('center')
                elif cell.endswith(':'):
                    row_aligns.append('right')
                elif cell.startswith(':'):
                    row_aligns.append('left')
                else:
                    row_aligns.append(None)
            else:
                if i > 0:
                    separator_idx = i
                    alignments = row_aligns
                    break

        if separator_idx == -1:
            return None
        while len(alignments) < max_cols:
            alignments.append(None)
        return rows, separator_idx, alignments

    def _find_closing_marker(self, text, marker, start):
        pos = start
        while True:
            pos = text.find(marker, pos)
            if pos == -1:
                return -1
            escapes = 0
            check = pos - 1
            while check >= 0 and text[check] == '\\':
                escapes += 1
                check -= 1
            if escapes % 2 == 0:
                return pos
            pos += len(marker)

    def _parse_inline_chars(self, text, styles=frozenset()):
        chars = []
        i = 0
        while i < len(text):
            if text[i] == '\\' and i + 1 < len(text):
                chars.append((text[i + 1], styles))
                i += 2
                continue

            if text[i] == '<':
                line_break = self._HTML_LINE_BREAK_RE.match(text, i)
                if line_break:
                    chars.append((self._EXPLICIT_LINE_BREAK, styles))
                    i = line_break.end()
                    continue

            if text[i] == '`':
                run_end = i + 1
                while run_end < len(text) and text[run_end] == '`':
                    run_end += 1
                marker = text[i:run_end]
                close = self._find_closing_marker(text, marker, run_end)
                if close != -1:
                    code_styles = styles | {'code'}
                    chars.extend((char, code_styles)
                                 for char in text[run_end:close])
                    i = close + len(marker)
                    continue

            marker = None
            if text.startswith('**', i):
                marker = '**'
            elif text.startswith('__', i):
                marker = '__'
            if marker:
                close = self._find_closing_marker(
                    text, marker, i + len(marker))
                if close != -1:
                    strong_styles = styles | {'strong'}
                    chars.extend(self._parse_inline_chars(
                        text[i + len(marker):close], strong_styles))
                    i = close + len(marker)
                    continue

            chars.append((text[i], styles))
            i += 1

        start = 0
        end = len(chars)
        while start < end and chars[start][0].isspace():
            start += 1
        while end > start and chars[end - 1][0].isspace():
            end -= 1
        return chars[start:end]

    def _split_explicit_lines(self, chars):
        lines = [[]]
        for char, styles in chars:
            if char == self._EXPLICIT_LINE_BREAK:
                lines.append([])
            else:
                lines[-1].append((char, styles))
        return lines

    def _styled_line_width(self, chars):
        return sum(self.char_width(c) for c, _ in chars)

    def _widest_styled_line_width(self, chars):
        return max(self._styled_line_width(line)
                   for line in self._split_explicit_lines(chars))

    def _wrap_styled_chars(self, chars, width):
        lines = []
        for explicit_line in self._split_explicit_lines(chars):
            lines.extend(self._wrap_styled_segment(explicit_line, width))
        return lines

    def _wrap_styled_segment(self, chars, width):
        if not chars:
            return [[]]
        remaining = list(chars)
        lines = []
        while remaining:
            display_width = 0
            end = 0
            for end, (char, _) in enumerate(remaining, 1):
                char_width = self.char_width(char)
                if display_width + char_width > width:
                    end -= 1
                    break
                display_width += char_width
            else:
                lines.append(remaining)
                break

            if end == 0:
                end = 1
            candidate = remaining[:end]
            whitespace_breaks = [
                i for i, (char, _) in enumerate(candidate) if char.isspace()
            ]
            if whitespace_breaks and whitespace_breaks[-1] > 0:
                end = whitespace_breaks[-1]
                candidate = remaining[:end]

            while candidate and candidate[-1][0].isspace():
                candidate.pop()
            lines.append(candidate)
            remaining = remaining[end:]
            while remaining and remaining[0][0].isspace():
                remaining.pop(0)
        return lines

    def _render_inline_html(self, chars):
        if not chars:
            return ""
        parts = []
        run = []
        current_styles = chars[0][1]

        def flush_run():
            if not run:
                return
            content = html.escape(''.join(run), quote=True)
            if 'code' in current_styles:
                content = f"<code>{content}</code>"
            if 'strong' in current_styles:
                content = f"<strong>{content}</strong>"
            parts.append(content)
            run.clear()

        for c, styles in chars:
            if styles != current_styles:
                flush_run()
                current_styles = styles
            run.append(c)
        flush_run()
        return ''.join(parts)

    def _pad_styled_line(self, chars, width, alignment):
        padding = max(0, width - self._styled_line_width(chars))
        if alignment == 'right':
            left = padding
        elif alignment == 'center':
            left = padding // 2
        else:
            left = 0
        right = padding - left
        plain = frozenset()
        return ([(' ', plain)] * left + chars + [(' ', plain)] * right)

    def render_html_table(self, parsed):
        rows, separator_idx, alignments = parsed
        display_rows = []
        natural_widths = [3] * len(rows[0])
        for i, row in enumerate(rows):
            if i == separator_idx:
                continue
            styled_row = [self._parse_inline_chars(cell) for cell in row]
            display_rows.append(styled_row)
            for j, chars in enumerate(styled_row):
                natural_widths[j] = max(
                    natural_widths[j],
                    self._widest_styled_line_width(chars),
                )

        col_widths = self._fit_column_widths(natural_widths, self.max_width)
        rendered = []
        for row_idx, styled_row in enumerate(display_rows):
            wrapped_cells = [
                self._wrap_styled_chars(chars, col_widths[j])
                for j, chars in enumerate(styled_row)
            ]
            row_height = max(len(lines) for lines in wrapped_cells)
            visual_lines = []
            for line_idx in range(row_height):
                pieces = []
                for j, lines in enumerate(wrapped_cells):
                    chars = lines[line_idx] if line_idx < len(lines) else []
                    padded = self._pad_styled_line(
                        chars, col_widths[j], alignments[j])
                    pieces.append(
                        ' ' + self._render_inline_html(padded) + ' ')
                visual_lines.append(
                    '<div class="visual-row">' + ''.join(pieces) + '</div>')

            row_classes = ["logical-row"]
            if row_idx == 0:
                row_classes.append("header-row")
            if row_idx == len(display_rows) - 1:
                row_classes.append("last-row")
            row_class_str = " ".join(row_classes)
            rendered.append(
                f'<div class="{row_class_str}">' +
                ''.join(visual_lines) + '</div>')

        return (
            '<style>'
            '.table{color:var(--foreground);font-family:monospace;'
            'font-size:1rem;line-height:1.25rem;white-space:pre;'
            'display:block;margin:0.8rem 0;'
            'border:1px solid color(var(--foreground) alpha(0.35));'
            'border-radius:2px}'
            '.logical-row{margin:0;padding-top:0.4rem;'
            'padding-bottom:0.4rem;'
            'border-bottom:1px solid color(var(--foreground) alpha(0.2))}'
            '.header-row{padding-top:0.45rem;padding-bottom:0.45rem;'
            'border-bottom-color:'
            'color(var(--foreground) alpha(0.35))}'
            '.last-row{border-bottom-width:0}'
            '.visual-row{margin:0;padding:0}'
            '.table code{font-family:monospace;color:var(--cyanish);'
            'background-color:color(var(--foreground) alpha(0.08))}'
            '.table strong{font-weight:bold}'
            '</style><div class="table">' + ''.join(rendered) + '</div>'
        )


def render_markdown_tables_as_html(text, max_width):
    """Scan markdown for table blocks and convert them to adaptive miniHTML tables."""
    text = text.expandtabs(4)
    lines = text.split('\n')
    output = []
    table_buffer = []
    in_code_block = False
    fence_char = None
    fence_len = 0

    formatter = HtmlTableRenderer(max_width=max_width)

    def flush_table():
        if not table_buffer:
            return
        parsed = formatter.parse_table(table_buffer)
        if parsed is not None:
            html_table = formatter.render_html_table(parsed)
            # Blank lines around raw HTML blocks ensure Python-Markdown treats
            # it as a raw HTML block and preserves it without escaping.
            output.append('')
            output.append(html_table)
            output.append('')
        else:
            output.extend(table_buffer)
        table_buffer.clear()

    for line in lines:
        stripped = line.strip()

        # Handle code fences (``` or ~~~)
        if not in_code_block:
            if stripped.startswith('```') or stripped.startswith('~~~'):
                flush_table()
                in_code_block = True
                fence_char = stripped[0]
                fence_len = len(stripped) - len(stripped.lstrip(fence_char))
                output.append(line)
                continue
        else:
            if stripped.startswith(fence_char * fence_len):
                in_code_block = False
                fence_char = None
                fence_len = 0
            output.append(line)
            continue

        if stripped.startswith('|') and '|' in stripped[1:]:
            table_buffer.append(line)
        else:
            flush_table()
            output.append(line)

    flush_table()
    return '\n'.join(output)
