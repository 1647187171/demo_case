"""
animation_presets.py — 动画预设配置

定义ASS字幕动画的预设模板，支持淡入淡出、弹跳、滑动、旋转、彩虹等效果。
每个预设包含ASS覆盖标签模板和默认参数。
"""
from typing import Dict, Any

# 动画预设字典：动画类型 → ASS模板和默认参数
ANIMATION_PRESETS: Dict[str, Dict[str, Any]] = {
    "fade_in": {
        "ass_template": "\\fad({duration},0)",
        "default_duration_ms": 250,
    },
    "fade_out": {
        "ass_template": "\\fad(0,{duration})",
        "default_duration_ms": 300,
    },
    "fade_in_out": {
        "ass_template": "\\fad({in_dur},{out_dur})",
        "default_in_ms": 200,
        "default_out_ms": 300,
    },
    "bounce": {
        "ass_template": "\\t(0,{half},\\fscx{peak}\\fscy{peak})\\t({half},{duration},\\fscx100\\fscy100)",
        "default_duration_ms": 400,
        "peak_scale": 120,
    },
    "glow_pulse": {
        "ass_template": "\\t(0,{half},\\blur3\\1c{bright})\\t({half},{duration},\\blur1\\1c{normal})",
        "default_duration_ms": 600,
    },
    "slide_up": {
        "ass_template": "\\move({x},{start_y},{x},{end_y},{start_ms},{end_ms})",
        "default_y_offset": 50,
    },
    "slide_down": {
        "ass_template": "\\move({x},{start_y},{x},{end_y},{start_ms},{end_ms})",
        "default_y_offset": -50,
    },
    "slide_left": {
        "ass_template": "\\move({start_x},{y},{end_x},{y},{start_ms},{end_ms})",
        "default_x_offset": 200,
    },
    "slide_right": {
        "ass_template": "\\move({start_x},{y},{end_x},{y},{start_ms},{end_ms})",
        "default_x_offset": -200,
    },
    "pop": {
        "ass_template": "\\t(0,{third},\\fscx30\\fscy30)\\t({third},{two_third},\\fscx{peak}\\fscy{peak})\\t({two_third},{duration},\\fscx100\\fscy100)",
        "default_duration_ms": 350,
        "peak_scale": 110,
    },
    "scale_up": {
        "ass_template": "\\fscx50\\fscy50\\t(0,{duration},\\fscx100\\fscy100)",
        "default_duration_ms": 400,
    },
    "shake": {
        "ass_template": "\\t(0,{step},\\pos({dx1},{dy}))\\t({step},{step2},\\pos({dx2},{dy}))\\t({step2},{duration},\\pos(0,{dy}))",
        "default_duration_ms": 300,
        "shake_px": 5,
    },
    "typewriter": {
        "per_char_delay_ms": 80,
    },
    "karaoke_word": {
        "ass_template": "\\K{duration_cs}",
    },
    "karaoke_char": {
        "ass_template": "\\k{duration_cs}",
    },
    "rainbow": {
        "colors": ["&H000000FF", "&H0000FF00", "&H00FF0000", "&H0000FFFF", "&H00FF00FF", "&H00FFFF00"],
        "default_duration_ms": 500,
    },
    "rotate": {
        "ass_template": "\\t(0,{duration},\\frz{angle})",
        "default_duration_ms": 500,
        "angle": 360,
    },
}


def get_animation_template(animation_type: str) -> Dict[str, Any]:
    """获取指定动画类型的预设配置"""
    return ANIMATION_PRESETS.get(animation_type, {})


def format_animation_override(
    animation_type: str,
    total_duration_ms: int,
    video_width: int = 1080,
    video_height: int = 1920,
    y_position: int = 1800,
) -> str:
    """将动画预设格式化为ASS覆盖标签字符串

    Args:
        animation_type: 动画类型名称
        total_duration_ms: 总时长（毫秒）
        video_width: 视频宽度
        video_height: 视频高度
        y_position: 字幕Y坐标

    Returns:
        格式化后的ASS覆盖标签（如 "{\\fad(250,0)}"）
    """
    preset = ANIMATION_PRESETS.get(animation_type)
    if not preset:
        return ""
    template = preset.get("ass_template", "")
    if not template:
        return ""
    cx = video_width // 2
    dur = total_duration_ms
    half = dur // 2
    third = dur // 3
    two_third = third * 2

    kwargs = {
        "duration": dur,
        "half": half,
        "third": third,
        "two_third": two_third,
        "x": cx,
        "start_y": y_position + preset.get("default_y_offset", 50),
        "end_y": y_position,
        "start_x": cx + preset.get("default_x_offset", 0),
        "end_x": cx,
        "y": y_position,
        "start_ms": 0,
        "end_ms": dur,
        "peak": preset.get("peak_scale", 110),
        "step": dur // 3,
        "step2": dur * 2 // 3,
        "dx1": preset.get("shake_px", 5),
        "dx2": -preset.get("shake_px", 5),
        "dy": 0,
        "duration_cs": max(1, dur // 10),
        "in_dur": min(preset.get("default_in_ms", 200), dur // 3),
        "out_dur": min(preset.get("default_out_ms", 300), dur // 3),
        "angle": preset.get("angle", 360),
        "bright": "&H00FFFFFF",
        "normal": "&H00FFFFFF",
    }
    try:
        return "{" + template.format(**kwargs) + "}"
    except (KeyError, IndexError):
        return ""
