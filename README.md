# MarkdownPreviewOverlay

MarkdownPreviewOverlay is an editor-native Markdown reading mode for Sublime
Text. It leaves the original Markdown in the buffer, folds the source, and
renders the document as a themed minihtml phantom in the same view.

Rendering is delegated directly to the `mdpopups` Package Control dependency.
The package does not bundle a separate Markdown parser.

This extension is built on concept discussed in the forum topic: [Provide markdown preview mode using folded source and phantom](https://forum.sublimetext.com/t/provide-markdown-preview-mode-using-folded-source-and-phantom/79042). Join the discussion and share your thoughts or feedback in that thread!


## Usage

MarkdownPreviewOverlay provides seamless ways to enter, navigate, and exit preview mode without leaving your active editor view.

### 1. Interactive Phantom Buttons

The package injects lightweight, non-intrusive interactive controls directly into the buffer:

- Entering Preview **(Edit Mode)**:
  Click the **`▣ Preview`** button at the top of the file (displayed as a right-aligned annotation badge, or a compact inline `▣` icon if the line is long) to fold the source text and enter the preview overlay.
- Leaving Preview **(Preview Mode)**:
  Click the **`✏️Edit source`** button in the top toolbar to exit preview mode. Your previous cursor selection, scroll position, original read-only status, and manual code folds are fully restored.

### 2. Command Palette

Press `Command+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux) and search for `Markdown Preview Overlay`:

| Command | Description |
| :--- | :--- |
| **`Markdown Preview Overlay: Toggle`** | Toggles seamlessly between Preview Mode and Edit Mode. |
| **`Markdown Preview Overlay: Preview Mode`** | Enters the rendered preview mode for the active Markdown document. |
| **`Markdown Preview Overlay: Edit Mode`** | Exits preview mode and returns to editing the source buffer. |
| **`Markdown Preview Overlay: Refresh`** | Forces a re-render of the preview layout (useful after resizing the window). |

### 3. Optional Key Bindings

To avoid shortcut collisions with other packages, default key bindings are provided as `.example` templates. To enable keyboard shortcuts, copy the bindings from the `.sublime-keymap.example` files into your User keymap (`Preferences -> Key Bindings`):

- **macOS** (`Default (OSX).sublime-keymap.example`):
  ```json
  [
      {
          "keys": ["super+alt+m"],
          "command": "markdown_preview_overlay_toggle",
          "context": [{ "key": "selector", "operator": "equal", "operand": "text.html.markdown" }]
      }
  ]
  ```
- **Windows / Linux** (`Default (Windows/Linux).sublime-keymap.example`):
  ```json
  [
      {
          "keys": ["ctrl+alt+m"],
          "command": "markdown_preview_overlay_toggle",
          "context": [{ "key": "selector", "operator": "equal", "operand": "text.html.markdown" }]
      }
  ]
  ```

### Behavior & Document Lifecycle

- **Read-only Safety**: Preview mode makes the buffer temporarily read-only to prevent accidental edits while viewing formatted text.
- **Buffer Integrity**: Source folding uses standard Sublime Text region folding without modifying the buffer text or polluting the undo history.
- **Auto-Refresh**: If the document is modified or saved, the preview updates automatically with debounced re-rendering.

## Development installation

Clone or link this directory as `Packages/MarkdownPreviewOverlay`, then run
**Package Control: Satisfy Dependencies**. Package Control installs `mdpopups`
according to `dependencies.json`.

Sublime Text build 4050 or newer is required. The package selects Sublime's
Python 3.8 plugin host through `.python-version`.
