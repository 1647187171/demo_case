from typing import Optional, Callable, Tuple, Dict, List, Any, Union
from .function.video_ai_effects import VideoAiEffectsCore

async def video_ai_effect(
    input_path: str,
    output_path: str,
    genre_hint: str = "",
    task_id: str = "",
    progress_callback: Optional[Callable] = None,
    master_name: str = ""
) -> Tuple[int, str]: 
    """
    AI 视频智能特效 API。
    """
    return await VideoAiEffectsCore.video_ai_effect(
        input_path=input_path,
        output_path=output_path,
        genre_hint=genre_hint,
        task_id=task_id,
        progress_callback=progress_callback
    )

def video_ai_effect_cancel_task(task_id: str) -> Tuple[int, str]:
    """
    取消指定的智能特效任务
    """
    return VideoAiEffectsCore.cancel_task(task_id)

def get_ass_subtitle_styles() -> Dict[str, Any]:
    """
    获取所有可用的 ASS 字幕样式列表 (121种, 16分类)
    """
    return VideoAiEffectsCore.get_available_styles()


