# MarkdownPreviewOverlay

MarkdownPreviewOverlay is an editor-native Markdown reading mode for Sublime
Text. It leaves the original Markdown in the buffer, folds the source, and
renders the document as a themed minihtml phantom in the same view.

Rendering is delegated directly to the `mdpopups` Package Control dependency.
The package does not bundle a separate Markdown parser.

## Usage

Every Markdown view gets a **Preview** button at the beginning of the file.
Click it, run **Markdown Preview Overlay: Toggle** from the Command Palette, or
use the platform shortcut:

- macOS: <kbd>Command</kbd>+<kbd>Option</kbd>+<kbd>M</kbd>
- Windows/Linux: <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>M</kbd>

Preview mode is read-only. Use **Edit source** to leave it, or **Refresh** to
render the current buffer again. Leaving preview restores the prior selection,
viewport position, read-only state, and folds.

The first source line remains visible in preview mode. This provides a stable
buffer anchor for the phantom without inserting a marker or modifying the undo
history.

## Development installation

Clone or link this directory as `Packages/MarkdownPreviewOverlay`, then run
**Package Control: Satisfy Dependencies**. Package Control installs `mdpopups`
according to `dependencies.json`.

Sublime Text build 4050 or newer is required. The package selects Sublime's
Python 3.8 plugin host through `.python-version`.
