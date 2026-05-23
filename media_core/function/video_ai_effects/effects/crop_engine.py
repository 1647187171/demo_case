"""
crop_engine.py — 自动画幅适配引擎

支持 9:16 ↔ 16:9 ↔ 1:1 互转，利用视觉分析数据进行智能构图。
通过FFmpeg crop滤镜实现，跟踪主体位置保持构图。
"""
from typing import Optional, Tuple
from ..models import CropConfig, VisualAnalysisResult

# 宽高比预设
ASPECT_RATIOS = {
    "9:16": (9, 16),
    "16:9": (16, 9),
    "1:1": (1, 1),
    "4:5": (4, 5),
    "original": None,
}


def calculate_crop_region(
    src_width: int,
    src_height: int,
    target_ratio: Tuple[int, int],
    strategy: str = "center",
    subject_pos: Optional[Tuple[float, float]] = None,
) -> Tuple[int, int, int, int]:
    """计算裁剪区域

    Args:
        src_width, src_height: 原始分辨率
        target_ratio: 目标宽高比 (w, h)，如 (9, 16)
        strategy: "center", "top", "smart_center"
        subject_pos: 主体归一化位置 (x_frac, y_frac)，仅 smart_center 模式使用

    Returns:
        (crop_w, crop_h, crop_x, crop_y)
    """
    target_w_h = target_ratio[0] / target_ratio[1]
    src_ratio = src_width / src_height

    if abs(target_w_h - src_ratio) < 0.02:
        return (src_width, src_height, 0, 0)

    if src_ratio > target_w_h:
        # 源更宽：裁剪宽度
        crop_h = src_height
        crop_w = int(src_height * target_w_h)
        crop_w = crop_w - (crop_w % 2)
        crop_y = 0

        if strategy == "smart_center" and subject_pos:
            cx = subject_pos[0] * src_width
            crop_x = int(cx - crop_w / 2)
        elif strategy == "top":
            crop_x = (src_width - crop_w) // 2
        else:
            crop_x = (src_width - crop_w) // 2

        crop_x = max(0, min(crop_x, src_width - crop_w))
    else:
        # 源更高：裁剪高度
        crop_w = src_width
        crop_h = int(src_width / target_w_h)
        crop_h = crop_h - (crop_h % 2)
        crop_x = 0

        if strategy == "smart_center" and subject_pos:
            cy = subject_pos[1] * src_height
            crop_y = int(cy - crop_h / 2)
        elif strategy == "top":
            crop_y = 0
        else:
            crop_y = (src_height - crop_h) // 2

        crop_y = max(0, min(crop_y, src_height - crop_h))

    return (crop_w, crop_h, crop_x, crop_y)


def estimate_subject_position(
    visual_analysis: Optional[VisualAnalysisResult],
) -> Optional[Tuple[float, float]]:
    """从视觉分析结果估算主体位置

    根据检测到的物体类型粗略推断：
    - 人物 → 画面中上部
    - 食物 → 画面中央
    - 产品 → 画面中央

    Returns:
        (x_frac, y_frac) 或 None
    """
    if not visual_analysis or not visual_analysis.detected_objects:
        return None

    objects_lower = [o.lower() for o in visual_analysis.detected_objects]

    person_keywords = ["person", "man", "woman", "face", "人", "脸"]
    food_keywords = ["food", "dish", "plate", "bowl", "食", "菜", "盘"]
    product_keywords = ["product", "bottle", "phone", "laptop", "产", "手机", "电脑"]

    if any(kw in " ".join(objects_lower) for kw in person_keywords):
        return (0.5, 0.4)
    if any(kw in " ".join(objects_lower) for kw in food_keywords):
        return (0.5, 0.55)
    if any(kw in " ".join(objects_lower) for kw in product_keywords):
        return (0.5, 0.5)

    return None


def build_crop_filter(
    src_width: int,
    src_height: int,
    config: CropConfig,
    visual_analysis: Optional[VisualAnalysisResult] = None,
) -> str:
    """构建FFmpeg crop滤镜字符串

    Returns:
        "crop=w:h:x:y" 或空字符串（不需要裁剪时）
    """
    if not config.target_aspect or config.target_aspect == "original":
        return ""

    target = ASPECT_RATIOS.get(config.target_aspect)
    if not target:
        return ""

    strategy = config.strategy
    subject_pos = None
    if strategy == "smart_center" and config.use_visual_analysis:
        subject_pos = estimate_subject_position(visual_analysis)

    crop_w, crop_h, crop_x, crop_y = calculate_crop_region(
        src_width, src_height, target,
        strategy if subject_pos else "center",
        subject_pos,
    )

    if crop_w == src_width and crop_h == src_height:
        return ""

    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
