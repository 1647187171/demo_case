"""
bgm_library.py — 背景音乐库

管理可用BGM资源，提供按情绪/类型推荐BGM的功能。
"""
from typing import Optional, Dict, List
from pathlib import Path

from libs.media_core.utils import utils
from ..models import VisualAnalysisResult, VideoGenre


# BGM目录：情绪类型 → 文件信息
BGM_CATALOG: Dict[str, Dict] = {
    "upbeat_energy": {
        "file": "upbeat_01.mp3",
        "mood": "energetic",
        "genre_match": ["vlog", "fitness", "meme_comedy", "kids", "pets"],
        "tempo": "fast",
        "description": "快节奏活力BGM",
    },
    "upbeat_pop": {
        "file": "upbeat_02.mp3",
        "mood": "happy",
        "genre_match": ["food", "vlog", "fashion", "travel"],
        "tempo": "fast",
        "description": "欢快流行BGM",
    },
    "calm_soft": {
        "file": "calm_01.mp3",
        "mood": "calm",
        "genre_match": ["education", "corporate", "vlog", "cinematic"],
        "tempo": "slow",
        "description": "轻柔舒缓BGM",
    },
    "calm_warm": {
        "file": "calm_02.mp3",
        "mood": "warm",
        "genre_match": ["vlog", "food", "romance", "travel"],
        "tempo": "slow",
        "description": "温暖治愈BGM",
    },
    "cinematic_epic": {
        "file": "cinematic.mp3",
        "mood": "dramatic",
        "genre_match": ["cinematic", "gaming", "sports", "horror"],
        "tempo": "medium",
        "description": "电影感史诗BGM",
    },
    "minimal_clean": {
        "file": "minimal_01.mp3",
        "mood": "clean",
        "genre_match": ["corporate", "education", "tech", "news"],
        "tempo": "medium",
        "description": "简洁干净BGM",
    },
    "tech_modern": {
        "file": "tech_01.mp3",
        "mood": "modern",
        "genre_match": ["tech", "gaming", "education", "corporate"],
        "tempo": "medium",
        "description": "科技感现代BGM",
    },
}


def _get_bgm_dir() -> Path:
    """获取BGM资源目录路径"""
    try:
        project_root = Path(utils.get_project_root())
        bgm_dir = project_root / "res" / "effects" / "bgm"
        if bgm_dir.exists():
            return bgm_dir
    except Exception:
        pass
    return Path("res/effects/bgm")


def get_bgm(mood: str) -> Optional[str]:
    """根据情绪类型获取BGM文件路径

    Args:
        mood: 情绪类型（如 "upbeat_energy", "calm_soft"）

    Returns:
        BGM文件的绝对路径，不存在则返回 None
    """
    entry = BGM_CATALOG.get(mood)
    if not entry:
        return None
    bgm_dir = _get_bgm_dir()
    path = bgm_dir / entry["file"]
    if path.exists():
        return str(path)
    return None


def get_all_bgm() -> Dict[str, str]:
    """获取所有可用的BGM 映射"""
    result = {}
    for name, entry in BGM_CATALOG.items():
        path = get_bgm(name)
        if path:
            result[name] = path
    return result


def recommend_bgm(
    visual_analysis: Optional[VisualAnalysisResult] = None,
    genre: str = "",
    mood: str = "",
) -> Optional[str]:
    """根据视觉分析和视频类型推荐BGM

    Args:
        visual_analysis: 视觉分析结果
        genre: 视频类型
        mood: 情绪提示

    Returns:
        推荐的BGM文件路径
    """
    # 情绪优先级匹配
    candidates = []

    # 1. 根据mood直接匹配
    if mood:
        for name, entry in BGM_CATALOG.items():
            if mood.lower() in entry["mood"] or entry["mood"] in mood.lower():
                candidates.append((name, 2.0))

    # 2. 根据genre匹配
    if genre:
        for name, entry in BGM_CATALOG.items():
            if genre in entry["genre_match"]:
                candidates.append((name, 1.0))

    # 3. 根据视觉分析的情绪匹配
    if visual_analysis and visual_analysis.overall_mood:
        mood_lower = visual_analysis.overall_mood.lower()
        mood_map = {
            "energetic": ["upbeat_energy", "upbeat_pop"],
            "happy": ["upbeat_pop", "upbeat_energy"],
            "calm": ["calm_soft", "calm_warm", "minimal_clean"],
            "dramatic": ["cinematic_epic", "tech_modern"],
            "warm": ["calm_warm", "calm_soft"],
            "modern": ["tech_modern", "minimal_clean"],
            "clean": ["minimal_clean", "tech_modern"],
        }
        for m, names in mood_map.items():
            if m in mood_lower:
                for n in names:
                    candidates.append((n, 1.5))

    if not candidates:
        # 默认推荐
        return get_bgm("upbeat_energy")

    # 按权重排序，选择得分最高的
    scores = {}
    for name, weight in candidates:
        scores[name] = scores.get(name, 0) + weight
    best = max(scores, key=scores.get)
    return get_bgm(best)


def get_bgm_tempo(bgm_name: str) -> str:
    """获取BGM的节奏类型"""
    entry = BGM_CATALOG.get(bgm_name)
    return entry.get("tempo", "medium") if entry else "medium"
