#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import ezdxf
import fitz
from PIL import Image, ImageDraw
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

DIMENSION_RE = re.compile(r"(?<![A-Za-z0-9])(?:R|Phi|Dia|M)?\s*\d+(?:\.\d+)?(?:\s*[xX*]\s*\d+(?:\.\d+)?)*")


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


def cad_point(point: fitz.Point, page_height: float, x_offset: float) -> tuple[float, float]:
    return (round(point.x + x_offset, 4), round(page_height - point.y, 4))


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


def add_polyline(msp, points: Iterable[tuple[float, float]], layer: str, close: bool = False) -> int:
    pts = list(points)
    if len(pts) < 2:
        return 0
    msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})
    return 1


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

            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") == 1:
                    bbox = fitz.Rect(block.get("bbox"))
                    entity_count += add_polyline(msp, rect_points(bbox, page_height, x_offset), "PDF_IMAGE_PLACEHOLDER", close=True)
                    continue
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = (span.get("text") or "").strip()
                        if not text:
                            continue
                        bbox = fitz.Rect(span.get("bbox"))
                        height = max(1.5, min(24.0, float(span.get("size") or 4.0)))
                        layer = text_layer(text)
                        insert = cad_point(fitz.Point(bbox.x0, bbox.y1), page_height, x_offset)
                        msp.add_text(text, dxfattribs={"height": height, "layer": layer}).set_placement(insert)
                        entity_count += 1
                        text_count += 1
                        if layer == "PDF_DIMENSIONS":
                            dimension_text_count += 1
                        elif layer == "PDF_TITLE_BLOCK":
                            title_text_count += 1

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
        "PDF_IMAGE_PLACEHOLDER": (160, 90, 0),
        "PDF_PAGE_FRAME": (120, 120, 120),
        "REVIEW_NOTES": (190, 0, 0),
    }.get(layer, (30, 30, 30))


def render_preview(dxf_path: Path, png_path: Path, pdf_path: Path) -> None:
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    entities = list(msp)
    points: list[tuple[float, float]] = []
    for entity in entities:
        points.extend(entity_points(entity))

    image = Image.new("RGB", (PREVIEW_WIDTH, PREVIEW_HEIGHT), "white")
    draw = ImageDraw.Draw(image)
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
                draw.text(tx((entity.dxf.insert.x, entity.dxf.insert.y)), text[:64], fill=color)

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
        "dimension_text_count": report.dimension_text_count,
        "findings": report.findings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if report.status in {"ok", "needs_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
