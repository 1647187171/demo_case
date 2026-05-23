"""
engagement_scorer.py — 传播力评分引擎

启发式评估视频的预期传播效果，从多个维度打分：
- Hook强度 (25%)
- 节奏感 (20%)
- 特效密度 (15%)
- 多样性 (15%)
- 排版质量 (15%)
- 音频质量 (10%)

附带改进建议。
"""
from typing import Optional, List
from ..models import (
    EngagementScore, HookConfig, SpeedRampConfig, KineticTypographyConfig,
    TransitionConfig, BeatInfo, KeywordEmphasis, SubtitleSegment,
)


def score_engagement(
    hook_config: Optional[HookConfig] = None,
    speed_ramp_config: Optional[SpeedRampConfig] = None,
    kinetic_config: Optional[KineticTypographyConfig] = None,
    transition_config: Optional[TransitionConfig] = None,
    beat_info: Optional[BeatInfo] = None,
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
    segments: Optional[List[SubtitleSegment]] = None,
    video_duration: float = 0.0,
    sfx_count: int = 0,
    zoom_pulse_count: int = 0,
    bgm_enabled: bool = False,
) -> EngagementScore:
    """综合评分

    Returns:
        EngagementScore with overall 0-100 score and breakdown
    """
    hook = _score_hook(hook_config, video_duration)
    pacing = _score_pacing(speed_ramp_config, beat_info, video_duration)
    density = _score_density(sfx_count, zoom_pulse_count, video_duration)
    variety = _score_variety(
        speed_ramp_config, transition_config, keyword_emphases, sfx_count,
    )
    typography = _score_typography(kinetic_config, keyword_emphases, segments)
    audio = _score_audio(sfx_count, bgm_enabled, beat_info)

    overall = (
        hook * 0.25 + pacing * 0.20 + density * 0.15 +
        variety * 0.15 + typography * 0.15 + audio * 0.10
    )

    suggestions = _generate_suggestions(
        hook, pacing, density, variety, typography, audio,
        hook_config, video_duration, sfx_count,
    )

    return EngagementScore(
        overall=round(min(overall, 100), 1),
        hook_strength=round(hook, 1),
        pacing_score=round(pacing, 1),
        effect_density=round(density, 1),
        variety_score=round(variety, 1),
        typography_score=round(typography, 1),
        audio_score=round(audio, 1),
        suggestions=suggestions,
    )


def _score_hook(hook_config: Optional[HookConfig], video_duration: float) -> float:
    if not hook_config:
        return 10.0  # 没有hook = 低分
    score = 40.0
    if hook_config.teaser_start_time is not None:
        score += 40  # 有提取的teaser
    elif hook_config.overlay_text:
        score += 20  # 有文字叠加
    if hook_config.teaser_duration <= 4.0:
        score += 10  # 合适的时长
    return min(score, 95.0)


def _score_pacing(
    speed_config: Optional[SpeedRampConfig],
    beat_info: Optional[BeatInfo],
    video_duration: float,
) -> float:
    score = 20.0
    if speed_config and speed_config.segments:
        varied = sum(1 for s in speed_config.segments if s.speed != 1.0)
        total = len(speed_config.segments)
        if total > 0:
            score += 40 * (varied / total)  # 变速段比例
        if varied >= 2:
            score += 20  # 多样的变速
    if beat_info and beat_info.tempo > 0:
        score += 10  # 有节拍信息
    return min(score, 90.0)


def _score_density(sfx_count: int, zoom_count: int, video_duration: float) -> float:
    if video_duration <= 0:
        return 30.0
    total_effects = sfx_count + zoom_count
    density = total_effects / max(video_duration, 1)
    # 理想密度: 0.5-2.0 effects/second
    if density < 0.2:
        return 20.0
    elif density <= 2.0:
        return 50.0 + density * 25
    else:
        return max(20.0, 80.0 - (density - 2.0) * 30)


def _score_variety(
    speed_config: Optional[SpeedRampConfig],
    transition_config: Optional[TransitionConfig],
    keyword_emphases: Optional[List],
    sfx_count: int,
) -> float:
    score = 15.0
    # 有变速 → +15
    if speed_config and speed_config.segments:
        score += 15
    # 有多样转场 → +20
    if transition_config and transition_config.transitions:
        unique_types = len(set(t["type"] for t in transition_config.transitions))
        score += min(unique_types * 6, 20)
    # 有关键词强调 → +15
    if keyword_emphases and len(keyword_emphases) >= 3:
        score += 15
    # 音效数量合理 → 加15分
    if 3 <= sfx_count <= 12:
        score += 15
    return min(score, 90.0)


def _score_typography(
    kinetic_config: Optional[KineticTypographyConfig],
    keyword_emphases: Optional[List],
    segments: Optional[List],
) -> float:
    score = 20.0
    if kinetic_config and kinetic_config.enabled:
        score += 30
        if kinetic_config.variable_word_size:
            score += 10
        if kinetic_config.color_by_word_type:
            score += 10
        if kinetic_config.multi_position:
            score += 10
    if keyword_emphases and len(keyword_emphases) >= 5:
        score += 10
    if segments and len(segments) >= 5:
        score += 5
    return min(score, 90.0)


def _score_audio(sfx_count: int, bgm_enabled: bool, beat_info: Optional[BeatInfo]) -> float:
    score = 15.0
    if sfx_count >= 3:
        score += 25
    elif sfx_count >= 1:
        score += 10
    if bgm_enabled:
        score += 25
    if beat_info and beat_info.tempo > 0:
        score += 15
    return min(score, 90.0)


def _generate_suggestions(
    hook: float, pacing: float, density: float,
    variety: float, typography: float, audio: float,
    hook_config: Optional[HookConfig],
    video_duration: float,
    sfx_count: int,
) -> List[str]:
    suggestions = []
    if hook < 40:
        suggestions.append("建议开启智能Hook，在视频开头3秒抓取注意力")
    if pacing < 30:
        suggestions.append("建议开启动态变速，让节奏更有起伏")
    if density < 30:
        suggestions.append("特效密度偏低，建议增加SFX音效或zoom脉冲")
    if variety < 30:
        suggestions.append("特效类型单一，建议启用丰富转场和动态排版")
    if typography < 40:
        suggestions.append("字幕效果基础，建议开启Kinetic Typography增强视觉冲击")
    if audio < 30:
        suggestions.append("音频质量可提升：添加BGM背景音乐或更多音效")
    if sfx_count < 2 and video_duration > 5:
        suggestions.append("建议至少添加2-3个音效增强观看体验")
    if not suggestions:
        suggestions.append("整体配置良好，预计有不错的传播效果！")
    return suggestions
