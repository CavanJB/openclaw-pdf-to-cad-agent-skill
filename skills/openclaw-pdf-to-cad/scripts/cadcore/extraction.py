from __future__ import annotations

import math
from collections.abc import Sequence

import fitz

from cadcore.models import TextCandidate
from cadcore.text_utils import (
    add_text_candidate,
    candidate_is_duplicate,
    clean_text,
    normalized_text_key,
)
from cadcore.ocr import ocr_page_candidates, repair_garbled_candidate


def point_from_pdf_value(value) -> fitz.Point | None:
    if not value:
        return None
    try:
        return fitz.Point(value)
    except Exception:
        try:
            return fitz.Point(float(value[0]), float(value[1]))
        except Exception:
            return None


def cad_point(point: fitz.Point, page_height: float, x_offset: float) -> tuple[float, float]:
    return (round(point.x + x_offset, 4), round(page_height - point.y, 4))


def line_rotation_deg(line: dict) -> float:
    direction = line.get("dir") or (1.0, 0.0)
    try:
        dx = float(direction[0])
        dy = float(direction[1])
    except Exception:
        return 0.0
    angle = math.degrees(math.atan2(-dy, dx))
    if abs(angle) < 0.1:
        return 0.0
    return round(angle, 4)


def rect_points(rect: fitz.Rect, page_height: float, x_offset: float) -> list[tuple[float, float]]:
    return [
        cad_point(fitz.Point(rect.x0, rect.y0), page_height, x_offset),
        cad_point(fitz.Point(rect.x1, rect.y0), page_height, x_offset),
        cad_point(fitz.Point(rect.x1, rect.y1), page_height, x_offset),
        cad_point(fitz.Point(rect.x0, rect.y1), page_height, x_offset),
    ]


def sample_cubic(points: Sequence[fitz.Point], page_height: float, x_offset: float) -> list[tuple[float, float]]:
    if len(points) != 4:
        return []
    p0, p1, p2, p3 = points
    sampled: list[tuple[float, float]] = []
    for index in range(13):
        t = index / 12.0
        mt = 1.0 - t
        x = mt**3 * p0.x + 3 * mt**2 * t * p1.x + 3 * mt * t**2 * p2.x + t**3 * p3.x
        y = mt**3 * p0.y + 3 * mt**2 * t * p1.y + 3 * mt * t**2 * p2.y + t**3 * p3.y
        sampled.append(cad_point(fitz.Point(x, y), page_height, x_offset))
    return sampled


def union_rects(rects: list[fitz.Rect]) -> fitz.Rect:
    result = fitz.Rect(rects[0])
    for rect in rects[1:]:
        result.include_rect(rect)
    return result


def extract_span_candidates(page: fitz.Page) -> tuple[list[TextCandidate], list[fitz.Rect]]:
    candidates: list[TextCandidate] = []
    image_bboxes: list[fitz.Rect] = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if block.get("type") == 1:
            image_bboxes.append(fitz.Rect(block.get("bbox")))
            continue
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rotation = line_rotation_deg(line)
            for span in line.get("spans", []):
                text = clean_text(span.get("text"))
                if not text:
                    continue
                bbox = fitz.Rect(span.get("bbox"))
                add_text_candidate(
                    candidates,
                    TextCandidate(
                        text=text,
                        bbox=bbox,
                        size=float(span.get("size") or 4.0),
                        rotation=rotation,
                        source="span",
                        font_name=span.get("font"),
                        origin=point_from_pdf_value(span.get("origin")),
                    ),
                )
    return candidates, image_bboxes


def extract_word_fallback_candidates(page: fitz.Page) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    grouped: dict[tuple[int, int], list[tuple]] = {}
    try:
        words = page.get_text("words", sort=True)
    except Exception:
        return candidates
    for word in words:
        if len(word) < 7:
            continue
        block_no = int(word[5])
        line_no = int(word[6])
        grouped.setdefault((block_no, line_no), []).append(word)
    for line_words in grouped.values():
        line_words.sort(key=lambda item: (item[1], item[0]))
        text = clean_text(" ".join(str(item[4]) for item in line_words))
        if not text:
            continue
        rects = [fitz.Rect(item[0], item[1], item[2], item[3]) for item in line_words]
        bbox = union_rects(rects)
        size = max(1.5, min(24.0, bbox.height * 0.85))
        add_text_candidate(candidates, TextCandidate(text=text, bbox=bbox, size=size, rotation=0.0, source="word_fallback"))
    return candidates


def line_text_from_chars(chars: list[dict]) -> str:
    if not chars:
        return ""
    ordered = sorted(chars, key=lambda item: (fitz.Rect(item.get("bbox")).x0 if item.get("bbox") else 0.0))
    widths: list[float] = []
    for char in ordered:
        if char.get("bbox"):
            rect = fitz.Rect(char.get("bbox"))
            if rect.width > 0:
                widths.append(rect.width)
    average_width = sum(widths) / len(widths) if widths else 3.0
    parts: list[str] = []
    previous_rect: fitz.Rect | None = None
    for char in ordered:
        value = char.get("c") or ""
        if not value:
            continue
        rect = fitz.Rect(char.get("bbox")) if char.get("bbox") else None
        if previous_rect and rect:
            gap = rect.x0 - previous_rect.x1
            if gap > max(average_width * 0.65, 1.8):
                parts.append(" ")
        parts.append(value)
        if rect:
            previous_rect = rect
    return clean_text("".join(parts))


def extract_raw_char_candidates(page: fitz.Page) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    try:
        raw_dict = page.get_text("rawdict")
    except Exception:
        return candidates
    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            rotation = line_rotation_deg(line)
            chars: list[dict] = []
            rects: list[fitz.Rect] = []
            max_size = 4.0
            font_name = None
            origin = None
            for span in line.get("spans", []):
                max_size = max(max_size, float(span.get("size") or 4.0))
                font_name = font_name or span.get("font")
                origin = origin or point_from_pdf_value(span.get("origin"))
                for char in span.get("chars", []):
                    value = char.get("c") or ""
                    if value:
                        chars.append(char)
                    if char.get("bbox"):
                        rects.append(fitz.Rect(char.get("bbox")))
            text = line_text_from_chars(chars)
            if not text or not rects:
                continue
            add_text_candidate(
                candidates,
                TextCandidate(
                    text=text,
                    bbox=union_rects(rects),
                    size=max_size,
                    rotation=rotation,
                    source="raw_char",
                    font_name=font_name,
                    origin=origin,
                ),
            )
    return candidates


def extract_annotation_candidates(page: fitz.Page) -> list[TextCandidate]:
    candidates: list[TextCandidate] = []
    try:
        annotations = list(page.annots() or [])
    except Exception:
        return candidates
    for annot in annotations:
        info = annot.info or {}
        parts = [
            clean_text(info.get("content")),
            clean_text(info.get("title")),
            clean_text(info.get("subject")),
        ]
        text = clean_text(" ".join(part for part in parts if part))
        if not text:
            continue
        rect = fitz.Rect(annot.rect)
        size = max(2.0, min(18.0, rect.height * 0.35))
        add_text_candidate(candidates, TextCandidate(text=text, bbox=rect, size=size, rotation=0.0, source="annotation"))
    return candidates


def extract_text_candidates(page: fitz.Page, enable_page_ocr: bool = False) -> tuple[list[TextCandidate], list[fitz.Rect]]:
    span_candidates, image_bboxes = extract_span_candidates(page)
    pool = []
    pool.extend(span_candidates)
    pool.extend(extract_word_fallback_candidates(page))
    pool.extend(extract_raw_char_candidates(page))
    pool.extend(extract_annotation_candidates(page))
    if enable_page_ocr or not pool:
        pool.extend(ocr_page_candidates(page))
    priority = {"annotation": 0, "raw_char": 1, "span": 2, "word_fallback": 3, "ocr_fallback": 4, "ocr_page": 5}
    accepted: list[TextCandidate] = []
    for candidate in sorted(pool, key=lambda item: (priority.get(item.source, 9), -len(normalized_text_key(item.text)))):
        if candidate_is_duplicate(candidate, accepted):
            continue
        accepted.append(repair_garbled_candidate(page, candidate))
    return accepted, image_bboxes
