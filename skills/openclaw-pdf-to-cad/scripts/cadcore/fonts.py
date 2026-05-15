from __future__ import annotations

import os
import platform
from functools import lru_cache
from pathlib import Path

from cadcore.constants import DEFAULT_CJK_FONT, TEXT_STYLE_FONTS

_CJK_CANDIDATES_MAC = (
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
)

_CJK_CANDIDATES_LINUX = (
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-VF.otf",
    "/usr/local/share/fonts/noto/NotoSansCJK-Regular.ttc",
)

_CJK_CANDIDATES_WIN = (
    "C:/Windows/Fonts/ArialUni.ttf",
    "C:/Windows/Fonts/ARIALUNI.TTF",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/MSYH.TTC",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/SIMSUN.TTC",
)

_CJK_FONT_CACHE: dict[str, str | None] = {}


def _system_cjk_candidates() -> list[str]:
    system = platform.system()
    if system == "Darwin":
        return list(_CJK_CANDIDATES_MAC)
    elif system == "Windows":
        return list(_CJK_CANDIDATES_WIN)
    else:
        return list(_CJK_CANDIDATES_LINUX)


def _user_font_dirs() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [home / "Library" / "Fonts"]
    elif system == "Windows":
        return []
    else:
        return [home / ".fonts", home / ".local" / "share" / "fonts"]


def cjk_preview_font_path() -> str | None:
    cache_key = "__cjk_preview__"
    if cache_key in _CJK_FONT_CACHE:
        return _CJK_FONT_CACHE[cache_key]

    configured = os.getenv("OPENCLAW_CJK_FONT", "").strip()
    if configured and Path(configured).exists():
        _CJK_FONT_CACHE[cache_key] = configured
        return configured

    font_dir = os.getenv("OPENCLAW_CJK_FONT_DIR", "").strip()
    if font_dir:
        base = Path(font_dir)
        if base.is_dir():
            for font_file in base.iterdir():
                if font_file.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                    _CJK_FONT_CACHE[cache_key] = str(font_file)
                    return str(font_file)

    for candidate in _system_cjk_candidates():
        if Path(candidate).exists():
            _CJK_FONT_CACHE[cache_key] = candidate
            return candidate

    for user_dir in _user_font_dirs():
        if user_dir.is_dir():
            for pattern in ("*Arial*Unicode*", "*WenQuanYi*", "*Noto*CJK*", "*msyh*", "*simsun*", "*simhei*"):
                matches = sorted(user_dir.glob(pattern))
                for match in matches:
                    if match.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                        _CJK_FONT_CACHE[cache_key] = str(match)
                        return str(match)

    _CJK_FONT_CACHE[cache_key] = None
    return None


def font_path_for_style(style_name: str) -> str | None:
    cache_key = f"__style_{style_name}__"
    if cache_key in _CJK_FONT_CACHE:
        return _CJK_FONT_CACHE[cache_key]

    font_file = TEXT_STYLE_FONTS.get(style_name) or DEFAULT_CJK_FONT
    direct = Path(font_file)
    if direct.exists():
        _CJK_FONT_CACHE[cache_key] = str(direct)
        return str(direct)

    resolved = _resolve_font_file(font_file)
    if resolved:
        _CJK_FONT_CACHE[cache_key] = resolved
        return resolved

    fallback = cjk_preview_font_path()
    _CJK_FONT_CACHE[cache_key] = fallback
    return fallback


def _resolve_font_file(font_file: str) -> str | None:
    search_dirs = _system_cjk_candidates()
    for candidate in search_dirs:
        parent = Path(candidate).parent
        candidate_path = parent / font_file
        if candidate_path.exists():
            return str(candidate_path)
    for user_dir in _user_font_dirs():
        candidate_path = user_dir / font_file
        if candidate_path.exists():
            return str(candidate_path)
    return None


@lru_cache(maxsize=128)
def load_measure_font(style_name: str, pixel_size: int):
    font_path = font_path_for_style(style_name)
    if not font_path:
        return None
    try:
        from PIL import ImageFont
        return ImageFont.truetype(font_path, size=max(1, pixel_size))
    except Exception:
        return None


def measure_text_width(text: str, style_name: str, height: float) -> float:
    pixel_scale = 16
    font = load_measure_font(style_name, max(1, int(round(height * pixel_scale))))
    if not font:
        return 0.0
    try:
        return float(font.getlength(text)) / pixel_scale
    except Exception:
        try:
            bbox = font.getbbox(text)
            return float(bbox[2] - bbox[0]) / pixel_scale
        except Exception:
            return 0.0


def text_width_factor(candidate, text: str, style_name: str) -> float:
    target_width = max(0.0, candidate.bbox.width)
    measured_width = measure_text_width(text, style_name, candidate.size)
    if target_width <= 0.0 or measured_width <= 0.0:
        return 1.0
    factor = target_width / measured_width
    if factor < 0.2 or factor > 5.0:
        return 1.0
    return round(factor, 4)
