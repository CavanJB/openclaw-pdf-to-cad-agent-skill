# Contributing / 贡献指南

## 中文

感谢你改进这个 OpenClaw PDF-to-CAD Agent Skill。这个仓库的目标是提供可公开复用的框架，而不是保存任何真实图纸数据。

### 可以提交

- Skill 指令、脚本和测试改进。
- 使用临时合成 PDF 的测试。
- 不含客户信息的文档、示例命令和架构说明。
- 通用 CAD 图层、质量报告、交付包规则。

### 不要提交

- 真实客户图纸、供应商图纸或私人测试图纸。
- 生成的 DXF、DWG、PDF、PNG、ZIP、日志或交付包。
- API key、SSH key、token、账号密码。
- 本机绝对路径、局域网地址、私有桥接配置。
- 无法证明来源或授权的第三方文件。

### 提交前检查

```bash
pytest -q
find . -type f \( -iname '*.pdf' -o -iname '*.dxf' -o -iname '*.dwg' -o -iname '*.zip' -o -iname '*.log' \) -print
rg -n "/Users/|ssh-|PRIVATE|API_KEY|TOKEN|PASSWORD" . || true
```

## English

Thank you for improving this OpenClaw PDF-to-CAD Agent Skill. The repository is meant to provide a reusable public framework, not a storage place for real drawing data.

### Good Contributions

- Skill instructions, scripts, and test improvements.
- Tests that generate synthetic PDFs at runtime.
- Documentation, example commands, and architecture notes without customer data.
- Generic CAD layering, quality-report, and delivery-package rules.

### Do Not Commit

- Real customer drawings, supplier drawings, or private test drawings.
- Generated DXF, DWG, PDF, PNG, ZIP, logs, or delivery packages.
- API keys, SSH keys, tokens, passwords.
- Local absolute paths, LAN addresses, or private bridge settings.
- Third-party files without a clear license or redistribution right.

### Pre-Commit Checks

```bash
pytest -q
find . -type f \( -iname '*.pdf' -o -iname '*.dxf' -o -iname '*.dwg' -o -iname '*.zip' -o -iname '*.log' \) -print
rg -n "/Users/|ssh-|PRIVATE|API_KEY|TOKEN|PASSWORD" . || true
```
