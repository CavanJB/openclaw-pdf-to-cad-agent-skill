# OpenClaw PDF to CAD Agent Skill

[中文](#中文说明) | [English](#english)

---

## 中文说明

`openclaw-pdf-to-cad-agent-skill` 是一个独立的 OpenClaw / Codex Agent Skill 框架，用于把 PDF 工程图转换成 CAD 交付包。

这个仓库是公开版基础框架，只包含 PDF/图片类图纸转换链路，不包含任何客户图纸、测试图纸、生成结果、日志、Windows 桥接配置、SolidWorks/STEP 三维转换代码或个人环境信息。

### 能力范围

- 识别 PDF 类型：矢量 PDF、扫描 PDF、混合 PDF、低置信度 PDF。
- 从矢量 PDF 中提取线条、矩形、曲线近似、文字和图像占位框。
- 输出分层 DXF，区分图纸几何、尺寸文字、标题栏文字、普通文字、页面边框和复核提示。
- 生成 PNG 预览、PDF 预览、质量报告和交付 README。
- 在配置了 DXF 转 DWG 工具时，自动补充 DWG；否则默认以 DXF 作为 CAD 交付文件。
- 对扫描图、混合图、无法确认的尺寸标记 `needs_review`，不冒充完全还原。

### 不承诺的能力

- 不处理 SolidWorks、STEP、IGES、STL、SLDPRT、SLDASM 或装配体。
- 不保证扫描图纸能自动重建为完全可制造 CAD 图。
- 不猜测缺失尺寸、不伪造标注、不把无法证明的内容写成正式值。

### 快速开始

```bash
git clone <your-repo-url>
cd openclaw-pdf-to-cad-agent-skill
./scripts/install.sh
source .venv/bin/activate
./skills/openclaw-pdf-to-cad/scripts/run_pdf_to_cad.sh /absolute/path/to/drawing.pdf --output-dir ./outputs
```

运行后会在 `outputs/` 下生成一个交付文件夹。

### 作为 OpenClaw Skill 安装

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/openclaw-pdf-to-cad" ~/.codex/skills/openclaw-pdf-to-cad
```

之后可以让 OpenClaw / Codex 在收到 PDF 工程图时调用 `openclaw-pdf-to-cad`。

### 交付文件

一次转换通常会生成：

- `*.dxf`：基础 CAD 输出。
- `*.dwg`：可选输出，仅当配置了 DXF 转 DWG 工具时生成。
- `preview.png`：图纸预览图。
- `preview.pdf`：预览 PDF。
- `quality_report.json`：机器可读质量报告。
- `README.md`：交付说明。
- `*.zip`：交付包压缩文件。

### 质量原则

- 矢量 PDF 优先提取真实几何和文字。
- 扫描 PDF 或混合 PDF 默认进入复核状态。
- 未配置 DWG 转换器时，不假装生成 DWG。
- 不能确认的尺寸和标注必须在报告里说明，不能猜。

### 开发测试

测试用例会在临时目录里生成一个合成 PDF，不会把任何真实图纸放进仓库。

```bash
source .venv/bin/activate
pytest -q
```

### 仓库结构

```text
skills/openclaw-pdf-to-cad/        # 可安装的 Agent Skill
skills/openclaw-pdf-to-cad/scripts # 转换脚本入口
docs/                              # 架构、发布和仓库结构说明
scripts/                           # 仓库级安装脚本
tests/                             # 不含真实图纸的自动化测试
```

后续如果继续开源新的图纸转换能力，建议按同样方式新增到 `skills/<skill-name>/`，不要把不同功能混在一个脚本目录里。

### 贡献边界

请不要提交真实客户图纸、测试图纸、生成结果、日志、密钥、本机路径或私有配置。更多说明见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [docs/REPOSITORY_STRUCTURE.md](docs/REPOSITORY_STRUCTURE.md)。

### 开源协议

本项目使用 MIT License。

---

## English

`openclaw-pdf-to-cad-agent-skill` is a standalone OpenClaw / Codex Agent Skill framework for converting engineering drawing PDFs into CAD-oriented delivery packages.

This public repository contains only the PDF/image drawing workflow. It does not include customer drawings, private test drawings, generated packages, logs, Windows bridge settings, SolidWorks/STEP 3D conversion code, or local machine-specific information.

### Features

- Classifies PDFs as vector, scanned, mixed, or low-confidence.
- Extracts vector lines, rectangles, approximated curves, text, and image placeholders from vector PDFs.
- Produces layered DXF files separating drawing geometry, dimension-like text, title-block-like text, ordinary text, page frames, and review notes.
- Generates PNG preview, PDF preview, quality report, and delivery README.
- Optionally generates DWG when a DXF-to-DWG converter is configured; otherwise DXF is the default CAD deliverable.
- Marks scanned, mixed, and uncertain outputs as `needs_review` instead of pretending the reconstruction is perfect.

### Out Of Scope

- No SolidWorks, STEP, IGES, STL, SLDPRT, SLDASM, or assembly conversion.
- No guarantee that raster-only scanned drawings can be automatically reconstructed into manufacturing-ready CAD.
- No guessing missing dimensions, fabricated annotations, or unverifiable values.

### Quick Start

```bash
git clone <your-repo-url>
cd openclaw-pdf-to-cad-agent-skill
./scripts/install.sh
source .venv/bin/activate
./skills/openclaw-pdf-to-cad/scripts/run_pdf_to_cad.sh /absolute/path/to/drawing.pdf --output-dir ./outputs
```

The command creates a delivery folder under `outputs/`.

### Install As An OpenClaw Skill

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/openclaw-pdf-to-cad" ~/.codex/skills/openclaw-pdf-to-cad
```

Then ask OpenClaw / Codex to use `openclaw-pdf-to-cad` when a PDF engineering drawing is provided.

### Delivery Output

A conversion usually creates:

- `*.dxf`: baseline CAD output.
- `*.dwg`: optional output, only when a DXF-to-DWG converter is configured.
- `preview.png`: visual preview image.
- `preview.pdf`: preview PDF.
- `quality_report.json`: machine-readable quality report.
- `README.md`: delivery notes.
- `*.zip`: zipped delivery package.

### Quality Rules

- Vector PDFs are converted using extracted geometry and text.
- Scanned or mixed PDFs are marked for review by default.
- If no DWG converter is configured, the tool does not pretend that DWG was generated.
- Unverifiable dimensions and annotations must be reported, not guessed.

### Development Checks

The smoke test creates a synthetic PDF in a temporary directory. No real drawings are stored in this repository.

```bash
source .venv/bin/activate
pytest -q
```

### Repository Layout

```text
skills/openclaw-pdf-to-cad/        # Installable Agent Skill
skills/openclaw-pdf-to-cad/scripts # Conversion entrypoints
docs/                              # Architecture, publishing, and structure docs
scripts/                           # Repository-level setup scripts
tests/                             # Automated tests without real drawings
```

If more drawing-conversion skills are open-sourced later, add them under `skills/<skill-name>/` and keep each skill isolated.

### Contribution Boundary

Do not commit real customer drawings, private test drawings, generated packages, logs, secrets, local paths, or private configuration. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/REPOSITORY_STRUCTURE.md](docs/REPOSITORY_STRUCTURE.md).

### License

This project is released under the MIT License.
