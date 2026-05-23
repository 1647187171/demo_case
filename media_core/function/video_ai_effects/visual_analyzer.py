"""
visual_analyzer.py — 视频视觉分析模块

提取视频帧并通过 VL (Vision Language) 模型分析画面内容，
为特效编排提供视觉上下文信息。
"""
import os
import asyncio
import subprocess
import json
from typing import List, Optional, Tuple
from pathlib import Path

from media_core.utils import utils

from .models import VisualFrameAnalysis, VisualAnalysisResult


def extract_frames(
    video_path: str,
    interval_sec: float = 2.0,
    output_dir: str = "",
    max_frames: int = 30,
) -> List[str]:
    """从视频中提取帧图像

    Args:
        video_path: 视频文件路径
        interval_sec: 帧提取间隔（秒）
        output_dir: 输出目录（空则自动创建临时目录）
        max_frames: 最大帧数

    Returns:
        提取的帧文件路径列表
    """
    if not output_dir:
        output_dir = os.path.join(
            utils.get_project_root(), "workflow_output",
            "ai_effects_projects", f"frames_{os.getpid()}", "frames"
        )
    os.makedirs(output_dir, exist_ok=True)

    ffmpeg = utils.get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", f"fps=1/{interval_sec}",
        "-frames:v", str(max_frames),
        "-q:v", "2",
        os.path.join(output_dir, "frame_%04d.jpg"),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            return []
    except Exception:
        return []

    frames = sorted([
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])
    return frames


def detect_scene_transitions(video_path: str, threshold: float = 0.3) -> List[float]:
    """使用 FFmpeg 检测场景切换时间点

    Args:
        video_path: 视频文件路径
        threshold: 场景变化阈值（0-1）

    Returns:
        场景切换时间戳列表（秒）
    """
    ffmpeg = utils.get_ffmpeg_path()
    cmd = [
        ffmpeg, "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null", "-",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        timestamps = []
        for line in result.stderr.split("\n"):
            if "pts_time:" in line:
                try:
                    pts = line.split("pts_time:")[1].split()[0].strip()
                    timestamps.append(float(pts))
                except (IndexError, ValueError):
                    pass
        return timestamps
    except Exception:
        return []


def analyze_video_visuals(
    video_path: str,
    task_id: str = "",
    interval_sec: float = 2.0,
) -> Optional[VisualAnalysisResult]:
    """分析视频的视觉内容

    通过 VL 模型分析提取的视频帧，获取场景描述、物体检测、
    动作识别和情绪分析等视觉信息。

    Args:
        video_path: 视频文件路径
        task_id: 任务ID
        interval_sec: 帧提取间隔

    Returns:
        VisualAnalysisResult 或 None（分析失败时）
    """
    try:
        frames = extract_frames(video_path, interval_sec)
        if not frames:
            return None

        scene_changes = detect_scene_transitions(video_path)

        loop = _get_or_create_loop()
        result = loop.run_until_complete(_analyze_frames(frames, task_id))

        if not result:
            return _build_minimal_result(frames, scene_changes)

        result.scene_changes = scene_changes
        return result

    except Exception as e:
        utils.print2(f"[VisualAnalyzer] Error: {e}")
        return None


async def _analyze_frames(
    frame_paths: List[str],
    task_id: str = "",
) -> Optional[VisualAnalysisResult]:
    """异步分析帧图像"""
    try:
        from libs.media_core.function.vl.vl_analyzer_factory import create_vision_analyzer
        # from libs.media_core.function.vl.configs import get_config_manager
        from media_core.function.vl.configs import get_config_manager

        config_manager = get_config_manager()
        config = config_manager.create_run_config(
            asset_dirs=[os.path.dirname(frame_paths[0])],
            task_id=task_id or "vfx_va",
        )

        analyzer = create_vision_analyzer(config)

        # 场景描述分析
        desc_prompt = (
            "请用中文简要描述这张图片的内容，包括：场景类型、主要物体、人物动作、"
            "整体氛围（如活力、安静、紧张等）、色彩风格。用JSON格式输出："
            '{"scene_type":"","objects":[],"actions":[],"mood":"","colors":"","style":""}'
        )

        desc_results = await analyzer.analyze_images(
            images=frame_paths,
            prompt=desc_prompt,
            target_size=(384, 384),
        )

        # 解析结果
        frame_analyses = []
        all_objects = []
        all_actions = []
        moods = []

        for i, frame_result in enumerate(desc_results):
            timestamp = i * 2.0
            response = frame_result.get("response", "")
            if not response:
                continue

            parsed = _parse_frame_response(response, timestamp)
            frame_analyses.append(parsed)
            all_objects.extend(parsed.objects)
            all_actions.extend(parsed.actions)
            if parsed.mood:
                moods.append(parsed.mood)

        if not frame_analyses:
            return None

        # 汇总分析
        overall_mood = _most_common(moods) if moods else "neutral"
        dominant_scene = _most_common([f.scene_type for f in frame_analyses if f.scene_type]) or ""
        all_objects_unique = list(dict.fromkeys(all_objects))[:20]
        all_actions_unique = list(dict.fromkeys(all_actions))[:10]

        summary = _generate_summary(frame_analyses, overall_mood, dominant_scene)

        return VisualAnalysisResult(
            frames=frame_analyses,
            overall_mood=overall_mood,
            dominant_scene_type=dominant_scene,
            detected_objects=all_objects_unique,
            detected_actions=all_actions_unique,
            visual_style=frame_analyses[0].style_tags[0] if frame_analyses and frame_analyses[0].style_tags else "",
            summary=summary,
        )

    except Exception as e:
        utils.print2(f"[VisualAnalyzer] VL analysis error: {e}")
        return None


def _parse_frame_response(response: str, timestamp: float) -> VisualFrameAnalysis:
    """解析 VL 模型返回的帧分析结果"""
    analysis = VisualFrameAnalysis(timestamp=timestamp)

    try:
        # 尝试提取JSON
        result = utils.extract_json_from_response(response)
        if result:
            analysis.scene_type = result.get("scene_type", "")
            analysis.objects = result.get("objects", [])[:10]
            analysis.actions = result.get("actions", [])[:5]
            analysis.mood = result.get("mood", "")
            style = result.get("style", "")
            if style:
                analysis.style_tags = [style]
            return analysis
    except Exception:
        pass

    # 降级：从文本中提取关键词
    text_lower = response.lower()
    mood_keywords = {
        "活力": "energetic", "安静": "calm", "紧张": "tense",
        "欢乐": "happy", "悲伤": "sad", "浪漫": "romantic",
        "戏剧": "dramatic", "energetic": "energetic", "calm": "calm",
        "happy": "happy", "dramatic": "dramatic", "fun": "funny",
    }
    for kw, mood in mood_keywords.items():
        if kw in text_lower:
            analysis.mood = mood
            break

    analysis.description = response[:200]
    return analysis


def _build_minimal_result(frames: List[str], scene_changes: List[float]) -> VisualAnalysisResult:
    """当 VL 分析失败时，构建最小化结果"""
    return VisualAnalysisResult(
        scene_changes=scene_changes,
        overall_mood="neutral",
        summary=f"视频包含 {len(frames)} 个采样帧，{len(scene_changes)} 个场景切换",
    )


def _generate_summary(frames: List[VisualFrameAnalysis], mood: str, scene_type: str) -> str:
    """生成视觉分析摘要"""
    parts = []
    if scene_type:
        parts.append(f"主要场景: {scene_type}")
    if mood:
        parts.append(f"整体氛围: {mood}")
    objects = list(dict.fromkeys(o for f in frames for o in f.objects))[:5]
    if objects:
        parts.append(f"主要物体: {', '.join(objects)}")
    actions = list(dict.fromkeys(a for f in frames for a in f.actions))[:3]
    if actions:
        parts.append(f"主要动作: {', '.join(actions)}")
    return "；".join(parts) if parts else "视觉分析完成"


def _most_common(lst: List[str]) -> str:
    """获取列表中最常见的元素"""
    if not lst:
        return ""
    from collections import Counter
    return Counter(lst).most_common(1)[0][0]


def _get_or_create_loop():
    """获取或创建事件循环"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
