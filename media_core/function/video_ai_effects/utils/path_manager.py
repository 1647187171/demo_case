"""
path_manager.py — 特效项目路径管理器

管理特效任务的临时目录结构（ASS、SRT、音频、输出、临时文件），
提供目录创建和清理功能。
"""
import shutil
from pathlib import Path
from typing import Dict, Optional

from libs.media_core.utils import utils


class EffectsPathManager:
    """特效项目路径管理器

    为每个任务创建独立的目录结构，包含 ass、srt、audio、output、temp 子目录。
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.project_dir = self._resolve_project_dir(task_id)
        self.directory_structure: Dict[str, Path] = {
            "project_dir": self.project_dir,
            "ass_dir": self.project_dir / "ass",
            "srt_dir": self.project_dir / "srt",
            "audio_dir": self.project_dir / "audio",
            "output_dir": self.project_dir / "output",
            "temp_dir": self.project_dir / "temp",
        }
        self.ensure_directories()

    @staticmethod
    def _resolve_project_dir(task_id: str) -> Path:
        try:
            project_root = Path(utils.get_project_root())
            candidate = project_root / "workflow_output" / "ai_effects_projects" / task_id
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except (PermissionError, OSError):
            fallback = Path("/tmp") / "ai_effects_projects" / task_id
            fallback.mkdir(parents=True, exist_ok=True)
            return fallback

    def ensure_directories(self):
        """确保所有目录存在"""
        for dir_path in self.directory_structure.values():
            dir_path.mkdir(parents=True, exist_ok=True)

    def get_path(self, dir_name: str) -> Path:
        """按名称获取目录路径"""
        return self.directory_structure[dir_name]

    def get_ass_path(self, filename: str = "subtitle.ass") -> Path:
        """获取ASS字幕文件路径"""
        return self.directory_structure["ass_dir"] / filename

    def get_output_path(self, filename: str = "output.mp4") -> Path:
        """获取输出文件路径"""
        return self.directory_structure["output_dir"] / filename

    def cleanup(self):
        """清理临时目录（保留项目根目录和输出目录）"""
        for name in ["ass_dir", "srt_dir", "audio_dir", "temp_dir"]:
            p = self.directory_structure.get(name)
            if p and p.exists():
                shutil.rmtree(p, ignore_errors=True)
