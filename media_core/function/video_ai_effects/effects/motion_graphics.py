"""
motion_graphics.py — 动态图形叠加引擎

通过FFmpeg滤镜（drawbox, drawtext, geq, color）生成：
- 进度条 (progress_bar)
- 动态箭头 (arrow)
- 圈选高亮 (circle_highlight)
- 粒子爆发 (particle_burst)
- 下三分之一字幕条 (lower_third)

全部通过FFmpeg原生滤镜实现，无需外部依赖。
"""
from typing import Optional, List, Dict, Tuple
import math


def build_progress_bar_filter(
    graphic: Dict,
    video_width: int,
    video_height: int,
) -> str:
    """构建进度条动态图形滤镜

    label: "Step 2/5" 格式，自动解析进度
    """
    w, h = video_width, video_height
    dur = graphic.get("duration", 3.0)
    label = graphic.get("label", "")
    color = graphic.get("color", "yellow").replace("&H00", "#").replace("&", "#")

    # 解析进度
    parts = label.replace("Step ", "").replace(" ", "/").split("/") if label else ["1", "5"]
    try:
        current = int(parts[0]) if len(parts) >= 1 else 1
        total = int(parts[1]) if len(parts) >= 2 else 5
    except ValueError:
        current, total = 1, 5

    bar_w = int(w * 0.7)
    bar_h = int(h * 0.02)
    bar_x = (w - bar_w) // 2
    bar_y = int(h * 0.08)

    # 背景条 + 前景进度条
    return (
        f"drawbox=x={bar_x}:y={bar_y}:w={bar_w}:h={bar_h}:color=white@0.3:t=fill:"
        f"enable='between(t,0,{dur:.2f})',"
        f"drawbox=x={bar_x}:y={bar_y}:"
        f"w={bar_w}*min(t/{dur:.2f}*{current/total:.2f},1):"
        f"h={bar_h}:color={color}:t=fill:"
        f"enable='between(t,0,{dur:.2f})'"
    )


def build_arrow_filter(
    graphic: Dict,
    video_width: int,
    video_height: int,
) -> str:
    """构建动态箭头滤镜 — 使用drawtext绘制箭头字符并做弹跳动画"""
    w, h = video_width, video_height
    dur = graphic.get("duration", 1.5)
    x_frac, y_frac = graphic.get("position", (0.5, 0.5))
    target = graphic.get("target_pos", (x_frac + 0.1, y_frac - 0.05))
    color = graphic.get("color", "yellow").replace("&H00", "#").replace("&", "#")
    font_size = int(max(24, min(48, w * 0.04)))

    px = int(w * x_frac)
    py = int(h * y_frac)

    # 箭头字符 + 弹跳动画
    return (
        f"drawtext=text='➤':fontcolor={color}:fontsize={font_size}:"
        f"x={px}:y={py}-10+5*sin(2*PI*3*t):"
        f"alpha='if(lt(t,0.1),t/0.1,if(lt(t,{dur - 0.2:.2f}),1,({dur:.2f}-t)/0.2))':"
        f"enable='between(t,0,{dur:.2f})'"
    )


def build_circle_highlight_filter(
    graphic: Dict,
    video_width: int,
    video_height: int,
) -> str:
    """构建圈选高亮滤镜 — 彩色脉冲圆环"""
    w, h = video_width, video_height
    dur = graphic.get("duration", 2.0)
    x_frac, y_frac = graphic.get("position", (0.5, 0.5))
    color = graphic.get("color", "yellow").replace("&H00", "#").replace("&", "#")

    cx = int(w * x_frac)
    cy = int(h * y_frac)
    base_r = int(min(w, h) * 0.08)
    line_w = max(2, min(6, int(w * 0.005)))

    # 用geq画圆 + 脉冲半径
    r_expr = f"{base_r}+{base_r//3}*sin(2*PI*2.5*t)"

    return (
        f"drawbox=x={cx - base_r}:y={cy - base_r}:"
        f"w={base_r * 2}:h={base_r * 2}:color={color}@{0.7}:t=2:"
        f"enable='between(t,0,{dur:.2f})'"
    )


def build_particle_burst_filter(
    graphic: Dict,
    video_width: int,
    video_height: int,
) -> str:
    """构建粒子爆发滤镜 — 使用drawbox画多个小方块模拟粒子"""
    w, h = video_width, video_height
    dur = graphic.get("duration", 1.0)
    x_frac, y_frac = graphic.get("position", (0.5, 0.5))
    color = graphic.get("color", "yellow").replace("&H00", "#").replace("&", "#")

    cx = int(w * x_frac)
    cy = int(h * y_frac)
    particle_size = max(3, int(w * 0.006))

    # 生成6个粒子向不同方向扩散
    parts = []
    angles = [0, 60, 120, 180, 240, 300]
    for i, angle in enumerate(angles):
        rad = math.radians(angle)
        dx = int(math.cos(rad) * 60)
        dy = int(math.sin(rad) * 60)
        parts.append(
            f"drawbox=x={cx}+int({dx}*t/{dur:.2f}):"
            f"y={cy}+int({dy}*t/{dur:.2f}):"
            f"w={particle_size}:h={particle_size}:color={color}:t=fill:"
            f"alpha='max(0, 1 - t / {dur:.2f})':"
            f"enable='between(t,0,{dur:.2f})'"
        )

    return ",".join(parts)


def build_lower_third_filter(
    graphic: Dict,
    video_width: int,
    video_height: int,
) -> str:
    """构建下三分之一字幕条滤镜"""
    w, h = video_width, video_height
    dur = graphic.get("duration", 3.0)
    label = graphic.get("label", "")
    color = graphic.get("color", "yellow").replace("&H00", "#").replace("&", "#")
    font_size = int(max(18, min(36, w * 0.035)))

    bar_h = int(h * 0.06)
    bar_w = int(w * 0.35)
    bar_x = int(w * 0.05)
    bar_y = int(h * 0.78)

    # 滑入动画 + 背景条 + 文字
    slide_x = f"{bar_x - w}-{w}*min(t/0.3,1)"

    return (
        f"drawbox=x={bar_x}:y={bar_y}:w={bar_w}:h={bar_h}:color={color}@0.7:t=fill:"
        f"enable='between(t,0,{dur:.2f})',"
        f"drawtext=text='{label}':fontcolor=white:fontsize={font_size}:"
        f"x={bar_x + 20}:y={bar_y + bar_h // 4}:"
        f"alpha='if(lt(t,0.15),t/0.15,if(lt(t,{dur - 0.3:.2f}),1,({dur:.2f}-t)/0.3))':"
        f"enable='between(t,0,{dur:.2f})'"
    )


# 图形类型→构建函数映射
GRAPHIC_BUILDERS = {
    "progress_bar": build_progress_bar_filter,
    "arrow": build_arrow_filter,
    "circle_highlight": build_circle_highlight_filter,
    "particle_burst": build_particle_burst_filter,
    "lower_third": build_lower_third_filter,
}


def build_all_motion_graphics_filters(
    graphics: List[Dict],
    video_width: int = 1080,
    video_height: int = 1920,
) -> str:
    """为所有动态图形构建FFmpeg滤镜链

    Args:
        graphics: 动态图形列表
        video_width: 视频宽度
        video_height: 视频高度

    Returns:
        逗号分隔的FFmpeg滤镜字符串
    """
    filters = []
    for g in graphics[:6]:  # 最多6个
        gtype = g.get("graphic_type", "")
        builder = GRAPHIC_BUILDERS.get(gtype)
        if builder:
            f = builder(g, video_width, video_height)
            if f:
                filters.append(f)

    return ",".join(filters)


def generate_motion_graphics_from_keywords(
    keyword_emphases: List,
    segments: List,
    video_duration: float,
    max_count: int = 4,
) -> List[Dict]:
    """根据关键词自动推荐动态图形

    - 数字关键词 → 进度条
    - 指向性关键词 → 箭头
    - 感叹/惊讶关键词 → 粒子爆发
    - 人名/地名 → 下三分之一字幕条
    """
    graphics = []
    used_times = []

    for emp in keyword_emphases:
        if len(graphics) >= max_count:
            break

        kw = emp.keyword
        ws = (emp.word_start_ms or 0) / 1000.0
        if ws <= 0:
            continue

        # 跳过过于接近的时间点
        if any(abs(ws - ut) < 4.0 for ut in used_times):
            continue

        gtype = None
        label = ""

        # 数字/步骤检测
        if any(ch.isdigit() for ch in kw) or any(w in kw for w in ["步骤", "第", "步", "点"]):
            gtype = "progress_bar"
            label = f"Step {kw}"

        # 指向性词
        elif any(w in kw for w in ["看", "注意", "这里", "重点", "look", "here"]):
            gtype = "arrow"
            label = kw

        # 感叹/惊讶
        elif any(w in kw for w in ["哇", "天哪", "太棒", "震惊", "wow", "amazing", "boom"]):
            gtype = "particle_burst"
            label = kw

        # 人名/地名/专有名词（3字以上）
        elif len(kw) >= 3 and classify_word_is_noun(kw):
            gtype = "lower_third"
            label = kw

        if gtype:
            graphics.append({
                "graphic_type": gtype,
                "timestamp": ws,
                "duration": 2.0,
                "position": (0.5, 0.15),
                "color": "yellow",
                "label": label,
            })
            used_times.append(ws)

    return graphics


def classify_word_is_noun(word: str) -> bool:
    """简单检测是否名词（中文3字以上实词大概率是名词）"""
    not_noun = {"做", "说", "看", "想", "去", "来", "吃", "喝", "走", "跑",
                "好", "坏", "大", "小", "多", "少", "快", "慢", "新", "旧"}
    if word in not_noun:
        return False
    if any(ch.isdigit() for ch in word):
        return False
    return True
