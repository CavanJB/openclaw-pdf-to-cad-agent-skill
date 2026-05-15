from __future__ import annotations

import re

PAGE_GAP = 80.0
PREVIEW_WIDTH = 2400
PREVIEW_HEIGHT = 1600
PREVIEW_MARGIN = 80
DXF_INSUNITS_MM = 4

LAYER_SPECS = {
    "PDF_GEOMETRY": 7,
    "PDF_DIMENSIONS": 3,
    "PDF_TITLE_BLOCK": 5,
    "PDF_TEXT": 2,
    "PDF_TEXT_UNCERTAIN": 1,
    "PDF_IMAGE_PLACEHOLDER": 6,
    "PDF_PAGE_FRAME": 8,
    "REVIEW_NOTES": 1,
}

TITLE_KEYWORDS = (
    "图号",
    "图名",
    "名称",
    "材料",
    "比例",
    "审核",
    "设计",
    "技术要求",
    "title",
    "drawing",
    "part",
    "material",
    "scale",
    "revision",
)

DIMENSION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:R|M|Phi|DIA|Dia|THK|T=|Φ|Ø|⌀)?\s*\d+(?:\.\d+)?(?:\s*[xX*×]\s*\d+(?:\.\d+)?)*"
)
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
GARBLED_RE = re.compile(r"(?:\?{2,}|�|□)")
DEFAULT_CJK_FONT = "Arial Unicode.ttf"
TEXT_STYLE_FONTS = {
    "OPENCLAW_CJK": DEFAULT_CJK_FONT,
    "OPENCLAW_CJK_HEI": "STHeiti Medium.ttc",
    "OPENCLAW_CJK_SONG": DEFAULT_CJK_FONT,
    "OPENCLAW_LATIN": DEFAULT_CJK_FONT,
}
