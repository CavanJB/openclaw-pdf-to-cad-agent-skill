from __future__ import annotations

import fitz

from cadcore.models import PageStats


def classify_page(page: fitz.Page, page_number: int) -> PageStats:
    drawings = page.get_drawings()
    text_dict = page.get_text("dict")
    text_spans = 0
    image_count = 0
    for block in text_dict.get("blocks", []):
        if block.get("type") == 1:
            image_count += 1
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if (span.get("text") or "").strip():
                    text_spans += 1

    vector_paths = len(drawings)
    if vector_paths >= 30 and text_spans >= 5:
        source_type = "vector"
    elif vector_paths >= 30:
        source_type = "vector"
    elif image_count > 0 and vector_paths < 10 and text_spans < 5:
        source_type = "scanned"
    elif image_count > 0:
        source_type = "mixed"
    else:
        source_type = "unknown"

    return PageStats(
        page_number=page_number,
        width=round(page.rect.width, 4),
        height=round(page.rect.height, 4),
        vector_paths=vector_paths,
        text_spans=text_spans,
        image_count=image_count,
        source_type=source_type,
    )
