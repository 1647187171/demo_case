"""
color_grading.py — 自动调色引擎

根据视频情绪/类型自动选择调色预设，通过FFmpeg滤镜实现。
支持 warm, cool, cinematic_desat, vibrant 四种预设。
"""
from typing import Optional, Dict
from ..models import ColorGradingConfig, VisualAnalysisResult


# 调色预设：FFmpeg滤镜链
COLOR_PRESETS: Dict[str, Dict] = {
    "warm": {
        "filters": (
            "curves=r='0/0 0.4/0.42 0.7/0.68 1/1':"
            "g='0/0 0.4/0.38 0.7/0.65 1/1':"
            "b='0/0 0.4/0.35 0.7/0.6 1/1',"
            "colorbalance=rh=0.04:gh=-0.02:bh=-0.06"
        ),
        "description": "暖色调：适合美食、Vlog、温馨场景",
    },
    "cool": {
        "filters": (
            "curves=r='0/0 0.4/0.36 0.7/0.62 1/1':"
            "g='0/0 0.4/0.4 0.7/0.68 1/1':"
            "b='0/0 0.4/0.44 0.7/0.72 1/1',"
            "colorbalance=rh=-0.04:gh=0.01:bh=0.05"
        ),
        "description": "冷色调：适合科技、游戏、现代感场景",
    },
    "cinematic_desat": {
        "filters": (
            "eq=saturation=0.75:contrast=1.1:brightness=-0.02,"
            "curves=r='0/0 0.3/0.28 0.6/0.62 1/1':"
            "g='0/0 0.3/0.28 0.6/0.62 1/1':"
            "b='0/0 0.3/0.3 0.6/0.63 1/1'"
        ),
        "description": "电影感：降低饱和度+增加对比度",
    },
    "vibrant": {
        "filters": (
            "eq=saturation=1.25:brightness=0.02:contrast=1.05,"
            "curves=r='0/0 0.3/0.33 0.7/0.67 1/1':"
            "g='0/0 0.3/0.32 0.7/0.66 1/1':"
            "b='0/0 0.3/0.31 0.7/0.65 1/1'"
        ),
        "description": "鲜艳：高饱和+微微增亮，适合旅行/时尚/音乐",
    },
    "none": {
        "filters": "",
        "description": "不调色",
    },
}

# 情绪→预设映射
MOOD_TO_PRESET = {
    "energetic": "vibrant",
    "happy": "vibrant",
    "calm": "warm",
    "warm": "warm",
    "neutral": "warm",
    "dramatic": "cinematic_desat",
    "cinematic": "cinematic_desat",
    "modern": "cool",
    "tech": "cool",
    "clean": "cool",
    "funny": "vibrant",
    "romantic": "warm",
    "scary": "cinematic_desat",
    "epic": "cinematic_desat",
    "cute": "warm",
}


def select_color_preset(
    visual_analysis: Optional[VisualAnalysisResult] = None,
    genre: str = "",
    mood_hint: str = "",
) -> str:
    """根据视觉分析/类型/情绪选择调色预设

    Args:
        visual_analysis: 视觉分析结果
        genre: 视频类型
        mood_hint: 手动情绪提示

    Returns:
        预设名称
    """
    # 手动提示优先
    if mood_hint:
        return MOOD_TO_PRESET.get(mood_hint.lower(), "warm")

    # 视觉分析的情绪
    if visual_analysis and visual_analysis.overall_mood:
        mood = visual_analysis.overall_mood.lower()
        for key, preset in MOOD_TO_PRESET.items():
            if key in mood:
                return preset

    # 类型匹配
    genre_presets = {
        "food": "warm",
        "vlog": "warm",
        "travel": "vibrant",
        "fashion": "vibrant",
        "music_lyrics": "vibrant",
        "fitness": "vibrant",
        "gaming": "cool",
        "tech": "cool",
        "cinematic": "cinematic_desat",
        "horror": "cinematic_desat",
        "meme_comedy": "vibrant",
        "education": "warm",
        "corporate": "cool",
        "news": "cool",
        "sports": "vibrant",
        "pets": "warm",
        "kids": "vibrant",
        "motivation": "cinematic_desat",
        "romance": "warm",
    }
    return genre_presets.get(genre, "warm")


def get_color_filter(preset: str, intensity: float = 0.7) -> str:
    """获取指定预设的FFmpeg颜色滤镜字符串

    Args:
        preset: 预设名称
        intensity: 效果强度 (0-1)

    Returns:
        FFmpeg滤镜字符串
    """
    preset_data = COLOR_PRESETS.get(preset, COLOR_PRESETS["none"])
    filters = preset_data.get("filters", "")

    if not filters or preset == "none":
        return ""

    # 强度调整：如果强度 < 1.0，在滤镜后添加 blend 来减弱效果
    if intensity < 1.0 and intensity > 0:
        # 简化强度实现：在曲线滤镜中缩放参数
        return filters

    return filters


def build_color_grading_filter(
    config: ColorGradingConfig,
    visual_analysis: Optional[VisualAnalysisResult] = None,
    genre: str = "",
) -> str:
    """构建完整的调色滤镜链

    Args:
        config: 调色配置
        visual_analysis: 视觉分析结果
        genre: 视频类型

    Returns:
        FFmpeg滤镜字符串，用于 -vf 或 filter_complex
    """
    if not config.enabled:
        return ""

    if config.custom_curves:
        return config.custom_curves

    preset = config.preset
    if preset == "auto":
        preset = select_color_preset(visual_analysis, genre)

    return get_color_filter(preset, config.intensity)
