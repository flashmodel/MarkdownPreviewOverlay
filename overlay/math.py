"""Optional MathJax rendering for minihtml previews.

Formulas are typeset by math/tex2png.js (MathJax SVG rasterized with resvg)
and embedded as PNG images. minihtml cannot draw TeX, MathML, or SVG itself.
"""

import base64
import collections
import functools
import html
import json
import os
import re
import shutil
import struct
import subprocess


_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)$')
_COLOR = re.compile(r'^#[0-9A-Fa-f]{3,8}$')
_COMMON_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "~/.cargo/bin", "~/.local/bin")
_DPI_SCALE = 2
_CACHE_MAX = 64
_PNG_CACHE = collections.OrderedDict()

MathRegion = collections.namedtuple('MathRegion', 'start end tex display')


def _find_executable(binary_name):
    """Find a binary on PATH or in common non-PATH install locations."""
    executable = shutil.which(binary_name)
    if executable:
        return executable
    for directory in _COMMON_DIRS:
        executable = shutil.which(binary_name, path=os.path.expanduser(directory))
        if executable:
            return executable
    return None


def _is_escaped(text, index):
    slashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == '\\':
        slashes += 1
        cursor -= 1
    return slashes % 2 == 1


def _is_line_start(text, index):
    return index == 0 or text[index - 1] == '\n'


def _line_bounds(text, index):
    """Return (line_without_break, index_after_line) for the line containing index."""
    end = text.find('\n', index)
    if end < 0:
        end = len(text)
        next_index = end
    else:
        next_index = end + 1
    line = text[index:end]
    if line.endswith('\r'):
        line = line[:-1]
    return line, next_index


def _find_unescaped(text, start, token):
    cursor = start
    while True:
        found = text.find(token, cursor)
        if found < 0:
            return None
        if not _is_escaped(text, found):
            return found
        cursor = found + 1


def _skip_inline_code(text, index):
    """Return the index after a closed inline code span, or None."""
    if text[index] != '`':
        return None
    length = 1
    while index + length < len(text) and text[index + length] == '`':
        length += 1
    cursor = index + length
    limit = len(text)
    while cursor < limit:
        if text[cursor] != '`':
            cursor += 1
            continue
        run = 1
        while cursor + run < limit and text[cursor + run] == '`':
            run += 1
        if run == length:
            return cursor + run
        cursor += run
    return None


def _match_inline(text, index):
    """Return (close_index, tex) for a GitHub-style $...$ span, or None."""
    if index + 1 >= len(text):
        return None
    nxt = text[index + 1]
    if nxt.isspace() or nxt == '$':
        return None
    cursor = index + 1
    limit = len(text)
    while cursor < limit:
        if text[cursor] == '\n':
            return None
        if text[cursor] == '$' and not _is_escaped(text, cursor):
            if cursor == index + 1 or text[cursor - 1].isspace():
                return None
            if cursor + 1 < limit and text[cursor + 1].isdigit():
                return None
            tex = text[index + 1:cursor]
            if not tex.strip():
                return None
            return cursor, tex
        cursor += 1
    return None


def _opening_fence(line):
    match = _FENCE.match(line)
    if not match:
        return None
    marker, info = match.groups()
    if marker[0] == '`' and '`' in info:
        return None
    return marker[0], len(marker)


def _closing_fence(line, fence):
    match = _FENCE.match(line)
    if not match or fence is None:
        return False
    marker, info = match.groups()
    char, length = fence
    return marker[0] == char and len(marker) >= length and not info.strip()


def math_regions(text):
    """Yield math spans outside fenced and inline code.

    Display math is ``$$...$$`` and may span lines. Inline math is ``$...$``
    with no whitespace against the delimiters and no newline inside.
    A backslash escapes a dollar sign.
    """
    if not text:
        return []
    regions = []
    index = 0
    limit = len(text)
    fence = None
    while index < limit:
        if _is_line_start(text, index):
            line, next_index = _line_bounds(text, index)
            if fence is None:
                opened = _opening_fence(line)
                if opened is not None:
                    fence = opened
                    index = next_index
                    continue
            elif _closing_fence(line, fence):
                fence = None
                index = next_index
                continue
            elif fence is not None:
                index = next_index
                continue
        if fence is not None:
            newline = text.find('\n', index)
            index = limit if newline < 0 else newline + 1
            continue
        if text[index] == '`' and not _is_escaped(text, index):
            closed = _skip_inline_code(text, index)
            if closed is not None:
                index = closed
                continue
        if text[index] == '$' and not _is_escaped(text, index):
            if text.startswith('$$', index):
                close = _find_unescaped(text, index + 2, '$$')
                if close is not None:
                    tex = text[index + 2:close].strip()
                    region_start = index
                    line_start = text.rfind('\n', 0, index) + 1
                    indent = text[line_start:index]
                    if indent.strip() == '' and '\t' not in indent:
                        region_start = line_start
                    if tex:
                        regions.append(MathRegion(region_start, close + 2, tex, True))
                    index = close + 2
                    continue
            else:
                inline = _match_inline(text, index)
                if inline is not None:
                    close, tex = inline
                    regions.append(MathRegion(index, close + 1, tex, False))
                    index = close + 1
                    continue
        index += 1
    return regions


def has_math(text):
    """Return whether text contains a math span this module would render."""
    return bool(math_regions(text))


def math_fallback(tex):
    """Wrap raw TeX in a fenced block so Markdown will not rewrite it."""
    fence = '```'
    while fence in tex:
        fence += '`'
    body = tex if tex.endswith('\n') else tex + '\n'
    return '\n\n{0}math\n{1}{0}\n\n'.format(fence, body)


def protect_math(text):
    """Replace math spans with fenced source so the first paint stays readable."""
    regions = math_regions(text)
    if not regions:
        return text
    parts = []
    previous = 0
    for region in regions:
        parts.append(text[previous:region.start])
        parts.append(math_fallback(region.tex))
        previous = region.end
    parts.append(text[previous:])
    return ''.join(parts)


def apply_replacements(text, spans):
    """Splice non-overlapping (start, end, replacement) spans into text."""
    if not spans:
        return text
    parts = []
    previous = 0
    for start, end, replacement in sorted(spans, key=lambda item: (item[0], item[1])):
        if start < previous or end < start:
            continue
        parts.append(text[previous:start])
        parts.append(replacement)
        previous = end
    parts.append(text[previous:])
    return ''.join(parts)


def _has_math_packages(modules_dir):
    if not modules_dir or not os.path.isdir(modules_dir):
        return False
    mathjax = os.path.join(modules_dir, 'mathjax', 'package.json')
    resvg = os.path.join(modules_dir, '@resvg', 'resvg-js', 'package.json')
    return os.path.isfile(mathjax) and os.path.isfile(resvg)


def _module_candidates(setting):
    expanded = os.path.expandvars(os.path.expanduser(setting.strip()))
    if not expanded:
        return []
    candidates = [expanded]
    if os.path.basename(os.path.normpath(expanded)) != 'node_modules':
        candidates.append(os.path.join(expanded, 'node_modules'))
    return candidates


def _npm_executable(node):
    directory = os.path.dirname(node)
    for name in ('npm', 'npm.cmd', 'npm.exe'):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return _find_executable('npm')


@functools.lru_cache(maxsize=4)
def _npm_root_global(npm_path):
    """Return npm's global module directory, or an empty string."""
    kwargs = {
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'timeout': 10,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    try:
        result = subprocess.run([npm_path, 'root', '-g'], **kwargs)
    except (OSError, subprocess.SubprocessError):
        return ''
    if result.returncode != 0:
        return ''
    lines = result.stdout.decode('utf-8', 'replace').splitlines()
    lines = [line.strip() for line in lines if line.strip()]
    return lines[-1] if lines else ''


def _default_module_dirs(node):
    candidates = []
    npm = _npm_executable(node)
    if npm:
        root = _npm_root_global(npm)
        if root:
            candidates.append(root)
    prefix = os.path.abspath(os.path.join(os.path.dirname(node), os.pardir, 'lib', 'node_modules'))
    candidates.append(prefix)
    home = os.path.expanduser('~')
    candidates.extend((
        '/usr/lib/node_modules',
        '/usr/local/lib/node_modules',
        os.path.join(home, '.npm-global', 'lib', 'node_modules'),
        os.path.join(home, '.local', 'lib', 'node_modules'),
    ))
    appdata = os.environ.get('APPDATA')
    if appdata:
        candidates.append(os.path.join(appdata, 'npm', 'node_modules'))
    return candidates


def _resolve_node(setting):
    if setting and str(setting).strip():
        raw = os.path.expandvars(os.path.expanduser(str(setting).strip()))
        resolved = shutil.which(raw)
        if resolved:
            return resolved
        return raw if os.path.isfile(raw) else None
    return _find_executable('node')


def find_math_runtime(node_setting=None, modules_setting=None):
    """Return (node, node_modules) when MathJax and resvg are installed.

    ``modules_setting`` may be a node_modules directory or a directory that
    contains one. An explicit setting that does not contain both packages
    does not fall through to the global search.
    """
    node = _resolve_node(node_setting)
    if not node:
        return None
    if modules_setting and str(modules_setting).strip():
        for candidate in _module_candidates(str(modules_setting)):
            if _has_math_packages(candidate):
                return node, candidate
        return None
    for candidate in _default_module_dirs(node):
        if _has_math_packages(candidate):
            return node, candidate
    return None


def _script_path():
    package_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(package_root, 'math', 'tex2png.js')


def normalize_color(color):
    """Return a #RRGGBB color, or black when color is not a hex value."""
    if not isinstance(color, str) or not _COLOR.match(color.strip()):
        return '#000000'
    text = color.strip()
    if len(text) == 4:
        return '#' + ''.join(ch * 2 for ch in text[1:])
    if len(text) == 9:
        return text[:7]
    return text


def clear_math_caches():
    """Drop rendered formulas and the cached npm root lookup."""
    _PNG_CACHE.clear()
    _npm_root_global.cache_clear()


def _cache_get(key):
    value = _PNG_CACHE.get(key)
    if value is not None:
        _PNG_CACHE.move_to_end(key)
    return value


def _cache_put(key, value):
    _PNG_CACHE[key] = value
    _PNG_CACHE.move_to_end(key)
    while len(_PNG_CACHE) > _CACHE_MAX:
        _PNG_CACHE.popitem(last=False)


def _decode_png(payload):
    if not payload.startswith(b'\x89PNG\r\n\x1a\n') or len(payload) < 24:
        raise ValueError('math renderer did not return a PNG')
    width, height = struct.unpack('>II', payload[16:24])
    if not width or not height:
        raise ValueError('math renderer returned invalid image dimensions')
    return payload, width, height


def _read_frames(data, count):
    frames = []
    offset = 0
    for _ in range(count):
        if offset + 8 > len(data):
            frames.append((1, b'short math renderer output'))
            continue
        status, length = struct.unpack_from('>II', data, offset)
        offset += 8
        if offset + length > len(data):
            frames.append((1, b'truncated math renderer output'))
            offset = len(data)
            continue
        frames.append((status, data[offset:offset + length]))
        offset += length
    return frames


def _render_batch(node, modules, items, color, scale, on_error):
    payload = json.dumps({
        'color': color,
        'scale': scale,
        'items': [{'tex': tex, 'display': display} for tex, display in items],
    }).encode('utf-8')
    kwargs = {
        'input': payload,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
        'timeout': 45,
    }
    if os.name == 'nt':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
    result = subprocess.run([node, _script_path(), modules], **kwargs)
    if result.returncode != 0:
        message = result.stderr.decode('utf-8', 'replace').strip() or 'math renderer failed'
        raise ValueError(message)
    frames = _read_frames(result.stdout, len(items))
    images = []
    for status, body in frames:
        if status != 0:
            message = body.decode('utf-8', 'replace').strip() or 'math formula failed'
            if on_error:
                on_error(message)
            images.append(None)
            continue
        try:
            images.append(_decode_png(body))
        except ValueError as error:
            if on_error:
                on_error(str(error))
            images.append(None)
    return images


def _display_size(width, height, scale, max_width):
    display_width = max(1, int(round(width / float(scale or 1))))
    display_height = max(1, int(round(height / float(scale or 1))))
    if max_width and display_width > max_width:
        display_height = max(1, int(display_height * max_width / display_width))
        display_width = max_width
    return display_width, display_height


def _image_html(encoded, alt, width, height, display):
    # display:inline is set on the tag because the document stylesheet makes
    # every img a block, and a block image inside a table row collapses.
    image = (
        '<img src="data:image/png;base64,{0}" alt="{1}" width="{2}" height="{3}" '
        'style="display:inline" />'
    ).format(encoded, html.escape(alt, quote=True), width, height)
    if display:
        return '\n<div class="math-display">{0}</div>\n'.format(image)
    return '<span class="math-inline" style="display:inline">{0}</span>'.format(image)


def render_math_blocks(
    text, node, modules, color='#000000', max_width=None, on_error=None,
    scale=_DPI_SCALE, deltas=None, spans=None,
):
    """Replace math spans with PNGs. Failed formulas become fenced source.

    ``node`` or ``modules`` may be missing; that leaves every formula fenced
    and does not raise. Successful renders are cached by formula, display
    mode, color, and scale. ``spans`` receives (start, end, replacement)
    offsets into ``text`` so callers can merge them with other replacements.
    """
    regions = math_regions(text)
    if not regions:
        return text
    if not node or not modules:
        if on_error:
            on_error('math renderer is not available')
        return _finish(
            text, regions, {}, scale=scale, max_width=max_width,
            deltas=deltas, spans=spans, failed=True,
        )

    color = normalize_color(color)
    scale = scale or _DPI_SCALE
    ready = {}
    pending = []
    pending_keys = set()
    for index, region in enumerate(regions):
        key = (region.tex, region.display, color, scale)
        cached = _cache_get(key)
        if cached is not None:
            ready[index] = cached
            continue
        if key in pending_keys:
            continue
        pending_keys.add(key)
        pending.append((key, region.tex, region.display))

    decoded = {}
    if pending:
        try:
            images = _render_batch(
                node, modules,
                [(tex, display) for _key, tex, display in pending],
                color, scale, on_error,
            )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            if on_error:
                on_error(str(error))
            images = [None] * len(pending)
        for (key, _tex, _display), image in zip(pending, images):
            decoded[key] = image
            if image is not None:
                _cache_put(key, image)

    for index, region in enumerate(regions):
        if index in ready:
            continue
        key = (region.tex, region.display, color, scale)
        ready[index] = decoded.get(key)
    return _finish(text, regions, ready, scale=scale, max_width=max_width,
                   deltas=deltas, spans=spans, failed=False)


def _finish(text, regions, ready, scale, max_width, deltas, spans, failed):
    parts = []
    previous = 0
    for index, region in enumerate(regions):
        parts.append(text[previous:region.start])
        image = None if failed else ready.get(index)
        if not image:
            replacement = math_fallback(region.tex)
        else:
            png, width, height = image
            display_width, display_height = _display_size(width, height, scale, max_width)
            if deltas is not None:
                deltas.append((text[:region.start].count('\n'), display_height))
            encoded = base64.b64encode(png).decode('ascii')
            alt = ' '.join(region.tex.split())
            if len(alt) > 500:
                alt = alt[:500]
            replacement = _image_html(
                encoded, alt, display_width, display_height, region.display,
            )
        parts.append(replacement)
        if spans is not None:
            spans.append((region.start, region.end, replacement))
        previous = region.end
    parts.append(text[previous:])
    return ''.join(parts)
