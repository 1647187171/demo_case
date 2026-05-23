"""
llm_director.py — LLM特效导演

通过LLM分析视频转录文本和视觉内容，自动推荐最佳字幕样式、
花字强调和音效编排。包含LLM调用、响应解析、视觉分析增强、
节拍同步对齐和关键词匹配降级方案。
"""
import json
import re
from typing import Optional, List
from media_core.utils import utils
from media_core.utils import llm

from .models import (
    EffectPlan, EffectDirectorOutput,
    VideoGenre, VideoPlatform, SubtitleSegment,
    VisualAnalysisResult, BeatInfo, KeywordEmphasis,
)
from .ass_styles import get_style, get_all_style_ids, get_all_categories, get_style_count
from .prompts.effect_director_prompt import DIRECTOR_SYSTEM_PROMPT, build_director_user_prompt
from .effects.sfx_library import get_sfx, match_sfx_to_keyword, get_sfx_for_mood
from .effects.huazi_presets import get_default_color_for_genre
from .effects.beat_sync import detect_beats, align_effects_to_beats


def analyze_and_recommend(
    transcript_text: str,
    srt_segments: List[SubtitleSegment],
    video_duration: float,
    video_resolution: tuple,
    platform_hint: str = "",
    genre_hint: str = "",
    visual_analysis: Optional[VisualAnalysisResult] = None,
    beat_info: Optional[BeatInfo] = None,
) -> Optional[EffectDirectorOutput]:
    """分析视频内容并推荐样式、花字和特效编排

    Args:
        transcript_text: 视频转录文本
        srt_segments: 字幕片段列表
        video_duration: 视频时长（秒）
        video_resolution: 视频分辨率 (width, height)
        platform_hint: 平台提示
        genre_hint: 类型提示
        visual_analysis: 视觉分析结果
        beat_info: 节拍检测信息

    Returns:
        EffectDirectorOutput 或 None
    """
    try:
        styles = get_all_style_ids()
        visual_summary = visual_analysis.summary if visual_analysis else ""
        beat_dict = None
        if beat_info:
            beat_dict = {
                "tempo": beat_info.tempo,
                "beat_times": beat_info.beat_times[:30],
            }

        user_prompt = build_director_user_prompt(
            transcript_text=transcript_text,
            video_duration=video_duration,
            video_resolution=video_resolution,
            available_styles=styles,
            platform_hint=platform_hint,
            genre_hint=genre_hint,
            visual_summary=visual_summary,
            beat_info=beat_dict,
        )

        raw_text = llm.call_qwen_model(
            user_content=user_prompt,
            system_content=DIRECTOR_SYSTEM_PROMPT,
        )

        print(f"[LLM Director] Qwen3.6-plus Response: {raw_text}")

        if not raw_text:
            return _fallback_selection(
                transcript_text, platform_hint, visual_analysis,
            )

        result = utils.extract_json_from_response(raw_text)
        if not result:
            return _fallback_selection(
                transcript_text, platform_hint, visual_analysis,
            )

        return _parse_director_response(
            result, video_duration, beat_info, visual_analysis,
            platform_hint=platform_hint,
        )
    except Exception as e:
        utils.print2(f"[LLM Director] Error: {e}")
        return _fallback_selection(
            transcript_text, platform_hint, visual_analysis,
        )


def _validate_style_for_platform(style_id: str, platform: str) -> str:
    """确保所选样式适合目标平台

    社交媒体平台（TikTok、Instagram）禁止使用
    企业/新闻/教育类正式风格 — 始终优先使用醒目、有吸引力的样式。
    """
    if platform not in ("tiktok", "instagram"):
        return style_id

    boring_prefixes = ("corp_", "news_", "edu_")
    for prefix in boring_prefixes:
        if style_id.startswith(prefix):
            viral_fallbacks = [
                "tiktok_neon_glow", "tiktok_karaoke_pop",
                "tiktok_bounce_bold", "meme_impact",
                "tiktok_pop_yellow", "gaming_neon_blue",
            ]
            for fb in viral_fallbacks:
                if get_style(fb):
                    utils.print2(f"[LLM Director] Style override: {style_id} -> {fb} "
                                 f"(platform={platform})")
                    return fb
            break
    return style_id


def _parse_director_response(
    raw: dict,
    video_duration: float,
    beat_info: Optional[BeatInfo] = None,
    visual_analysis: Optional[VisualAnalysisResult] = None,
    platform_hint: str = "",
) -> Optional[EffectDirectorOutput]:
    """解析LLM导演响应为EffectDirectorOutput"""
    style_id = raw.get("style_id", "")
    style_config = get_style(style_id)
    if not style_config:
        style_id = ""

    # 确保样式适合目标平台
    if platform_hint:
        style_id = _validate_style_for_platform(style_id, platform_hint)

    genre_str = raw.get("genre", "vlog")
    try:
        genre = VideoGenre(genre_str)
    except ValueError:
        genre = VideoGenre.VLOG

    platform_str = raw.get("platform", "generic")
    try:
        platform = VideoPlatform(platform_str)
    except ValueError:
        platform = VideoPlatform.GENERIC

    mood = raw.get("mood", "")

    # 解析花字关键词强调
    keyword_emphases = _parse_keyword_emphases(raw.get("keyword_emphases", []), genre_str)

    # 解析音效
    max_effects = max(3, min(30, int(video_duration / 1.5)))
    effects = []
    raw_effects = raw.get("effects", [])

    for eff in raw_effects[:max_effects]:
        sfx_name = eff.get("sfx_name", "")
        sfx_path = get_sfx(sfx_name) if sfx_name else None
        effects.append(EffectPlan(
            timestamp=float(eff.get("timestamp", 0)),
            effect_type=eff.get("effect_type", "sfx"),
            sfx_path=sfx_path,
            duration=float(eff.get("duration", 0.5)),
            intensity=float(eff.get("intensity", 0.7)),
        ))

    # 节拍对齐
    if beat_info and beat_info.beat_times and effects:
        effects = _align_effects_to_beats(effects, beat_info)

    # 最小间隔过滤（sfx之间0.5秒，不同类型可共存）
    effects = _enforce_min_gap(effects, min_gap=0.5)

    # 解析BGM推荐
    bgm_rec = raw.get("bgm_recommendation")

    return EffectDirectorOutput(
        style_id=style_id,
        genre=genre,
        platform=platform,
        confidence=float(raw.get("confidence", 0.5)),
        effects=effects,
        key_terms=raw.get("key_terms", []),
        reasoning=raw.get("reasoning", ""),
        visual_analysis=visual_analysis,
        beat_info=beat_info,
        keyword_emphases=keyword_emphases,
        bgm_recommendation=bgm_rec,
    )


def _parse_keyword_emphases(
    raw_emphases: list,
    genre: str = "",
) -> List[KeywordEmphasis]:
    """解析花字关键词强调配置"""
    result = []
    default_color = get_default_color_for_genre(genre)

    for item in raw_emphases[:20]:
        keyword = item.get("keyword", "")
        if not keyword:
            continue
        result.append(KeywordEmphasis(
            keyword=keyword,
            preset=item.get("preset", "pop_highlight"),
            color=item.get("color", default_color),
            scale=float(item.get("scale", 1.2)),
            outline_color=item.get("outline_color"),
            outline_width=float(item["outline_width"]) if "outline_width" in item else None,
            bg_color=item.get("bg_color"),
            bg_padding=int(item.get("bg_padding", 4)),
            duration_ms=int(item.get("duration_ms", 400)),
            emoji=item.get("emoji"),
        ))
    return result


def _align_effects_to_beats(
    effects: List[EffectPlan],
    beat_info: BeatInfo,
    tolerance: float = 0.3,
) -> List[EffectPlan]:
    """将音效时间戳对齐到最近的节拍"""
    if not beat_info.beat_times or not effects:
        return effects

    aligned = []
    for effect in effects:
        ts = effect.timestamp
        closest = min(beat_info.beat_times, key=lambda b: abs(b - ts))
        if abs(closest - ts) <= tolerance:
            aligned.append(EffectPlan(
                timestamp=closest,
                effect_type=effect.effect_type,
                sfx_path=effect.sfx_path,
                duration=effect.duration,
                intensity=effect.intensity,
                beat_aligned=True,
            ))
        else:
            aligned.append(effect)
    return aligned


def _enforce_min_gap(effects: List[EffectPlan], min_gap: float = 0.5) -> List[EffectPlan]:
    """强制同类型特效之间最小间隔"""
    if not effects:
        return effects
    effects.sort(key=lambda e: e.timestamp)

    # 分类型处理：sfx和huazi可以同时触发
    sfx_effects = [e for e in effects if e.effect_type == "sfx"]
    other_effects = [e for e in effects if e.effect_type != "sfx"]

    filtered_sfx = []
    if sfx_effects:
        filtered_sfx = [sfx_effects[0]]
        for eff in sfx_effects[1:]:
            if eff.timestamp - filtered_sfx[-1].timestamp >= min_gap:
                filtered_sfx.append(eff)

    return sorted(filtered_sfx + other_effects, key=lambda e: e.timestamp)


def _fallback_selection(
    transcript_text: str,
    platform_hint: str = "",
    visual_analysis: Optional[VisualAnalysisResult] = None,
) -> EffectDirectorOutput:
    """降级方案：当LLM不可用时，通过关键词+视觉分析选择样式和音效"""
    text_lower = transcript_text.lower()

    # 关键词匹配检测视频类型
    genre = VideoGenre.VLOG
    keyword_map = {
        VideoGenre.FOOD: ["recipe", "cook", "food", "eat", "chef", "菜", "食", "烹饪", "美食", "好吃"],
        VideoGenre.FITNESS: ["workout", "exercise", "gym", "fit", "训练", "健身", "运动"],
        VideoGenre.GAMING: ["game", "play", "level", "boss", "游戏", "通关", "电竞"],
        VideoGenre.MUSIC_LYRICS: ["song", "sing", "music", "lyrics", "歌", "唱", "音乐"],
        VideoGenre.MEME_COMEDY: ["funny", "lol", "joke", "meme", "搞笑", "段子", "哈哈"],
        VideoGenre.EDUCATION: ["learn", "study", "teach", "tutorial", "学", "教", "教程"],
        VideoGenre.CORPORATE: ["business", "company", "meeting", "report", "公司", "会议", "报告"],
        VideoGenre.TRAVEL: ["travel", "trip", "visit", "explore", "旅行", "旅游", "探索"],
        VideoGenre.FASHION: ["fashion", "style", "outfit", "wear", "时尚", "穿搭", "衣服"],
        VideoGenre.NEWS: ["news", "report", "update", "breaking", "新闻", "报道"],
        VideoGenre.KIDS: ["kids", "children", "baby", "toy", "孩子", "宝宝", "玩具"],
        VideoGenre.CINEMATIC: ["film", "movie", "scene", "director", "电影", "场景"],
        VideoGenre.TECH: ["tech", "code", "program", "ai", "科技", "编程", "代码"],
        VideoGenre.SPORTS: ["sport", "game", "match", "win", "体育", "比赛", "冠军"],
        VideoGenre.PETS: ["cat", "dog", "pet", "cute", "猫", "狗", "宠物"],
        VideoGenre.MOTIVATION: ["motivate", "inspire", "dream", "努力", "梦想", "坚持"],
    }

    best_count = 0
    for g, keywords in keyword_map.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > best_count:
            best_count = count
            genre = g

    # 使用视觉分析改进类型判断
    if visual_analysis:
        va_genre = _genre_from_visual(visual_analysis)
        if va_genre:
            genre = va_genre

    platform = VideoPlatform.GENERIC
    if platform_hint:
        try:
            platform = VideoPlatform(platform_hint)
        except ValueError:
            pass

    style_id = _select_style_by_genre_and_platform(genre, platform)

    # 基于关键词和情绪生成一些默认音效
    mood = visual_analysis.overall_mood if visual_analysis else "neutral"
    default_sfx_names = get_sfx_for_mood(mood)
    effects = []
    for i, sfx_name in enumerate(default_sfx_names[:5]):
        sfx_path = get_sfx(sfx_name)
        if sfx_path:
            effects.append(EffectPlan(
                timestamp=float(i * 3),
                effect_type="sfx",
                sfx_path=sfx_path,
                duration=0.5,
                intensity=0.6,
            ))

    # 从文本中提取关键词做花字
    keyword_emphases = _extract_keyword_emphases(transcript_text, genre.value)

    return EffectDirectorOutput(
        style_id=style_id,
        genre=genre,
        platform=platform,
        confidence=0.3,
        effects=effects,
        key_terms=[],
        reasoning="Fallback keyword-based selection",
        visual_analysis=visual_analysis,
        keyword_emphases=keyword_emphases,
    )


def _genre_from_visual(visual: VisualAnalysisResult) -> Optional[VideoGenre]:
    """从视觉分析结果推断视频类型"""
    objects_str = " ".join(visual.detected_objects).lower()
    actions_str = " ".join(visual.detected_actions).lower()
    combined = objects_str + " " + actions_str

    if any(w in combined for w in ["cook", "food", "dish", "厨房", "食物"]):
        return VideoGenre.FOOD
    if any(w in combined for w in ["exercise", "gym", "健身", "运动"]):
        return VideoGenre.FITNESS
    if any(w in combined for w in ["game", "screen", "游戏"]):
        return VideoGenre.GAMING
    if any(w in combined for w in ["stage", "microphone", "singer", "舞台", "唱歌"]):
        return VideoGenre.MUSIC_LYRICS
    if any(w in combined for w in ["computer", "code", "laptop", "电脑"]):
        return VideoGenre.TECH
    if any(w in combined for w in ["cat", "dog", "pet", "猫", "狗"]):
        return VideoGenre.PETS
    return None


def _extract_keyword_emphases(text: str, genre: str) -> List[KeywordEmphasis]:
    """从文本中提取值得强调的关键词（增强版：自动分配emoji和变化预设）"""
    from .effects.huazi_presets import KEYWORD_EMOJI_MAP, PRESET_ROTATION, auto_assign_emoji

    default_color = get_default_color_for_genre(genre)
    found = {}  # 关键词 → (emoji, preset_index)

    # 1. 从emoji映射表匹配（优先匹配长词）
    sorted_map = sorted(KEYWORD_EMOJI_MAP.items(), key=lambda x: len(x[0]), reverse=True)
    for kw, emoji in sorted_map:
        if kw in text and len(kw) >= 2:
            if kw not in found:
                found[kw] = emoji

    # 2. 数字+单位模式
    for m in re.finditer(r'([\d.]+[%倍万千万亿]+)', text):
        kw = m.group(1)
        if kw not in found:
            found[kw] = "🔥"

    # 3. 如果关键词不足5个，从中文高频实词中补充
    if len(found) < 5:
        _fill_keywords_from_text(text, found)

    if not found:
        return []

    # 4. 构建 KeywordEmphasis 列表，轮转预设保持视觉多样性
    result = []
    for i, (kw, emoji) in enumerate(list(found.items())[:15]):
        preset = PRESET_ROTATION[i % len(PRESET_ROTATION)]
        result.append(KeywordEmphasis(
            keyword=kw,
            preset=preset,
            color=default_color,
            scale=1.3,
            emoji=emoji,
            duration_ms=500,
        ))
    return result


def _fill_keywords_from_text(text: str, found: dict) -> None:
    """当关键词不足时，用TF-IDF式打分补充有价值的中文实词

    打分逻辑：出现1次且是名词/动词的词得分最高，频繁出现的通用词得分低。
    """
    stopwords = {
        "的话", "然后", "所以", "因为", "但是", "不过", "其实", "还是",
        "已经", "可以", "可能", "应该", "不是", "就是", "这个", "那个",
        "什么", "怎么", "一个", "这样", "那样", "这些", "那些", "没有",
        "他们", "我们", "你们", "自己", "现在", "时候", "地方", "东西",
        "知道", "觉得", "认为", "发现", "虽然", "而且", "或者", "如果",
        "于是", "因此", "非常", "特别", "比较", "真的",
        "还有", "当然", "确实", "另外", "比如", "例如", "关于",
        "起来", "出来", "下来", "上去", "过来", "回来", "进去",
        "大家", "一些", "这种", "那种", "很多", "通过", "进行",
        "使用", "需要", "开始", "成为", "得到", "时候", "目前",
        "方面", "问题", "情况", "关系", "时间", "工作", "事情",
        "发展", "世界", "社会", "国家", "经济", "企业", "市场",
        "系统", "平台", "功能", "用户", "服务", "产品",
    }
    # 提取2-4字中文片段并统计频次
    candidates = {}
    seen = set(found.keys())
    for length in [4, 3, 2]:
        for i in range(len(text) - length + 1):
            substr = text[i:i + length]
            if not all('一' <= ch <= '鿿' for ch in substr):
                continue
            if substr in stopwords or substr in seen:
                continue
            has_value = True
            for suffix in ["的", "了", "着", "过", "地", "得"]:
                if substr.startswith(suffix) or substr.endswith(suffix):
                    has_value = False
                    break
            if not has_value:
                continue
            candidates[substr] = candidates.get(substr, 0) + 1

    if not candidates:
        return

    # TF-IDF 式打分：频次越低得分越高（稀有词更有价值），2-3字词优先
    scored = []
    for word, freq in candidates.items():
        rarity = 1.0 / max(freq, 1)
        length_bonus = 1.5 if len(word) <= 3 else 1.0
        score = rarity * length_bonus
        scored.append((word, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    for word, _ in scored:
        if len(found) >= 8:
            return
        if word not in found:
            seen.add(word)
            found[word] = "✨"


def _select_style_by_genre_and_platform(genre: VideoGenre, platform: VideoPlatform) -> str:
    """根据类型和平台组合选择最佳样式ID"""
    mapping = {
        (VideoGenre.CINEMATIC, VideoPlatform.GENERIC): "cine_subtitle_classic",
        (VideoGenre.GAMING, VideoPlatform.TIKTOK): "gaming_neon_blue",
        (VideoGenre.MUSIC_LYRICS, VideoPlatform.TIKTOK): "music_karaoke_word",
        (VideoGenre.MEME_COMEDY, VideoPlatform.TIKTOK): "meme_impact",
        (VideoGenre.EDUCATION, VideoPlatform.YOUTUBE): "edu_clean_sans",
        (VideoGenre.CORPORATE, VideoPlatform.YOUTUBE): "corp_professional",
        (VideoGenre.VLOG, VideoPlatform.INSTAGRAM): "vlog_warm_casual",
        (VideoGenre.FOOD, VideoPlatform.TIKTOK): "food_warm_orange",
        (VideoGenre.FITNESS, VideoPlatform.TIKTOK): "fitness_bold_energy",
        (VideoGenre.TRAVEL, VideoPlatform.INSTAGRAM): "travel_adventure",
        (VideoGenre.FASHION, VideoPlatform.INSTAGRAM): "fashion_editorial",
        (VideoGenre.NEWS, VideoPlatform.YOUTUBE): "news_ticker",
        (VideoGenre.KIDS, VideoPlatform.TIKTOK): "kids_bright_primary",
    }
    key = (genre, platform)
    if key in mapping:
        style_id = mapping[key]
        if get_style(style_id):
            return style_id
    for (g, _), style_id in mapping.items():
        if g == genre and get_style(style_id):
            return style_id
    default = "tiktok_pop_yellow"
    return default if get_style(default) else "tiktok_pop_yellow"
