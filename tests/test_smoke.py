from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ezdxf
import fitz
from reportlab.pdfgen import canvas


def _make_synthetic_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=(420, 297))
    for x in range(40, 260, 8):
        c.line(x, 90, x + 3, 93)
    c.rect(40, 90, 220, 120)
    c.line(40, 210, 260, 90)
    c.drawString(55, 230, "DIM 220")
    c.drawString(55, 70, "TITLE BLOCK MATERIAL SCALE")
    c.showPage()
    c.save()


def _make_cjk_pdf(path: Path) -> None:
    font_file = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=297)
    page.draw_rect(fitz.Rect(40, 80, 220, 180), color=(0, 0, 0), width=0.8)
    page.insert_text(
        (55, 52),
        "技术要求：",
        fontsize=12,
        fontname="ArialUnicode",
        fontfile=font_file,
        color=(0, 0, 0),
    )
    page.insert_text(
        (55, 68),
        "1. 未注尺寸公差按GB/T1804-f级；",
        fontsize=9,
        fontname="ArialUnicode",
        fontfile=font_file,
        color=(0, 0, 0),
    )
    page.insert_text(
        (55, 84),
        "M8 - 6H 完全贯穿",
        fontsize=9,
        fontname="ArialUnicode",
        fontfile=font_file,
        color=(0, 0.5, 0),
    )
    page.insert_text(
        (55, 100),
        "表面处理：锐角倒钝；",
        fontsize=9,
        fontname="ArialUnicode",
        fontfile=font_file,
        color=(0, 0, 0),
    )
    doc.save(path)
    doc.close()


def _make_garbled_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=(420, 297))
    c.rect(40, 90, 220, 120)
    c.drawString(55, 230, "M8 - 6H ???")
    c.drawString(55, 70, "TITLE ???? MATERIAL")
    c.showPage()
    c.save()


def test_pdf_to_cad_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "skills" / "openclaw-pdf-to-cad" / "scripts" / "openclaw_pdf_to_cad.py"
    source_pdf = tmp_path / "synthetic.pdf"
    output_dir = tmp_path / "outputs"
    _make_synthetic_pdf(source_pdf)

    result = subprocess.run(
        ["python3", str(script), str(source_pdf), "--output-dir", str(output_dir), "--label", "smoke"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] in {"ok", "needs_review"}
    assert Path(payload["dxf_path"]).exists()
    assert Path(payload["preview_pdf"]).exists()
    assert Path(payload["quality_report"]).exists()

    doc = ezdxf.readfile(payload["dxf_path"])
    layers = {layer.dxf.name for layer in doc.layers}
    assert "PDF_GEOMETRY" in layers
    assert "PDF_DIMENSIONS" in layers
    assert len(list(doc.modelspace())) > 0


def test_cjk_text_is_preserved_with_cjk_styles(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "skills" / "openclaw-pdf-to-cad" / "scripts" / "openclaw_pdf_to_cad.py"
    source_pdf = tmp_path / "cjk.pdf"
    output_dir = tmp_path / "outputs"
    _make_cjk_pdf(source_pdf)

    result = subprocess.run(
        ["python3", str(script), str(source_pdf), "--output-dir", str(output_dir), "--label", "cjk"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["cjk_text_count"] >= 4

    doc = ezdxf.readfile(payload["dxf_path"])
    texts = [entity.dxf.text for entity in doc.modelspace() if entity.dxftype() == "TEXT"]
    joined = "\n".join(texts)
    assert "技术要求" in joined
    assert "未注尺寸公差" in joined
    assert "完全贯穿" in joined
    assert "表面处理" in joined
    assert "????" not in joined

    styles = {style.dxf.name: style.dxf.font for style in doc.styles}
    assert "OPENCLAW_CJK" in styles
    assert any("Arial Unicode" in (font or "") for font in styles.values())


def test_garbled_text_is_not_written_as_fake_annotation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "skills" / "openclaw-pdf-to-cad" / "scripts" / "openclaw_pdf_to_cad.py"
    source_pdf = tmp_path / "garbled.pdf"
    output_dir = tmp_path / "outputs"
    _make_garbled_pdf(source_pdf)

    result = subprocess.run(
        ["python3", str(script), str(source_pdf), "--output-dir", str(output_dir), "--label", "garbled"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "needs_review"
    assert payload["garbled_text_count"] >= 2

    doc = ezdxf.readfile(payload["dxf_path"])
    texts = [entity.dxf.text for entity in doc.modelspace() if entity.dxftype() == "TEXT"]
    joined = "\n".join(texts)
    assert "????" not in joined
    assert "OCR_REQUIRED_TEXT" in joined
    layers = {entity.dxf.layer for entity in doc.modelspace() if entity.dxftype() == "TEXT"}
    assert "PDF_TEXT_UNCERTAIN" in layers


def test_openclaw_install_and_verify(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    install_script = root / "scripts" / "install_openclaw.sh"
    verify_script = root / "scripts" / "verify_openclaw_install.sh"
    skills_dir = tmp_path / "openclaw-skills"

    subprocess.run(
        [str(install_script), "--skills-dir", str(skills_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    result = subprocess.run(
        [str(verify_script), "--skills-dir", str(skills_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["target_runtime"] == "openclaw"

    installed_skill = skills_dir / "openclaw-pdf-to-cad"
    manifest = json.loads((installed_skill / "openclaw.skill.json").read_text())
    install_record = json.loads((installed_skill / "OPENCLAW_INSTALL.json").read_text())
    assert manifest["target_runtime"] == "openclaw"
    assert install_record["target_runtime"] == "openclaw"
    assert (installed_skill / "scripts" / "run_pdf_to_cad.sh").exists()
