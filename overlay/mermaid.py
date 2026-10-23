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
_COMMON_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "~/.cargo/bin", "~/.local/bin")
_DPI_SCALE = 2


def _detect_cli_type(path):
    """Detect whether the executable is merman-cli or mmdc."""
    real_path = os.path.realpath(path)
    combined = (os.path.basename(path) + " " + os.path.basename(real_path)).lower()
    if "merman" in combined:
        return "merman-cli"
    return "mmdc"


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


def find_mermaid_cli(custom_path=None):
    """Find a supported Mermaid CLI tool (mmdc or merman-cli).

    Returns a tuple of (executable_path, cli_type) or None if no CLI is found.
    """
    if custom_path:
        expanded = os.path.expandvars(os.path.expanduser(custom_path))
        resolved = shutil.which(expanded) or shutil.which(custom_path)
        if resolved:
            return resolved, _detect_cli_type(resolved)
        return None

    for binary_name in ("mmdc", "merman-cli"):
        executable = _find_executable(binary_name)
        if executable:
            return executable, _detect_cli_type(executable)

    return None


def find_merman_cli():
    """Find the CLI, including common install locations outside a GUI app's PATH."""
    result = find_mermaid_cli()
    if result:
        return result[0]
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


@functools.lru_cache(maxsize=64)
def _render_png(executable, source, cli_type=None, scale=_DPI_SCALE):
    """Cache successful renders so refreshes and resizing do not rerun the CLI."""
    if cli_type is None:
        cli_type = _detect_cli_type(executable)

    scale_str = str(scale)
    if cli_type == "mmdc":
        cmd = [
            executable, "-i", "-", "-o", "-", "-e", "png",
            "-b", "white", "-s", scale_str, "-q",
        ]
    else:
        cmd = [
            executable, "render", "-", "--format", "png",
            "--background", "white", "--scale", scale_str, "--output", "-", "--quiet",
        ]

    kwargs = {
        "input": source.encode("utf-8"),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": 15,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    result = subprocess.run(cmd, **kwargs)
    result.check_returncode()
    png = result.stdout
    if not png.startswith(b'\x89PNG\r\n\x1a\n') or len(png) < 24:
        raise ValueError("{} did not return a PNG image".format(cli_type))
    width, height = struct.unpack('>II', png[16:24])
    if not width or not height:
        raise ValueError("{} returned invalid image dimensions".format(cli_type))
    return base64.b64encode(png).decode("ascii"), width, height


def render_mermaid_blocks(
    text, executable, max_width=None, on_error=None, cli_type=None, scale=_DPI_SCALE
):
    """Replace Mermaid fences with embedded PNGs; preserve failed blocks verbatim."""
    output = []
    previous = 0
    if cli_type is None:
        cli_type = _detect_cli_type(executable)
    for start, end, source in mermaid_blocks(text):
        output.append(text[previous:start])
        try:
            encoded, width, height = _render_png(
                executable, source, cli_type=cli_type, scale=scale
            )
            display_width = max(1, int(round(width / scale)))
            display_height = max(1, int(round(height / scale)))
            if max_width and display_width > max_width:
                display_height = max(1, int(display_height * max_width / display_width))
                display_width = max_width
            image = (
                '<img src="data:image/png;base64,{}" alt="Mermaid diagram" '
                'width="{}" height="{}" />'
            ).format(html.escape(encoded, quote=True), display_width, display_height)
            output.append('\n' + image + '\n\n')
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            output.append(text[start:end])
            if on_error:
                on_error(str(error))
        previous = end
    output.append(text[previous:])
    return ''.join(output)
