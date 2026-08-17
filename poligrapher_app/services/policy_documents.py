"""Create durable, provenance-labelled policy documents from captured text."""

from __future__ import annotations

from html import escape
from pathlib import Path


def render_captured_policy_pdf(
    target: str | Path,
    *,
    title: str,
    source_url: str,
    capture_date: str,
    text: str,
) -> None:
    """Render policy text to a paginated PDF for the existing upload pipeline."""
    import fitz

    paragraphs = "\n".join(
        f"<p>{escape(block).replace(chr(10), '<br>')}</p>"
        for block in text.strip().split("\n\n")
        if block.strip()
    )
    document_html = f"""
        <header>
          <h1>{escape(title)}</h1>
          <p class="provenance"><b>Official source:</b> {escape(source_url)}</p>
          <p class="provenance"><b>Captured:</b> {escape(capture_date)}</p>
        </header>
        <main>{paragraphs}</main>
    """
    css = """
        body { font-family: sans-serif; font-size: 9.5pt; line-height: 1.35; color: #1b1b1b; }
        h1 { font-size: 20pt; text-align: center; margin: 0 0 18pt; }
        header { margin-bottom: 18pt; }
        p { margin: 0 0 8pt; }
        .provenance { color: #4a4a4a; font-size: 8pt; margin-bottom: 4pt; }
    """
    story = fitz.Story(document_html, user_css=css, em=10)
    writer = fitz.DocumentWriter(str(target))
    media_box = fitz.paper_rect("letter")
    content_box = media_box + (46, 46, -46, -46)

    def page_rect(_rect_number: int, _filled: tuple[float, float, float, float]):
        return media_box, content_box, None

    try:
        story.write(writer, page_rect)
    finally:
        writer.close()
