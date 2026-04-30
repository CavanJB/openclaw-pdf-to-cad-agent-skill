from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ezdxf
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
