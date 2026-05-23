"""
ass_styles — ASS字幕样式注册表

汇聚所有平台和类型的字幕样式，提供查询接口。
"""
from typing import Dict, List, Optional
from ..models import ASSStyleConfig

from .tiktok import TIKTOK_STYLES
from .instagram import INSTAGRAM_STYLES
from .youtube import YOUTUBE_STYLES
from .cinematic import CINEMATIC_STYLES
from .gaming import GAMING_STYLES
from .music_lyrics import MUSIC_LYRICS_STYLES
from .meme_comedy import MEME_COMEDY_STYLES
from .education import EDUCATION_STYLES
from .corporate import CORPORATE_STYLES
from .vlog import VLOG_STYLES
from .food import FOOD_STYLES
from .fitness import FITNESS_STYLES
from .travel import TRAVEL_STYLES
from .fashion import FASHION_STYLES
from .news import NEWS_STYLES
from .kids import KIDS_STYLES

# 全局样式字典：style_id → ASSStyleConfig
ALL_STYLES: Dict[str, ASSStyleConfig] = {}

for _module_styles in [
    TIKTOK_STYLES,
    INSTAGRAM_STYLES,
    YOUTUBE_STYLES,
    CINEMATIC_STYLES,
    GAMING_STYLES,
    MUSIC_LYRICS_STYLES,
    MEME_COMEDY_STYLES,
    EDUCATION_STYLES,
    CORPORATE_STYLES,
    VLOG_STYLES,
    FOOD_STYLES,
    FITNESS_STYLES,
    TRAVEL_STYLES,
    FASHION_STYLES,
    NEWS_STYLES,
    KIDS_STYLES,
]:
    ALL_STYLES.update(_module_styles)


def get_style(style_id: str) -> Optional[ASSStyleConfig]:
    """根据样式ID获取样式配置"""
    return ALL_STYLES.get(style_id)


def get_styles_by_category(category: str) -> Dict[str, ASSStyleConfig]:
    """按分类过滤样式"""
    return {k: v for k, v in ALL_STYLES.items() if v.category == category}


def get_styles_by_platform(platform: str) -> Dict[str, ASSStyleConfig]:
    """按平台过滤样式"""
    return {k: v for k, v in ALL_STYLES.items() if v.platform == platform}


def get_all_categories() -> List[str]:
    """获取所有样式分类列表（去重排序）"""
    return sorted(set(v.category for v in ALL_STYLES.values()))


def get_all_style_ids() -> List[Dict[str, str]]:
    """获取所有样式的摘要信息列表"""
    return [
        {
            "id": k,
            "name": v.style_name,
            "category": v.category,
            "platform": v.platform,
            "description": v.description,
            "tags": ",".join(v.tags),
        }
        for k, v in sorted(ALL_STYLES.items())
    ]


def get_style_count() -> int:
    """获取样式总数"""
    return len(ALL_STYLES)
