"""
beat_sync.py — 音频节拍检测与特效对齐

提供基于 librosa 的节拍检测能力，将视觉特效与音乐重音对齐。
"""
import tempfile
import os
from typing import List, Optional, Dict

import numpy as np

try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    _HAS_LIBROSA = False


def detect_beats(video_path: str) -> Optional[Dict]:
    """检测视频音轨中的节拍和起始点

    Args:
        video_path: 视频文件路径

    Returns:
        包含 tempo、beat_times、onset_times、onset_strengths 的字典，
        如果 librosa 不可用或无音轨则返回 None
    """
    if not _HAS_LIBROSA:
        return None

    audio_path = _extract_audio(video_path)
    if not audio_path:
        # 降级：直接用 librosa 加载视频文件
        try:
            y, sr = librosa.load(video_path, sr=22050, mono=True)
            tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
            onset_times = librosa.frames_to_time(frames, sr=sr).tolist()
            return {
                "tempo": float(tempo) if isinstance(tempo, (int, float)) else float(tempo[0]),
                "beat_times": onset_times,
                "onset_times": onset_times,
                "onset_strengths": [],
            }
        except Exception:
            return None

    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=180)

        if len(y) < sr * 0.5:
            return None

        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr).tolist()
        onset_strengths = onset_env[onset_frames].tolist()

        return {
            "tempo": float(np.atleast_1d(tempo)[0]),
            "beat_times": beat_times,
            "onset_times": onset_times,
            "onset_strengths": onset_strengths,
        }
    except Exception:
        return None
    finally:
        if audio_path and audio_path.startswith(tempfile.gettempdir()):
            try:
                os.unlink(audio_path)
            except OSError:
                pass


def align_effects_to_beats(
    effects: List[Dict],
    beat_times: List[float],
    tolerance: float = 0.3,
) -> List[Dict]:
    """将特效时间戳对齐到最近的节拍

    Args:
        effects: 特效列表，每项包含 timestamp 字段
        beat_times: 节拍时间戳列表
        tolerance: 最大容许偏移（秒）

    Returns:
        对齐后的特效列表
    """
    if not beat_times or not effects:
        return effects

    aligned = []
    for effect in effects:
        ts = effect.get("timestamp", 0)
        closest = min(beat_times, key=lambda b: abs(b - ts))
        if abs(closest - ts) <= tolerance:
            new_effect = dict(effect)
            new_effect["timestamp"] = closest
            new_effect["beat_aligned"] = True
            aligned.append(new_effect)
        else:
            aligned.append(effect)
    return aligned


def get_beat_intervals(beat_times: List[float], max_interval: float = 2.0) -> List[Dict]:
    """获取节拍之间的时间间隔"""
    intervals = []
    for i in range(len(beat_times) - 1):
        duration = beat_times[i + 1] - beat_times[i]
        if duration <= max_interval:
            intervals.append({
                "start": beat_times[i],
                "end": beat_times[i + 1],
                "duration": duration,
            })
    return intervals


def get_strong_beats(
    beat_times: List[float],
    onset_strengths: List[float],
    percentile: float = 50.0,
    max_beats: int = 12,
) -> List[Dict]:
    """筛选 onset strength 超过阈值的强拍用于视频缩放脉冲

    Args:
        beat_times: 节拍时间列表
        onset_strengths: 对应的 onset 强度列表
        percentile: 强度百分位阈值 (50=中位数)
        max_beats: 最大返回数量

    Returns:
        [{"time": float, "strength": float}] 按时间排序
    """
    if not beat_times:
        return []

    if not onset_strengths or len(onset_strengths) != len(beat_times):
        # 无强度数据时取前 max_beats 个均匀间隔节拍
        step = max(1, len(beat_times) // max_beats)
        return [{"time": beat_times[i], "strength": 0.5} for i in range(0, len(beat_times), step)][:max_beats]

    threshold = float(np.percentile(onset_strengths, percentile)) if onset_strengths else 0
    max_strength = max(onset_strengths) if onset_strengths else 1.0

    strong = []
    for i, (t, s) in enumerate(zip(beat_times, onset_strengths)):
        if s >= threshold:
            strong.append({"time": float(t), "strength": float(s / max(max_strength, 1e-6))})

    # 优先选最强节拍，但保持时间顺序
    if len(strong) > max_beats:
        strong.sort(key=lambda x: x["strength"], reverse=True)
        strong = strong[:max_beats]
    strong.sort(key=lambda x: x["time"])
    return strong


def _extract_audio(video_path: str) -> str:
    """使用 ffmpeg 从视频中提取音频到临时 WAV 文件"""
    import subprocess

    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.close()

    try:
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '22050', '-ac', '1',
            tmp.name
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.getsize(tmp.name) > 1000:
            return tmp.name
    except Exception:
        pass

    try:
        os.unlink(tmp.name)
    except OSError:
        pass
    return ""
