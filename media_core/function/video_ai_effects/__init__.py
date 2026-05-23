"""
video_ai_effects — 视频AI特效包

提供视频字幕样式自动选择、ASS字幕生成、音效编排、FFmpeg渲染的完整能力。
"""
from .video_ai_effects_core import VideoAiEffectsCore
from .models import (
    ASSStyleConfig,
    ASSAnimationType,
    RenderingConfig,
    SubtitleSegment,
    EffectPlan,
    EffectDirectorOutput,
    VideoPlatform,
    VideoGenre,
)
from .ass_engine import generate_ass_file, parse_srt_to_segments, parse_json_subtitles
from .renderer import FFmpegRenderer
from .ass_styles import get_style, get_all_style_ids, get_styles_by_category, get_style_count

__all__ = [
    "VideoAiEffectsCore",
    "ASSStyleConfig",
    "ASSAnimationType",
    "RenderingConfig",
    "SubtitleSegment",
    "EffectPlan",
    "EffectDirectorOutput",
    "VideoPlatform",
    "VideoGenre",
    "generate_ass_file",
    "parse_srt_to_segments",
    "parse_json_subtitles",
    "FFmpegRenderer",
    "get_style",
    "get_all_style_ids",
    "get_styles_by_category",
    "get_style_count",
]
