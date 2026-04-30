# OpenClaw Install / OpenClaw 安装说明

## 中文

这个仓库的主目标是 OpenClaw Agent Skill。它同时采用 Codex 兼容的
`SKILL.md` 格式，是为了让本地 agent 能直接读取和执行，不代表它只能给
Codex 使用。

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

### 用户测试 Prompt

```text
我已经安装好了 openclaw-pdf-to-cad-agent-skill。

请把我上传的 PDF 工程图转换成 CAD 交付包。

要求：
1. 输出可以用 CAD 打开的文件。
2. 同时提供 PDF 或 PNG 预览。
3. 提供质量报告，说明是否需要人工复核。
4. 不要猜测缺失尺寸，不要伪造标注。
5. 如果原图是扫描图或识别不充分，请明确标记 needs_review。
```

## English

This repository is primarily an OpenClaw Agent Skill. It also uses a
Codex-compatible `SKILL.md` format so local agents can read and run it directly;
that does not mean it is limited to Codex.

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
