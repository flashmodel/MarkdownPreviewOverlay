"""Custom Markdown rendering, transformations, and miniHTML formatting."""

import html
from html.parser import HTMLParser
import os
import pathlib
import re
import struct
import unicodedata
import urllib.parse

from .inline_math import render_inline_math


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
        for i, row in enumerate(rows):
            if i == separator_idx:
                continue
            rows[i] = [render_inline_math(cell, html_output=False) for cell in row]
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


_LIST_ITEM_RE = re.compile(r'^(\s*)([-*+]|\d+[.)])(\s+.*)$')
_LIST_SEP_HTML = '<div class="markdown-preview-overlay-list-sep"></div>'
_LIST_SEP_RE = re.compile(
    r'(?:<p>\s*)?<div class="markdown-preview-overlay-list-sep"></div>(?:\s*</p>)?\n?'
)


def _parse_fence_open(stripped):
    """Return (char, count) if stripped opens a fenced code block, else None."""
    if not stripped.startswith(('```', '~~~')):
        return None
    char = stripped[0]
    rest = stripped.lstrip(char)
    if char == '`' and '`' in rest:
        return None
    return char, len(stripped) - len(rest)


def _is_fence_close(stripped, fence):
    """Return True if stripped closes an active fenced code block."""
    char, count = fence
    return stripped.startswith(char * count) and not stripped.lstrip(char)


def normalize_markdown_list_indentation(text):
    """Normalize 2-space or irregular list indentation to standard 4-space indentation.

    This ensures Python-Markdown (used by mdpopups) correctly recognizes nested sub-lists
    written using modern 2-space or 3-space indentation conventions.
    Leaves fenced code blocks, horizontal rules, and non-list content untouched.
    """
    if not text:
        return text

    lines = text.split('\n')
    new_lines = []
    fence = None
    indent_stack = []
    last_root_kind = None
    consecutive_blanks = 0

    for line in lines:
        stripped = line.strip()

        # 1. Handle fenced code blocks
        if fence is not None:
            if _is_fence_close(stripped, fence):
                fence = None
            new_lines.append(line)
            consecutive_blanks = 0
            continue

        fence = _parse_fence_open(stripped)
        if fence is not None:
            if not line[0].isspace() or not indent_stack:  # 0-indent fence terminates list
                indent_stack.clear()
                last_root_kind = None
            new_lines.append(line)
            consecutive_blanks = 0
            continue

        # 2. Blank lines (consecutive blank lines terminate lists in Markdown)
        if not stripped:
            consecutive_blanks += 1
            if consecutive_blanks >= 2:
                indent_stack.clear()
            new_lines.append(line)
            continue
        consecutive_blanks = 0

        # 3. Horizontal rules (e.g. ---, - - -, ***)
        clean = stripped.replace(' ', '')
        if len(clean) >= 3 and set(clean) in ({'-'}, {'*'}, {'_'}):
            indent_stack.clear()
            last_root_kind = None
            new_lines.append(line)
            continue

        # 4. Check list item
        m = _LIST_ITEM_RE.match(line)
        if m:
            raw_spaces, marker, rest = m.groups()
            raw_len = len(raw_spaces.expandtabs(4))
            list_kind = 'ol' if marker[0].isdigit() else 'ul'
            prev_kind = None

            # Python-Markdown requires a blank line before a root list following text.
            if (
                not indent_stack
                and raw_len < 4
                and rest.strip()
                and (list_kind == 'ul' or marker == '1.')
                and new_lines
                and new_lines[-1].strip()
            ):
                new_lines.append('')
            if indent_stack and raw_len - indent_stack[-1][0] >= 2:
                # Deeper by >= 2 spaces: start a nested sub-list.
                norm_len = len(indent_stack) * 4
                indent_stack.append((raw_len, norm_len, list_kind))
            else:
                while indent_stack and indent_stack[-1][0] > raw_len:
                    indent_stack.pop()
                if indent_stack:
                    # Same level (or 1-space typo snapped to parent): track kind switch.
                    top_raw, norm_len, prev_kind = indent_stack[-1]
                    indent_stack[-1] = (top_raw, norm_len, list_kind)
                else:
                    # Root level (or resumed after blank lines): check last root kind.
                    norm_len, prev_kind = 0, last_root_kind
                    indent_stack.append((raw_len, 0, list_kind))

            if prev_kind and prev_kind != list_kind:
                if new_lines and new_lines[-1].strip():
                    new_lines.append('')
                new_lines.append((' ' * norm_len) + _LIST_SEP_HTML)
                new_lines.append('')

            if norm_len == 0:
                last_root_kind = list_kind

            new_lines.append((' ' * norm_len) + marker + rest)
        else:
            # 5. Non-list item
            raw_indent = len(line) - len(line.lstrip())
            if indent_stack and raw_indent > 0:
                while indent_stack and indent_stack[-1][0] > raw_indent:
                    indent_stack.pop()
                if indent_stack:
                    diff = indent_stack[-1][1] - indent_stack[-1][0]
                    new_indent = max(0, raw_indent + diff)
                    new_lines.append((' ' * new_indent) + line.lstrip())
                else:
                    last_root_kind = None
                    new_lines.append(line)
            else:
                indent_stack.clear()
                last_root_kind = None
                new_lines.append(line)

    return '\n'.join(new_lines)


class _OrderedListHtmlTransformer(HTMLParser):
    """Rewrite <ol>/<li> HTML into numbered block divs for minihtml rendering."""

    _MARKER_WRAPPER_TAGS = frozenset({'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'})
    _OL_TYPES = frozenset({'1', 'a', 'A', 'i', 'I'})
    _OL_DROP_ATTRS = frozenset({'start', 'reversed', 'type'})
    _LI_DROP_ATTRS = frozenset({'value'})
    _ROMAN_NUMERALS = (
        (1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'),
        (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
        (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i'),
    )

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self._out = []
        self._list_stack = []
        self._li_stack = []
        self._pre_depth = 0

    def get_html(self):
        return ''.join(self._out)

    def _raw_start_tag(self, tag, attrs, self_closing=False):
        raw = self.get_starttag_text()
        if raw:
            return raw
        parts = [f'<{tag}']
        for key, value in attrs:
            if value is None:
                parts.append(f' {key}')
            else:
                parts.append(f' {key}="{html.escape(value, quote=True)}"')
        parts.append(' />' if self_closing else '>')
        return ''.join(parts)

    def _flush_pending_num(self, trailing_space=True):
        if not self._li_stack:
            return False
        top_li = self._li_stack[-1]
        pending = top_li['pending_num']
        if pending is None:
            return False
        top_li['pending_num'] = None
        kind = pending[0]
        if kind == 'fixed':
            suffix = ' ' if trailing_space else ''
            self._out.append(
                f'<span class="markdown-preview-overlay-ol-num">{pending[1]}</span>{suffix}'
            )
        else:
            _, frame, offset = pending
            out_idx = len(self._out)
            self._out.append('')
            frame['deferred'].append((out_idx, offset, trailing_space))
        return True

    def _close_li(self):
        self._flush_pending_num(trailing_space=False)
        top_li = self._li_stack.pop()
        self._out.append('</div>' if top_li['owner'] == 'ol' else '</li>')

    def _close_list(self, frame, closing_tag=None):
        if frame['tag'] == 'ol':
            start = frame['count']
            for out_idx, offset, trailing_space in frame['deferred']:
                label = self._format_ol_marker(start - offset, frame['list_type'])
                suffix = ' ' if trailing_space else ''
                self._out[out_idx] = (
                    f'<span class="markdown-preview-overlay-ol-num">{label}</span>{suffix}'
                )
            self._out.append('</div>')
        else:
            self._out.append(f'</{closing_tag}>' if closing_tag else '</ul>')

    @staticmethod
    def _parse_int_attr(attrs, name):
        for key, value in attrs:
            if key.lower() == name and value is not None:
                try:
                    return int(value.strip())
                except (ValueError, TypeError):
                    return None
        return None

    @classmethod
    def _parse_type_attr(cls, attrs):
        for key, value in attrs:
            if key.lower() == 'type' and value is not None:
                candidate = value.strip()
                if candidate in cls._OL_TYPES:
                    return candidate
                return '1'
        return '1'

    @staticmethod
    def _has_attr(attrs, name):
        return any(key.lower() == name for key, _ in attrs)

    @staticmethod
    def _to_alpha(n):
        chars = []
        while n > 0:
            n, rem = divmod(n - 1, 26)
            chars.append(chr(ord('a') + rem))
        return ''.join(reversed(chars))

    @classmethod
    def _to_roman(cls, n):
        parts = []
        for value, symbol in cls._ROMAN_NUMERALS:
            while n >= value:
                parts.append(symbol)
                n -= value
        return ''.join(parts)

    @classmethod
    def _format_ol_marker(cls, num, list_type):
        if list_type == 'a' and num > 0:
            return f'{cls._to_alpha(num)}.'
        if list_type == 'A' and num > 0:
            return f'{cls._to_alpha(num).upper()}.'
        if list_type == 'i' and 1 <= num <= 3999:
            return f'{cls._to_roman(num)}.'
        if list_type == 'I' and 1 <= num <= 3999:
            return f'{cls._to_roman(num).upper()}.'
        return f'{num}.'

    @staticmethod
    def _build_div_start_tag(base_class, attrs, drop_attrs):
        classes = [base_class]
        seen_classes = {base_class}
        extra_parts = []
        for key, value in attrs:
            lower = key.lower()
            if lower in drop_attrs:
                continue
            if lower == 'class':
                if value:
                    for token in value.split():
                        if token not in seen_classes:
                            seen_classes.add(token)
                            classes.append(token)
                continue
            if value is None:
                extra_parts.append(f' {key}')
            else:
                extra_parts.append(f' {key}="{html.escape(value, quote=True)}"')
        class_str = html.escape(' '.join(classes), quote=True)
        return f'<div class="{class_str}"{"".join(extra_parts)}>'

    def handle_starttag(self, tag, attrs):
        lower = tag.lower()
        if lower == 'pre':
            if self._pre_depth == 0:
                self._flush_pending_num()
            self._pre_depth += 1
            self._out.append(self._raw_start_tag(tag, attrs))
            return

        if self._pre_depth > 0:
            self._out.append(self._raw_start_tag(tag, attrs))
            return

        if lower == 'ol':
            self._flush_pending_num()
            start = self._parse_int_attr(attrs, 'start')
            is_reversed = self._has_attr(attrs, 'reversed')
            step = -1 if is_reversed else 1
            list_type = self._parse_type_attr(attrs)
            if start is not None:
                next_num = start
            elif is_reversed:
                next_num = None
            else:
                next_num = 1
            self._list_stack.append({
                'tag': 'ol',
                'next_num': next_num,
                'step': step,
                'list_type': list_type,
                'count': 0,
                'deferred': [],
            })
            self._out.append(
                self._build_div_start_tag('markdown-preview-overlay-ol', attrs, self._OL_DROP_ATTRS)
            )
            return

        if lower == 'ul':
            self._flush_pending_num()
            self._list_stack.append({'tag': 'ul'})
            self._out.append(self._raw_start_tag(tag, attrs))
            return

        if lower == 'li':
            top_list = self._list_stack[-1] if self._list_stack else None
            if top_list is None:
                self._out.append(self._raw_start_tag(tag, attrs))
                return
            depth = len(self._list_stack)
            while self._li_stack and self._li_stack[-1]['depth'] >= depth:
                self._close_li()
            if top_list['tag'] == 'ol':
                top_list['count'] += 1
                explicit_val = self._parse_int_attr(attrs, 'value')
                if explicit_val is not None:
                    num = explicit_val
                    top_list['next_num'] = num + top_list['step']
                    pending_num = ('fixed', self._format_ol_marker(num, top_list['list_type']))
                elif top_list['next_num'] is not None:
                    num = top_list['next_num']
                    top_list['next_num'] += top_list['step']
                    pending_num = ('fixed', self._format_ol_marker(num, top_list['list_type']))
                else:
                    offset = top_list['count'] - 1
                    pending_num = ('deferred', top_list, offset)
                self._li_stack.append({
                    'owner': 'ol',
                    'depth': depth,
                    'pending_num': pending_num,
                })
                self._out.append(
                    self._build_div_start_tag(
                        'markdown-preview-overlay-li', attrs, self._LI_DROP_ATTRS
                    )
                )
            else:
                self._li_stack.append({
                    'owner': 'ul',
                    'depth': depth,
                    'pending_num': None,
                })
                self._out.append(self._raw_start_tag(tag, attrs))
            return

        if self._li_stack and self._li_stack[-1]['pending_num'] is not None:
            if lower in self._MARKER_WRAPPER_TAGS:
                self._out.append(self._raw_start_tag(tag, attrs))
                self._flush_pending_num()
                return
            self._flush_pending_num()

        self._out.append(self._raw_start_tag(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        if self._pre_depth == 0:
            self._flush_pending_num()
        self._out.append(self._raw_start_tag(tag, attrs, self_closing=True))

    def handle_endtag(self, tag):
        lower = tag.lower()
        if lower == 'pre':
            if self._pre_depth > 0:
                self._pre_depth -= 1
            self._out.append(f'</{tag}>')
            return

        if self._pre_depth > 0:
            self._out.append(f'</{tag}>')
            return

        if lower == 'li':
            if self._li_stack and self._li_stack[-1]['depth'] == len(self._list_stack):
                self._close_li()
            elif not self._list_stack:
                self._out.append(f'</{tag}>')
            return

        if lower in ('ol', 'ul'):
            match_idx = None
            for idx in range(len(self._list_stack) - 1, -1, -1):
                if self._list_stack[idx]['tag'] == lower:
                    match_idx = idx
                    break
            if match_idx is None:
                self._out.append(f'</{tag}>')
                return
            while len(self._list_stack) > match_idx:
                depth = len(self._list_stack)
                while self._li_stack and self._li_stack[-1]['depth'] >= depth:
                    self._close_li()
                frame = self._list_stack.pop()
                closing_tag = tag if len(self._list_stack) == match_idx else None
                self._close_list(frame, closing_tag=closing_tag)
            return

        self._out.append(f'</{tag}>')

    def handle_data(self, data):
        if (self._pre_depth == 0
                and self._li_stack
                and self._li_stack[-1]['pending_num'] is not None):
            if data.strip():
                self._flush_pending_num()
                self._out.append(data.lstrip())
                return
        self._out.append(data)

    def handle_entityref(self, name):
        if self._pre_depth == 0:
            self._flush_pending_num()
        self._out.append(f'&{name};')

    def handle_charref(self, name):
        if self._pre_depth == 0:
            self._flush_pending_num()
        self._out.append(f'&#{name};')

    def handle_comment(self, data):
        self._out.append(f'<!--{data}-->')

    def handle_decl(self, decl):
        self._out.append(f'<!{decl}>')

    def handle_pi(self, data):
        self._out.append(f'<?{data}>')

    def unknown_decl(self, data):
        self._out.append(f'<![{data}]>')

    def close(self):
        super().close()
        while self._list_stack:
            depth = len(self._list_stack)
            while self._li_stack and self._li_stack[-1]['depth'] >= depth:
                self._close_li()
            frame = self._list_stack.pop()
            self._close_list(frame)
        while self._li_stack:
            self._close_li()


def render_ordered_lists_as_html(html_text):
    """Rewrite <ol>/<li> blocks to explicit numbered divs for minihtml."""
    if not html_text:
        return html_text
    if _LIST_SEP_HTML in html_text:
        html_text = _LIST_SEP_RE.sub('', html_text)
    if '<ol' not in html_text.lower():
        return html_text
    parser = _OrderedListHtmlTransformer()
    parser.feed(html_text)
    parser.close()
    return parser.get_html()
