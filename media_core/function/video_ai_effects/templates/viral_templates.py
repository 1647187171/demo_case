"""
viral_templates.py — 爆款视频模板

预组合最佳实践配置，一键生成不同风格的社交媒体视频。
每个模板定义：字幕样式、转场偏好、调色方案、排版风格、
变速策略、Hook模式、BGM情绪、结尾模板。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ViralTemplate:
    """爆款视频模板定义"""
    name: str
    description: str
    platform: str = "tiktok"
    # 样式
    style_id: str = "tiktok_pop_yellow"
    # 转场
    preferred_transitions: List[str] = field(default_factory=lambda: ["zoom_blur", "crossfade"])
    transition_min_gap: float = 2.0
    # 调色
    color_grading_preset: str = "auto"
    color_grading_intensity: float = 0.7
    # 排版
    kinetic_preset: str = "viral"
    kinetic_variable_size: bool = True
    kinetic_color_by_type: bool = True
    kinetic_multi_position: bool = True
    # 变速
    speed_ramp_enabled: bool = True
    speed_min: float = 0.75
    speed_max: float = 1.40
    # Hook配置
    hook_mode: str = "auto"
    hook_duration: float = 3.0
    # 背景音乐配置
    bgm_mood: str = "upbeat_energy"
    bgm_volume: float = 0.10
    # 特效密度
    sfx_volume: float = 0.35
    max_sfx_per_minute: int = 6
    # 结尾
    end_screen_template: str = "centered"
    end_screen_cta: str = "Follow for more!"
    # 其它
    enable_ducking: bool = True
    enable_huazi: bool = True


# ===========================================================================
# 预置模板
# ===========================================================================

VIRAL_TEMPLATES: Dict[str, ViralTemplate] = {
    "tiktok_explainer": ViralTemplate(
        name="tiktok_explainer",
        description="TikTok知识讲解风格：快节奏、大字幕、强Hook",
        platform="tiktok",
        style_id="tiktok_pop_yellow",
        preferred_transitions=["zoom_blur", "whip_pan", "crossfade"],
        color_grading_preset="vibrant",
        color_grading_intensity=0.8,
        kinetic_preset="viral",
        kinetic_multi_position=True,
        speed_ramp_enabled=True,
        speed_min=0.75,
        speed_max=1.35,
        hook_mode="auto",
        hook_duration=3.0,
        bgm_mood="upbeat_energy",
        sfx_volume=0.40,
        max_sfx_per_minute=8,
        end_screen_cta="关注获取更多干货！",
    ),

    "tiktok_product": ViralTemplate(
        name="tiktok_product",
        description="TikTok产品展示风格：强调产品特点、多用zoom和pop音效",
        platform="tiktok",
        style_id="fashion_editorial",
        preferred_transitions=["zoom_blur", "slide_push", "crossfade"],
        color_grading_preset="vibrant",
        color_grading_intensity=0.9,
        kinetic_preset="kinetic",
        kinetic_variable_size=True,
        speed_ramp_enabled=True,
        speed_min=0.80,
        speed_max=1.30,
        hook_mode="auto",
        hook_duration=2.5,
        bgm_mood="upbeat_pop",
        sfx_volume=0.45,
        max_sfx_per_minute=6,
        end_screen_cta="下单链接在主页！",
    ),

    "youtube_montage": ViralTemplate(
        name="youtube_montage",
        description="YouTube精彩混剪：电影感、大气转场、史诗BGM",
        platform="youtube",
        style_id="cine_subtitle_classic",
        preferred_transitions=["whip_pan", "zoom_blur", "glitch", "crossfade"],
        color_grading_preset="cinematic_desat",
        color_grading_intensity=0.85,
        kinetic_preset="kinetic",
        kinetic_variable_size=True,
        speed_ramp_enabled=True,
        speed_min=0.70,
        speed_max=1.50,
        hook_mode="extract_teaser",
        hook_duration=4.0,
        bgm_mood="cinematic_epic",
        bgm_volume=0.12,
        sfx_volume=0.30,
        max_sfx_per_minute=5,
        end_screen_cta="Subscribe for more!",
        end_screen_template="centered",
    ),

    "instagram_aesthetic": ViralTemplate(
        name="instagram_aesthetic",
        description="Instagram唯美风格：慢节奏、暖色调、优雅转场",
        platform="instagram",
        style_id="vlog_warm_casual",
        preferred_transitions=["crossfade", "fade_black"],
        color_grading_preset="warm",
        color_grading_intensity=0.6,
        kinetic_preset="subtle",
        kinetic_multi_position=False,
        speed_ramp_enabled=False,
        hook_mode="text_overlay",
        hook_duration=3.0,
        bgm_mood="calm_warm",
        bgm_volume=0.15,
        sfx_volume=0.20,
        max_sfx_per_minute=3,
        end_screen_cta="Follow for more aesthetic ✨",
    ),

    "gaming_highlight": ViralTemplate(
        name="gaming_highlight",
        description="游戏高光剪辑：快节奏、glitch转场、重低音BGM",
        platform="tiktok",
        style_id="gaming_neon_blue",
        preferred_transitions=["glitch", "whip_pan", "zoom_blur"],
        color_grading_preset="cool",
        color_grading_intensity=0.8,
        kinetic_preset="viral",
        kinetic_color_by_type=True,
        speed_ramp_enabled=True,
        speed_min=0.65,
        speed_max=1.50,
        hook_mode="extract_teaser",
        hook_duration=3.5,
        bgm_mood="cinematic_epic",
        bgm_volume=0.10,
        sfx_volume=0.50,
        max_sfx_per_minute=10,
        end_screen_cta="Like & Subscribe!",
    ),

    "food_vlog": ViralTemplate(
        name="food_vlog",
        description="美食Vlog：暖色调、慢动作特写、温馨BGM",
        platform="tiktok",
        style_id="food_warm_orange",
        preferred_transitions=["crossfade", "zoom_blur"],
        color_grading_preset="warm",
        color_grading_intensity=0.75,
        kinetic_preset="viral",
        speed_ramp_enabled=True,
        speed_min=0.70,
        speed_max=1.25,
        hook_mode="auto",
        hook_duration=3.0,
        bgm_mood="calm_warm",
        bgm_volume=0.15,
        sfx_volume=0.30,
        max_sfx_per_minute=4,
        end_screen_cta="关注获取更多美食！",
    ),

    "tech_review": ViralTemplate(
        name="tech_review",
        description="科技评测：冷色调、简洁排版、数据驱动节奏",
        platform="youtube",
        style_id="tech_modern",
        preferred_transitions=["slide_push", "zoom_blur", "crossfade"],
        color_grading_preset="cool",
        color_grading_intensity=0.7,
        kinetic_preset="kinetic",
        kinetic_multi_position=True,
        speed_ramp_enabled=True,
        speed_min=0.80,
        speed_max=1.30,
        hook_mode="auto",
        hook_duration=3.0,
        bgm_mood="tech_modern",
        bgm_volume=0.08,
        sfx_volume=0.30,
        max_sfx_per_minute=5,
        end_screen_cta="Subscribe for tech reviews!",
    ),
}


def apply_template(template_name: str, config: Any) -> Any:
    """将模板配置应用到RenderingConfig

    Args:
        template_name: 模板名称
        config: RenderingConfig 实例

    Returns:
        应用模板后的 config（原地修改）
    """
    template = VIRAL_TEMPLATES.get(template_name)
    if not template:
        return config

    # 应用模板默认值（仅在config没有显式设置时）
    if not config.style_id:
        config.style_id = template.style_id
    if not config.platform or config.platform == "tiktok":
        config.platform = template.platform

    # 调色
    if config.enable_color_grading and not config.color_grading_config:
        from ..effects.color_grading import ColorGradingConfig
        config.color_grading_config = ColorGradingConfig(
            enabled=True,
            preset=template.color_grading_preset,
            intensity=template.color_grading_intensity,
        )

    # 变速
    if config.enable_speed_ramp and not config.speed_ramp_config:
        from ..models import SpeedRampConfig
        config.speed_ramp_config = SpeedRampConfig(
            enabled=template.speed_ramp_enabled,
            min_speed=template.speed_min,
            max_speed=template.speed_max,
        )

    # 排版
    if config.enable_kinetic_typo and not config.kinetic_typo_config:
        from ..models import KineticTypographyConfig
        config.kinetic_typo_config = KineticTypographyConfig(
            enabled=True,
            emphasis_preset=template.kinetic_preset,
            variable_word_size=template.kinetic_variable_size,
            color_by_word_type=template.kinetic_color_by_type,
            multi_position=template.kinetic_multi_position,
        )

    # Hook配置
    if config.enable_smart_hook and not config.hook_config:
        from ..models import HookConfig
        config.hook_config = HookConfig(
            mode=template.hook_mode,
            teaser_duration=template.hook_duration,
        )

    # 背景音乐配置
    config.bgm_volume = config.bgm_volume or template.bgm_volume

    # 音效配置
    if config.sfx_volume == 0.35:
        config.sfx_volume = template.sfx_volume

    # 转场
    if config.enable_variety_transitions and not config.transition_config:
        from ..models import TransitionConfig
        config.transition_config = TransitionConfig(
            min_gap=template.transition_min_gap,
        )

    # 结尾
    if config.enable_end_screen and not config.end_screen_config:
        from ..models import EndScreenConfig
        config.end_screen_config = EndScreenConfig(
            enabled=True,
            cta_text=template.end_screen_cta,
            template=template.end_screen_template,
        )

    # 闪避
    if config.enable_ducking and not config.ducking_config:
        config.ducking_config = None  # 将使用默认值

    return config
