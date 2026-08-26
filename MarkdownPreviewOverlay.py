"""Render Markdown as an editor-native overlay with mdpopups."""

import os
import threading
import urllib.parse
import webbrowser

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
