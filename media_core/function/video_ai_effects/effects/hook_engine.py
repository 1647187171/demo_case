"""
hook_engine.py — 智能开头Hook引擎

分析视频内容找到最吸引人的片段作为开头teaser，或生成文字叠加式Hook。
通过能量评分（节拍密度+关键词密度+onset强度）定位高吸引力片段。
"""
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from libs.media_core.utils import utils
from ..models import (
    HookConfig, BeatInfo, VisualAnalysisResult,
    KeywordEmphasis, SubtitleSegment, SpeedRampSegment,
)

# ---------------------------------------------------------------------------
# Hook 文字模板库
# ---------------------------------------------------------------------------

HOOK_TEMPLATES = {
    "question": [
        "你知道吗？",
        "这个秘密没人告诉你...",
        "你还在这样做吗？",
        "99%的人不知道...",
    ],
    "statistic": [
        "3秒学会！",
        "数据告诉你真相...",
        "这个方法太绝了！",
        "效果惊人！",
    ],
    "wow": [
        "天呐！这也太...",
        "不敢相信！",
        "必须收藏！",
        "绝了！",
    ],
    "countdown": [
        "3...2...1...",
        "准备好了吗？",
        "前方高能！",
    ],
}


def detect_best_hook_moment(
    beat_info: Optional[BeatInfo],
    keyword_emphases: Optional[List[KeywordEmphasis]],
    segments: Optional[List[SubtitleSegment]],
    video_duration: float,
    hook_duration: float = 3.0,
    window_step: float = 0.5,
) -> Optional[float]:
    """检测视频中最适合做Hook的高能片段起始时间

    对每个0.5s时间窗口打分：
    - 节拍密度 (0.40)
    - 关键词密度 (0.30)
    - onset强度 (0.30)

    Args:
        beat_info: 节拍检测结果
        keyword_emphases: 关键词强调列表
        segments: 字幕片段列表
        video_duration: 视频时长(秒)
        hook_duration: Hook片段时长(秒)
        window_step: 窗口步长(秒)

    Returns:
        最佳Hook片段起始时间(秒), 或 None
    """
    if video_duration < hook_duration + 1.0:
        return None

    windows = []
    t = 0.0
    while t + hook_duration <= video_duration:
        windows.append((t, t + hook_duration))
        t += window_step

    if not windows:
        return None

    best_score = 0.0
    best_start = None

    for w_start, w_end in windows:
        beat_score = _score_beat_density(beat_info, w_start, w_end)
        kw_score = _score_keyword_density(keyword_emphases, segments, w_start, w_end)
        onset_score = _score_onset_strength(beat_info, w_start, w_end)
        total = beat_score * 0.40 + kw_score * 0.30 + onset_score * 0.30

        if total > best_score:
            best_score = total
            best_start = w_start

    # 返回找到的最佳起始时间；分数太低时不强行使用（避免teaser=视频开头）
    if best_start is not None and best_score > 0.05 and best_start > 0.5:
        return best_start
    return None


def _score_beat_density(beat_info: Optional[BeatInfo], w_start: float, w_end: float) -> float:
    """窗口内节拍密度评分（归一化到0-1）"""
    if not beat_info or not beat_info.beat_times:
        return 0.0
    beats_in_window = sum(1 for b in beat_info.beat_times if w_start <= b < w_end)
    dur = w_end - w_start
    density = beats_in_window / max(dur, 0.1)
    # 理想密度: 1-3 beats/sec (对应 60-180 BPM)
    if density < 0.3:
        return density / 0.3 * 0.3
    elif density <= 3.0:
        return 0.3 + (density - 0.3) / 2.7 * 0.5
    else:
        return max(0.0, 0.8 - (density - 3.0) * 0.1)


def _score_keyword_density(
    keyword_emphases: Optional[List[KeywordEmphasis]],
    segments: Optional[List[SubtitleSegment]],
    w_start: float, w_end: float,
) -> float:
    """窗口内关键词密度评分"""
    if not keyword_emphases or not segments:
        return 0.0
    kw_start_ms = w_start * 1000
    kw_end_ms = w_end * 1000

    # 统计窗口内的关键词
    count = 0
    for emp in keyword_emphases:
        ws = emp.word_start_ms or 0
        if kw_start_ms <= ws < kw_end_ms:
            count += 1

    # 也统计字幕段内的关键词匹配
    for seg in segments:
        if not (seg.end_ms > kw_start_ms and seg.start_ms < kw_end_ms):
            continue
        if keyword_emphases:
            for emp in keyword_emphases:
                if emp.keyword in seg.text:
                    count += 1

    dur = w_end - w_start
    density = count / max(dur, 0.1)
    return min(density / 3.0, 1.0)


def _score_onset_strength(beat_info: Optional[BeatInfo], w_start: float, w_end: float) -> float:
    """窗口内平均onset强度"""
    if not beat_info or not beat_info.onset_strengths or not beat_info.onset_times:
        return 0.0
    strengths = []
    for t, s in zip(beat_info.onset_times, beat_info.onset_strengths):
        if w_start <= t < w_end:
            strengths.append(s)
    if not strengths:
        return 0.0
    return min(sum(strengths) / len(strengths), 1.0)


def select_hook_text(
    config: HookConfig,
    transcript: str = "",
    genre: str = "",
) -> str:
    """选择合适的Hook文字

    Args:
        config: Hook配置
        transcript: 视频转录文本
        genre: 视频类型

    Returns:
        Hook文字内容
    """
    if config.overlay_text:
        return config.overlay_text

    # 从转录文本中提取第一句话作为候选
    if transcript:
        sentences = transcript.replace("\n", " ").split("。")
        for s in sentences:
            s = s.strip()
            if len(s) >= 4 and len(s) <= 40:
                return s + "..."

    # 使用模板
    import random
    style = config.overlay_style or "question"
    templates = HOOK_TEMPLATES.get(style, HOOK_TEMPLATES["question"])
    return random.choice(templates)


def build_hook_ffmpeg_filter(
    video_path: str,
    hook_start: float,
    hook_duration: float,
    resolution: Tuple[int, int],
) -> Dict:
    """构建Hook teaser提取的FFmpeg滤镜参数

    Returns:
        包含 filter_complex 片段和 concat 参数的字典
    """
    w, h = resolution
    return {
        "teaser_trim": f"[0:v]trim=start={hook_start:.3f}:duration={hook_duration:.3f},setpts=PTS-STARTPTS[teaser]",
        "main_trim": f"[0:v]trim=start=0:end={hook_start:.3f},setpts=PTS-STARTPTS[prehook];"
                      f"[0:v]trim=start={hook_start:.3f},setpts=PTS-STARTPTS[main]",
        "concat_order": "[teaser][main]",
        "duration": hook_duration,
        "start": hook_start,
    }


def build_text_hook_filter(
    text: str,
    duration: float,
    resolution: Tuple[int, int],
    style: str = "question",
    color: str = "white",
) -> Dict:
    """构建文字叠加Hook的FFmpeg滤镜

    生成一个纯色背景+动画文字的intro片段。

    Returns:
        FFmpeg滤镜参数字典
    """
    w, h = resolution
    font_size = max(32, min(72, int(w * 0.065)))
    cx = w // 2
    cy = h // 2

    return {
        "bg_filter": f"color=c=0x1a1a2e:s={w}x{h}:d={duration:.3f}:r=30[hookbg]",
        "text_filter": (
            f"[hookbg]drawtext=text='{text}':fontcolor={color}:fontsize={font_size}:"
            f"x=(w-text_w)/2:y=(h-text_h)/2-20:"
            f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"alpha='if(lt(t,0.2), t/0.2, if(lt(t,{duration-0.3:.3f}), 1, ({duration:.3f}-t)/0.3))'"
            f"[hooktext]"
        ),
        "style": style,
        "duration": duration,
    }


def generate_hook_energy_curve(
    beat_info: Optional[BeatInfo],
    keyword_emphases: Optional[List[KeywordEmphasis]],
    segments: Optional[List[SubtitleSegment]],
    video_duration: float,
    window_step: float = 0.5,
) -> List[Tuple[float, float]]:
    """生成全视频能量曲线用于可视化/调试

    Returns:
        [(时间, 能量分数), ...]
    """
    curve = []
    t = 0.0
    while t < video_duration:
        w_end = min(t + window_step, video_duration)
        beat_s = _score_beat_density(beat_info, t, w_end)
        kw_s = _score_keyword_density(keyword_emphases, segments, t, w_end)
        onset_s = _score_onset_strength(beat_info, t, w_end)
        score = beat_s * 0.4 + kw_s * 0.3 + onset_s * 0.3
        curve.append((t, score))
        t += window_step
    return curve
