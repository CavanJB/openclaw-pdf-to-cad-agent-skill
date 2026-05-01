# OpenClaw Install / OpenClaw 安装说明

## 中文

这个仓库的主目标是 OpenClaw Agent Skill。`SKILL.md` 是可移植的 agent
skill 描述文件，不代表它只能给某一个运行器使用。OpenClaw 的安装入口、
manifest 和验证脚本是本仓库的主路径。

### 推荐安装方式

```bash
git clone https://github.com/CavanJB/openclaw-pdf-to-cad-agent-skill.git
cd openclaw-pdf-to-cad-agent-skill
./scripts/install_openclaw.sh
```

默认会安装到：

```text
~/.openclaw/workspace-cadbot/skills/openclaw-pdf-to-cad
```

如果你的 OpenClaw skills 目录不同：

```bash
./scripts/install_openclaw.sh --skills-dir /path/to/openclaw/skills
```

### 安装验证

安装后运行：

```bash
./scripts/verify_openclaw_install.sh
```

如果你的 OpenClaw skills 目录不同：

```bash
./scripts/verify_openclaw_install.sh --skills-dir /path/to/openclaw/skills
```

成功时会返回类似：

```json
{
  "ok": true,
  "skill": "openclaw-pdf-to-cad",
  "target_runtime": "openclaw"
}
```

安装后的 skill 目录里应该包含：

```text
SKILL.md
openclaw.skill.json
OPENCLAW_INSTALL.json
scripts/run_pdf_to_cad.sh
scripts/openclaw_pdf_to_cad.py
```

如果某个 agent 说“这个 skill 只能给 Codex 用”，请让它优先读取
`openclaw.skill.json` 和 `OPENCLAW_INSTALL.json`。这两个文件明确声明
`target_runtime` 是 `openclaw`。

### 用户测试 Prompt

```text
我已经安装好了 openclaw-pdf-to-cad-agent-skill。

请把我上传的 PDF 工程图转换成 CAD 交付包。

要求：
1. 输出可以用 CAD 打开的文件。
2. 同时提供 PDF 或 PNG 预览。
3. 提供质量报告，说明是否需要人工复核。
4. 不要猜测缺失尺寸，不要伪造标注。
5. 尽量保留中文标注；如果中文变成问号，请明确标记 needs_review。
6. 如果原图是扫描图或识别不充分，请明确标记 needs_review。
```

### 可选 OCR 增强

如果 PDF 显示中文正常，但提取出的文字变成 `??/????`，skill 会在检测到本机
`tesseract` 时尝试 OCR 兜底。未安装 OCR 时，相关文字会进入
`PDF_TEXT_UNCERTAIN` 图层并触发 `needs_review`，不会被冒充为正确标注。

macOS 可选安装方式：

```bash
brew install tesseract tesseract-lang
```

可通过环境变量指定 OCR 程序或语言：

```bash
export OPENCLAW_TESSERACT=/opt/homebrew/bin/tesseract
export OPENCLAW_OCR_LANGS=chi_sim+eng
```

## English

This repository is primarily an OpenClaw Agent Skill. `SKILL.md` is a portable
agent-skill descriptor, but the OpenClaw installer, manifest, and verifier are
the primary path for this repository.

### Recommended Installation

```bash
git clone https://github.com/CavanJB/openclaw-pdf-to-cad-agent-skill.git
cd openclaw-pdf-to-cad-agent-skill
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

### Verify Installation

After installing, run:

```bash
./scripts/verify_openclaw_install.sh
```

If your OpenClaw skills directory is different:

```bash
./scripts/verify_openclaw_install.sh --skills-dir /path/to/openclaw/skills
```

On success it returns JSON similar to:

```json
{
  "ok": true,
  "skill": "openclaw-pdf-to-cad",
  "target_runtime": "openclaw"
}
```

### Optional OCR Enhancement

If a PDF displays Chinese correctly but its extracted text becomes `??/????`,
the skill will try OCR fallback when `tesseract` is available. Without OCR, the
affected text is moved to the `PDF_TEXT_UNCERTAIN` layer and the package is
marked `needs_review` instead of pretending the annotation is correct.

Optional macOS setup:

```bash
brew install tesseract tesseract-lang
```

Optional environment variables:

```bash
export OPENCLAW_TESSERACT=/opt/homebrew/bin/tesseract
export OPENCLAW_OCR_LANGS=chi_sim+eng
```
