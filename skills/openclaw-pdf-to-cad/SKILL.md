---
name: openclaw-pdf-to-cad
description: OpenClaw Agent Skill for converting engineering drawing PDFs into CAD-oriented delivery packages. Use this skill when an OpenClaw user provides a PDF engineering drawing and wants DXF/CAD output, preview files, a delivery package, and a quality report. Do not use it for STEP, IGES, STL, SLDPRT, SLDASM, SolidWorks, or other 3D model conversion tasks.
---

# OpenClaw PDF to CAD

This is an OpenClaw Agent Skill. It is not a subagent and not a 3D/SolidWorks
converter. It is a callable local skill that OpenClaw/Jarvis can invoke when a
PDF engineering drawing is provided.

## Scope

Use this skill for PDF engineering drawing conversion only.

- Supported input: `.pdf`
- Baseline output: layered `.dxf`, `.png` preview, `.pdf` preview, `quality_report.json`, delivery README, zip package
- Optional output: `.dwg` when a DXF-to-DWG converter is configured
- Unsupported here: STEP, IGES, STL, SLDPRT, SLDASM, SolidWorks, assemblies, 3D-to-2D drawing generation

## Required Behavior

1. Treat OpenClaw as the primary runtime for this skill.
2. Verify that the source file is a PDF before running the script.
3. Run the bundled script from this skill folder.
4. Return the delivery folder, zip path, recommended CAD file, preview PDF, and quality status.
5. If the report says `needs_review`, explain why instead of claiming a perfect conversion.
6. Never invent dimensions or annotations that were not present or confidently extracted from the PDF.
7. Never send a raw DXF alone when the delivery folder exists.

## Command

```bash
./scripts/run_pdf_to_cad.sh /absolute/path/to/drawing.pdf --output-dir /absolute/path/to/outputs
```

Optional fields:

```bash
./scripts/run_pdf_to_cad.sh /absolute/path/to/drawing.pdf \
  --output-dir /absolute/path/to/outputs \
  --customer-name "Customer" \
  --project-name "Project" \
  --label "delivery-name"
```

## Output Interpretation

The script prints JSON. Use these fields in the agent response:

- `status`: `ok`, `needs_review`, or `error`
- `delivery_dir`: folder containing all deliverables
- `zip_path`: zipped delivery package
- `recommended_cad_file`: prefer DWG if present, otherwise DXF
- `preview_pdf`: human-readable preview
- `quality_report`: detailed machine-readable report
- `findings`: limitations and review notes

## Handoff Message Template

```text
PDF-to-CAD conversion finished.
Recommended CAD file: <recommended_cad_file>
Preview PDF: <preview_pdf>
Quality status: <status>
Review notes: <findings or none>
```

If status is `needs_review`, say the output is a CAD candidate requiring manual review, not a final production drawing.
