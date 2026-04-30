# Architecture

## Scope

This repository is a standalone PDF-to-CAD agent skill framework. It is deliberately separated from any 3D/SolidWorks workflow.

## Flow

```mermaid
flowchart LR
  A[Input PDF] --> B[Preflight classification]
  B --> C[Vector and text extraction]
  C --> D[Layered DXF writer]
  D --> E[Preview renderer]
  D --> F[Optional DWG converter]
  E --> G[Delivery package]
  F --> G
  G --> H[Quality report and README]
```

## Agent Boundary

The agent should:

- Accept only PDF input for this skill.
- Reject or route 3D formats to a different skill.
- Never invent missing dimensions.
- Return the delivery package path and quality status.
- Prefer DXF as the baseline CAD output, with DWG only when a converter is configured.

## Privacy Boundary

The public repository must not contain:

- Customer or private drawings.
- Generated delivery packages.
- Logs from real jobs.
- SSH keys, API keys, private chat messages, bridge settings, or machine-specific paths.
