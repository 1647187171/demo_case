"""
huazi_presets.py — 花字/关键词强调ASS预设

提供社交平台常用的关键词视觉强调效果，通过ASS内联覆盖标签实现。
每种预设将关键词文本包裹在动态ASS标签中，形成花字效果。
"""
from typing import Optional

from ..models import KeywordEmphasis


def apply_huazi(keyword_text: str, emphasis: KeywordEmphasis,
                seg_start_ms: int = 0, seg_end_ms: int = 0) -> str:
    """根据预设类型对关键词应用花字效果

    Args:
        keyword_text: 要强调的关键词文本（已转义）
        emphasis: 关键词强调配置
        seg_start_ms: 字幕片段起始时间(ms)
        seg_end_ms: 字幕片段结束时间(ms)

    Returns:
        包含ASS覆盖标签的关键词文本
    """
    preset_fn = PRESETS.get(emphasis.preset)
    if not preset_fn:
        return _default_highlight(keyword_text, emphasis)
    return preset_fn(keyword_text, emphasis, seg_start_ms, seg_end_ms)


def _default_highlight(text: str, e: KeywordEmphasis, *_args) -> str:
    """默认高亮：换色 + 加粗 + 放大"""
    scale = int(e.scale * 100)
    color = e.color
    outline = ""
    if e.outline_color:
        outline = f"\\3c{e.outline_color}"
    if e.outline_width:
        outline += f"\\bord{e.outline_width}"
    emoji = e.emoji or ""
    return f"{{\\c{color}{outline}\\fscx{scale}\\fscy{scale}}}{text}{emoji}{{\\r}}"


def _pop_highlight(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """弹出高亮：关键词先缩小再放大弹出"""
    scale = int(e.scale * 100)
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    t1 = dur // 3
    t2 = t1 * 2
    color = e.color
    emoji = e.emoji or ""
    return (
        f"{{\\c{color}\\be1\\shad2\\fscx60\\fscy60}}"
        f"{{\\t(0,{t1},\\fscx{scale}\\fscy{scale})}}"
        f"{{\\t({t1},{t2},\\fscx{min(scale + 10, 150)}\\fscy{min(scale + 10, 150)})}}"
        f"{{\\t({t2},{dur},\\fscx{scale}\\fscy{scale})}}"
        f"{text}{emoji}{{\\r}}"
    )


def _glow_emphasis(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """发光强调：关键词产生脉冲发光效果"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    half = dur // 2
    color = e.color
    emoji = e.emoji or ""
    return (
        f"{{\\c{color}\\blur2}}"
        f"{{\\t(0,{half},\\blur6\\1c{color})}}"
        f"{{\\t({half},{dur},\\blur2)}}"
        f"{text}{emoji}{{\\r}}"
    )


def _shake_word(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """抖动强调：关键词产生快速抖动效果"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    color = e.color
    scale = int(e.scale * 100)
    parts = [f"{{\\c{color}\\fscx{scale}\\fscy{scale}}}"]
    step = 50
    for offset in range(0, min(dur, 300), step):
        dx = 4 if (offset // step) % 2 == 0 else -4
        dy = 2 if (offset // step) % 2 == 0 else -2
        parts.append(f"{{\\t({offset},{offset + step},\\pos({dx},{dy}))}}")
    emoji = e.emoji or ""
    parts.append(f"{text}{emoji}{{\\r}}")
    return "".join(parts)


def _color_flash(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """颜色闪烁：关键词在两种颜色之间快速切换"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    color1 = e.color
    color2 = e.outline_color or "&H00FF00FF"
    scale = int(e.scale * 100)
    colors = [color1, color2]
    step = dur // 6
    parts = [f"{{\\fscx{scale}\\fscy{scale}\\c{color1}}}"]
    for i in range(6):
        c = colors[i % 2]
        t = i * step
        parts.append(f"{{\\t({t},{t + step},\\c{c})}}")
    emoji = e.emoji or ""
    parts.append(f"{text}{emoji}{{\\r}}")
    return "".join(parts)


def _bounce_letter(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """逐字弹跳：关键词的每个字符依次弹跳"""
    color = e.color
    scale = int(e.scale * 100)
    dur_per_char = min(e.duration_ms // max(len(text), 1), 200)
    chars = list(text)
    parts = []
    for i, ch in enumerate(chars):
        t_start = i * dur_per_char
        half = dur_per_char // 2
        peak = min(scale + 20, 160)
        parts.append(
            f"{{\\c{color}}}"
            f"{{\\t({t_start},{t_start + half},\\fscx{peak}\\fscy{peak})}}"
            f"{{\\t({t_start + half},{t_start + dur_per_char},\\fscx{scale}\\fscy{scale})}}"
            f"{ch}"
        )
    emoji = e.emoji or ""
    parts.append(f"{emoji}{{\\r}}")
    return "".join(parts)


def _gradient_fill(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """渐变填充：关键词颜色呈彩虹渐变"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    scale = int(e.scale * 100)
    colors = ["&H000000FF", "&H0000FF00", "&H00FF0000", "&H0000FFFF", "&H00FF00FF", "&H00FFFF00"]
    n_colors = len(colors)
    step = dur // n_colors
    parts = [f"{{\\fscx{scale}\\fscy{scale}}}"]
    for i, color in enumerate(colors):
        t_start = i * step
        t_end = (i + 1) * step
        parts.append(f"{{\\t({t_start},{t_end},\\c{color})}}")
    emoji = e.emoji or ""
    parts.append(f"{text}{emoji}{{\\r}}")
    return "".join(parts)


def _box_highlight(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """框线高亮：关键词用彩色背景框包围"""
    color = e.color
    bg = e.bg_color or "&H80000000"
    border_w = e.outline_width or 2.0
    scale = int(e.scale * 100)
    padding = e.bg_padding
    # 用ASS的边框色(3c) + 边框宽(bord)模拟背景框效果
    return (
        f"{{\\c{color}\\3c{bg}\\3a&H60&\\bord{border_w + padding}\\fscx{scale}\\fscy{scale}}}"
        f"{text}"
        f"{{\\r}}"
    )


def _underline_sweep(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """下划线扫过：关键词下方有一条线扫过"""
    color = e.color
    scale = int(e.scale * 100)
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    # 通过颜色渐变模拟下划线效果
    return (
        f"{{\\c{color}\\fscx{scale}\\fscy{scale}\\3c&H00000000\\bord{e.outline_width or 2.0}}}"
        f"{{\\t(0,{dur},\\3c{color})}}"
        f"{text}"
        f"{{\\r}}"
    )


def _scale_pulse(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """缩放脉冲：关键词反复放大缩小"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    color = e.color
    scale = int(e.scale * 100)
    peak = min(scale + 15, 150)
    quarter = dur // 4
    emoji = e.emoji or ""
    return (
        f"{{\\c{color}}}"
        f"{{\\t(0,{quarter},\\fscx{peak}\\fscy{peak})}}"
        f"{{\\t({quarter},{quarter * 2},\\fscx{scale}\\fscy{scale})}}"
        f"{{\\t({quarter * 2},{quarter * 3},\\fscx{peak}\\fscy{peak})}}"
        f"{{\\t({quarter * 3},{dur},\\fscx{scale}\\fscy{scale})}}"
        f"{text}{emoji}{{\\r}}"
    )


def _emoji_pop(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """表情弹出：关键词后弹出一个表情符号"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    color = e.color
    scale = int(e.scale * 100)
    emoji = e.emoji or "✨"
    half = dur // 2
    return (
        f"{{\\c{color}\\fscx{scale}\\fscy{scale}}}"
        f"{text}"
        f"{{\\fscx30\\fscy30}}"
        f"{{\\t({half},{dur},\\fscx80\\fscy80)}}"
        f"{emoji}"
        f"{{\\r}}"
    )


def _neon_flash(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """霓虹闪烁：关键词像霓虹灯一样闪烁"""
    dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    color = e.color
    scale = int(e.scale * 100)
    step = dur // 8
    parts = [f"{{\\c{color}\\fscx{scale}\\fscy{scale}\\be2}}"]
    for i in range(8):
        alpha = "&H00" if i % 2 == 0 else "&H80"
        t = i * step
        parts.append(f"{{\\t({t},{t + step},\\1a{alpha})}}")
    parts.append(f"{text}{{\\r}}")
    return "".join(parts)


def _typewriter_reveal(text: str, e: KeywordEmphasis, start_ms: int, end_ms: int) -> str:
    """打字机揭示：关键词逐字显示"""
    color = e.color
    scale = int(e.scale * 100)
    chars = list(text)
    total_dur = min(e.duration_ms, end_ms - start_ms) if end_ms > start_ms else e.duration_ms
    per_char = max(30, total_dur // max(len(chars), 1))
    parts = []
    for i, ch in enumerate(chars):
        t_show = i * per_char
        parts.append(
            f"{{\\c{color}\\fscx{scale}\\fscy{scale}\\alpha&HFF&}}"
            f"{{\\t({t_show},{t_show + 30},\\alpha&H00&)}}"
            f"{ch}"
        )
    emoji = e.emoji or ""
    parts.append(f"{emoji}{{\\r}}")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 预设注册表
# ---------------------------------------------------------------------------

PRESETS = {
    "pop_highlight": _pop_highlight,
    "glow_emphasis": _glow_emphasis,
    "shake_word": _shake_word,
    "color_flash": _color_flash,
    "bounce_letter": _bounce_letter,
    "gradient_fill": _gradient_fill,
    "box_highlight": _box_highlight,
    "underline_sweep": _underline_sweep,
    "scale_pulse": _scale_pulse,
    "emoji_pop": _emoji_pop,
    "neon_flash": _neon_flash,
    "typewriter_reveal": _typewriter_reveal,
}

PRESET_NAMES = list(PRESETS.keys())

# 默认花字颜色方案（按类型）
DEFAULT_HUAZI_COLORS = {
    "food": "&H000088FF",        # 橙色
    "fitness": "&H000000FF",     # 红色
    "gaming": "&H00FF0000",      # 蓝色
    "comedy": "&H0000FFFF",      # 黄色
    "education": "&H0000FF00",   # 绿色
    "fashion": "&H00FF00FF",     # 紫红
    "travel": "&H00FF8000",      # 天蓝
    "tech": "&H00FF0000",        # 蓝色
    "music": "&H00FF00FF",       # 紫红
    "vlog": "&H0000FFFF",        # 黄色
    "cinematic": "&H00FFFFFF",   # 白色
    "motivation": "&H000000FF",  # 红色
    "news": "&H000000FF",        # 红色
    "kids": "&H00FF00FF",        # 紫红
    "corporate": "&H0000FF00",   # 绿色
    "default": "&H0000FFFF",     # 黄色
}


def get_default_color_for_genre(genre: str) -> str:
    """根据视频类型获取默认花字颜色"""
    return DEFAULT_HUAZI_COLORS.get(genre, DEFAULT_HUAZI_COLORS["default"])


# ---------------------------------------------------------------------------
# 关键词 → Emoji 自动映射表
# ---------------------------------------------------------------------------

KEYWORD_EMOJI_MAP = {
    # 动作/行为
    "推荐": "👍", "分享": "📢", "关注": "👀", "收藏": "⭐", "点赞": "❤️",
    "赚钱": "💰", "投资": "📈", "创业": "🚀", "学习": "📚", "成长": "🌱",
    "改变": "🔄", "突破": "🚀", "创新": "💡", "颠覆": "💥", "逆袭": "🔥",
    "坚持": "💪", "努力": "💪", "奋斗": "💪", "拼搏": "💪", "成功": "🏆",
    "选择": "🎯", "决定": "🎯", "掌握": "🎯", "实现": "✨",
    "解决": "🔧", "提高": "📈", "降低": "📉", "增加": "⬆️", "减少": "⬇️",
    "开始": "🎬", "结束": "🏁", "发现": "🔍", "证明": "✅", "展示": "👁️",
    "打造": "🔨", "构建": "🏗️", "设计": "🎨", "优化": "⚡", "升级": "⬆️",
    "吃": "🍔", "喝": "🥤", "睡": "😴", "跑": "🏃", "飞": "✈️",
    "笑": "😂", "哭": "😭", "赢": "🏆", "打": "👊",
    # 名词/事物
    "机会": "🎯", "方法": "📋", "技巧": "💡", "秘诀": "🤫", "策略": "♟️",
    "趋势": "📈", "未来": "🔮", "世界": "🌍", "市场": "🏪", "行业": "🏭",
    "技术": "💻", "产品": "📦", "服务": "🤝", "平台": "🌐", "系统": "⚙️",
    "资源": "📚", "工具": "🔧", "数据": "📊", "信息": "💡", "知识": "📖",
    "价值": "💎", "质量": "✨", "效果": "✅", "结果": "📊", "目标": "🎯",
    "梦想": "🌟", "理想": "🌈", "自由": "🕊️", "快乐": "😊", "幸福": "❤️",
    "财富": "💰", "健康": "💚", "美丽": "🌹", "力量": "💪", "智慧": "🧠",
    "问题": "❓", "挑战": "🏔️", "危机": "⚠️", "风险": "🎲", "困难": "🧱",
    "钱": "💰", "免费": "🎁", "优惠": "🏷️", "打折": "💸", "折扣": "💸",
    "美食": "🍜", "旅行": "✈️", "电影": "🎬", "音乐": "🎵",
    "游戏": "🎮", "运动": "⚽", "健身": "💪", "宠物": "🐱",
    "猫": "🐱", "狗": "🐶", "孩子": "👶", "家": "🏠",
    "手机": "📱", "电脑": "💻", "车": "🚗",
    # 形容词/评价
    "厉害": "💪", "强大": "💪", "优秀": "🌟", "完美": "💯", "惊艳": "✨",
    "震撼": "😱", "独特": "🎯", "专业": "👨‍💼", "顶级": "👑", "大气": "🌟",
    "重要": "❗", "必须": "💪", "关键": "🔑", "核心": "💎",
    "必要": "✅", "真实": "💯", "靠谱": "👍",
    "神奇": "✨", "恐怖": "😱", "搞笑": "😂", "浪漫": "💕", "经典": "👑",
    "豪华": "💎", "奢侈": "💰", "精致": "✨", "高端": "👑",
    "大": "⬆️", "小": "⬇️", "多": "📈", "少": "📉",
    "快": "⚡", "慢": "🐢", "热": "🔥", "冷": "❄️",
    "新": "🆕", "好": "👍", "美": "🌹", "最好": "🏆",
    "第一": "🥇", "最大": "🏆", "最快": "⚡", "最新": "🆕",
    "独家": "⭐", "限时": "⏰", "首次": "🎊",
    # 情绪词
    "震惊": "😱", "惊喜": "🎁", "感动": "🥺", "兴奋": "🤩", "激动": "💓",
    "愤怒": "😡", "焦虑": "😰", "期待": "🤩", "开心": "😄", "害怕": "😨",
    "希望": "🌈", "自信": "💪", "骄傲": "🦚", "满足": "😌",
    "好看": "😍", "好吃": "😋", "好玩": "🎉", "好棒": "👏",
    # 程度/数量
    "万": "🔥", "亿": "🤯", "倍": "⚡", "超级": "🔥", "非常": "🔥",
    "特别": "⭐", "极其": "🔥", "相当": "💪", "十分": "💯",
    # 英文关键词
    "amazing": "🤩", "best": "🏆", "free": "🎁", "new": "🆕", "top": "🔝",
    "must": "💪", "wow": "😮", "cool": "😎", "hot": "🔥", "big": "⬆️",
    "fast": "⚡", "love": "❤️", "win": "🏆", "pro": "👑", "epic": "🔥",
    "crazy": "🤪", "wow": "😮", "boom": "💥", "go": "🏃", "yes": "✅",
    "no": "❌", "ok": "👌", "hey": "👋", "wow": "😮", "super": "🦸",
}


def auto_assign_emoji(keyword: str) -> str:
    """根据关键词自动分配emoji，无匹配则随机一个"""
    kw_lower = keyword.lower()
    for k, v in KEYWORD_EMOJI_MAP.items():
        if k in kw_lower or kw_lower in k:
            return v
    import random
    return random.choice(["✨", "💥", "🔥", "💫", "⚡", "🌟", "❗", "💯", "🎯"])


# 花字预设轮转列表（用于自动分配变化的预设）
PRESET_ROTATION = [
    "pop_highlight", "emoji_pop", "scale_pulse",
    "bounce_letter", "glow_emphasis", "color_flash",
    "box_highlight", "neon_flash",
]
