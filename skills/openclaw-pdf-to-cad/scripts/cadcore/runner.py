from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from cadcore.dxf_writer import convert_pdf_to_dxf
from cadcore.dwg import try_make_dwg
from cadcore.models import ConversionReport
from cadcore.preview import render_preview
from cadcore.report import write_delivery_readme, write_quality_report, zip_dir
from cadcore.text_utils import safe_name


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
    write_quality_report(report, report_path)
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
    import sys
    raise SystemExit(main(sys.argv[1:]))
