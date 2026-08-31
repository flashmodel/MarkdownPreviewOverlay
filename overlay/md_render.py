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

    def is_url_scheme(self, src):
        """Return True if src contains a scheme like http:, data:, or res: (excluding Windows drive letters)."""
        if not src:
            return False
        # Exclude Windows drive letters like C:\ or D:/
        if (
            len(src) >= 2
            and src[0].isalpha()
            and src[1] == ':'
            and (len(src) == 2 or src[2] in ('\\', '/'))
        ):
            return False
        return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', src))

    def resolve_path(self, raw_path):
        """Resolve a single raw image path into (uri, local_abs_path)."""
        if not self.base_dir or not raw_path or raw_path.startswith('//') or raw_path.startswith('#'):
            return None, None
        if self.is_url_scheme(raw_path):
            return None, None

        url_parts = urllib.parse.urlsplit(raw_path)
        path_part = url_parts.path
        if not path_part:
            return None, None

        unquoted = urllib.parse.unquote(path_part)
        if os.path.isabs(unquoted):
            abs_path = os.path.normpath(unquoted)
        else:
            abs_path = os.path.normpath(os.path.join(self.base_dir, unquoted))

        try:
            uri = pathlib.Path(abs_path).as_uri()
            if url_parts.query:
                uri += f'?{url_parts.query}'
            if url_parts.fragment:
                uri += f'#{url_parts.fragment}'
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

        if title:
            return f'![{alt}]({resolved_uri} {title})'
        return f'![{alt}]({resolved_uri})'

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

