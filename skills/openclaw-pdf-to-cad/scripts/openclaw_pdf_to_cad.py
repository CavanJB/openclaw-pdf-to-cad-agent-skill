#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import ezdxf
import fitz
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE_GAP = 80.0
PREVIEW_WIDTH = 2400
PREVIEW_HEIGHT = 1600
PREVIEW_MARGIN = 80
DXF_INSUNITS_MM = 4

LAYER_SPECS = {
    "PDF_GEOMETRY": 7,
    "PDF_DIMENSIONS": 3,
    "PDF_TITLE_BLOCK": 5,
    "PDF_TEXT": 2,
    "PDF_TEXT_UNCERTAIN": 1,
    "PDF_IMAGE_PLACEHOLDER": 6,
    "PDF_PAGE_FRAME": 8,
    "REVIEW_NOTES": 1,
}

TITLE_KEYWORDS = (
    "图号",
    "图名",
    "名称",
    "材料",
    "比例",
    "审核",
    "设计",
    "技术要求",
    "title",
    "drawing",
    "part",
    "material",
    "scale",
    "revision",
)

DIMENSION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:R|M|Phi|DIA|Dia|THK|T=|Φ|Ø|⌀)?\s*\d+(?:\.\d+)?(?:\s*[xX*×]\s*\d+(?:\.\d+)?)*"
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
GARBLED_RE = re.compile(r"(?:\?{2,}|�|□)")
DEFAULT_CJK_FONT = "Arial Unicode.ttf"
TEXT_STYLE_FONTS = {
    "OPENCLAW_CJK": DEFAULT_CJK_FONT,
    "OPENCLAW_CJK_HEI": "STHeiti Medium.ttc",
    "OPENCLAW_CJK_SONG": DEFAULT_CJK_FONT,
    "OPENCLAW_LATIN": DEFAULT_CJK_FONT,
}


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


def cjk_preview_font_path() -> str | None:
    for font_path in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ):
        if Path(font_path).exists():
            return font_path
    return None


def font_path_for_style(style_name: str) -> str | None:
    font_file = TEXT_STYLE_FONTS.get(style_name) or DEFAULT_CJK_FONT
    direct = Path(font_file)
    if direct.exists():
        return str(direct)
    for base in (
        Path("/System/Library/Fonts/Supplemental"),
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
    ):
        candidate = base / font_file
        if candidate.exists():
            return str(candidate)
    return cjk_preview_font_path()


@lru_cache(maxsize=128)
def load_measure_font(style_name: str, pixel_size: int):
    font_path = font_path_for_style(style_name)
    if not font_path:
        return None
    try:
        return ImageFont.truetype(font_path, size=max(1, pixel_size))
    except Exception:
        return None


def measure_text_width(text: str, style_name: str, height: float) -> float:
    pixel_scale = 16
    font = load_measure_font(style_name, max(1, int(round(height * pixel_scale))))
    if not font:
        return 0.0
    try:
        return float(font.getlength(text)) / pixel_scale
    except Exception:
        try:
            bbox = font.getbbox(text)
            return float(bbox[2] - bbox[0]) / pixel_scale
        except Exception:
            return 0.0


def text_width_factor(candidate: TextCandidate, text: str, style_name: str) -> float:
    target_width = max(0.0, candidate.bbox.width)
    measured_width = measure_text_width(text, style_name, candidate.size)
    if target_width <= 0.0 or measured_width <= 0.0:
        return 1.0
    factor = target_width / measured_width
    if factor < 0.2 or factor > 5.0:
        return 1.0
    return round(factor, 4)


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


@lru_cache(maxsize=1)
def find_tesseract() -> str | None:
    configured = os.getenv("OPENCLAW_TESSERACT", "").strip()
    candidates = [configured] if configured else []
    found = shutil.which("tesseract")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def ocr_text_candidate(page: fitz.Page, candidate: TextCandidate) -> str:
    tesseract = find_tesseract()
    if not tesseract:
        return ""
    clip = fitz.Rect(candidate.bbox)
    clip.x0 = max(0.0, clip.x0 - 3.0)
    clip.y0 = max(0.0, clip.y0 - 3.0)
    clip.x1 = min(page.rect.width, clip.x1 + 3.0)
    clip.y1 = min(page.rect.height, clip.y1 + 3.0)
    if clip.is_empty or clip.width < 1.0 or clip.height < 1.0:
        return ""

    langs = os.getenv("OPENCLAW_OCR_LANGS", "chi_sim+eng").strip() or "chi_sim+eng"
    with tempfile.TemporaryDirectory(prefix="openclaw-ocr-") as tmpdir:
        image_path = Path(tmpdir) / "candidate.png"
        try:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=clip, alpha=False)
            pixmap.save(image_path)
            result = subprocess.run(
                [tesseract, str(image_path), "stdout", "-l", langs, "--psm", "7", "--dpi", "300"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
        except Exception:
            return ""
    if result.returncode != 0:
        return ""
    text = normalize_ocr_text(result.stdout)
    if not text or looks_garbled(text):
        return ""
    return text


def repair_garbled_candidate(page: fitz.Page, candidate: TextCandidate) -> TextCandidate:
    if not looks_garbled(candidate.text):
        return candidate
    ocr_text = ocr_text_candidate(page, candidate)
    if ocr_text:
        return replace(candidate, text=ocr_text, source="ocr_fallback")
    return replace(candidate, source="garbled_unresolved")


def tesseract_langs() -> str:
    return os.getenv("OPENCLAW_OCR_LANGS", "chi_sim+eng").strip() or "chi_sim+eng"


def run_tesseract(image_path: Path, *extra_args: str, timeout: int = 45) -> subprocess.CompletedProcess[str] | None:
    tesseract = find_tesseract()
    if not tesseract:
        return None
    try:
        return subprocess.run(
            [tesseract, str(image_path), "stdout", "-l", tesseract_langs(), *extra_args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None


def group_tesseract_words(rows: list[dict[str, str]], scale: float) -> list[TextCandidate]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        text = normalize_ocr_text(row.get("text", ""))
        if not text:
            continue
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            confidence = -1.0
        if confidence < 35:
            continue
        key = (row.get("block_num", "0"), row.get("par_num", "0"), row.get("line_num", "0"))
        grouped.setdefault(key, []).append(row)

    candidates: list[TextCandidate] = []
    for words in grouped.values():
        try:
            words.sort(key=lambda row: int(row.get("left", "0")))
        except ValueError:
            pass
        parts: list[str] = []
        rects: list[fitz.Rect] = []
        for row in words:
            text = normalize_ocr_text(row.get("text", ""))
            if not text:
                continue
            try:
                left = float(row["left"]) / scale
                top = float(row["top"]) / scale
                width = float(row["width"]) / scale
                height = float(row["height"]) / scale
            except Exception:
                continue
            parts.append(text)
            rects.append(fitz.Rect(left, top, left + width, top + height))
        if not parts or not rects:
            continue
        text = clean_text(" ".join(parts))
        bbox = union_rects(rects)
        size = max(1.5, min(24.0, bbox.height * 0.9))
        add_text_candidate(
            candidates,
            TextCandidate(
                text=text,
                bbox=bbox,
                size=size,
                rotation=0.0,
                source="ocr_page",
                origin=fitz.Point(bbox.x0, bbox.y1),
            ),
        )
    return candidates


def ocr_page_candidates(page: fitz.Page) -> list[TextCandidate]:
    if not find_tesseract():
        return []
    scale = 4.0
    with tempfile.TemporaryDirectory(prefix="openclaw-page-ocr-") as tmpdir:
        image_path = Path(tmpdir) / "page.png"
        try:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            pixmap.save(image_path)
        except Exception:
            return []
        result = run_tesseract(image_path, "--psm", "6", "--dpi", "300", "tsv")
    if not result or result.returncode != 0 or not result.stdout.strip():
        return []

    lines = result.stdout.splitlines()
    if len(lines) < 2:
        return []
    headers = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        values = line.split("\t")
        if len(values) < len(headers):
            values.extend([""] * (len(headers) - len(values)))
        rows.append(dict(zip(headers, values)))
    return group_tesseract_words(rows, scale)


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

    pages: list[PageStats] = []
    findings: list[str] = []
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


def entity_points(entity) -> list[tuple[float, float]]:
    try:
        dxftype = entity.dxftype()
        if dxftype == "LINE":
            return [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
        if dxftype == "LWPOLYLINE":
            return [(point[0], point[1]) for point in entity.get_points()]
        if dxftype == "TEXT":
            return [(entity.dxf.insert.x, entity.dxf.insert.y)]
    except Exception:
        return []
    return []


def layer_color(layer: str) -> tuple[int, int, int]:
    return {
        "PDF_GEOMETRY": (20, 20, 20),
        "PDF_DIMENSIONS": (0, 120, 0),
        "PDF_TITLE_BLOCK": (120, 40, 120),
        "PDF_TEXT": (30, 70, 140),
        "PDF_TEXT_UNCERTAIN": (190, 0, 0),
        "PDF_IMAGE_PLACEHOLDER": (160, 90, 0),
        "PDF_PAGE_FRAME": (120, 120, 120),
        "REVIEW_NOTES": (190, 0, 0),
    }.get(layer, (30, 30, 30))


def load_preview_font(size: int = 18):
    for font_path in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
    ):
        try:
            if Path(font_path).exists():
                return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return None


def render_preview(dxf_path: Path, png_path: Path, pdf_path: Path) -> None:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    entities = list(msp)
    points: list[tuple[float, float]] = []
    for entity in entities:
        points.extend(entity_points(entity))

    image = Image.new("RGB", (PREVIEW_WIDTH, PREVIEW_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    preview_font = load_preview_font()
    if not points:
        draw.text((80, 80), "No preview geometry", fill=(190, 0, 0))
        image.save(png_path)
        png_to_pdf(png_path, pdf_path)
        return

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    scale = min((PREVIEW_WIDTH - PREVIEW_MARGIN * 2) / width, (PREVIEW_HEIGHT - PREVIEW_MARGIN * 2) / height)

    def tx(point: tuple[float, float]) -> tuple[int, int]:
        x = PREVIEW_MARGIN + (point[0] - min_x) * scale
        y = PREVIEW_HEIGHT - PREVIEW_MARGIN - (point[1] - min_y) * scale
        return (int(round(x)), int(round(y)))

    for entity in entities:
        layer = getattr(entity.dxf, "layer", "0") or "0"
        color = layer_color(layer)
        dxftype = entity.dxftype()
        if dxftype == "LINE":
            draw.line([tx((entity.dxf.start.x, entity.dxf.start.y)), tx((entity.dxf.end.x, entity.dxf.end.y))], fill=color, width=2)
        elif dxftype == "LWPOLYLINE":
            pts = [(point[0], point[1]) for point in entity.get_points()]
            if len(pts) >= 2:
                draw.line([tx(point) for point in pts], fill=color, width=2)
                if bool(entity.closed):
                    draw.line([tx(pts[-1]), tx(pts[0])], fill=color, width=2)
        elif dxftype == "TEXT":
            text = entity.dxf.text or ""
            if text:
                draw.text(tx((entity.dxf.insert.x, entity.dxf.insert.y)), text[:64], fill=color, font=preview_font)

    image.save(png_path)
    png_to_pdf(png_path, pdf_path)


def png_to_pdf(png_path: Path, pdf_path: Path) -> None:
    image = Image.open(png_path)
    try:
        width, height = image.size
        c = canvas.Canvas(str(pdf_path), pagesize=(width, height))
        c.drawImage(ImageReader(image), 0, 0, width=width, height=height)
        c.showPage()
        c.save()
    finally:
        image.close()


def find_dwg_converter() -> str | None:
    configured = os.getenv("OPENCLAW_DWG_CONVERTER", "").strip()
    candidates = [configured] if configured else []
    found = shutil.which("dwg2dwg")
    if found:
        candidates.append(found)
    candidates.append("/Applications/QCAD.app/Contents/Resources/dwg2dwg")
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def try_make_dwg(dxf_path: Path, dwg_path: Path, findings: list[str]) -> str | None:
    converter = find_dwg_converter()
    if not converter:
        findings.append("DWG was not generated because no DXF-to-DWG converter was configured")
        return None

    attempts = [
        [converter, "-o", str(dwg_path), str(dxf_path)],
        [converter, str(dxf_path), str(dwg_path)],
    ]
    for command in attempts:
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if dwg_path.exists() and dwg_path.stat().st_size > 0:
                return str(dwg_path)
        except Exception:
            continue
    findings.append("DWG converter was found but conversion failed; DXF remains the recommended CAD output")
    return None


def write_delivery_readme(report: ConversionReport, readme_path: Path) -> None:
    findings = "\n".join(f"- {item}" for item in report.findings) or "- None"
    readme_path.write_text(
        f"""# PDF-to-CAD Delivery

Status: `{report.status}`

Recommended CAD file: `{Path(report.recommended_cad_file).name}`
Preview PDF: `{Path(report.preview_pdf).name}`
Quality report: `quality_report.json`

## Summary

- Source type: `{report.source_type}`
- Pages: {report.page_count}
- CAD entities: {report.entity_count}
- Extracted text entities: {report.text_count}
- CJK text entities: {report.cjk_text_count}
- OCR-recovered text entities: {report.ocr_text_count}
- Unresolved garbled text entities: {report.garbled_text_count}
- Dimension-like text entities: {report.dimension_text_count}
- Title-block-like text entities: {report.title_text_count}

## Review Findings

{findings}

## Notes

This package is generated by the standalone OpenClaw PDF-to-CAD skill. For scanned or mixed PDFs, treat the DXF as a review candidate and verify geometry and dimensions before manufacturing use.
""",
        encoding="utf-8",
    )


def zip_dir(directory: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(directory.rglob("*")):
            if file_path == zip_path or not file_path.is_file():
                continue
            zf.write(file_path, file_path.relative_to(directory))


def run(pdf_path: Path, output_dir: Path, customer_name: str = "", project_name: str = "", label: str = "") -> ConversionReport:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("openclaw-pdf-to-cad only supports PDF input")

    package_label = safe_name(label or project_name or pdf_path.stem) + "_cad_delivery"
    package_dir = output_dir / package_label
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)

    dxf_path = package_dir / f"{safe_name(pdf_path.stem)}.dxf"
    dwg_path = package_dir / f"{safe_name(pdf_path.stem)}.dwg"
    preview_png = package_dir / "preview.png"
    preview_pdf = package_dir / "preview.pdf"
    report_path = package_dir / "quality_report.json"
    readme_path = package_dir / "README.md"

    report, _cad_doc = convert_pdf_to_dxf(pdf_path, dxf_path)
    report.output_dir = str(package_dir)
    report.package_name = package_dir.name

    dwg_result = try_make_dwg(dxf_path, dwg_path, report.findings)
    report.dwg_path = dwg_result
    if dwg_result:
        if report.cjk_text_count or report.garbled_text_count or report.ocr_text_count:
            report.findings.append(
                "DWG was generated, but Unicode/CJK text fidelity cannot be validated automatically; DXF remains the recommended CAD file until the DWG is opened and checked"
            )
        else:
            report.recommended_cad_file = dwg_result

    render_preview(dxf_path, preview_png, preview_pdf)
    report.preview_png = str(preview_png)
    report.preview_pdf = str(preview_pdf)

    if customer_name:
        report.findings.append(f"customer_name recorded: {customer_name}")
    if project_name:
        report.findings.append(f"project_name recorded: {project_name}")

    write_delivery_readme(report, readme_path)
    zip_path = package_dir.with_suffix(".zip")
    zip_dir(package_dir, zip_path)
    report.zip_path = str(zip_path)
    report_path.write_text(json.dumps({**asdict(report), "quality_report": str(report_path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a PDF engineering drawing into a CAD delivery package")
    parser.add_argument("pdf_path", help="Absolute or relative path to the source PDF")
    parser.add_argument("--output-dir", default="outputs", help="Directory where delivery packages are created")
    parser.add_argument("--customer-name", default="", help="Optional customer label for the report")
    parser.add_argument("--project-name", default="", help="Optional project label for the report")
    parser.add_argument("--label", default="", help="Optional delivery folder label")
    args = parser.parse_args(argv)

    try:
        report = run(
            Path(args.pdf_path).expanduser().resolve(),
            Path(args.output_dir).expanduser().resolve(),
            customer_name=args.customer_name,
            project_name=args.project_name,
            label=args.label,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2

    result = {
        "status": report.status,
        "delivery_dir": report.output_dir,
        "zip_path": report.zip_path,
        "recommended_cad_file": report.recommended_cad_file,
        "dxf_path": report.dxf_path,
        "dwg_path": report.dwg_path,
        "preview_png": report.preview_png,
        "preview_pdf": report.preview_pdf,
        "quality_report": str(Path(report.output_dir) / "quality_report.json"),
        "source_type": report.source_type,
        "entity_count": report.entity_count,
        "text_count": report.text_count,
        "cjk_text_count": report.cjk_text_count,
        "garbled_text_count": report.garbled_text_count,
        "ocr_text_count": report.ocr_text_count,
        "dimension_text_count": report.dimension_text_count,
        "text_source_counts": report.text_source_counts,
        "findings": report.findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if report.status in {"ok", "needs_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
