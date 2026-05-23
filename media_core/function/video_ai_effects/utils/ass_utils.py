"""
ass_utils.py — ASS字幕工具函数

提供ASS时间格式化、SRT时间解析、颜色转换、文本转义、语言字体解析等基础工具。
"""
import re
from typing import Optional


def format_ass_time(ms: int) -> str:
    """将毫秒时间戳格式化为ASS时间格式 H:MM:SS.CC"""
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    cs = (ms % 1000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def parse_srt_time(time_str: str) -> int:
    """解析SRT时间格式为毫秒时间戳"""
    time_str = time_str.strip()
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", time_str)
    if not match:
        return 0
    h, m, s, ms_str = match.groups()
    ms_str = ms_str.ljust(3, "0")[:3]
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms_str)


def rgb_to_ass_color(r: int, g: int, b: int, a: int = 0) -> str:
    """RGB颜色转ASS颜色格式（&HAABBGGRR）"""
    return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"


def ass_color_to_rgb(ass_color: str) -> tuple:
    """ASS颜色格式转RGB元组"""
    clean = ass_color.replace("&H", "").lstrip("0") or "0"
    val = int(clean, 16)
    r = val & 0xFF
    g = (val >> 8) & 0xFF
    b = (val >> 16) & 0xFF
    a = (val >> 24) & 0xFF
    return (r, g, b, a)


def escape_ass_text(text: str) -> str:
    """转义ASS文本中的特殊字符（反斜杠、花括号、换行）"""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("\n", "\\N")
    return text


def resolve_font_for_language(language: str, default_font: str = "SourceHanSansSC-Bold") -> str:
    """根据语言代码解析最佳字体

    查找顺序：精确匹配 → 基础语言匹配 → 前缀匹配 → 默认字体
    """
    from ..ass_styles.base import LANGUAGE_FONT_MAP
    lang_lower = language.lower()
    if lang_lower in LANGUAGE_FONT_MAP:
        return LANGUAGE_FONT_MAP[lang_lower]
    base_lang = lang_lower.split("-")[0]
    if base_lang in LANGUAGE_FONT_MAP:
        return LANGUAGE_FONT_MAP[base_lang]
    for key, font in LANGUAGE_FONT_MAP.items():
        if key.startswith(base_lang):
            return font
    return default_font
