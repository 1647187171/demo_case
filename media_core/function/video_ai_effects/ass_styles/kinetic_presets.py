"""
kinetic_presets.py — 动态排版预设

提供词级动画效果、按词性着色、重要性评分、多位置字幕分布。
用于ASS字幕生成中的逐词渲染，实现"kinetic typography"效果。
"""
from typing import Optional, List, Dict, Tuple
import re

# ---------------------------------------------------------------------------
# 词性→颜色映射（中文语义色）
# ---------------------------------------------------------------------------

POS_COLOR_MAP = {
    "noun": "&H00FF8040&",      # 暖橙 — 名词/实物
    "verb": "&H0040A0FF&",      # 冷蓝 — 动词/动作
    "adjective": "&H00FF40FF&", # 亮紫 — 形容词/修饰
    "number": "&H0000FF00&",    # 绿色 — 数字/量化
    "adverb": "&H00FFC040&",    # 金色 — 副词
    "exclamation": "&H000040FF&", # 红色 — 感叹词
    "default": "&H0000FFFF&",   # 黄色 — 默认
}

# 高频中文动词
CN_VERBS = {
    "做", "说", "看", "想", "去", "来", "吃", "喝", "走", "跑", "飞",
    "买", "卖", "给", "拿", "放", "打", "开", "关", "写", "读", "听",
    "学", "教", "用", "找", "等", "让", "叫", "问", "回", "出", "进",
    "上", "下", "过", "起", "到", "发", "收", "推", "拉", "转", "跳",
    "笑", "哭", "唱", "弹", "画", "拍", "剪", "装", "修", "改", "变",
    "选", "赢", "输", "帮", "救", "追", "赶", "停", "动", "试", "练",
    "讲", "解", "播", "录", "传", "送", "换", "交", "带", "搬", "移",
    "推荐", "分享", "关注", "收藏", "点赞", "投资", "创业", "学习",
    "成长", "改变", "突破", "创新", "颠覆", "坚持", "努力", "奋斗",
    "选择", "决定", "掌握", "实现", "解决", "提高", "降低", "增加",
    "减少", "开始", "发现", "证明", "展示", "打造", "构建", "设计",
    "优化", "升级",
}

# 高频中文形容词
CN_ADJECTIVES = {
    "好", "坏", "大", "小", "多", "少", "快", "慢", "新", "旧",
    "高", "低", "长", "短", "远", "近", "冷", "热", "美", "丑",
    "强", "弱", "难", "易", "贵", "便宜", "深", "浅", "轻", "重",
    "厉害", "强大", "优秀", "完美", "惊艳", "震撼", "独特", "专业",
    "顶级", "重要", "必须", "关键", "核心", "真实", "靠谱",
    "神奇", "恐怖", "搞笑", "浪漫", "经典", "豪华", "精致", "高端",
    "好看", "好吃", "好玩",
}

# 高频中文感叹词
CN_EXCLAMATIONS = {
    "哇", "啊", "呀", "哦", "哈", "嘿", "嗯", "哼", "诶",
    "天哪", "太棒了", "不可思议", "厉害了", "绝了",
    "震惊", "惊喜", "感动", "兴奋",
}

# 高频中文数字/量化词
CN_NUMBERS_PATTERN = re.compile(
    r'[\d.]+[%倍万千亿百十]?|第[一二三四五六七八九十\d]+|[一二三四五六七八九十百千万亿]+'
)


def classify_word_type(word: str) -> str:
    """分类中文词性（简化版：基于高频词表+规则）

    Returns: "noun", "verb", "adjective", "number", "exclamation", "adverb", "default"
    """
    if not word:
        return "default"

    # 数字检测
    if CN_NUMBERS_PATTERN.fullmatch(word):
        return "number"
    if word.isdigit() or re.match(r'^[\d.]+$', word):
        return "number"

    if word in CN_EXCLAMATIONS:
        return "exclamation"
    if word in CN_VERBS:
        return "verb"
    if word in CN_ADJECTIVES:
        return "adjective"

    # 英文词性判断
    if word.isascii():
        if word.endswith("ly"):
            return "adverb"
        if word.endswith("ing") or word.endswith("ed"):
            return "verb"
        if word.endswith("est") or word.endswith("er"):
            return "adjective"
        # 常见英文词
        en_verbs = {"is", "are", "was", "were", "be", "do", "does", "did", "go", "get", "make", "know", "think", "take", "see", "come", "want", "use", "find", "give", "tell", "work", "call", "try", "ask", "need", "feel", "become"}
        en_adjs = {"good", "new", "big", "old", "great", "high", "small", "large", "long", "best", "free", "full", "sure", "easy", "hard", "fast", "nice", "real", "right", "wrong"}
        if word.lower() in en_verbs:
            return "verb"
        if word.lower() in en_adjs:
            return "adjective"

    # 规则：2字词，末尾是常见虚词的是副词
    if len(word) >= 2 and word[-1] in "地然得过":
        return "adverb"

    # 默认：名词（中文实词中名词占绝大多数）
    return "noun"


def get_word_color(word: str, color_enabled: bool = True) -> str:
    """根据词性返回颜色"""
    if not color_enabled:
        return "&H00FFFFFF&"
    pos = classify_word_type(word)
    return POS_COLOR_MAP.get(pos, POS_COLOR_MAP["default"])


# ---------------------------------------------------------------------------
# 词重要性评分
# ---------------------------------------------------------------------------

def score_word_importance(
    word: str,
    is_keyword: bool = False,
    word_type: str = "default",
    position_in_sentence: float = 0.5,
) -> float:
    """对词的重要性打分 (0.0-1.0)，用于决定字号和动画强度

    Args:
        word: 词文本
        is_keyword: 是否命中关键词列表
        word_type: 词性类型
        position_in_sentence: 在句子中的相对位置 (0=开头, 1=结尾)
    """
    score = 0.3  # 基础分

    if is_keyword:
        score += 0.4

    if len(word) >= 3:
        score += 0.1

    if word_type in ("verb", "adjective"):
        score += 0.1
    elif word_type == "number":
        score += 0.15

    # 句首和句尾的词更重要
    if position_in_sentence < 0.2 or position_in_sentence > 0.8:
        score += 0.05

    return min(score, 1.0)


def get_word_size_multiplier(importance: float, size_range: Tuple[float, float] = (0.85, 1.5)) -> float:
    """根据重要性计算字号倍数"""
    lo, hi = size_range
    return lo + importance * (hi - lo)


# ---------------------------------------------------------------------------
# 词级动画预设
# ---------------------------------------------------------------------------

def animate_word_bounce(
    word_text: str,
    word_index: int,
    total_words: int,
    word_duration_ms: int,
    base_color: str = "&H00FFFFFF&",
    word_importance: float = 0.5,
) -> str:
    """弹跳入场：每个词依次弹跳出现"""
    delay = word_index * 80  # 每个词延迟80ms
    half = word_duration_ms // 2
    scale = int(80 + word_importance * 50)
    peak = min(scale + 20, 160)
    return (
        f"{{\\c{base_color}\\fscx{scale}\\fscy{scale}}}"
        f"{{\\t({delay},{delay + half},\\fscx{peak}\\fscy{peak})}}"
        f"{{\\t({delay + half},{delay + word_duration_ms},\\fscx{scale}\\fscy{scale})}}"
        f"{word_text}"
    )


def animate_word_stagger(
    word_text: str,
    word_index: int,
    total_words: int,
    word_duration_ms: int,
    base_color: str = "&H00FFFFFF&",
    word_importance: float = 0.5,
) -> str:
    """交错入场：词从左右交替滑入"""
    delay = word_index * 60
    direction = 20 if word_index % 2 == 0 else -20
    dur = word_duration_ms
    return (
        f"{{\\c{base_color}\\fscx{100}\\fscy{100}}}"
        f"{{\\t({delay},{delay + dur},\\pos({direction},0))}}"
        f"{word_text}"
    )


def animate_word_pulse(
    word_text: str,
    word_index: int,
    total_words: int,
    word_duration_ms: int,
    base_color: str = "&H00FFFFFF&",
    word_importance: float = 0.5,
) -> str:
    """脉冲强调：词出现后脉动，重要词汇脉动更强"""
    quarter = word_duration_ms // 4
    scale = int(90 + word_importance * 40)
    peak = min(scale + 15, 150)
    return (
        f"{{\\c{base_color}\\fscx{scale}\\fscy{scale}}}"
        f"{{\\t(0,{quarter},\\fscx{peak}\\fscy{peak})}}"
        f"{{\\t({quarter},{quarter * 2},\\fscx{scale}\\fscy{scale})}}"
        f"{{\\t({quarter * 2},{quarter * 3},\\fscx{peak}\\fscy{peak})}}"
        f"{{\\t({quarter * 3},{word_duration_ms},\\fscx{scale}\\fscy{scale})}}"
        f"{word_text}"
    )


def animate_word_wipe(
    word_text: str,
    word_index: int,
    total_words: int,
    word_duration_ms: int,
    base_color: str = "&H00FFFFFF&",
    word_importance: float = 0.5,
) -> str:
    """渐显擦除：词逐步显现，带透明度过渡"""
    delay = word_index * 50
    return (
        f"{{\\c{base_color}\\alpha&HFF&}}"
        f"{{\\t({delay},{delay + 150},\\alpha&H00&)}}"
        f"{word_text}"
    )


def animate_word_glow_reveal(
    word_text: str,
    word_index: int,
    total_words: int,
    word_duration_ms: int,
    base_color: str = "&H00FFFFFF&",
    word_importance: float = 0.5,
) -> str:
    """发光揭示：词从发光状态过渡到正常"""
    delay = word_index * 60
    half = word_duration_ms // 2
    scale = int(95 + word_importance * 30)
    return (
        f"{{\\c{base_color}\\fscx{scale}\\fscy{scale}\\blur6}}"
        f"{{\\t({delay},{delay + half},\\blur1)}}"
        f"{{\\t({delay + half},{delay + word_duration_ms},\\blur0)}}"
        f"{word_text}"
    )


# 动画预设注册表
KINETIC_PRESETS = {
    "bounce": animate_word_bounce,
    "stagger": animate_word_stagger,
    "pulse": animate_word_pulse,
    "wipe": animate_word_wipe,
    "glow_reveal": animate_word_glow_reveal,
}

KINETIC_PRESET_NAMES = list(KINETIC_PRESETS.keys())

# 默认轮转序列：每个词使用不同的动画以增加视觉多样性
DEFAULT_ANIMATION_ROTATION = ["bounce", "pulse", "wipe", "glow_reveal", "bounce", "pulse"]


def get_kinetic_animation(
    word_index: int,
    preset_name: str = "viral",
) -> str:
    """根据预设名和词索引返回动画类型名"""
    if preset_name == "viral":
        return DEFAULT_ANIMATION_ROTATION[word_index % len(DEFAULT_ANIMATION_ROTATION)]
    elif preset_name == "kinetic":
        return ["bounce", "pulse", "stagger", "wipe", "glow_reveal"][word_index % 5]
    elif preset_name == "subtle":
        return "wipe"
    elif preset_name in KINETIC_PRESET_NAMES:
        return preset_name
    return "wipe"


# ---------------------------------------------------------------------------
# 多位置字幕分布
# ---------------------------------------------------------------------------

def get_caption_position(
    segment_index: int,
    keyword_emphases: Optional[List] = None,
    config_weights: Optional[Dict[str, float]] = None,
) -> Tuple[int, Optional[Tuple[int, int]]]:
    """为字幕选择位置（ASS alignment + 可选坐标）

    Returns:
        (alignment, (x, y) or None)
    """
    import random
    import hashlib

    # 使用segment_index确定性选择位置（同样输入得到同样结果）
    weights = config_weights or {
        "bottom_center": 0.55, "top_center": 0.15, "center": 0.15,
        "left_third": 0.08, "right_third": 0.07,
    }

    # 检查是否有需要特殊位置的关键词
    if keyword_emphases:
        for emp in keyword_emphases:
            if emp.position:
                pos_map = {
                    "center": (5, None),  # 居中
                    "top": (8, None),     # 顶部居中
                    "bottom": (2, None),  # 底部居中
                    "left": (1, None),
                    "right": (3, None),
                }
                return pos_map.get(emp.position, (2, None))

    # 按权重随机选择
    # 确定性随机（同一segment_index总得到相同结果）
    seed_val = hashlib.md5(str(segment_index).encode()).digest()
    seed_int = int.from_bytes(seed_val[:4], 'big')
    rng = random.Random(seed_int)

    positions = list(weights.keys())
    probs = [weights[p] for p in positions]
    choice = rng.choices(positions, weights=probs, k=1)[0]

    pos_map = {
        "bottom_center": (2, None),
        "top_center": (8, None),
        "center": (5, None),
        "left_third": (1, None),
        "right_third": (3, None),
    }
    return pos_map.get(choice, (2, None))


# ---------------------------------------------------------------------------
# 序列动画：整句词依次出现的整体编排
# ---------------------------------------------------------------------------

def build_kinetic_word_sequence(
    words: List[Dict],
    keyword_emphases: Optional[List] = None,
    preset_name: str = "viral",
    color_by_type: bool = True,
    variable_size: bool = True,
    size_range: Tuple[float, float] = (0.85, 1.5),
) -> str:
    """为整句构建逐词动画序列

    Args:
        words: [{"text": str, "start_ms": int, "end_ms": int}, ...]
        keyword_emphases: 关键词强调列表
        preset_name: 动画预设名
        color_by_type: 是否按词性着色
        variable_size: 是否使用可变字号
        size_range: 字号范围 (min_multiplier, max_multiplier)

    Returns:
        完整的ASS内联标签包裹的文本序列
    """
    if not words:
        return ""

    total = len(words)

    # 构建关键词集合
    kw_set = set()
    if keyword_emphases:
        for emp in keyword_emphases:
            kw_set.add(emp.keyword)

    parts = []
    for i, word in enumerate(words):
        word_text = word["text"]
        if not word_text.strip():
            parts.append(word_text)
            continue

        is_kw = word_text in kw_set or any(kw in word_text for kw in kw_set)
        word_type = classify_word_type(word_text)
        importance = score_word_importance(
            word_text, is_keyword=is_kw, word_type=word_type,
            position_in_sentence=i / max(total - 1, 1),
        )
        word_dur = max(50, word.get("end_ms", 100) - word.get("start_ms", 0))

        # 选择颜色
        if is_kw:
            color = "&H0000FF00&"  # 关键词绿色（与现有关键词高亮保持一致）
        elif color_by_type:
            color = get_word_color(word_text, True)
        else:
            color = "&H00FFFFFF&"

        # 选择动画
        anim_name = get_kinetic_animation(i, preset_name)
        anim_fn = KINETIC_PRESETS.get(anim_name, animate_word_wipe)
        animated = anim_fn(word_text, i, total, word_dur, color, importance)

        # 可变字号
        if variable_size and not is_kw:
            mult = get_word_size_multiplier(importance, size_range)
            fs_mult = int(mult * 100)
            # 在动画标签后插入字号
            animated = f"{{\\fscx{fs_mult}\\fscy{fs_mult}}}{animated}"

        parts.append(animated)

    return "".join(parts)
