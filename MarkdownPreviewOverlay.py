"""Render Markdown as an editor-native overlay with mdpopups."""

import os
import threading
import urllib.parse
import webbrowser
import re
import html
import unicodedata

import mdpopups
import sublime
import sublime_plugin


PHANTOM_KEY = "markdown_preview_overlay"
ANNOTATION_KEY = "markdown_preview_overlay.control"
MODE_SETTING = "markdown_preview_overlay.preview_mode"
STATUS_KEY = "markdown_preview_overlay"

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}

OVERLAY_CSS = """
.markdown-preview-overlay-toolbar {
    background-color: color(var(--cyanish) alpha(0.08));
    border: 1px solid color(var(--cyanish) alpha(0.25));
    border-left: 4px solid var(--cyanish);
    border-radius: 4px;
    padding: 0.5rem 0.8rem;
    margin: 0.5rem 0 1rem;
}
a.markdown-preview-overlay-source {
    display: inline-block;
    font-weight: bold;
    cursor: pointer;
    color: var(--cyanish);
    text-decoration: none;
}
span.markdown-preview-overlay-arrow {
    display: inline-block;
    margin-left: 0.2rem;
    margin-right: 1.5rem;
}
span.markdown-preview-overlay-label {
    display: inline-block;
}
a.markdown-preview-overlay-preview-icon {
    display: inline-block;
    padding: 0 0.15rem 0 0.1rem;
    margin-right: 0.1rem;
    font-size: 1.35rem;
    position: relative;
    top: -0.2rem;
    text-decoration: none;
    color: var(--cyanish);
    {{'background'|css('background-color')}}
}
.markdown-preview-overlay-document {
    padding: 0.8rem 1.4rem 3rem 1.4rem;
    line-height: 1.6;
    font-size: 1.05rem;
    {{'background'|css('background-color')}}
}
.markdown-preview-overlay-document p {
    margin: 0.8rem 0;
    line-height: 1.6;
}
.markdown-preview-overlay-document h1,
.markdown-preview-overlay-document h2,
.markdown-preview-overlay-document h3,
.markdown-preview-overlay-document h4,
.markdown-preview-overlay-document h5,
.markdown-preview-overlay-document h6 {
    font-weight: bold;
    line-height: 1.3;
    color: var(--foreground);
}
.markdown-preview-overlay-document h1 {
    font-size: 1.85rem;
    margin: 1.8rem 0 1rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid color(var(--foreground) alpha(0.18));
}
.markdown-preview-overlay-document h2 {
    font-size: 1.45rem;
    margin: 1.5rem 0 0.8rem;
    padding-bottom: 0.35rem;
    border-bottom: 1px solid color(var(--foreground) alpha(0.14));
}
.markdown-preview-overlay-document h3 {
    font-size: 1.2rem;
    margin: 1.3rem 0 0.6rem;
}
.markdown-preview-overlay-document h4 {
    font-size: 1.05rem;
    margin: 1.1rem 0 0.5rem;
}
.markdown-preview-overlay-document h5,
.markdown-preview-overlay-document h6 {
    font-size: 0.95rem;
    margin: 1rem 0 0.4rem;
}
.markdown-preview-overlay-document ul,
.markdown-preview-overlay-document ol {
    margin: 0.6rem 0;
    padding-left: 1.8rem;
}
.markdown-preview-overlay-document li {
    margin: 0.35rem 0;
    line-height: 1.55;
}
.markdown-preview-overlay-document li > p {
    margin: 0.3rem 0;
}
.markdown-preview-overlay-document code {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background-color: color(var(--background) blend(var(--foreground) 90%));
    padding: 0.15rem 0.35rem;
    border-radius: 3px;
}
.markdown-preview-overlay-document pre {
    background-color: color(var(--background) blend(var(--foreground) 94%));
    border: 1px solid color(var(--foreground) alpha(0.1));
    border-radius: 6px;
    padding: 0.9rem 1.1rem;
    margin: 1rem 0;
    line-height: 1.45;
}
.markdown-preview-overlay-document pre code {
    background-color: transparent;
    padding: 0;
    border-radius: 0;
    font-size: 0.92em;
}
.markdown-preview-overlay-document blockquote {
    margin: 1rem 0;
    padding: 0.5rem 1rem;
    border-left: 4px solid color(var(--foreground) alpha(0.25));
    color: color(var(--foreground) blend(var(--background) 70%));
    background-color: color(var(--background) blend(var(--foreground) 97%));
    border-radius: 0 4px 4px 0;
}
.markdown-preview-overlay-document blockquote > p {
    margin: 0.3rem 0;
}
.markdown-preview-overlay-document table {
    border-collapse: collapse;
    margin: 1rem 0;
    width: 100%;
}
.markdown-preview-overlay-document th,
.markdown-preview-overlay-document td {
    padding: 0.55rem 0.9rem;
    border: 1px solid color(var(--foreground) alpha(0.18));
}
.markdown-preview-overlay-document th {
    font-weight: bold;
    background-color: color(var(--background) blend(var(--foreground) 92%));
}
.markdown-preview-overlay-document tr:nth-child(even) {
    background-color: color(var(--background) blend(var(--foreground) 97%));
}
.markdown-preview-overlay-document hr {
    border: 0;
    height: 2px;
    background-color: color(var(--foreground) alpha(0.15));
    margin: 1.8rem 0;
}
.markdown-preview-overlay-document a {
    color: var(--accent);
    text-decoration: underline;
}
.markdown-preview-overlay-document img {
    max-width: 100%;
    margin: 0.8rem 0;
}
"""

ANNOTATION_HTML = """
<body id="markdown-preview-overlay-control">
    <style>
        a.preview-link {
            display: inline-block;
            color: var(--cyanish);
            font-weight: bold;
            line-height: 1.4rem;
            text-decoration: none;
        }
        span.preview-icon {
            display: inline-block;
            margin-left: -0.1rem;
            margin-right: 0.3rem;
            font-size: 1.2rem;
            line-height: 1;
            vertical-align: middle;
        }
    </style>
    <a class="preview-link" href="overlay:preview"><span class="preview-icon">▣</span>Preview</a>
</body>
"""

ANNOTATION_RESERVED_WIDTH = 150.0




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
            for end, (c, _) in enumerate(remaining, 1):
                cw = self.char_width(c)
                if display_width + cw > width:
                    end -= 1
                    break
                display_width += cw
            else:
                lines.append(remaining)
                break

            if end == 0:
                end = 1
            candidate = remaining[:end]
            whitespace_breaks = [
                i for i, (c, _) in enumerate(candidate) if c.isspace()
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

def _is_markdown(view):
    """Return whether a file-backed Markdown view should receive controls."""

    if (
        view is None
        or not view.is_valid()
        or view.is_scratch()
        or view.settings().get("is_widget", False)
    ):
        return False

    # Keep transient views such as Codeform chat panes out of the default
    # experience. A buffer must be associated with a real file before this
    # package exposes preview controls.
    file_name = view.file_name()
    if not file_name:
        return False

    if view.match_selector(0, "text.html.markdown"):
        return True

    return os.path.splitext(file_name)[1].lower() in MARKDOWN_EXTENSIONS


def _copy_regions(regions):
    return [sublime.Region(region.a, region.b) for region in regions]


class PreviewState(object):
    """Own the preview and restoration data for a single View."""

    def __init__(self, view):
        self.view = view
        self.phantom_set = mdpopups.PhantomSet(view, PHANTOM_KEY)
        self.previewing = False
        self.fold_region = None
        self.original_folds = []
        self.original_selections = []
        self.original_viewport = (0.0, 0.0)
        self.original_read_only = False
        self.original_gutter = True
        self.rendered_change_count = view.change_count()
        self.refresh_generation = 0
        self.control_generation = 0
        self.edit_control_mode = None
        self.refresh_lock = threading.Lock()


    def _get_table_max_width(self):
        try:
            settings = sublime.load_settings("MarkdownPreviewOverlay.sublime-settings")
            value = settings.get("table_max_width")
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value

            wrap_width = self.view.settings().get("wrap_width", 0)
            if (isinstance(wrap_width, int)
                    and not isinstance(wrap_width, bool)
                    and wrap_width > 0):
                return max(20, wrap_width - 8)

            viewport_width, _ = self.view.viewport_extent()
            character_width = self.view.em_width()
            if viewport_width > 0 and character_width > 0:
                return max(
                    20,
                    int(viewport_width / character_width) - 8,
                )
        except Exception:
            pass
        return 100

    def render(self):
        """Render the mode button and, in preview mode, the document."""

        if not self.view.is_valid():
            return

        self.view.erase_regions(ANNOTATION_KEY)

        if self.previewing:
            primary_action = "edit"
            primary_title = "Edit source"
        else:
            primary_action = "preview"
            # The edit-mode phantom is only used when the first line is too
            # long for the right-aligned annotation. Keep this fallback
            # compact so it displaces as little source text as possible.
            primary_label = "▣"
            primary_title = "Preview Markdown"

        if self.previewing:
            toolbar = (
                '<div class="markdown-preview-overlay-toolbar">'
                '<a class="markdown-preview-overlay-source" '
                'href="overlay:{0}" title="{1}">'
                '<span class="markdown-preview-overlay-arrow">◀</span>'
                '<span class="markdown-preview-overlay-label">✏️Edit source</span>'
                '</a>'
                '</div>'.format(
                    primary_action, primary_title
                )
            )
            toolbar_layout = sublime.LAYOUT_BLOCK
        else:
            toolbar = (
                '<a class="markdown-preview-overlay-preview-icon" '
                'href="overlay:{0}" title="{1}">{2}</a>'.format(
                    primary_action, primary_title, primary_label
                )
            )
            toolbar_layout = sublime.LAYOUT_INLINE

            if self._should_use_annotation():
                self.phantom_set.update([])
                self._render_annotation()
                self.edit_control_mode = "annotation"
                self.rendered_change_count = self.view.change_count()
                return

            self.edit_control_mode = "inline"

        # In preview mode, anchor at EOF. The source fold is [0, size), so
        # this real boundary point stays outside the fold and lays the
        # phantoms out below the folded document.
        anchor = self.view.size() if self.previewing else 0

        phantoms = [
            mdpopups.Phantom(
                sublime.Region(anchor),
                toolbar,
                toolbar_layout,
                md=False,
                css=OVERLAY_CSS,
                on_navigate=self.on_navigate,
                wrapper_class="markdown-preview-overlay"
            )
        ]

        if self.previewing:
            markdown = self.view.substr(
                sublime.Region(0, self.view.size())
            )
            max_width = self._get_table_max_width()
            markdown = render_markdown_tables_as_html(markdown, max_width)

            phantoms.append(
                mdpopups.Phantom(
                    sublime.Region(anchor),
                    markdown,
                    sublime.LAYOUT_BLOCK,
                    md=True,
                    css=OVERLAY_CSS,
                    on_navigate=self.on_navigate,
                    wrapper_class="markdown-preview-overlay-document"
                )
            )

        self.phantom_set.update(phantoms)
        self.rendered_change_count = self.view.change_count()

    def show(self):
        """Enter preview mode without changing the buffer contents."""

        if self.previewing or not _is_markdown(self.view):
            return

        self.original_read_only = self.view.is_read_only()
        self.original_gutter = self.view.settings().get("gutter", True)
        self.original_selections = _copy_regions(self.view.sel())
        self.original_viewport = self.view.viewport_position()
        self.original_folds = _copy_regions(self.view.folded_regions())

        # Remove nested folds before creating our single source fold. They are
        # recreated when preview mode ends.
        for region in self.original_folds:
            self.view.unfold(region)

        self.fold_region = sublime.Region(
            0, self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.previewing = True
        self.view.settings().set(MODE_SETTING, True)
        self.view.set_status(STATUS_KEY, "Markdown Preview Overlay")
        self.view.settings().set("gutter", False)
        self.view.set_read_only(True)
        self.render()
        self.view.set_viewport_position((0.0, 0.0), False)

    def hide(self):
        """Leave preview mode and restore the prior View presentation."""

        if not self.previewing:
            self.render()
            return

        # Temporarily make the view writable so restoration also works for a
        # view that was editable before preview mode.
        self.view.set_read_only(False)
        if self.fold_region is not None and not self.fold_region.empty():
            self.view.unfold(self.fold_region)

        for region in self.original_folds:
            self.view.fold(region)

        self.previewing = False
        self.fold_region = None
        self.view.settings().erase(MODE_SETTING)
        self.view.erase_status(STATUS_KEY)
        self.view.settings().set("gutter", self.original_gutter)
        self.view.set_read_only(self.original_read_only)
        self.render()

        selections = _copy_regions(self.original_selections)
        viewport = self.original_viewport

        def restore_position():
            if not self.view.is_valid():
                return
            self.view.sel().clear()
            for selection in selections:
                self.view.sel().add(selection)
            self.view.set_viewport_position(viewport, False)

        sublime.set_timeout(restore_position)

    def refresh(self):
        """Re-read the buffer, update its fold, and rebuild the preview."""

        if not self.previewing or not self.view.is_valid():
            return

        self.view.set_read_only(False)
        if self.fold_region is not None and not self.fold_region.empty():
            self.view.unfold(self.fold_region)

        self.fold_region = sublime.Region(
            0, self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.view.set_read_only(True)
        self.render()

    def schedule_refresh(self):
        """Debounce refreshes caused by reloads or saves."""

        with self.refresh_lock:
            self.refresh_generation += 1
            generation = self.refresh_generation

        def refresh_if_current():
            with self.refresh_lock:
                if generation != self.refresh_generation:
                    return
            if (
                self.previewing
                and self.view.is_valid()
                and self.view.change_count() != self.rendered_change_count
            ):
                self.refresh()

        sublime.set_timeout(refresh_if_current, 250)

    def schedule_control_render(self):
        """Debounce edit-mode placement after the first line changes."""

        with self.refresh_lock:
            self.control_generation += 1
            generation = self.control_generation

        def render_if_current():
            with self.refresh_lock:
                if generation != self.control_generation:
                    return
            if not self.previewing and self.view.is_valid():
                self.update_control_placement()

        sublime.set_timeout(render_if_current, 100)

    def dispose(self, restore=True):
        """Remove all UI owned by this state."""

        if restore and self.view.is_valid() and self.previewing:
            self.hide()
        if self.view.is_valid():
            self.view.erase_regions(ANNOTATION_KEY)
        self.phantom_set.update([])

    def on_navigate(self, href):
        """Handle toolbar actions and links in rendered Markdown."""

        if href == "overlay:preview":
            self.view.run_command("markdown_preview_overlay_show")
        elif href == "overlay:edit":
            self.view.run_command("markdown_preview_overlay_hide")
        elif href == "overlay:refresh":
            self.view.run_command("markdown_preview_overlay_refresh")
        else:
            _open_link(self.view, href)

    def update_control_placement(self):
        """Move the edit control only when its desired mode has changed."""

        if self.previewing or not self.view.is_valid():
            return
        desired = "annotation" if self._should_use_annotation() else "inline"
        if desired != self.edit_control_mode:
            self.render()

    def _render_annotation(self):
        """Draw a Preview action at the right edge of the first line."""

        self.view.add_regions(
            ANNOTATION_KEY,
            [sublime.Region(0)],
            annotations=[ANNOTATION_HTML],
            annotation_color="#aaa0",
            on_navigate=self.on_navigate
        )

    def _should_use_annotation(self):
        """Use annotation unless the first line competes for its space."""

        first_line = self.view.line(0)
        first_line_text = self.view.substr(first_line)

        # A blank first line is an ideal annotation row: the button stays at
        # the top-right without shifting any Markdown content.
        if not first_line_text.strip():
            return True

        viewport_width = self.view.viewport_extent()[0]
        if viewport_width <= 0:
            return False

        start_xy = self.view.text_to_layout(first_line.begin())
        end_xy = self.view.text_to_layout(first_line.end())

        # A visually wrapped first line already consumes multiple rows and is
        # not a good host for a right-edge annotation.
        if end_xy[1] > start_xy[1]:
            return False

        return end_xy[0] <= viewport_width - ANNOTATION_RESERVED_WIDTH

_states = {}


def _state_for(view):
    state = _states.get(view.id())
    if state is None:
        state = PreviewState(view)
        _states[view.id()] = state
    return state


def _open_link(view, href):
    """Open web links externally and local Markdown links in Sublime."""

    parsed = urllib.parse.urlparse(href)
    if parsed.scheme in {"http", "https", "mailto"}:
        webbrowser.open_new_tab(href)
        return

    if href.startswith("#"):
        sublime.status_message(
            "Markdown Preview Overlay: heading links are not supported"
        )
        return

    if parsed.scheme and parsed.scheme != "file":
        return

    path = urllib.parse.unquote(parsed.path)
    if not os.path.isabs(path):
        file_name = view.file_name()
        if not file_name:
            return
        path = os.path.join(os.path.dirname(file_name), path)

    path = os.path.normpath(path)
    if os.path.isfile(path) and view.window() is not None:
        view.window().open_file(path)


class MarkdownPreviewOverlayToggleCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        state = _state_for(self.view)
        if state.previewing:
            state.hide()
        else:
            state.show()

    def is_enabled(self):
        return _is_markdown(self.view)


class MarkdownPreviewOverlayShowCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _state_for(self.view).show()

    def is_enabled(self):
        state = _states.get(self.view.id())
        return _is_markdown(self.view) and not (
            state is not None and state.previewing
        )


class MarkdownPreviewOverlayHideCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _state_for(self.view).hide()

    def is_enabled(self):
        state = _states.get(self.view.id())
        return bool(state is not None and state.previewing)


class MarkdownPreviewOverlayRefreshCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _state_for(self.view).refresh()

    def is_enabled(self):
        state = _states.get(self.view.id())
        return bool(state is not None and state.previewing)


class MarkdownPreviewOverlayListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        self._schedule_button_update(view)

    def on_activated_async(self, view):
        self._schedule_button_update(view)

    def on_post_save_async(self, view):
        self._schedule_button_update(view)
        state = _states.get(view.id())
        if state is not None:
            state.schedule_refresh()

    def on_modified_async(self, view):
        state = _states.get(view.id())
        if state is not None:
            if state.previewing:
                state.schedule_refresh()
            else:
                state.schedule_control_render()

    def on_selection_modified_async(self, view):
        state = _states.get(view.id())
        if state is not None and not state.previewing:
            sublime.set_timeout(state.update_control_placement)

    def on_close(self, view):
        state = _states.pop(view.id(), None)
        if state is not None:
            state.dispose()

    @staticmethod
    def _schedule_button_update(view):
        def update():
            if not view.is_valid():
                return
            if _is_markdown(view):
                state = _state_for(view)
                if not state.previewing:
                    state.render()
            else:
                state = _states.pop(view.id(), None)
                if state is not None:
                    state.dispose()

        sublime.set_timeout(update)


def plugin_loaded():
    for window in sublime.windows():
        for view in window.views():
            if _is_markdown(view):
                _state_for(view).render()


def plugin_unloaded():
    for state in list(_states.values()):
        state.dispose()
    _states.clear()
