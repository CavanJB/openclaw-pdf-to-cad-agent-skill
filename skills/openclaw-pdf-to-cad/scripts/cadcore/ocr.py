from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import fitz

from cadcore.models import TextCandidate
from cadcore.text_utils import (
    add_text_candidate,
    clean_text,
    looks_garbled,
    normalize_ocr_text,
    union_rects,
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

    langs = tesseract_langs()
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
