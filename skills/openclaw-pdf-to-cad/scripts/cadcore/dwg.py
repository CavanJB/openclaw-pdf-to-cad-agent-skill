from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


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
