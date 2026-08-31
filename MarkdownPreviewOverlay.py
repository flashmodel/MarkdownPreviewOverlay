"""
Render Markdown as an editor-native overlay with mdpopups.
"""

import os
import sys
import threading
import urllib.parse
import webbrowser

import mdpopups
import sublime
import sublime_plugin

prefix = __package__ + "."
for module_name in [
    m for m in sys.modules
    if m.startswith(prefix) and m != __name__
]:
    del sys.modules[module_name]

from .overlay.styles import (
    OVERLAY_CSS,
    ANNOTATION_HTML,
    ANNOTATION_RESERVED_WIDTH,
)
from .overlay.md_render import (
    render_markdown_tables_as_html,
    resolve_markdown_image_paths,
)


PHANTOM_KEY = "markdown_preview_overlay"
ANNOTATION_KEY = "markdown_preview_overlay.control"
MODE_SETTING = "markdown_preview_overlay.preview_mode"
ORIGINAL_STATE_SETTING = "markdown_preview_overlay.original_state"
STATUS_KEY = "markdown_preview_overlay"
SETTINGS_NAME = "MarkdownPreviewOverlay.sublime-settings"
SETTINGS_KEY = "markdown_preview_overlay.settings"
PREVIEW_MARGIN = 16

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}


def _is_markdown(view):
    """Return whether a file-backed Markdown view should receive controls."""

    if (
        view is None
        or not view.is_valid()
        or view.is_scratch()
        or view.settings().get("is_widget", False)
    ):
        return False

    # Keep transient views such as TermMate chat panes out of the default
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


def _capture_view_state(view):
    """Capture the current viewport, selections, folds, and layout settings of a view."""
    return {
        "read_only": view.is_read_only(),
        "gutter": view.settings().get("gutter"),
        "line_numbers": view.settings().get("line_numbers"),
        "highlight_line": view.settings().get("highlight_line"),
        "margin": view.settings().get("margin"),
        "selections": [[s.a, s.b] for s in view.sel()],
        "viewport": list(view.viewport_position()),
        "folds": [[f.a, f.b] for f in view.folded_regions()],
    }


def _restore_view_state(view, saved_state):
    """Restore a view's presentation, selections, viewport, and folds from saved state."""
    if not isinstance(saved_state, dict):
        saved_state = {}

    orig_read_only = saved_state.get("read_only", False)
    orig_gutter = saved_state.get("gutter", True)
    orig_line_numbers = saved_state.get("line_numbers", True)
    orig_highlight_line = saved_state.get("highlight_line")
    orig_margin = saved_state.get("margin")
    orig_selections = [
        sublime.Region(r[0], r[1])
        for r in saved_state.get("selections", [])
        if isinstance(r, (list, tuple)) and len(r) == 2
    ]
    orig_viewport = tuple(saved_state.get("viewport", [0.0, 0.0]))
    orig_folds = [
        sublime.Region(r[0], r[1])
        for r in saved_state.get("folds", [])
        if isinstance(r, (list, tuple)) and len(r) == 2
    ]

    # Temporarily make the view writable so restoration works for editable views
    view.set_read_only(False)
    view.unfold(sublime.Region(0, view.size()))

    for region in orig_folds:
        view.fold(region)

    if orig_gutter is not None:
        view.settings().set("gutter", orig_gutter)
    else:
        view.settings().erase("gutter")

    if orig_line_numbers is not None:
        view.settings().set("line_numbers", orig_line_numbers)
    else:
        view.settings().erase("line_numbers")

    if orig_highlight_line is not None:
        view.settings().set("highlight_line", orig_highlight_line)
    else:
        view.settings().erase("highlight_line")

    if orig_margin is not None:
        view.settings().set("margin", orig_margin)
    else:
        view.settings().erase("margin")

    view.set_read_only(bool(orig_read_only))

    selections = (
        _copy_regions(orig_selections)
        if orig_selections
        else [sublime.Region(0, 0)]
    )
    viewport = (
        orig_viewport
        if len(orig_viewport) == 2
        else (0.0, 0.0)
    )

    def restore_position():
        if not view.is_valid():
            return
        view.sel().clear()
        for selection in selections:
            view.sel().add(selection)
        view.set_viewport_position(viewport, False)

    sublime.set_timeout(restore_position)


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
        self.original_line_numbers = True
        self.original_highlight_line = None
        self.original_margin = None
        self.rendered_change_count = view.change_count()
        self.refresh_generation = 0
        self.control_generation = 0
        self.edit_control_mode = None
        self.refresh_lock = threading.Lock()

    def _load_original_state(self, state):
        """Load original presentation and layout attributes into instance state."""
        if not isinstance(state, dict):
            state = {}
        self.original_read_only = state.get("read_only", False)
        self.original_gutter = (
            state.get("gutter") if state.get("gutter") is not None else True
        )
        self.original_line_numbers = (
            state.get("line_numbers")
            if state.get("line_numbers") is not None
            else True
        )
        self.original_highlight_line = state.get("highlight_line")
        self.original_margin = state.get("margin")
        self.original_selections = [
            sublime.Region(r[0], r[1])
            for r in state.get("selections", [])
            if isinstance(r, (list, tuple)) and len(r) == 2
        ]
        self.original_viewport = tuple(state.get("viewport", [0.0, 0.0]))
        self.original_folds = [
            sublime.Region(r[0], r[1])
            for r in state.get("folds", [])
            if isinstance(r, (list, tuple)) and len(r) == 2
        ]

    def _dump_original_state(self):
        """Serialize current in-memory restoration data to a dictionary."""
        return {
            "read_only": self.original_read_only,
            "gutter": self.original_gutter,
            "line_numbers": self.original_line_numbers,
            "highlight_line": self.original_highlight_line,
            "margin": self.original_margin,
            "selections": [[s.a, s.b] for s in self.original_selections],
            "viewport": list(self.original_viewport),
            "folds": [[f.a, f.b] for f in self.original_folds],
        }

    def _should_hide_line_numbers(self):
        try:
            settings = sublime.load_settings(SETTINGS_NAME)
            value = settings.get("hide_line_numbers")
            if value is None:
                return True
            return bool(value)
        except Exception:
            return True

    def _should_show_button(self):
        try:
            settings = sublime.load_settings(SETTINGS_NAME)
            value = settings.get("show_preview_button")
            if value is None:
                value = settings.get("show_button", True)
            return bool(value)
        except Exception:
            return True

    def _should_show_status_indicator(self):
        try:
            settings = sublime.load_settings(SETTINGS_NAME)
            value = settings.get("show_status_indicator")
            if value is None:
                value = settings.get("show_status", True)
            return bool(value)
        except Exception:
            return True

    def _should_resolve_image_paths(self):
        try:
            settings = sublime.load_settings(SETTINGS_NAME)
            return bool(settings.get("resolve_image_paths", False))
        except Exception:
            return False

    def _get_table_max_width(self):
        try:
            settings = sublime.load_settings(SETTINGS_NAME)
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

    def _get_image_max_width(self):
        """Calculate maximum display width for images, bounded by viewport width and settings."""
        try:
            viewport_width, _ = self.view.viewport_extent()
            available = (
                max(100, min(int(viewport_width * 0.96), int(viewport_width - 36)))
                if viewport_width > 0
                else None
            )

            settings = sublime.load_settings(SETTINGS_NAME)
            configured = settings.get("image_max_width")
            if isinstance(configured, int) and not isinstance(configured, bool) and configured > 0:
                return min(configured, available) if available else configured

            return available
        except Exception:
            pass
        return None

    def _render_button(self):
        """Render the edit-mode button as an annotation or compact inline icon."""
        if not self.view.is_valid():
            return

        self.view.erase_regions(ANNOTATION_KEY)

        if not self._should_show_button():
            self.phantom_set.update([])
            self.edit_control_mode = None
            self.rendered_change_count = self.view.change_count()
            return

        if self._should_use_annotation():
            self.phantom_set.update([])
            self._render_annotation()
            self.edit_control_mode = "annotation"
            self.rendered_change_count = self.view.change_count()
            return

        toolbar = (
            '<a class="markdown-preview-overlay-preview-icon" '
            'href="overlay:preview" title="Preview Markdown">▣</a>'
        )
        phantom = mdpopups.Phantom(
            sublime.Region(0),
            toolbar,
            sublime.LAYOUT_INLINE,
            md=False,
            css=OVERLAY_CSS,
            on_navigate=self.on_navigate,
            wrapper_class="markdown-preview-overlay"
        )
        self.phantom_set.update([phantom])
        self.edit_control_mode = "inline"
        self.rendered_change_count = self.view.change_count()

    def _render_preview_overlay(self):
        """Render the preview toolbar and document markdown phantoms below the folded document."""
        if not self.view.is_valid():
            return

        self.view.erase_regions(ANNOTATION_KEY)

        anchor = self.view.size()
        toolbar = (
            '<a class="markdown-preview-overlay-toolbar-link" '
            'href="overlay:edit" title="Edit source">'
            '<div class="markdown-preview-overlay-toolbar">'
            '<span class="markdown-preview-overlay-arrow">◀</span>'
            '<span class="markdown-preview-overlay-label">✏️Edit source</span>'
            '</div>'
            '</a>'
        )
        phantoms = [
            mdpopups.Phantom(
                sublime.Region(anchor),
                toolbar,
                sublime.LAYOUT_BLOCK,
                md=False,
                css=OVERLAY_CSS,
                on_navigate=self.on_navigate,
                wrapper_class="markdown-preview-overlay"
            )
        ]

        markdown = self.view.substr(sublime.Region(0, self.view.size()))
        file_name = self.view.file_name()
        if file_name and self._should_resolve_image_paths():
            max_img_width = self._get_image_max_width()
            markdown = resolve_markdown_image_paths(markdown, file_name, max_width=max_img_width)
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

    def render(self):
        """Render the mode button in edit mode, or toolbar and document in preview mode."""
        if not self.view.is_valid():
            return
        if self.previewing:
            self._render_preview_overlay()
        else:
            self._render_button()

    def show(self, preserve_saved_state=False):
        """Enter preview mode without changing the buffer contents."""

        if self.previewing or not _is_markdown(self.view):
            return

        if not preserve_saved_state or not self.view.settings().has(ORIGINAL_STATE_SETTING):
            original_state = _capture_view_state(self.view)
            self.view.settings().set(ORIGINAL_STATE_SETTING, original_state)
            self._load_original_state(original_state)
        else:
            saved_state = self.view.settings().get(ORIGINAL_STATE_SETTING)
            self._load_original_state(saved_state)

        # Remove nested folds before creating our single source fold. They are
        # recreated when preview mode ends.
        for region in _copy_regions(self.view.folded_regions()):
            self.view.unfold(region)

        self.fold_region = sublime.Region(
            0, self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.previewing = True
        self.view.settings().set(MODE_SETTING, True)
        if self._should_show_status_indicator():
            self.view.set_status(STATUS_KEY, "MarkdownOverlay")
        else:
            self.view.erase_status(STATUS_KEY)
        self.view.settings().set("highlight_line", False)
        if self._should_hide_line_numbers():
            self.view.settings().set("line_numbers", False)
            self.view.settings().set("gutter", False)
            self.view.settings().set("margin", PREVIEW_MARGIN)
        self.view.set_read_only(True)
        self._render_preview_overlay()
        if not preserve_saved_state:
            self.view.set_viewport_position((0.0, 0.0), False)

    def hide(self):
        """Leave preview mode and restore the prior View presentation."""

        if not self.previewing and not self.view.settings().get(MODE_SETTING, False):
            self._render_button()
            return

        saved_state = self.view.settings().get(ORIGINAL_STATE_SETTING)
        if not isinstance(saved_state, dict):
            saved_state = self._dump_original_state()

        _restore_view_state(self.view, saved_state)

        self.previewing = False
        self.fold_region = None
        self.view.settings().erase(MODE_SETTING)
        self.view.settings().erase(ORIGINAL_STATE_SETTING)
        self.view.erase_status(STATUS_KEY)
        self._render_button()

    def refresh(self):
        """Re-read the buffer, update its fold, and rebuild the preview."""

        if not self.previewing or not self.view.is_valid():
            return

        self.view.set_read_only(False)
        for fold in _copy_regions(self.view.folded_regions()):
            self.view.unfold(fold)

        self.fold_region = sublime.Region(
            0, self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.view.set_read_only(True)
        self.phantom_set = mdpopups.PhantomSet(self.view, PHANTOM_KEY)
        self._render_preview_overlay()

    def schedule_refresh(self):
        """Debounce refreshes caused by reloads or saves."""

        with self.refresh_lock:
            self.refresh_generation += 1
            generation = self.refresh_generation

        def refresh_if_current():
            with self.refresh_lock:
                if generation != self.refresh_generation:
                    return
            if self.previewing and self.view.is_valid():
                self.refresh()

        sublime.set_timeout(refresh_if_current, 100)

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
        if not self._should_show_button():
            if self.edit_control_mode is not None:
                self._render_button()
            return
        desired = "annotation" if self._should_use_annotation() else "inline"
        if desired != self.edit_control_mode:
            self._render_button()

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


def _update_button(view):
    """Render or update the preview button for an edit-mode view."""

    if not view.is_valid():
        return

    if not _is_markdown(view):
        state = _states.pop(view.id(), None)
        if state is not None:
            state.dispose(restore=True)
        return

    state = _state_for(view)
    if not state.previewing and not view.settings().get(MODE_SETTING, False):
        state._render_button()


def _sync_preview_overlay(view):
    """Synchronize the preview overlay and folded markdown state for a view."""

    if not view.is_valid() or view.is_loading():
        return

    if not _is_markdown(view):
        state = _states.pop(view.id(), None)
        if state is not None:
            state.dispose(restore=True)
        return

    state = _state_for(view)
    is_preview_mode = bool(view.settings().get(MODE_SETTING, False))

    if is_preview_mode:
        if not state.previewing:
            state.show(preserve_saved_state=True)
        else:
            state.schedule_refresh()
    else:
        if state.previewing:
            state.hide()


def _sync_view_mode(view):
    """Synchronize both the preview overlay and the edit-mode button for a view."""

    if not view.is_valid() or view.is_loading():
        return

    if not _is_markdown(view):
        state = _states.pop(view.id(), None)
        if state is not None:
            state.dispose(restore=True)
        return

    state = _state_for(view)
    is_preview_mode = bool(view.settings().get(MODE_SETTING, False))

    if is_preview_mode:
        _sync_preview_overlay(view)
    else:
        _update_button(view)


def _open_link(view, href):
    """Open web links externally and local Markdown links in Sublime."""

    parsed = urllib.parse.urlparse(href)
    if parsed.scheme in {"http", "https", "mailto"}:
        webbrowser.open_new_tab(href)
        return

    if href.startswith("#"):
        sublime.status_message(
            "Markdown Overlay: heading links are not supported"
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
        if state.previewing or self.view.settings().get(MODE_SETTING, False):
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
        is_preview = (
            (state is not None and state.previewing)
            or bool(self.view.settings().get(MODE_SETTING, False))
        )
        return _is_markdown(self.view) and not is_preview


class MarkdownPreviewOverlayHideCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _state_for(self.view).hide()

    def is_enabled(self):
        state = _states.get(self.view.id())
        is_preview = (
            (state is not None and state.previewing)
            or bool(self.view.settings().get(MODE_SETTING, False))
        )
        return _is_markdown(self.view) and bool(is_preview)


class MarkdownPreviewOverlayRefreshCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        _state_for(self.view).refresh()

    def is_enabled(self):
        state = _states.get(self.view.id())
        is_preview = (
            (state is not None and state.previewing)
            or bool(self.view.settings().get(MODE_SETTING, False))
        )
        return _is_markdown(self.view) and bool(is_preview)


class MarkdownPreviewOverlayListener(sublime_plugin.EventListener):
    def on_load_async(self, view):
        _sync_view_mode(view)

    def on_activated_async(self, view):
        _sync_view_mode(view)

    def on_reload_async(self, view):
        _sync_view_mode(view)

    def on_revert_async(self, view):
        _sync_view_mode(view)

    def on_post_save_async(self, view):
        _sync_view_mode(view)

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
            state.dispose(restore=True)


def _on_settings_change():
    for window in sublime.windows():
        for view in window.views():
            if _is_markdown(view):
                state = _state_for(view)
                if not state.previewing:
                    state.render()
                else:
                    if state._should_hide_line_numbers():
                        view.settings().set("line_numbers", False)
                        view.settings().set("gutter", False)
                        view.settings().set("margin", PREVIEW_MARGIN)
                    else:
                        view.settings().set("line_numbers", state.original_line_numbers)
                        view.settings().set("gutter", state.original_gutter)
                        if state.original_margin is not None:
                            view.settings().set("margin", state.original_margin)
                        else:
                            view.settings().erase("margin")


def plugin_loaded():
    settings = sublime.load_settings(SETTINGS_NAME)
    settings.add_on_change(SETTINGS_KEY, _on_settings_change)

    for window in sublime.windows():
        for view in window.views():
            _sync_view_mode(view)


def plugin_unloaded():
    settings = sublime.load_settings(SETTINGS_NAME)
    settings.clear_on_change(SETTINGS_KEY)

    for state in list(_states.values()):
        state.dispose(restore=False)
    _states.clear()
