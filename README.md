# OpenClaw PDF to CAD Agent Skill

[中文](#中文说明) | [English](#english)

---

## 中文说明

`openclaw-pdf-to-cad-agent-skill` 是一个独立的 OpenClaw Agent Skill 框架，用于把 PDF 工程图转换成 CAD 交付包。OpenClaw 是本仓库的主适配对象；`SKILL.md` 只是可移植的 agent skill 描述文件，方便不同本地 agent 读取和执行。

这个仓库是公开版基础框架，只包含 PDF/图片类图纸转换链路，不包含任何客户图纸、测试图纸、生成结果、日志、Windows 桥接配置、SolidWorks/STEP 三维转换代码或个人环境信息。

### 能力范围

- 识别 PDF 类型：矢量 PDF、扫描 PDF、混合 PDF、低置信度 PDF。
- 从矢量 PDF 中提取线条、矩形、曲线近似、文字和图像占位框。
- 输出分层 DXF，区分图纸几何、尺寸文字、标题栏文字、普通文字、页面边框和复核提示。
- 高保真还原 PDF 文字位置：优先使用原 PDF 的文字基线、字号、旋转方向和宽度比例，减少文字飘位。
- 尽量保留中文/CJK 标注；当 PDF 提取结果已经变成 `??/????` 时，会尝试 OCR 兜底，失败则标记为待复核而不是冒充正确文字。
- 对扫描图或图片化文字，在检测到 Tesseract OCR 时会按行识别并尽量放回原始位置。
- 生成 PNG 预览、PDF 预览、质量报告和交付 README。
- 在配置了 DXF 转 DWG 工具时，自动补充 DWG；含中文/CJK 或 OCR 风险时，DXF 仍会作为推荐 CAD 文件，直到 DWG 被人工打开验证。
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
./scripts/install_openclaw.sh
```

默认安装到：

```text
~/.openclaw/workspace-cadbot/skills/openclaw-pdf-to-cad
```

如果你的 OpenClaw skills 目录不同：

```bash
./scripts/install_openclaw.sh --skills-dir /path/to/openclaw/skills
```

更详细说明见 [docs/OPENCLAW_INSTALL.md](docs/OPENCLAW_INSTALL.md)。

安装后可以验证：

```bash
./scripts/verify_openclaw_install.sh
```

如果某个 agent 误判它“只给 Codex 使用”，请让它读取已安装目录内的：

```text
openclaw.skill.json
OPENCLAW_INSTALL.json
```

这两个文件会明确标记 `target_runtime` 为 `openclaw`。

### 其他本地 Agent 兼容安装（可选）

如果你希望其他支持 `SKILL.md` 的本地 agent 也能直接调用这个 skill，可以额外建立软链接：

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/openclaw-pdf-to-cad" ~/.codex/skills/openclaw-pdf-to-cad
```

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
- 中文/CJK 标注必须保留为 Unicode；如果提取到的是问号或替换字符，输出进入 `needs_review`。
- 文字位置必须优先使用 PDF 原生 baseline/origin，而不是简单使用 bbox 左下角。
- OCR 文字只能作为兜底恢复，必须在报告中体现，不能冒充原生矢量文字。
- 含中文/CJK 的 DWG 若无法自动验证字体保真，不会被冒充为首选交付文件。
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

`openclaw-pdf-to-cad-agent-skill` is a standalone OpenClaw Agent Skill framework for converting engineering drawing PDFs into CAD-oriented delivery packages. OpenClaw is the primary target; `SKILL.md` is a portable agent-skill descriptor that allows compatible local agents to read and run the skill.

This public repository contains only the PDF/image drawing workflow. It does not include customer drawings, private test drawings, generated packages, logs, Windows bridge settings, SolidWorks/STEP 3D conversion code, or local machine-specific information.

### Features

- Classifies PDFs as vector, scanned, mixed, or low-confidence.
- Extracts vector lines, rectangles, approximated curves, text, and image placeholders from vector PDFs.
- Produces layered DXF files separating drawing geometry, dimension-like text, title-block-like text, ordinary text, page frames, and review notes.
- Preserves PDF text placement with baseline/origin, font size, rotation, and width-factor fitting where possible.
- Preserves Chinese/CJK annotations as Unicode whenever possible; if extracted PDF text is already `??/????`, it tries OCR fallback and otherwise marks the item for review instead of pretending it is correct.
- Uses line-level OCR fallback for scanned or image-based text when Tesseract is available, placing recovered text near its source location.
- Generates PNG preview, PDF preview, quality report, and delivery README.
- Optionally generates DWG when a DXF-to-DWG converter is configured; for Chinese/CJK or OCR-risk drawings, DXF remains the recommended CAD file until the DWG is manually verified.
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
./scripts/install_openclaw.sh
```

Default install target:

```text
~/.openclaw/workspace-cadbot/skills/openclaw-pdf-to-cad
```

If your OpenClaw skills directory is different:

```bash
./scripts/install_openclaw.sh --skills-dir /path/to/openclaw/skills
```

See [docs/OPENCLAW_INSTALL.md](docs/OPENCLAW_INSTALL.md) for details.

Verify the installation:

```bash
./scripts/verify_openclaw_install.sh
```

If an agent mistakenly says this skill is only for Codex, ask it to read these files in the installed skill directory:

```text
openclaw.skill.json
OPENCLAW_INSTALL.json
```

They explicitly mark `target_runtime` as `openclaw`.

### Other Local Agent Compatibility (Optional)

If you also want another local agent runtime that understands `SKILL.md` to call this skill directly, create a symlink:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/openclaw-pdf-to-cad" ~/.codex/skills/openclaw-pdf-to-cad
```

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
