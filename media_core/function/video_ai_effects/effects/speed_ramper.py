"""
speed_ramper.py — 动态变速引擎

分析视频各段的能量水平，自动生成变速方案：
- 低能量段：1.2x-1.5x 加速（跳过无聊部分）
- 高能量段：0.7x-0.9x 慢放（强调精彩时刻）
- 普通段：1.0x 正常速度

使用segment级别的能量评分，基于节拍密度和关键词密度。
"""
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from ..models import (
    SpeedRampConfig, SpeedRampSegment, BeatInfo,
    KeywordEmphasis, SubtitleSegment,
)

# 最小段长（秒），避免产生过短的变速段
MIN_SEGMENT_DURATION = 1.5

# 默认段长（秒），用于分析窗口
DEFAULT_SEGMENT_SIZE = 2.0


def analyze_segment_energy(
    seg_start: float,
    seg_end: float,
    beat_info: Optional[BeatInfo],
    keyword_emphases: Optional[List[KeywordEmphasis]],
    segments: Optional[List[SubtitleSegment]],
) -> float:
    """计算一个时间段的综合能量分数 (0.0-1.0)

    评分因子：
    - 节拍密度 (0.40)：窗口内节拍数/时长，归一化
    - 关键词密度 (0.30)：窗口内命中关键词数/时长
    - 字幕活跃度 (0.30)：窗口内有字幕覆盖的比例
    """
    dur = seg_end - seg_start
    if dur <= 0:
        return 0.5

    # 节拍密度
    beat_score = 0.0
    if beat_info and beat_info.beat_times:
        beats_in = sum(1 for b in beat_info.beat_times if seg_start <= b < seg_end)
        density = beats_in / dur
        beat_score = min(density / 3.0, 1.0) * 0.33 + min(density, 0.5)

    # 关键词密度
    kw_score = 0.0
    if keyword_emphases:
        kw_in = 0
        for emp in keyword_emphases:
            ws = (emp.word_start_ms or 0) / 1000.0
            if seg_start <= ws < seg_end:
                kw_in += 1
        kw_score = min(kw_in / max(dur, 0.1), 2.0) / 2.0

    # 字幕活跃度
    subtitle_score = 0.0
    if segments:
        covered_ms = 0
        seg_start_ms = seg_start * 1000
        seg_end_ms = seg_end * 1000
        for seg in segments:
            if seg.end_ms > seg_start_ms and seg.start_ms < seg_end_ms:
                overlap_start = max(seg.start_ms, seg_start_ms)
                overlap_end = min(seg.end_ms, seg_end_ms)
                covered_ms += max(0, overlap_end - overlap_start)
        subtitle_score = min(covered_ms / max(dur * 1000, 1), 1.0)

    return beat_score * 0.40 + kw_score * 0.30 + subtitle_score * 0.30


def generate_speed_ramp_segments(
    video_duration: float,
    beat_info: Optional[BeatInfo],
    keyword_emphases: Optional[List[KeywordEmphasis]],
    segments: Optional[List[SubtitleSegment]],
    config: SpeedRampConfig,
) -> List[SpeedRampSegment]:
    """生成完整的变速段列表

    将视频按固定窗口分析能量，相邻相似能量的段合并，
    然后为每段分配合适的播放速度。

    Args:
        video_duration: 视频总时长(秒)
        beat_info: 节拍信息
        keyword_emphases: 关键词强调列表
        segments: 字幕片段
        config: 变速配置

    Returns:
        SpeedRampSegment 列表
    """
    if video_duration < MIN_SEGMENT_DURATION * 3:
        return []

    # 第一步：按固定窗口分析各段能量
    window_size = max(MIN_SEGMENT_DURATION, min(DEFAULT_SEGMENT_SIZE, video_duration / 8))
    raw_segments = []
    t = 0.0
    while t < video_duration:
        end_t = min(t + window_size, video_duration)
        energy = analyze_segment_energy(t, end_t, beat_info, keyword_emphases, segments)
        raw_segments.append({
            "start": t, "end": end_t, "energy": energy,
        })
        t = end_t

    if len(raw_segments) <= 1:
        return []

    # 第二步：合并相邻且能量相近的段（能量差 < 0.15）
    merged = [raw_segments[0]]
    for raw in raw_segments[1:]:
        prev = merged[-1]
        if abs(raw["energy"] - prev["energy"]) < 0.15:
            prev["end"] = raw["end"]
            prev["energy"] = (prev["energy"] + raw["energy"]) / 2
        else:
            merged.append(raw)

    # 第三步：去除过短的段（合并到相邻段中）
    final = []
    for i, m in enumerate(merged):
        dur = m["end"] - m["start"]
        if dur < MIN_SEGMENT_DURATION and final:
            final[-1]["end"] = m["end"]
            continue
        final.append(m)

    if len(final) <= 1:
        return []

    # 第四步：为每段分配播放速度
    result = []
    for f in final:
        energy = f["energy"]
        if energy < config.energy_threshold_low:
            speed = config.max_speed  # 加速无聊段
            reason = "low_energy"
        elif energy > config.energy_threshold_high:
            speed = config.min_speed  # 慢放精彩段
            reason = "high_impact"
        else:
            speed = 1.0
            reason = "normal"
        result.append(SpeedRampSegment(
            start_time=f["start"],
            end_time=f["end"],
            speed=speed,
            reason=reason,
        ))

    # 平滑：首尾段保持正常速度
    if result:
        result[0].speed = 1.0
        result[0].reason = "intro_normal"
        result[-1].speed = 1.0
        result[-1].reason = "outro_normal"

    return result


def build_speed_ramp_filters(
    ramp_segments: List[SpeedRampSegment],
    video_duration: float,
    transition_frames: int = 6,
) -> Dict:
    """为FFmpeg构建分段变速的filter_complex

    将视频按变速段切割，每段应用 setpts (视频) 和 atempo (音频)，
    最后用 concat 重新拼接。

    Returns:
        {
            "filter_complex": str,  # 完整的 filter_complex 字符串
            "video_labels": [str],   # 视频输出标签列表
            "audio_labels": [str],   # 音频输出标签列表
            "segment_count": int,
        }
    """
    if not ramp_segments:
        return {"filter_complex": "", "video_labels": [], "audio_labels": [], "segment_count": 0}

    n = len(ramp_segments)
    video_parts = []
    audio_parts = []
    video_labels = []
    audio_labels = []

    for i, seg in enumerate(ramp_segments):
        start = seg.start_time
        end = min(seg.end_time, video_duration)
        speed = seg.speed

        vid_label = f"v{i}"
        aud_label = f"a{i}"
        video_labels.append(vid_label)
        audio_labels.append(aud_label)

        if speed == 1.0:
            # 正常速度：直接 trim
            video_parts.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[{vid_label}]")
            audio_parts.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[{aud_label}]")
        else:
            # 变速处理
            video_parts.append(
                f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=(PTS-STARTPTS)/{speed:.3f}[{vid_label}]"
            )
            # FFmpeg atempo 滤镜的范围是 0.5-2.0，变速参数在此范围内
            audio_parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,atempo={speed:.3f}[{aud_label}]"
            )

    v_concat = "".join(f"[{vl}]" for vl in video_labels)
    a_concat = "".join(f"[{al}]" for al in audio_labels)

    filter_complex = (
        ";".join(video_parts + audio_parts) +
        f";{v_concat}concat=n={n}:v=1:a=0[vout];" +
        f"{a_concat}concat=n={n}:v=0:a=1[aout]"
    )

    return {
        "filter_complex": filter_complex,
        "video_labels": video_labels,
        "audio_labels": audio_labels,
        "segment_count": n,
    }


def apply_speed_ramp_prepass(
    input_path: str,
    output_path: str,
    ramp_segments: List[SpeedRampSegment],
    video_duration: float,
    ffmpeg_path: str = "ffmpeg",
) -> bool:
    """预处理：生成变速后的视频文件

    将变速作为一个独立的FFmpeg预处理步骤，
    输出到临时文件，后续流水线使用此文件作为输入。

    Args:
        input_path: 原始视频路径
        output_path: 变速后视频输出路径
        ramp_segments: 变速段列表
        video_duration: 视频时长
        ffmpeg_path: FFmpeg可执行文件路径

    Returns:
        是否成功
    """
    import subprocess

    filters = build_speed_ramp_filters(ramp_segments, video_duration)
    if not filters["filter_complex"]:
        # 无变速，直接复制
        import shutil
        shutil.copy2(input_path, output_path)
        return True

    cmd = [
        ffmpeg_path, "-y",
        "-i", input_path,
        "-filter_complex", filters["filter_complex"],
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and Path(output_path).stat().st_size > 10000:
            return True
        return False
    except Exception:
        return False


def remap_timestamps_for_speed(
    effects: List[Dict],
    ramp_segments: List[SpeedRampSegment],
) -> List[Dict]:
    """将特效时间戳按变速映射重新计算

    当视频变速后，原始时间轴需要重新映射。
    例如：原始时间 5.0s 的SFX，如果在 1.2x 加速段中，
    实际触发时间会提前。

    Args:
        effects: 特效列表（含 timestamp 字段的字典列表）
        ramp_segments: 变速段列表

    Returns:
        重新映射后的特效列表
    """
    if not ramp_segments:
        return effects

    # 构建时间映射函数
    # 对每个变速段计算累积偏移
    cumulative_offset = 0.0
    breakpoints = []  # [(原始时间, 偏移量), ...]

    for seg in ramp_segments:
        dur = seg.end_time - seg.start_time
        if seg.speed == 1.0:
            breakpoints.append((seg.end_time, cumulative_offset))
        else:
            # 变速后的时长
            new_dur = dur / seg.speed
            offset = new_dur - dur  # 负值 = 加速(时间提前), 正值 = 慢放(时间延后)
            cumulative_offset += offset
            breakpoints.append((seg.end_time, cumulative_offset))

    # 对每个特效重新计算时间
    remapped = []
    for eff in effects:
        ts = eff.get("timestamp", 0)
        # 查找 ts 所在的段
        offset = 0.0
        prev_bp = 0.0
        for bp_time, bp_offset in breakpoints:
            if ts < bp_time:
                # 在前一段中找到
                for seg in ramp_segments:
                    if seg.start_time <= prev_bp and ts >= seg.start_time:
                        if seg.speed != 1.0:
                            offset = (ts - seg.start_time) * (1.0 / seg.speed - 1.0)
                        break
                break
            prev_bp = bp_time

        new_eff = dict(eff)
        new_eff["timestamp"] = round(ts + offset, 3)
        new_eff["_original_timestamp"] = ts
        remapped.append(new_eff)

    return remapped
