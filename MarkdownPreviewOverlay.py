"""Render Markdown as an editor-native overlay with mdpopups."""

import os
import threading
import urllib.parse
import webbrowser

import mdpopups
import sublime
import sublime_plugin


PHANTOM_KEY = "markdown_preview_overlay"
MODE_SETTING = "markdown_preview_overlay.preview_mode"
STATUS_KEY = "markdown_preview_overlay"

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}

OVERLAY_CSS = """
.markdown-preview-overlay-toolbar {
    margin: 0 0 0.55rem 0;
    padding: 0.35rem 0;
}
.markdown-preview-overlay-toolbar a {
    padding: 0.3rem 0.7rem;
    border-radius: 0.25rem;
    text-decoration: none;
    {{'string'|css}}
    {{'background'|css('background-color')|brightness(1.15)}}
}
.markdown-preview-overlay-toolbar a.secondary {
    margin-left: 0.4rem;
}
.markdown-preview-overlay-document {
    padding: 0.2rem 0.7rem 1rem 0.7rem;
}
"""


def _is_markdown(view):
    """Return whether a view should receive the overlay controls."""

    if (
        view is None
        or not view.is_valid()
        or view.settings().get("is_widget", False)
    ):
        return False

    if view.match_selector(0, "text.html.markdown"):
        return True

    file_name = view.file_name() or ""
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
        self.rendered_change_count = view.change_count()
        self.refresh_generation = 0
        self.refresh_lock = threading.Lock()

    def render(self):
        """Render the mode button and, in preview mode, the document."""

        if not self.view.is_valid():
            return

        if self.previewing:
            primary_action = "edit"
            primary_label = "Edit source"
        else:
            primary_action = "preview"
            primary_label = "Preview"

        toolbar = (
            '<div class="markdown-preview-overlay-toolbar">'
            '<a href="overlay:{0}">{1}</a>'.format(
                primary_action, primary_label
            )
        )
        if self.previewing:
            toolbar += (
                '<a class="secondary" href="overlay:refresh">Refresh</a>'
            )
        toolbar += "</div>"

        phantoms = [
            mdpopups.Phantom(
                sublime.Region(0),
                toolbar,
                sublime.LAYOUT_BLOCK,
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
            phantoms.append(
                mdpopups.Phantom(
                    # Keep both phantoms on the same real, unfolded anchor.
                    # A point on the fold boundary is less reliable during
                    # layout updates and external file reloads.
                    sublime.Region(0),
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
        self.original_selections = _copy_regions(self.view.sel())
        self.original_viewport = self.view.viewport_position()
        self.original_folds = _copy_regions(self.view.folded_regions())

        # Remove nested folds before creating our single source fold. They are
        # recreated when preview mode ends.
        for region in self.original_folds:
            self.view.unfold(region)

        self.fold_region = sublime.Region(
            self._source_fold_start(), self.view.size()
        )
        if not self.fold_region.empty():
            self.view.fold(self.fold_region)

        self.previewing = True
        self.view.settings().set(MODE_SETTING, True)
        self.view.set_status(STATUS_KEY, "Markdown Preview Overlay")
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
            self._source_fold_start(), self.view.size()
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

    def dispose(self, restore=True):
        """Remove all UI owned by this state."""

        if restore and self.view.is_valid() and self.previewing:
            self.hide()
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

    def _source_fold_start(self):
        """Keep the first line available as a stable phantom anchor."""

        if not self.view.size():
            return 0
        return self.view.full_line(0).end()


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
        if state is not None and state.previewing:
            state.schedule_refresh()

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
