"""
CSS and HTML templates for Markdown Preview Overlay.
"""

OVERLAY_CSS = """
a.markdown-preview-overlay-toolbar-link {
    display: block;
    text-decoration: none;
    cursor: pointer;
}
.markdown-preview-overlay-toolbar {
    display: block;
    background-color: color(var(--background) blend(var(--foreground) 95%));
    border: 1px solid color(var(--foreground) alpha(0.12));
    border-left: 4px solid var(--cyanish);
    border-radius: 4px;
    padding: 0.5rem 0.8rem;
    margin: 0.5rem 0 1rem;
    color: var(--cyanish);
    font-weight: bold;
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
    display: block;
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
