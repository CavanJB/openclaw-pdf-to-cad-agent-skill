# Repository Structure / 仓库结构

## 中文

这个仓库按“可复用 Agent Skill”来组织，方便后续继续上传其他开源能力。

```text
.
├── skills/
│   └── openclaw-pdf-to-cad/
│       ├── SKILL.md
│       ├── openclaw.skill.json
│       ├── agents/
│       │   └── openai.yaml
│       └── scripts/
│           ├── openclaw_pdf_to_cad.py
│           └── run_pdf_to_cad.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PUBLISHING.md
│   └── REPOSITORY_STRUCTURE.md
├── scripts/
│   └── install.sh
│   ├── install_openclaw.sh
│   └── verify_openclaw_install.sh
├── tests/
│   └── test_smoke.py
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── requirements.txt
```

### 分类规则

- `skills/`：每一个可安装 agent skill 单独占一个子目录。
- `skills/<skill-name>/SKILL.md`：该 skill 的触发说明、边界和使用流程。
- `skills/<skill-name>/openclaw.skill.json`：OpenClaw 优先读取的运行器、输入输出和质量策略 manifest。
- `skills/<skill-name>/scripts/`：该 skill 专属脚本。
- `docs/`：仓库级架构、发布、边界、扩展说明。
- `scripts/`：仓库级安装或维护脚本，不放客户转换脚本。
- `tests/`：只放可公开测试；测试样本必须运行时生成，不能提交真实图纸。

### 后续扩展建议

如果以后继续开源其他能力，例如 `image-to-cad`、`cad-delivery-packager`、`drawing-quality-checker`，建议新增为：

```text
skills/image-to-cad/
skills/cad-delivery-packager/
skills/drawing-quality-checker/
```

不要把多个 skill 的核心逻辑塞进同一个脚本，否则后续维护和安装都会变乱。

## English

This repository is organized as a reusable Agent Skill package so future open-source capabilities can be added cleanly.

```text
.
├── skills/
│   └── openclaw-pdf-to-cad/
│       ├── SKILL.md
│       ├── openclaw.skill.json
│       ├── agents/
│       │   └── openai.yaml
│       └── scripts/
│           ├── openclaw_pdf_to_cad.py
│           └── run_pdf_to_cad.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PUBLISHING.md
│   └── REPOSITORY_STRUCTURE.md
├── scripts/
│   ├── install.sh
│   ├── install_openclaw.sh
│   └── verify_openclaw_install.sh
├── tests/
│   └── test_smoke.py
├── README.md
├── CONTRIBUTING.md
├── LICENSE
└── requirements.txt
```

### Organization Rules

- `skills/`: one installable agent skill per subdirectory.
- `skills/<skill-name>/SKILL.md`: trigger rules, boundaries, and workflow.
- `skills/<skill-name>/openclaw.skill.json`: OpenClaw-first runtime, input/output, and quality-policy manifest.
- `skills/<skill-name>/scripts/`: scripts owned by that skill.
- `docs/`: repository-level architecture, publishing, boundary, and extension notes.
- `scripts/`: repository-level setup or maintenance scripts.
- `tests/`: public tests only; test drawings must be generated at runtime.

### Future Expansion

If more capabilities are open-sourced later, such as `image-to-cad`, `cad-delivery-packager`, or `drawing-quality-checker`, add them as separate skill folders:

```text
skills/image-to-cad/
skills/cad-delivery-packager/
skills/drawing-quality-checker/
```

Avoid mixing multiple skills into one script directory. Isolation keeps installation, testing, and maintenance predictable.
