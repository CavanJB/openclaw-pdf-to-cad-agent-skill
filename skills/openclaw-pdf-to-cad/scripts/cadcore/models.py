from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import fitz


@dataclass
class PageStats:
    page_number: int
    width: float
    height: float
    vector_paths: int
    text_spans: int
    image_count: int
    source_type: str


@dataclass
class TextCandidate:
    text: str
    bbox: fitz.Rect
    size: float
    rotation: float
    source: str
    font_name: str | None = None
    origin: fitz.Point | None = None


@dataclass
class ConversionReport:
    status: str
    source_pdf: str
    output_dir: str
    package_name: str
    source_type: str
    page_count: int
    entity_count: int
    text_count: int
    dimension_text_count: int
    title_text_count: int
    cjk_text_count: int
    garbled_text_count: int
    ocr_text_count: int
    annotation_text_count: int
    word_fallback_text_count: int
    raw_char_text_count: int
    text_source_counts: dict[str, int]
    layers: list[str]
    dxf_path: str
    dwg_path: str | None
    preview_png: str
    preview_pdf: str
    zip_path: str
    recommended_cad_file: str
    findings: list[str] = field(default_factory=list)
    pages: list[PageStats] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
