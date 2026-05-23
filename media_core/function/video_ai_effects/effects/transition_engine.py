"""
transition_engine.py — 丰富转场引擎

提供5+种转场类型及自动选择逻辑。
根据相邻场景的能量变化自动选择最合适的转场效果。

转场类型：
- fade_black: 经典黑场淡入淡出
- zoom_blur: 缩放+模糊过渡
- slide_push: 滑动推开
- crossfade: 平滑交叉溶解
- glitch: 数字故障效果
- whip_pan: 快速方向模糊摇镜
"""
from typing import Optional, List, Dict, Tuple, Any
from ..models import TransitionType, TransitionConfig, BeatInfo


def select_transition_type(
    energy_delta: float,
    config: Optional[TransitionConfig] = None,
) -> str:
    """根据场景间能量差选择合适的转场类型

    Args:
        energy_delta: 当前场景与下一场景的能量差 (0-1)
        config: 转场配置

    Returns:
        转场类型名称
    """
    if energy_delta < 0.05:
        return "crossfade"
    elif energy_delta < 0.15:
        return "zoom_blur"
    elif energy_delta < 0.25:
        return "slide_push"
    elif energy_delta < 0.35:
        return "whip_pan"
    else:
        return "glitch"


def select_transition_type_round_robin(
    scene_index: int,
    energy_delta: float,
) -> str:
    """轮转选择：确保相邻转场不重复

    Args:
        scene_index: 场景序号
        energy_delta: 能量差

    Returns:
        转场类型名称
    """
    high_energy_types = ["zoom_blur", "slide_push", "whip_pan", "glitch"]
    low_energy_types = ["crossfade", "fade_black"]

    if energy_delta < 0.08:
        return low_energy_types[scene_index % len(low_energy_types)]
    else:
        return high_energy_types[scene_index % len(high_energy_types)]


def build_transition_filter(
    transition_type: str,
    timestamp: float,
    duration: float = 0.4,
    video_width: int = 1080,
    video_height: int = 1920,
    direction: str = "right",
) -> str:
    """为单个转场构建FFmpeg滤镜片段

    Args:
        transition_type: 转场类型
        timestamp: 转场时间点(秒)
        duration: 转场持续时长(秒)
        video_width: 视频宽度
        video_height: 视频高度
        direction: 方向 (left, right, up, down)

    Returns:
        FFmpeg滤镜字符串（用于filter_complex）
    """
    t = timestamp
    d = duration
    w, h = video_width, video_height

    builders = {
        "fade_black": lambda: f"fade=t=out:st={t - d * 0.3:.3f}:d={d * 0.3:.3f},fade=t=in:st={t:.3f}:d={d * 0.3:.3f}",
        "crossfade": lambda: f"fade=t=out:st={t - d * 0.5:.3f}:d={d * 0.5:.3f},fade=t=in:st={t - d * 0.2:.3f}:d={d * 0.5:.3f}",
        "zoom_blur": lambda: (
            f"zoompan=z='if(between(t,{t - d:.3f},{t + d:.3f}),"
            f"1.0+0.15*sin(PI*(t-{t - d:.3f})/{d:.3f}),1.0)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}"
        ),
        "slide_push": lambda: (
            f"overlay=x='if(between(t,{t - d * 0.5:.3f},{t + d * 0.5:.3f}),"
            f"{w}-{w}*(t-{t - d * 0.5:.3f})/{d:.3f},0)':"
            f"enable='between(t,{t - d * 0.5:.3f},{t + d * 0.5:.3f})'"
        ),
        "whip_pan": lambda: (
            f"gblur=sigma='if(between(t,{t - d:.3f},{t + d:.3f}),"
            f"15*sin(PI*(t-{t - d:.3f})/{d:.3f}),0)'"
        ),
        "glitch": lambda: (
            f"geq=r='if(between(t,{t:.3f},{t + d:.3f})*not(mod(floor(t*30),2)),"
            f"r(X+5,Y),r(X,Y))':"
            f"g='if(between(t,{t:.3f},{t + d:.3f})*not(mod(floor(t*30),2)),"
            f"g(X-3,Y),g(X,Y))':"
            f"b='if(between(t,{t + d * 0.5:.3f},{t + d:.3f})*not(mod(floor(t*30),2)),"
            f"b(X,Y+3),b(X,Y))'"
        ),
    }

    builder = builders.get(transition_type, builders["fade_black"])
    return builder()


def generate_transition_plan(
    scene_changes: List[float],
    beat_info: Optional[BeatInfo] = None,
    video_duration: float = 0.0,
    config: Optional[TransitionConfig] = None,
) -> List[Dict[str, Any]]:
    """根据场景切换列表生成完整的转场计划

    Args:
        scene_changes: 场景切换时间点列表
        beat_info: 节拍信息，用于评估各场景能量
        video_duration: 视频时长
        config: 转场配置

    Returns:
        [{"time": float, "type": str, "duration": float, "direction": str}, ...]
    """
    if not scene_changes:
        return []

    min_gap = config.min_gap if config else 2.0
    max_count = config.max_count if config else 6
    default_dur = config.default_duration if config else 0.4

    # 过滤：去重、去首尾、最小间隔
    filtered = sorted(set(scene_changes))
    filtered = [t for t in filtered if 0.8 < t < (video_duration - 0.8)]
    deduped = []
    for t in filtered:
        if not deduped or t - deduped[-1] >= min_gap:
            deduped.append(t)
    deduped = deduped[:max_count]

    if not deduped:
        return []

    # 评估各场景间能量差
    directions = ["right", "left", "up", "down"]
    plan = []
    last_type = ""

    for i, t in enumerate(deduped):
        # 估算能量差（基于节拍密度）
        energy_delta = 0.0
        if beat_info and beat_info.beat_times:
            window_before = 1.0
            window_after = 1.0
            beats_before = sum(1 for b in beat_info.beat_times if t - window_before <= b < t)
            beats_after = sum(1 for b in beat_info.beat_times if t <= b < t + window_after)
            max_beats = max(beats_before, beats_after, 1)
            energy_delta = abs(beats_before - beats_after) / max_beats

        # 选择类型（确保不连续重复）
        tt = select_transition_type(energy_delta, config)
        if tt == last_type and len(deduped) > 1:
            tt = select_transition_type_round_robin(i, energy_delta)
        last_type = tt

        plan.append({
            "time": t,
            "type": tt,
            "duration": default_dur,
            "direction": directions[i % len(directions)],
        })

    return plan


def build_all_transition_filters(
    plan: List[Dict[str, Any]],
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """为完整转场计划构建FFmpeg滤镜链

    Returns:
        以逗号分隔的滤镜链字符串，用于 -vf
    """
    filters = []
    for item in plan:
        f = build_transition_filter(
            transition_type=item["type"],
            timestamp=item["time"],
            duration=item["duration"],
            video_width=video_width,
            video_height=video_height,
            direction=item.get("direction", "right"),
        )
        if f:
            filters.append(f)

    return ",".join(filters) if filters else ""
