# Publishing / 发布说明

## 中文

推荐仓库名：`openclaw-pdf-to-cad-agent-skill`

发布前检查：

```bash
find . -type f \( -iname '*.pdf' -o -iname '*.dxf' -o -iname '*.dwg' -o -iname '*.step' -o -iname '*.sldprt' -o -iname '*.sldasm' -o -iname '*.log' -o -iname '*.zip' \) -print
rg -n "/Users/|ssh-|PRIVATE|API_KEY|TOKEN|PASSWORD" . || true
pytest -q
```

这个仓库只发布 PDF-to-CAD skill 框架，不发布真实图纸样本。

## English

Recommended repository name: `openclaw-pdf-to-cad-agent-skill`

Pre-publish checks:

```bash
find . -type f \( -iname '*.pdf' -o -iname '*.dxf' -o -iname '*.dwg' -o -iname '*.step' -o -iname '*.sldprt' -o -iname '*.sldasm' -o -iname '*.log' -o -iname '*.zip' \) -print
rg -n "/Users/|ssh-|PRIVATE|API_KEY|TOKEN|PASSWORD" . || true
pytest -q
```

Publish only the PDF-to-CAD skill framework. Do not publish real drawing samples.
