"""Optional, headless Mermaid rendering for minihtml previews."""

import base64
import functools
import html
import os
import re
import shutil
import struct
import subprocess


_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})([^\r\n]*)\r?\n?$')


def find_merman_cli():
    """Find the CLI, including common install locations outside a GUI app's PATH."""
    executable = shutil.which("merman-cli")
    if executable:
        return executable
    for directory in ("/opt/homebrew/bin", "/usr/local/bin", "~/.cargo/bin"):
        executable = shutil.which("merman-cli", path=os.path.expanduser(directory))
        if executable:
            return executable
    return None


def mermaid_blocks(text):
    """Yield closed Mermaid fences without interpreting fences inside other code."""
    offset = 0
    opening = None
    for line in text.splitlines(keepends=True):
        match = _FENCE.match(line)
        if opening is None:
            if match:
                fence, info = match.groups()
                if fence[0] == '`' and '`' in info:
                    offset += len(line)
                    continue
                opening = (offset, offset + len(line), fence, info.strip() == "mermaid")
        elif match:
            fence, info = match.groups()
            start, body_start, original_fence, is_mermaid = opening
            if (fence[0] == original_fence[0]
                    and len(fence) >= len(original_fence) and not info.strip()):
                if is_mermaid:
                    yield start, offset + len(line), text[body_start:offset]
                opening = None
        offset += len(line)


@functools.lru_cache(maxsize=32)
def _render_png(executable, source):
    """Cache successful renders so refreshes and resizing do not rerun the CLI."""
    result = subprocess.run(
        [executable, "render", "-", "--format", "png", "--output", "-", "--quiet"],
        input=source.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=15,
    )
    result.check_returncode()
    png = result.stdout
    if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) < 24:
        raise ValueError("merman-cli did not return a PNG image")
    width, height = struct.unpack('>II', png[16:24])
    if not width or not height:
        raise ValueError("merman-cli returned invalid image dimensions")
    return base64.b64encode(png).decode("ascii"), width, height


def render_mermaid_blocks(text, executable, max_width=None, on_error=None):
    """Replace Mermaid fences with embedded PNGs; preserve failed blocks verbatim."""
    output = []
    previous = 0
    for start, end, source in mermaid_blocks(text):
        output.append(text[previous:start])
        try:
            encoded, width, height = _render_png(executable, source)
            if max_width and width > max_width:
                height = max(1, int(height * max_width / width))
                width = max_width
            image = (
                '<img src="data:image/png;base64,{}" alt="Mermaid diagram" '
                'width="{}" height="{}" />'
            ).format(html.escape(encoded, quote=True), width, height)
            output.append('\n' + image + '\n\n')
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            output.append(text[start:end])
            if on_error:
                on_error(str(error))
        previous = end
    output.append(text[previous:])
    return ''.join(output)
