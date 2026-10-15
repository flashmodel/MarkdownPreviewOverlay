"""Custom Markdown rendering, transformations, and miniHTML formatting."""

import html
import os
import pathlib
import re
import struct
import unicodedata
import urllib.parse


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

    def flush_table_buffer(self, table_buffer, output):
        """Parse buffered table lines and append rendered table or raw lines to output."""
        if not table_buffer:
            return
        parsed = self.parse_table(table_buffer)
        if parsed is not None:
            # Blank lines around raw HTML blocks ensure Python-Markdown treats
            # it as a raw HTML block and preserves it without escaping.
            output.append('')
            output.append(self.render_html_table(parsed))
            output.append('')
        else:
            output.extend(table_buffer)
        table_buffer.clear()

    def transform_markdown(self, text):
        """Scan markdown for table blocks and convert them to adaptive miniHTML tables."""
        text = text.expandtabs(4)
        lines = text.split('\n')
        output = []
        table_buffer = []
        in_code_block = False
        fence_char = None
        fence_len = 0

        for line in lines:
            stripped = line.strip()

            # Handle code fences (``` or ~~~)
            if not in_code_block:
                if stripped.startswith('```') or stripped.startswith('~~~'):
                    self.flush_table_buffer(table_buffer, output)
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
                self.flush_table_buffer(table_buffer, output)
                output.append(line)

        self.flush_table_buffer(table_buffer, output)
        return '\n'.join(output)


def render_markdown_tables_as_html(text, max_width):
    """Scan markdown for table blocks and convert them to adaptive miniHTML tables."""
    return HtmlTableRenderer(max_width=max_width).transform_markdown(text)


COPY_HREF_PREFIX = "overlay:copy:"


class CopyLinkInjector:
    """Helper to inject click-to-copy links for code blocks, paragraphs and inline code.

    Copied texts are collected in ``self.texts`` and referenced by index from
    ``overlay:copy:<index>`` hrefs so large text is never embedded in a link.
    """

    _INLINE_CODE_RE = re.compile(r'(?<![\\`])(`+)(?!`)(.+?)(?<!`)\1(?!`)')
    _PROTECTED_RE = re.compile(
        r'!?\[[^\]\n]*\](?:\([^)\n]*\)|\[[^\]\n]*\])|<[^>\n]+>'
    )
    _LIST_ITEM_RE = re.compile(r'^\s*(?:[-+*]|\d{1,9}[.)])(?:\s+|$)')
    _BLOCKQUOTE_RE = re.compile(r'^\s{0,3}>\s?')
    _HEADING_RE = re.compile(r'^\s{0,3}#{1,6}(?:\s|$)')
    _HR_RE = re.compile(r'^\s{0,3}([-*_])(?:\s*\1){2,}\s*$')
    _SETEXT_RE = re.compile(r'^\s{0,3}(?:=+|-+)\s*$')

    def __init__(self, code_blocks=True, paragraphs=False, inline_code=True):
        self.code_blocks = code_blocks
        self.paragraphs = paragraphs
        self.inline_code = inline_code
        self.texts = []

    def _href(self, text):
        self.texts.append(text)
        return f'{COPY_HREF_PREFIX}{len(self.texts) - 1}'

    @staticmethod
    def _indent_width(line):
        expanded = line.expandtabs(4)
        return len(expanded) - len(expanded.lstrip(' '))

    @staticmethod
    def _is_fence(stripped):
        return stripped.startswith('```') or stripped.startswith('~~~')

    @staticmethod
    def _is_table_line(stripped):
        return stripped.startswith('|') and '|' in stripped[1:]

    @staticmethod
    def _strip_indent(line, width):
        """Remove up to ``width`` columns of leading whitespace from a line."""
        removed = 0
        i = 0
        while i < len(line) and removed < width:
            if line[i] == ' ':
                removed += 1
            elif line[i] == '\t':
                removed += 4 - (removed % 4)
            else:
                break
            i += 1
        return line[i:]

    @staticmethod
    def _encode_inline(text):
        """Encode code text so Markdown inline processing leaves it untouched.

        mdpopups unescapes numeric entities before handing HTML to minihtml,
        so ``&``, ``<`` and ``>`` must use the named entities it preserves.
        """
        named = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}
        return ''.join(
            c if c.isalnum() or c == ' ' else named.get(c, f'&#{ord(c)};')
            for c in text
        )

    def _is_block_start(self, line):
        stripped = line.strip()
        return (
            not stripped
            or self._is_fence(stripped)
            or self._is_table_line(stripped)
            or stripped.startswith('<')
            or bool(self._HEADING_RE.match(line))
            or bool(self._HR_RE.match(line))
        )

    def _emit_code_link(self, output, indent, code):
        if output and output[-1].strip():
            output.append('')
        output.append(
            f'{indent}<a class="markdown-preview-overlay-copy-code" '
            f'href="{self._href(code)}">⧉ Copy</a>'
        )
        output.append('')

    def wrap_inline_code(self, line):
        """Wrap inline code spans of a single line in copy links."""
        if not self.inline_code or '`' not in line:
            return line
        matches = list(self._INLINE_CODE_RE.finditer(line))
        if not matches:
            return line

        def inside(pos, spans):
            return any(start <= pos < end for start, end in spans)

        code_spans = [(m.start(), m.end()) for m in matches]
        protected = [
            (m.start(), m.end())
            for m in self._PROTECTED_RE.finditer(line)
            if not inside(m.start(), code_spans)
        ]

        parts = []
        last = 0
        for m in matches:
            if inside(m.start(), protected):
                continue
            content = m.group(2)
            if (len(content) >= 2 and content[0] == ' '
                    and content[-1] == ' ' and content.strip()):
                content = content[1:-1]
            parts.append(line[last:m.start()])
            parts.append(
                f'<a class="markdown-preview-overlay-copy-inline" '
                f'href="{self._href(content)}">'
                f'<code>{self._encode_inline(content)}</code></a>'
            )
            last = m.end()
        parts.append(line[last:])
        return ''.join(parts)

    def _consume_fence(self, lines, i, output):
        """Copy a fenced code block to output and return the index after it."""
        line = lines[i]
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]
        fence_char = stripped[0]
        fence_len = len(stripped) - len(stripped.lstrip(fence_char))

        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith(fence_char * fence_len):
            j += 1
        body = lines[i + 1:j]

        if self.code_blocks:
            width = self._indent_width(indent)
            code = '\n'.join(self._strip_indent(b, width) for b in body)
            self._emit_code_link(output, indent, code)
        output.append(line)
        output.extend(body)
        if j < len(lines):
            output.append(lines[j])
        return j + 1

    def _consume_indented_code(self, lines, i, output):
        """Copy an indented code block to output and return the index after it."""
        j = i
        while j < len(lines) and (not lines[j].strip() or self._indent_width(lines[j]) >= 4):
            j += 1
        while j > i and not lines[j - 1].strip():
            j -= 1
        body = lines[i:j]

        if self.code_blocks:
            code = '\n'.join(self._strip_indent(b, 4) for b in body)
            self._emit_code_link(output, '', code)
        output.extend(body)
        return j

    def _consume_prose(self, lines, i, output):
        """Copy a paragraph, list item or blockquote paragraph and return the index after it."""
        first = lines[i]
        if self._BLOCKQUOTE_RE.match(first):
            kind = 'quote'
        elif self._LIST_ITEM_RE.match(first):
            kind = 'list'
        else:
            kind = 'para'

        j = i + 1
        while j < len(lines):
            line = lines[j]
            if kind == 'para' and self._SETEXT_RE.match(line):
                # Setext heading: emit text and underline without a copy link.
                output.extend(self.wrap_inline_code(l) for l in lines[i:j])
                output.append(line)
                return j + 1
            if self._is_block_start(line) or self._LIST_ITEM_RE.match(line):
                break
            if kind != 'quote' and self._BLOCKQUOTE_RE.match(line):
                break
            j += 1

        block = lines[i:j]
        rendered = [self.wrap_inline_code(l) for l in block]
        if self.paragraphs:
            if kind == 'quote':
                source = [self._BLOCKQUOTE_RE.sub('', l, count=1).strip() for l in block]
            elif kind == 'list':
                source = [self._LIST_ITEM_RE.sub('', block[0], count=1).strip()]
                source.extend(l.strip() for l in block[1:])
            else:
                source = [l.strip() for l in block]
            rendered[-1] = (
                rendered[-1].rstrip() +
                f' <a class="markdown-preview-overlay-copy-para" '
                f'href="{self._href(chr(10).join(source))}">⧉</a>'
            )
        output.extend(rendered)
        return j

    def inject(self, text):
        """Return markdown with copy links injected; copied texts are kept in ``self.texts``."""
        if not (self.code_blocks or self.paragraphs or self.inline_code):
            return text

        lines = text.split('\n')
        output = []
        in_list = False
        prev_blank = True
        in_html = False
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                output.append(line)
                prev_blank = True
                in_html = False
                i += 1
                continue

            if in_html:
                output.append(line)
                i += 1
                continue

            indent = self._indent_width(line)
            if self._LIST_ITEM_RE.match(line):
                in_list = True
            elif prev_blank and indent == 0:
                in_list = False

            if self._is_fence(stripped):
                i = self._consume_fence(lines, i, output)
            elif prev_blank and indent >= 4 and not in_list:
                i = self._consume_indented_code(lines, i, output)
            elif self._is_table_line(stripped):
                output.append(line)
                i += 1
            elif stripped.startswith('<'):
                output.append(line)
                in_html = True
                i += 1
            elif self._HEADING_RE.match(line) or self._HR_RE.match(line):
                output.append(self.wrap_inline_code(line))
                i += 1
            else:
                i = self._consume_prose(lines, i, output)
            prev_blank = False

        return '\n'.join(output)


def inject_copy_links(text, code_blocks=True, paragraphs=False, inline_code=True):
    """Inject click-to-copy links; return (markdown, texts) where hrefs index into texts."""
    injector = CopyLinkInjector(
        code_blocks=code_blocks, paragraphs=paragraphs, inline_code=inline_code)
    return injector.inject(text), injector.texts


def get_image_size(file_path):
    """Read image dimensions (width, height) directly from file header without external dependencies."""
    if not file_path or not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, 'rb') as f:
            head = f.read(64)
            if not head:
                return None

            # PNG: bytes 16..24 (width, height as 4-byte big-endian ints)
            if head.startswith(b'\x89PNG\r\n\x1a\n') and len(head) >= 24:
                return struct.unpack('>II', head[16:24])

            # GIF: bytes 6..10 (width, height as 2-byte little-endian ints)
            if (head.startswith(b'GIF87a') or head.startswith(b'GIF89a')) and len(head) >= 10:
                return struct.unpack('<HH', head[6:10])

            # BMP: bytes 18..26 (width, height as 4-byte little-endian ints)
            if head.startswith(b'BM') and len(head) >= 26:
                return struct.unpack('<II', head[18:26])

            # WebP: RIFF....WEBP
            if head.startswith(b'RIFF') and len(head) >= 30 and head[8:12] == b'WEBP':
                if head[12:16] == b'VP8 ' and len(head) >= 30:
                    w, h = struct.unpack('<HH', head[26:30])
                    return (w & 0x3fff, h & 0x3fff)
                elif head[12:16] == b'VP8L' and len(head) >= 25:
                    b0, b1, b2, b3, b4 = head[21:26]
                    w = 1 + (((b1 & 0x3f) << 8) | b0)
                    h = 1 + (((b3 & 0xf) << 10) | (b2 << 2) | ((b1 & 0xc0) >> 6))
                    return (w, h)
                elif head[12:16] == b'VP8X' and len(head) >= 30:
                    w = 1 + (head[24] | (head[25] << 8) | (head[26] << 16))
                    h = 1 + (head[27] | (head[28] << 8) | (head[29] << 16))
                    return (w, h)

            # JPEG: scan markers for SOF (0xFF, 0xC0..0xC3)
            if head.startswith(b'\xff\xd8'):
                f.seek(0)
                data = f.read(8192)
                idx = 2
                while idx < len(data) - 8:
                    if data[idx] != 0xff:
                        idx += 1
                        continue
                    marker = data[idx + 1]
                    if marker in (0xc0, 0xc1, 0xc2, 0xc3):
                        h, w = struct.unpack('>HH', data[idx + 5:idx + 9])
                        return (w, h)
                    idx += 2 + struct.unpack('>H', data[idx + 2:idx + 4])[0]
    except Exception:
        pass
    return None


class MarkdownImageResolver:
    """Helper to resolve relative Markdown and HTML image paths to absolute file:// URLs and adapt large images."""

    _MD_IMG_PATTERN = re.compile(
        r'!\[(?P<alt>[^\]]*)\]\(\s*(?P<url><[^>\n]+>|[^)\s]+)(?:\s+(?P<title>(?:"[^"]*")|(?:\'[^\']*\')|(?:\([^)\n]*\))))?\s*\)'
    )

    _HTML_IMG_PATTERN = re.compile(
        r'<img\b[^>]*>',
        re.IGNORECASE
    )

    _CODE_PATTERN = re.compile(
        r'(```[\s\S]*?```|~~~[\s\S]*?~~~|`+[^`\n]+`+)'
    )

    def __init__(self, file_name, max_width=None):
        self.file_name = file_name
        self.max_width = max_width
        self.base_dir = (
            os.path.dirname(os.path.abspath(file_name))
            if file_name
            else None
        )

    @staticmethod
    def _is_windows_drive_path(path):
        """Check if path starts with a Windows drive letter (e.g., C:\\, D:/, C:foo)."""
        return bool(path and len(path) >= 2 and path[0].isalpha() and path[1] == ':')

    @classmethod
    def _to_file_uri(cls, abs_path):
        """Convert local absolute path to minihtml-compatible file URI (avoids Windows 3-slash & encoding bugs)."""
        normalized = abs_path.replace('\\', '/')
        if cls._is_windows_drive_path(normalized):
            return f"file://{normalized}"
        return pathlib.Path(abs_path).as_uri()

    def is_url_scheme(self, src):
        """Return True if src contains a scheme like http:, data:, or res: (excluding Windows drive letters)."""
        if not src or self._is_windows_drive_path(src):
            return False
        return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', src))

    def resolve_path(self, raw_path):
        """Resolve a single raw image path into (uri, local_abs_path)."""
        if not raw_path or raw_path.startswith('//') or raw_path.startswith('#'):
            return None, None
        if raw_path.startswith(('res:', 'data:')):
            return None, None
        if self.is_url_scheme(raw_path) and not raw_path.lower().startswith('file:'):
            return None, None

        query = fragment = ''
        if raw_path.lower().startswith('file:'):
            url_parts = urllib.parse.urlsplit(raw_path)
            path_part = urllib.parse.unquote(url_parts.path)
            # Remove leading slash in /C:/... on Windows
            if path_part.startswith('/') and self._is_windows_drive_path(path_part[1:]):
                path_part = path_part[1:]
            abs_path = os.path.normpath(path_part)
            query, fragment = url_parts.query, url_parts.fragment
        elif self._is_windows_drive_path(raw_path):
            abs_path = os.path.normpath(raw_path)
        else:
            # Relative path or POSIX absolute path
            url_parts = urllib.parse.urlsplit(raw_path)
            path_part = url_parts.path
            if not path_part:
                return None, None

            unquoted = urllib.parse.unquote(path_part)
            if os.path.isabs(unquoted):
                abs_path = os.path.normpath(unquoted)
            elif self.base_dir:
                # Resolve relative path about markdown directory
                abs_path = os.path.normpath(os.path.join(self.base_dir, unquoted))
            else:
                return None, None
            query, fragment = url_parts.query, url_parts.fragment

        try:
            uri = self._to_file_uri(abs_path)
            if query:
                uri += f'?{query}'
            if fragment:
                uri += f'#{fragment}'
            return uri, abs_path
        except Exception:
            return None, None

    def replace_md_image(self, match):
        """Regex replacement callback for Markdown image syntax."""
        alt = match.group('alt')
        raw_url = match.group('url')
        title = match.group('title')
        wrapped = raw_url.startswith('<') and raw_url.endswith('>')
        url = raw_url[1:-1] if wrapped else raw_url

        resolved_uri, local_path = self.resolve_path(url)
        if not resolved_uri:
            return match.group(0)

        # Scale down proportionally if local image width exceeds available viewport width
        if local_path and self.max_width:
            size = get_image_size(local_path)
            if size and size[0] > self.max_width:
                orig_w, orig_h = size
                scaled_h = max(1, int(orig_h * (self.max_width / orig_w)))
                clean_title = title.strip('\'"()') if title else ''
                title_attr = f' title="{html.escape(clean_title, quote=True)}"' if clean_title else ''
                alt_attr = html.escape(alt, quote=True)
                return (
                    f'<img src="{resolved_uri}" alt="{alt_attr}"{title_attr} '
                    f'width="{self.max_width}" height="{scaled_h}" />'
                )

        uri_str = f'<{resolved_uri}>' if (' ' in resolved_uri or wrapped) else resolved_uri
        if title:
            return f'![{alt}]({uri_str} {title})'
        return f'![{alt}]({uri_str})'

    def _append_tag_attributes(self, tag_str, attrs_str):
        """Append extra attribute(s) to an HTML tag before its closing > or />."""
        closing_idx = tag_str.rfind('>')
        if closing_idx == -1:
            return tag_str
        if tag_str[closing_idx - 1] == '/':
            return tag_str[:closing_idx - 1].rstrip() + f' {attrs_str} />'
        return tag_str[:closing_idx].rstrip() + f' {attrs_str}>'

    def adjust_html_image_dimensions(self, tag_str, local_path):
        """Ensure proportional width/height attributes are injected for local HTML <img> tags."""
        if not local_path:
            return tag_str

        size = get_image_size(local_path)
        if not size:
            return tag_str

        orig_w, orig_h = size
        w_m = re.search(r'\bwidth=(?P<q>["\']?)(?P<w>[0-9]+(?:\.[0-9]+)?%?)(?P=q)', tag_str, re.IGNORECASE)
        h_m = re.search(r'\bheight=(?P<q>["\']?)(?P<h>[0-9]+(?:\.[0-9]+)?%?)(?P=q)', tag_str, re.IGNORECASE)

        if w_m and not h_m:
            w_str = w_m.group('w')
            if w_str.endswith('%') and self.max_width:
                pct = float(w_str[:-1]) / 100.0
                target_w = max(1, int(self.max_width * pct))
                target_h = max(1, int(orig_h * (target_w / orig_w)))
                return tag_str[:w_m.start()] + f'width="{target_w}" height="{target_h}"' + tag_str[w_m.end():]
            elif not w_str.endswith('%'):
                try:
                    target_w = int(float(w_str))
                    target_h = max(1, int(orig_h * (target_w / orig_w)))
                    return self._append_tag_attributes(tag_str, f'height="{target_h}"')
                except Exception:
                    pass
        elif not w_m and not h_m and self.max_width and orig_w > self.max_width:
            target_w = self.max_width
            target_h = max(1, int(orig_h * (target_w / orig_w)))
            return self._append_tag_attributes(tag_str, f'width="{target_w}" height="{target_h}"')

        return tag_str

    def replace_html_image(self, match):
        """Regex replacement callback for HTML <img> tag syntax."""
        tag_str = match.group(0)
        src_m = re.search(r'\bsrc=(?P<q>["\'])(?P<src>[^"\'\n]+)(?P=q)', tag_str, re.IGNORECASE)
        if not src_m:
            return tag_str

        src = src_m.group('src')
        resolved_uri, local_path = self.resolve_path(src)
        if not resolved_uri:
            return tag_str

        # Replace relative src with absolute file:// URI
        new_tag = tag_str[:src_m.start('src')] + resolved_uri + tag_str[src_m.end('src'):]

        # Ensure aspect ratio and responsive sizing are preserved
        return self.adjust_html_image_dimensions(new_tag, local_path)

    def process_segment(self, segment):
        """Process a text segment outside code blocks."""
        segment = self._MD_IMG_PATTERN.sub(self.replace_md_image, segment)
        segment = self._HTML_IMG_PATTERN.sub(self.replace_html_image, segment)
        return segment

    def resolve(self, markdown_text):
        """Transform all relative image paths in markdown_text to file:// URIs and scale down large images."""
        if not self.base_dir or not markdown_text:
            return markdown_text

        parts = self._CODE_PATTERN.split(markdown_text)
        for i in range(0, len(parts), 2):
            parts[i] = self.process_segment(parts[i])

        return ''.join(parts)


def resolve_markdown_image_paths(markdown_text, file_name, max_width=None):
    """Resolve relative Markdown and HTML image paths to absolute file:// URLs and adapt large images."""
    return MarkdownImageResolver(file_name, max_width=max_width).resolve(markdown_text)


def estimate_markdown_scroll_ratio(markdown_text, target_line, wrap_width=80):
    """Estimate the vertical rendered layout ratio (0.0 to 1.0) using visual line equivalents.

    Each Markdown construct is weighted by its rendered visual height in body line units:
    - Images: ~24 lines (~500px block)
    - Headings (#, ##, ###): 2.0 to 3.8 lines (font scale + margins)
    - Prose text: wrapped visual lines (len / wrap_width)
    - Code blocks & tables: 1.0 to 1.3 lines
    - Blank lines: 0.5 lines for first, 0.0 for consecutive (CSS margin collapse)
    """
    if not markdown_text or target_line <= 0:
        return 0.0

    lines = markdown_text.splitlines()
    if target_line >= len(lines):
        return 1.0

    weights = []
    in_code = False
    prev_blank = False
    wrap_w = float(max(20, wrap_width or 80))

    for line in lines:
        s = line.strip()

        # 1. Monospace code blocks (verbatim lines, no prose wrapping)
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            weights.append(1.0)
            prev_blank = False
            continue
        if in_code:
            weights.append(1.0)
            prev_blank = False
            continue

        # 2. Blank lines (HTML collapses consecutive blank lines)
        if not s:
            weights.append(0.0 if prev_blank else 0.5)
            prev_blank = True
            continue
        prev_blank = False

        # 3. Block elements (images, headings, tables)
        if s.startswith("![") or "<img" in s.lower():
            weights.append(24.0)
        elif s.startswith("# "):
            weights.append(3.8)
        elif s.startswith("## "):
            weights.append(2.8)
        elif s.startswith("### "):
            weights.append(2.0)
        elif s.startswith(("#### ", "##### ", "###### ")):
            weights.append(1.5)
        elif s.startswith("|"):
            weights.append(1.3)
        else:
            # 4. Prose text wrapping
            weights.append(max(1.0, len(s) / wrap_w))

    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0

    return min(1.0, max(0.0, float(sum(weights[:target_line])) / float(total_weight)))


