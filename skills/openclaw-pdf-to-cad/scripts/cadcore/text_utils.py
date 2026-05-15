from __future__ import annotations

import re

import fitz

from cadcore.constants import CJK_RE, DIMENSION_RE, GARBLED_RE, TITLE_KEYWORDS
from cadcore.models import TextCandidate


def safe_name(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", value).strip().strip(".")
    return name or "pdf_to_cad_delivery"


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("\u00a0", " ").replace("\u200b", "")
    cleaned = re.sub(r"[\r\n\t\f\v]+", " ", cleaned)
    return cleaned.strip()


def contains_cjk(value: str) -> bool:
    return bool(CJK_RE.search(value))


def garbled_score(value: str) -> float:
    compact = re.sub(r"\s+", "", value or "")
    if not compact:
        return 0.0
    suspicious = compact.count("?") + compact.count("�") + compact.count("□")
    return suspicious / max(len(compact), 1)


def looks_garbled(value: str) -> bool:
    compact = re.sub(r"\s+", "", value or "")
    if not compact:
        return False
    return bool(GARBLED_RE.search(compact)) or garbled_score(compact) >= 0.2


def normalize_ocr_text(value: str) -> str:
    text = clean_text(value)
    text = text.replace("|", "丨") if contains_cjk(text) else text
    return text.strip(" -_")


def normalize_font_name(font_name: str | None) -> str:
    if not font_name:
        return ""
    return font_name.split("+")[-1].strip().lower()


def detect_text_style(text: str, font_name: str | None = None) -> str:
    normalized = normalize_font_name(font_name)
    if contains_cjk(text):
        if "hei" in normalized or "simhei" in normalized:
            return "OPENCLAW_CJK_HEI"
        if "song" in normalized or "simsun" in normalized:
            return "OPENCLAW_CJK_SONG"
        return "OPENCLAW_CJK"
    return "OPENCLAW_LATIN"


def text_layer(text: str) -> str:
    lowered = text.lower()
    if any(keyword in lowered or keyword in text for keyword in TITLE_KEYWORDS):
        return "PDF_TITLE_BLOCK"
    if DIMENSION_RE.search(text):
        return "PDF_DIMENSIONS"
    return "PDF_TEXT"


def rect_area(rect: fitz.Rect) -> float:
    return max(0.0, rect.x1 - rect.x0) * max(0.0, rect.y1 - rect.y0)


def overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    x0 = max(a.x0, b.x0)
    y0 = max(a.y0, b.y0)
    x1 = min(a.x1, b.x1)
    y1 = min(a.y1, b.y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    intersection = (x1 - x0) * (y1 - y0)
    smallest = min(rect_area(a), rect_area(b))
    if smallest <= 0:
        return 0.0
    return intersection / smallest


def normalized_text_key(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def add_text_candidate(pool: list[TextCandidate], candidate: TextCandidate) -> None:
    text = clean_text(candidate.text)
    if not text:
        return
    if candidate.bbox.is_empty or candidate.bbox.is_infinite:
        return
    pool.append(
        TextCandidate(
            text=text,
            bbox=fitz.Rect(candidate.bbox),
            size=max(1.5, min(24.0, float(candidate.size or 4.0))),
            rotation=candidate.rotation,
            source=candidate.source,
            font_name=candidate.font_name,
            origin=fitz.Point(candidate.origin) if candidate.origin else None,
        )
    )


def candidate_is_duplicate(candidate: TextCandidate, accepted: list[TextCandidate]) -> bool:
    candidate_key = normalized_text_key(candidate.text)
    for existing in accepted:
        existing_key = normalized_text_key(existing.text)
        if not candidate_key or not existing_key:
            continue
        if overlap_ratio(candidate.bbox, existing.bbox) < 0.45:
            continue
        if candidate_key == existing_key:
            return True
        if candidate_key in existing_key or existing_key in candidate_key:
            return True
    return False


def union_rects(rects: list[fitz.Rect]) -> fitz.Rect:
    result = fitz.Rect(rects[0])
    for rect in rects[1:]:
        result.include_rect(rect)
    return result
