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
from .overlay.md_render import render_markdown_tables_as_html


PHANTOM_KEY = "markdown_preview_overlay"
ANNOTATION_KEY = "markdown_preview_overlay.control"
MODE_SETTING = "markdown_preview_overlay.preview_mode"
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
        self.original_line_numbers = True
        self.original_margin = None
        self.rendered_change_count = view.change_count()
        self.refresh_generation = 0
        self.control_generation = 0
        self.edit_control_mode = None
        self.refresh_lock = threading.Lock()


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

    def render(self):
        """Render the mode button and, in preview mode, the document."""

        if not self.view.is_valid():
            return

        self.view.erase_regions(ANNOTATION_KEY)

        if not self.previewing:
            if not self._should_show_button():
                self.phantom_set.update([])
                self.edit_control_mode = None
                self.rendered_change_count = self.view.change_count()
                return

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
                '<a class="markdown-preview-overlay-toolbar-link" '
                'href="overlay:{0}" title="{1}">'
                '<div class="markdown-preview-overlay-toolbar">'
                '<span class="markdown-preview-overlay-arrow">◀</span>'
                '<span class="markdown-preview-overlay-label">✏️Edit source</span>'
                '</div>'
                '</a>'.format(
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
        self.original_line_numbers = self.view.settings().get("line_numbers", True)
        self.original_margin = self.view.settings().get("margin")
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
        if self._should_hide_line_numbers():
            self.view.settings().set("line_numbers", False)
            self.view.settings().set("gutter", False)
            self.view.settings().set("margin", PREVIEW_MARGIN)
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
        self.view.settings().set("line_numbers", self.original_line_numbers)
        if self.original_margin is not None:
            self.view.settings().set("margin", self.original_margin)
        else:
            self.view.settings().erase("margin")
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
        for fold in _copy_regions(self.view.folded_regions()):
            self.view.unfold(fold)

        self.fold_region = sublime.Region(
            0, self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.view.set_read_only(True)
        self.phantom_set = mdpopups.PhantomSet(self.view, PHANTOM_KEY)
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
                self.render()
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
        state = _states.get(view.id())
        if state is not None and state.previewing:
            state.schedule_refresh()

    def on_activated_async(self, view):
        self._schedule_button_update(view)
        state = _states.get(view.id())
        if state is not None and state.previewing:
            state.schedule_refresh()

    def on_reload_async(self, view):
        self._schedule_button_update(view)
        state = _states.get(view.id())
        if state is not None and state.previewing:
            state.schedule_refresh()

    def on_revert_async(self, view):
        self._schedule_button_update(view)
        state = _states.get(view.id())
        if state is not None and state.previewing:
            state.schedule_refresh()

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
            if _is_markdown(view):
                _state_for(view).render()


def plugin_unloaded():
    settings = sublime.load_settings(SETTINGS_NAME)
    settings.clear_on_change(SETTINGS_KEY)

    for state in list(_states.values()):
        state.dispose()
    _states.clear()
