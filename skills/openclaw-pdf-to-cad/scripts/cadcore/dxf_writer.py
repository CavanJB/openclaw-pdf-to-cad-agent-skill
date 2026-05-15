from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path

import ezdxf
import fitz

from cadcore.classification import classify_page
from cadcore.constants import DEFAULT_CJK_FONT, DXF_INSUNITS_MM, LAYER_SPECS, PAGE_GAP, TEXT_STYLE_FONTS
from cadcore.extraction import (
    cad_point,
    extract_text_candidates,
    rect_points,
    sample_cubic,
)
from cadcore.fonts import text_width_factor
from cadcore.models import ConversionReport, TextCandidate
from cadcore.text_utils import (
    contains_cjk,
    detect_text_style,
    text_layer,
)


def add_polyline(msp, points: Iterable[tuple[float, float]], layer: str, close: bool = False) -> int:
    pts = list(points)
    if len(pts) < 2:
        return 0
    msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})
    return 1


def add_cad_text(msp, candidate: TextCandidate, page_height: float, x_offset: float) -> str:
    if candidate.source == "garbled_unresolved":
        layer = "PDF_TEXT_UNCERTAIN"
        text = "OCR_REQUIRED_TEXT"
    else:
        layer = text_layer(candidate.text)
        text = candidate.text
    style = detect_text_style(text, candidate.font_name)
    insert_source = candidate.origin or fitz.Point(candidate.bbox.x0, candidate.bbox.y1)
    insert = cad_point(insert_source, page_height, x_offset)
    dxfattribs = {
        "height": candidate.size,
        "layer": layer,
        "style": style,
    }
    width_factor = text_width_factor(candidate, text, style)
    if abs(width_factor - 1.0) > 0.03:
        dxfattribs["width"] = width_factor
    if abs(candidate.rotation) >= 0.1:
        dxfattribs["rotation"] = candidate.rotation
    msp.add_text(text, dxfattribs=dxfattribs).set_placement(insert)
    return layer


def prepare_doc() -> ezdxf.EzDxf:
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = DXF_INSUNITS_MM
    doc.header["$DWGCODEPAGE"] = "ANSI_936"
    if "Standard" in doc.styles:
        doc.styles.get("Standard").dxf.font = DEFAULT_CJK_FONT
    for style_name, font_file in TEXT_STYLE_FONTS.items():
        if style_name not in doc.styles:
            doc.styles.add(style_name, font=font_file)
    for layer_name, color in LAYER_SPECS.items():
        if layer_name not in doc.layers:
            doc.layers.add(layer_name, color=color)
    return doc


def convert_pdf_to_dxf(pdf_path: Path, dxf_path: Path) -> tuple[ConversionReport, ezdxf.EzDxf]:
    source_doc = fitz.open(pdf_path)
    cad_doc = prepare_doc()
    msp = cad_doc.modelspace()

    pages = []
    findings = []
    entity_count = 0
    text_count = 0
    dimension_text_count = 0
    title_text_count = 0
    cjk_text_count = 0
    garbled_text_count = 0
    ocr_text_count = 0
    annotation_text_count = 0
    word_fallback_text_count = 0
    raw_char_text_count = 0
    text_source_counts: Counter[str] = Counter()
    x_offset = 0.0

    try:
        for page_index, page in enumerate(source_doc, start=1):
            stats = classify_page(page, page_index)
            pages.append(stats)
            page_height = page.rect.height
            page_width = page.rect.width

            frame = [
                (x_offset, 0.0),
                (x_offset + page_width, 0.0),
                (x_offset + page_width, page_height),
                (x_offset, page_height),
            ]
            entity_count += add_polyline(msp, frame, "PDF_PAGE_FRAME", close=True)

            if stats.source_type in {"scanned", "mixed", "unknown"}:
                findings.append(f"page {page_index}: classified as {stats.source_type}; raster or low-vector content may require manual review")
                note = f"PAGE {page_index} {stats.source_type.upper()} REVIEW REQUIRED"
                msp.add_text(note, dxfattribs={"height": 8.0, "layer": "REVIEW_NOTES"}).set_placement((x_offset + 12.0, page_height - 16.0))
                entity_count += 1

            for drawing in page.get_drawings():
                for item in drawing.get("items", []):
                    op = item[0]
                    try:
                        if op == "l" and len(item) >= 3:
                            p1 = cad_point(item[1], page_height, x_offset)
                            p2 = cad_point(item[2], page_height, x_offset)
                            msp.add_line(p1, p2, dxfattribs={"layer": "PDF_GEOMETRY"})
                            entity_count += 1
                        elif op == "re" and len(item) >= 2:
                            entity_count += add_polyline(msp, rect_points(item[1], page_height, x_offset), "PDF_GEOMETRY", close=True)
                        elif op == "c" and len(item) >= 5:
                            entity_count += add_polyline(msp, sample_cubic([item[1], item[2], item[3], item[4]], page_height, x_offset), "PDF_GEOMETRY")
                        elif op == "qu" and len(item) >= 2:
                            quad = item[1]
                            pts = [
                                cad_point(quad.ul, page_height, x_offset),
                                cad_point(quad.ur, page_height, x_offset),
                                cad_point(quad.lr, page_height, x_offset),
                                cad_point(quad.ll, page_height, x_offset),
                            ]
                            entity_count += add_polyline(msp, pts, "PDF_GEOMETRY", close=True)
                    except Exception as exc:
                        findings.append(f"page {page_index}: skipped unsupported drawing item {op}: {exc}")

            text_candidates, image_bboxes = extract_text_candidates(page, enable_page_ocr=stats.source_type in {"scanned", "mixed"})
            for bbox in image_bboxes:
                entity_count += add_polyline(msp, rect_points(bbox, page_height, x_offset), "PDF_IMAGE_PLACEHOLDER", close=True)

            if not text_candidates and stats.source_type in {"scanned", "mixed", "unknown"}:
                findings.append(f"page {page_index}: no extractable PDF text was found; OCR or manual review is required for rasterized annotations")

            for candidate in text_candidates:
                layer = add_cad_text(msp, candidate, page_height, x_offset)
                entity_count += 1
                text_count += 1
                text_source_counts[candidate.source] += 1
                if candidate.source == "annotation":
                    annotation_text_count += 1
                elif candidate.source == "word_fallback":
                    word_fallback_text_count += 1
                elif candidate.source == "raw_char":
                    raw_char_text_count += 1
                elif candidate.source in {"ocr_fallback", "ocr_page"}:
                    ocr_text_count += 1
                elif candidate.source == "garbled_unresolved":
                    garbled_text_count += 1
                if layer == "PDF_DIMENSIONS":
                    dimension_text_count += 1
                elif layer == "PDF_TITLE_BLOCK":
                    title_text_count += 1
                if candidate.source != "garbled_unresolved" and contains_cjk(candidate.text):
                    cjk_text_count += 1

            x_offset += page_width + PAGE_GAP
    finally:
        source_doc.close()

    cad_doc.saveas(dxf_path)

    page_types = {page.source_type for page in pages}
    if page_types == {"vector"}:
        source_type = "vector"
    elif "scanned" in page_types or "mixed" in page_types:
        source_type = "mixed_or_scanned"
    else:
        source_type = "unknown_or_low_confidence"

    status = "ok"
    if source_type != "vector" or entity_count <= 0:
        status = "needs_review"
    if dimension_text_count == 0:
        findings.append("no dimension-like text was confidently extracted; verify dimensions manually")
        if status == "ok":
            status = "needs_review"
    if word_fallback_text_count or raw_char_text_count:
        findings.append("some text was recovered through fallback extraction; verify annotation placement and grouping")
    if any(page.source_type in {"scanned", "mixed"} for page in pages):
        findings.append("rasterized or outline-only text may still require OCR/manual review because it is not true PDF text")
    if cjk_text_count:
        findings.append("CJK text was written with OpenClaw CJK text styles; if DWG still shows question marks, use the DXF/PDF preview or a DWG converter with Unicode/CJK font support")
    if garbled_text_count:
        findings.append("some PDF text extracted as question marks or replacement glyphs; unresolved items were moved to PDF_TEXT_UNCERTAIN and require OCR/manual review")
        status = "needs_review"
    if ocr_text_count:
        findings.append("some garbled PDF text was recovered with OCR fallback; verify OCR text before manufacturing use")

    report = ConversionReport(
        status=status,
        source_pdf=str(pdf_path),
        output_dir=str(dxf_path.parent),
        package_name=dxf_path.parent.name,
        source_type=source_type,
        page_count=len(pages),
        entity_count=entity_count,
        text_count=text_count,
        dimension_text_count=dimension_text_count,
        title_text_count=title_text_count,
        cjk_text_count=cjk_text_count,
        garbled_text_count=garbled_text_count,
        ocr_text_count=ocr_text_count,
        annotation_text_count=annotation_text_count,
        word_fallback_text_count=word_fallback_text_count,
        raw_char_text_count=raw_char_text_count,
        text_source_counts=dict(sorted(text_source_counts.items())),
        layers=sorted(LAYER_SPECS),
        dxf_path=str(dxf_path),
        dwg_path=None,
        preview_png="",
        preview_pdf="",
        zip_path="",
        recommended_cad_file=str(dxf_path),
        findings=sorted(dict.fromkeys(findings)),
        pages=pages,
    )
    return report, cad_doc
