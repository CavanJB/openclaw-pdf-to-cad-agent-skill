from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ezdxf
import fitz


def _make_benchmark_pdf(path: Path) -> None:
    """Synthetic engineering drawing with known ground-truth geometry and text."""
    font_file = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    doc = fitz.open()
    page = doc.new_page(width=420, height=297)

    for i in range(20):
        page.draw_line(fitz.Point(40 + i * 8, 70), fitz.Point(43 + i * 8, 75), color=(0, 0, 0), width=0.5)
    for i in range(10):
        page.draw_line(fitz.Point(40, 90 + i * 12), fitz.Point(45, 90 + i * 12), color=(0, 0, 0), width=0.5)
    for i in range(10):
        page.draw_line(fitz.Point(260, 90 + i * 12), fitz.Point(265, 90 + i * 12), color=(0, 0, 0), width=0.5)

    page.draw_rect(fitz.Rect(40, 70, 260, 160), color=(0, 0, 0), width=0.8)
    page.draw_line(fitz.Point(40, 230), fitz.Point(300, 230), color=(0, 0, 0), width=0.8)

    page.insert_text(fitz.Point(55, 42), "TITLE: BENCHMARK PART", fontsize=10, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(55, 260), "MATERIAL: STEEL", fontsize=10, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(180, 42), "SCALE: 1:2", fontsize=10, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(55, 54), "DIM: R10", fontsize=9, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(55, 270), "DIM: M8-6H", fontsize=9, fontname="helv", color=(0, 0, 0))

    doc.save(path)
    doc.close()


def _benchmark_ground_truth() -> dict:
    return {
        "expected_status": {"ok", "needs_review"},
        "expected_source_type": "vector",
        "expected_layers": {
            "PDF_GEOMETRY",
            "PDF_TITLE_BLOCK",
            "PDF_DIMENSIONS",
            "PDF_PAGE_FRAME",
            "PDF_TEXT",
        },
        "expected_text_patterns": [
            "TITLE: BENCHMARK PART",
            "MATERIAL: STEEL",
            "SCALE: 1:2",
            "DIM: R10",
            "DIM: M8-6H",
        ],
        "expected_min_entities": 5,
        "expected_min_text_entities": 5,
        "expected_dimension_min": 2,
        "expected_title_min": 3,
    }


def _evaluate_precision(report: dict, dxf_path: str, ground_truth: dict) -> dict:
    scores: dict[str, float] = {}

    doc = ezdxf.readfile(dxf_path)
    actual_layers = {layer.dxf.name for layer in doc.layers}
    expected_layers = ground_truth["expected_layers"]
    intersection = actual_layers & expected_layers
    scores["layer_recall"] = len(intersection) / len(expected_layers) if expected_layers else 1.0

    texts = [entity.dxf.text for entity in doc.modelspace() if entity.dxftype() == "TEXT"]
    joined = "\n".join(texts)
    found = sum(1 for pattern in ground_truth["expected_text_patterns"] if pattern in joined)
    scores["text_recall"] = found / len(ground_truth["expected_text_patterns"]) if ground_truth["expected_text_patterns"] else 1.0

    entity_count = report.get("entity_count", 0)
    scores["entity_ratio"] = min(1.0, entity_count / ground_truth["expected_min_entities"]) if ground_truth["expected_min_entities"] else 1.0

    text_count = report.get("text_count", 0)
    scores["text_ratio"] = min(1.0, text_count / ground_truth["expected_min_text_entities"]) if ground_truth["expected_min_text_entities"] else 1.0

    dimension_count = report.get("dimension_text_count", 0)
    scores["dimension_ratio"] = min(1.0, dimension_count / ground_truth["expected_dimension_min"]) if ground_truth["expected_dimension_min"] else 1.0

    title_count = report.get("title_text_count", 0)
    scores["title_ratio"] = min(1.0, title_count / ground_truth["expected_title_min"]) if ground_truth["expected_title_min"] else 1.0

    if report.get("garbled_text_count", 0) == 0:
        scores["garbled_penalty"] = 0.0
    else:
        scores["garbled_penalty"] = 1.0

    overall = sum(v for k, v in scores.items() if k != "garbled_penalty") / max(1, len(scores) - 1)
    return {"scores": scores, "overall": round(overall, 4)}


def test_benchmark_precision(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "skills" / "openclaw-pdf-to-cad" / "scripts" / "openclaw_pdf_to_cad.py"
    source_pdf = tmp_path / "benchmark.pdf"
    output_dir = tmp_path / "outputs"

    _make_benchmark_pdf(source_pdf)
    ground_truth = _benchmark_ground_truth()

    venv_python = root / ".venv" / "bin" / "python"
    python_bin = str(venv_python) if venv_python.exists() else "python3"

    result = subprocess.run(
        [python_bin, str(script), str(source_pdf), "--output-dir", str(output_dir), "--label", "benchmark"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    report = json.loads(result.stdout)
    evaluation = _evaluate_precision(report, report["dxf_path"], ground_truth)

    assert evaluation["overall"] >= 0.6, f"Overall benchmark score {evaluation['overall']} below 0.6, report: source_type={report.get('source_type')}, entity_count={report.get('entity_count')}, text_count={report.get('text_count')}"
    assert evaluation["scores"]["text_recall"] >= 0.8, f"Text recall {evaluation['scores']['text_recall']} below 0.8"
    assert evaluation["scores"]["garbled_penalty"] == 0.0, "Unexpected garbled text detected"

    results_file = tmp_path / "benchmark_results.json"
    results_file.write_text(json.dumps(evaluation, indent=2, ensure_ascii=False))
