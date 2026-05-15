from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONFIG_YAML = "openclaw-pdf-to-cad.yaml"

_CONFIG_CACHE: dict | None = None


def _default_config() -> dict:
    return {
        "preview": {
            "width": 2400,
            "height": 1600,
            "margin": 80,
        },
        "dxf": {
            "page_gap": 80.0,
            "code_page": "ANSI_936",
            "insunits": 4,
        },
        "ocr": {
            "langs": "chi_sim+eng",
            "dpi": 300,
            "confidence_threshold": 35,
            "timeout": 45,
            "page_scale": 4.0,
        },
        "fonts": {
            "cjk_font_dir": None,
            "cjk_font": None,
        },
        "dwg": {
            "converter": None,
        },
        "text": {
            "min_size": 1.5,
            "max_size": 24.0,
            "garbled_threshold": 0.2,
            "width_factor_min": 0.2,
            "width_factor_max": 5.0,
        },
    }


def _merge_configs(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _merge_configs(base[key], value)
        else:
            base[key] = value
    return base


def _find_config_file() -> Path | None:
    candidates = [
        Path.cwd() / DEFAULT_CONFIG_YAML,
        Path(__file__).resolve().parents[3] / DEFAULT_CONFIG_YAML,
        Path.home() / ".config" / "openclaw" / DEFAULT_CONFIG_YAML,
    ]
    configured = os.getenv("OPENCLAW_CONFIG", "").strip()
    if configured:
        candidates.insert(0, Path(configured))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_config() -> dict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    config = _default_config()
    config_path = _find_config_file()
    if config_path:
        try:
            import yaml
            with open(config_path, encoding="utf-8") as fh:
                user_config = yaml.safe_load(fh) or {}
            config = _merge_configs(config, user_config)
        except Exception:
            pass

    if os.getenv("OPENCLAW_OCR_LANGS"):
        config["ocr"]["langs"] = os.getenv("OPENCLAW_OCR_LANGS").strip()
    if os.getenv("OPENCLAW_DWG_CONVERTER"):
        config["dwg"]["converter"] = os.getenv("OPENCLAW_DWG_CONVERTER").strip()
    if os.getenv("OPENCLAW_CJK_FONT"):
        config["fonts"]["cjk_font"] = os.getenv("OPENCLAW_CJK_FONT").strip()
    if os.getenv("OPENCLAW_CJK_FONT_DIR"):
        config["fonts"]["cjk_font_dir"] = os.getenv("OPENCLAW_CJK_FONT_DIR").strip()

    _CONFIG_CACHE = config
    return config


def get_config_value(*keys: str, default=None):
    config = load_config()
    node = config
    for key in keys:
        if isinstance(node, dict):
            node = node.get(key)
        else:
            return default
    return node if node is not None else default
