from __future__ import annotations

from pathlib import Path

import ezdxf
from PIL import Image, ImageDraw

from cadcore.fonts import cjk_preview_font_path

PREVIEW_WIDTH = 2400
PREVIEW_HEIGHT = 1600
PREVIEW_MARGIN = 80


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
    font_path = cjk_preview_font_path()
    if not font_path:
        return None
    try:
        from PIL import ImageFont
        return ImageFont.truetype(font_path, size=size)
    except Exception:
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
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image = Image.open(png_path)
    try:
        width, height = image.size
        c = canvas.Canvas(str(pdf_path), pagesize=(width, height))
        c.drawImage(ImageReader(image), 0, 0, width=width, height=height)
        c.showPage()
        c.save()
    finally:
        image.close()
