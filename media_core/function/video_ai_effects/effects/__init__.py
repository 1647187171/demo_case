"""
effects — 特效子包

提供音效库、动画预设、节拍检测与对齐、花字强调、BGM推荐、
Hook检测、变速、转场、调色、动态图形、传播力评分、智能裁剪等能力。
"""
from .sfx_library import get_sfx, get_all_sfx, match_sfx_to_keyword, get_sfx_for_mood, match_sfx_to_visual
from .animation_presets import get_animation_template, format_animation_override, ANIMATION_PRESETS
from .beat_sync import detect_beats, align_effects_to_beats
from .huazi_presets import apply_huazi, PRESET_NAMES, get_default_color_for_genre
from .bgm_library import recommend_bgm, get_bgm, get_all_bgm, BGM_CATALOG
from .hook_engine import detect_best_hook_moment, select_hook_text
from .speed_ramper import generate_speed_ramp_segments, apply_speed_ramp_prepass
from .transition_engine import generate_transition_plan, build_all_transition_filters
from .color_grading import select_color_preset, build_color_grading_filter
from .motion_graphics import generate_motion_graphics_from_keywords
from .engagement_scorer import score_engagement
from .crop_engine import calculate_crop_region, estimate_subject_position, build_crop_filter
