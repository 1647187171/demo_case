"""
base.py — ASS字幕基础常量配置

定义语言-字体映射、平台边距、CJK字体映射等全局常量，
供样式模块和ASS引擎共用。
"""
from ..models import ASSStyleConfig, ASSAnimationType

# 默认ASS播放分辨率
DEFAULT_PLAY_RES_X = 1080
DEFAULT_PLAY_RES_Y = 1920

# 语言 → 字体映射（用于根据字幕语言自动选择合适的字体）
LANGUAGE_FONT_MAP = {
    "zh-cn": "SourceHanSansSC-Bold",
    "zh-tw": "NotoSansCJKtc-Bold",
    "zh_sc": "SourceHanSansSC-Bold",
    "yue": "SourceHanSansSC-Bold",
    "ja": "NotoSansJP-Bold",
    "ja-jp": "NotoSansJP-Bold",
    "ko": "NotoSansKR-Bold",
    "ko-kr": "NotoSansKR-Bold",
    "en": "NotoSans-Bold",
    "en-us": "NotoSans-Bold",
    "en-gb": "NotoSans-Bold",
    "fr": "NotoSans-Bold",
    "de": "NotoSans-Bold",
    "es": "NotoSans-Bold",
    "it": "NotoSans-Bold",
    "pt": "NotoSans-Bold",
    "ru": "NotoSans-Bold",
    "ar": "NotoSansArabic-Bold",
    "fa": "NotoSansArabic-Bold",
    "ur": "NotoSansArabic-Bold",
    "th": "NotoSansThai-Bold",
    "th-th": "NotoSansThai-Bold",
    "hi": "Hind-Bold",
    "vi": "NotoSans-Bold",
    "id": "NotoSans-Bold",
    "ms": "NotoSans-Bold",
    "tl": "NotoSans-Bold",
    "km": "NotoSansKhmer-Bold",
    "lo": "NotoSansLao-Bold",
    "my": "NotoSansMyanmar-Bold",
    "he": "Heebo-Bold",
    "default": "SourceHanSansSC-Bold",
}

# 平台安全底部边距（ASS PlayResY=288 坐标空间）
# TikTok / Instagram Reels 的UI覆盖底部约25-30%
PLATFORM_MARGIN_V = {
    "tiktok": 90,
    "instagram": 85,
    "youtube": 75,
    "generic": 80,
}

# 9:16竖版视频的底部边距（1080x1920 PlayRes）
PLATFORM_MARGIN_V_FULLRES = {
    "tiktok": 180,
    "instagram": 170,
    "youtube": 150,
    "generic": 160,
}

# 中日韩语言字体映射（常用子集）
CJK_FONT_MAP = {
    "zh-CN": "SourceHanSansSC-Bold",
    "zh-TW": "NotoSansCJKtc-Bold",
    "ja": "NotoSansJP-Bold",
    "ko": "NotoSansKR-Bold",
    "en": "NotoSans-Bold",
    "default": "SourceHanSansSC-Bold",
}

# 完整语言字体映射
FULL_FONT_MAP = {
    "zh-CN": "SourceHanSansSC-Bold",
    "zh-TW": "NotoSansCJKtc-Bold",
    "yue": "SourceHanSansSC-Bold",
    "ja": "NotoSansJP-Bold",
    "ko": "NotoSansKR-Bold",
    "en": "NotoSans-Bold",
    "fr": "NotoSans-Bold",
    "de": "NotoSans-Bold",
    "es": "NotoSans-Bold",
    "it": "NotoSans-Bold",
    "pt": "NotoSans-Bold",
    "ru": "NotoSans-Bold",
    "ar": "NotoSansArabic-Bold",
    "fa": "NotoSansArabic-Bold",
    "ur": "NotoSansArabic-Bold",
    "th": "NotoSansThai-Bold",
    "hi": "Hind-Bold",
    "vi": "NotoSans-Bold",
    "id": "NotoSans-Bold",
    "ms": "NotoSans-Bold",
    "tl": "NotoSans-Bold",
    "km": "NotoSansKhmer-Bold",
    "lo": "NotoSansLao-Bold",
    "my": "NotoSansMyanmar-Bold",
    "he": "Heebo-Bold",
    "default": "SourceHanSansSC-Bold",
}
