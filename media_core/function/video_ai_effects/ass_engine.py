"""
ass_engine.py — ASS字幕文件生成引擎

负责将字幕片段列表转换为标准ASS格式文件，支持多种动画效果、
逐词高亮（默认）、花字/关键词强调覆盖层。
"""
import re
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from .models import ASSStyleConfig, ASSAnimationType, SubtitleSegment, KeywordEmphasis, KineticTypographyConfig
from .utils.ass_utils import format_ass_time, parse_srt_time, escape_ass_text, resolve_font_for_language
from .ass_styles.kinetic_presets import (
    build_kinetic_word_sequence, get_caption_position,
    classify_word_type, get_word_color, score_word_importance,
    get_word_size_multiplier,
)


# ---------------------------------------------------------------------------
# 文本宽度估算（用于自动缩放防止溢出）
# ---------------------------------------------------------------------------

def _estimate_text_pixel_width(text: str, font_size: int, scale_x: float = 100.0) -> float:
    eff = font_size * (scale_x / 100.0)
    width = 0.0
    for ch in text:
        if '一' <= ch <= '鿿':
            width += eff
        elif ch.isascii() and ch.isprintable():
            width += eff * 0.55
        else:
            width += eff * 0.75
    return width


# ---------------------------------------------------------------------------
# 改进5: 自动拆行长字幕
# ---------------------------------------------------------------------------

def auto_split_segments(
    segments: List[SubtitleSegment],
    max_pixel_width: int = 0,
    font_size: int = 52,
    scale_x: float = 100.0,
    max_cjk_chars: int = 20,
    max_words: int = 10,
) -> List[SubtitleSegment]:
    """将像素宽度严重超限的字幕片段拆分为多行

    判定逻辑：先用像素宽度估算，超限 1.3 倍才拆分（_build_events_section
    的 auto-scale 已经能缩放字体到 ~55% 适配普通溢出）。无像素宽度参数
    时退化为字符数判定（CJK 仅数汉字，不含英文）。
    """
    result = []
    idx = 0
    for seg in segments:
        needs_split = False
        if max_pixel_width > 0:
            est = _estimate_text_pixel_width(seg.text, font_size, scale_x)
            if est > max_pixel_width * 1.3:
                needs_split = True
        else:
            is_cjk = any('一' <= ch <= '鿿' for ch in seg.text)
            if is_cjk:
                cjk_count = sum(1 for ch in seg.text if '一' <= ch <= '鿿')
                if cjk_count > max_cjk_chars:
                    needs_split = True
            else:
                if len(seg.text.split()) > max_words:
                    needs_split = True

        if not needs_split:
            seg.index = idx
            result.append(seg)
            idx += 1
            continue

        if max_pixel_width > 0:
            chunks = _split_text_by_pixel_width(
                seg.text, int(max_pixel_width * 0.85), font_size, scale_x,
            )
        else:
            is_cjk = any('一' <= ch <= '鿿' for ch in seg.text)
            threshold = max_cjk_chars if is_cjk else max_words
            chunks = _split_text_at_breaks(seg.text, threshold)

        timings = _redistribute_timing(seg.start_ms, seg.end_ms, chunks)
        for chunk_text, (chunk_start, chunk_end) in zip(chunks, timings):
            chunk_words = None
            if seg.words:
                chunk_words = _extract_words_for_chunk(seg.words, chunk_text, chunk_start, chunk_end)
            result.append(SubtitleSegment(
                index=idx, start_ms=chunk_start, end_ms=chunk_end,
                text=chunk_text, words=chunk_words,
            ))
            idx += 1
    return result


def _split_text_by_pixel_width(
    text: str, target_px: int, font_size: int, scale_x: float,
) -> List[str]:
    """按像素宽度目标拆分文本，在自然断点处切割，不在英文单词中间断开"""
    BREAK_CHARS = set('。！？，、；：…—')

    chunks = []
    remaining = text.strip()
    while remaining:
        est = _estimate_text_pixel_width(remaining, font_size, scale_x)
        if est <= target_px:
            chunks.append(remaining)
            break

        # 逐步累积像素宽度，找到不超过 target_px 的最远位置
        cumul = 0.0
        best_pos = 0
        eff = font_size * (scale_x / 100.0)
        for i, ch in enumerate(remaining):
            if '一' <= ch <= '鿿':
                cumul += eff
            elif ch.isascii() and ch.isprintable():
                cumul += eff * 0.55
            else:
                cumul += eff * 0.75
            if cumul > target_px:
                best_pos = i
                break
        else:
            best_pos = len(remaining)

        if best_pos == 0:
            best_pos = 1

        # 找最近自然断点（优先标点，其次空格），向后搜索一小段
        cut_pos = best_pos
        search_end = min(len(remaining), best_pos + 8)
        for i in range(best_pos, search_end):
            if remaining[i] in BREAK_CHARS:
                cut_pos = i + 1
                break
            if remaining[i] == ' ':
                cut_pos = i + 1
                break

        # 向前搜索标点/空格（如果向后没找到）
        if cut_pos == best_pos:
            search_start = max(1, best_pos - 8)
            for i in range(best_pos - 1, search_start - 1, -1):
                if remaining[i] in BREAK_CHARS or remaining[i] == ' ':
                    cut_pos = i + 1
                    break

        # 确保不在英文单词中间切断：如果 cut_pos 两侧都是字母则回退到空格
        if (cut_pos < len(remaining) and cut_pos > 0
                and remaining[cut_pos - 1].isalpha()
                and remaining[cut_pos].isalpha()):
            for i in range(cut_pos - 1, max(0, cut_pos - 20), -1):
                if remaining[i] == ' ':
                    cut_pos = i + 1
                    break

        cut_pos = max(1, min(cut_pos, len(remaining)))
        chunks.append(remaining[:cut_pos])
        remaining = remaining[cut_pos:].strip()
    return chunks


def _split_text_at_breaks(text: str, target_chunk_size: int) -> List[str]:
    """在自然断点处拆分文本（字符数模式的备用路径）"""
    BREAK_CHARS = set('。！？，、；：…—')
    chunks = []
    remaining = text.strip()
    while remaining:
        is_cjk = any('一' <= ch <= '鿿' for ch in remaining)
        if not is_cjk:
            words = remaining.split()
            if len(words) <= target_chunk_size:
                chunks.append(remaining)
                break
            chunk = ' '.join(words[:target_chunk_size])
            remaining = ' '.join(words[target_chunk_size:])
            chunks.append(chunk)
            continue

        if len(remaining) <= target_chunk_size:
            chunks.append(remaining)
            break

        best_pos = target_chunk_size
        search_start = max(2, target_chunk_size - 4)
        search_end = min(len(remaining), target_chunk_size + 4)
        for i in range(search_start, search_end):
            if remaining[i] in BREAK_CHARS:
                best_pos = i + 1
                break
        chunks.append(remaining[:best_pos])
        remaining = remaining[best_pos:].strip()
    return chunks


def _redistribute_timing(
    start_ms: int, end_ms: int, chunks: List[str],
) -> List[Tuple[int, int]]:
    """按字符数比例重新分配时间"""
    if not chunks:
        return [(start_ms, end_ms)]
    total_chars = sum(len(c) for c in chunks)
    if total_chars == 0:
        dur = (end_ms - start_ms) // max(len(chunks), 1)
        return [(start_ms + i * dur, start_ms + (i + 1) * dur) for i in range(len(chunks))]

    gap_ms = 30
    total_gap = gap_ms * max(0, len(chunks) - 1)
    usable = (end_ms - start_ms) - total_gap
    timings = []
    cur = start_ms
    for i, chunk in enumerate(chunks):
        chunk_dur = int(usable * len(chunk) / total_chars)
        chunk_end = cur + chunk_dur
        if i == len(chunks) - 1:
            chunk_end = end_ms
        timings.append((cur, chunk_end))
        cur = chunk_end + gap_ms
    return timings


def _extract_words_for_chunk(
    words: List[Dict[str, Any]], chunk_text: str, chunk_start: int, chunk_end: int,
) -> List[Dict[str, Any]]:
    """从原始 words 中提取属于该 chunk 的子集"""
    chunk_words = []
    for w in words:
        w_start = w.get("start_ms", 0)
        w_end = w.get("end_ms", 0)
        if w_end <= chunk_start or w_start >= chunk_end:
            continue
        chunk_words.append({
            "text": w["text"],
            "start_ms": max(w_start, chunk_start),
            "end_ms": min(w_end, chunk_end),
        })
    if not chunk_words and words:
        total_dur = chunk_end - chunk_start
        per_word = total_dur // max(len(words), 1)
        for i, w in enumerate(words[:3]):
            chunk_words.append({
                "text": w["text"],
                "start_ms": chunk_start + i * per_word,
                "end_ms": chunk_start + (i + 1) * per_word,
            })
    return chunk_words


# ---------------------------------------------------------------------------
# 改进1: 伪词级时间生成（SRT 输入无 word timing 时）
# ---------------------------------------------------------------------------

def _generate_pseudo_word_timing(seg: SubtitleSegment) -> List[Dict[str, Any]]:
    """为没有 word-level timing 的字幕段生成伪时间"""
    text = seg.text
    total_dur = seg.end_ms - seg.start_ms
    if total_dur <= 0 or not text.strip():
        return []

    # 中日韩文字：逐字拆分
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return []

    is_cjk = any('一' <= ch <= '鿿' for ch in text)
    if is_cjk:
        per_char = total_dur // max(len(chars), 1)
        return [
            {"text": ch, "start_ms": seg.start_ms + i * per_char, "end_ms": seg.start_ms + (i + 1) * per_char}
            for i, ch in enumerate(chars)
        ]
    # 拉丁字母：逐词拆分
    words = text.split()
    per_word = total_dur // max(len(words), 1)
    return [
        {"text": w, "start_ms": seg.start_ms + i * per_word, "end_ms": seg.start_ms + (i + 1) * per_word}
        for i, w in enumerate(words)
    ]


# ---------------------------------------------------------------------------
# 改进2: 关键词词级时间定位
# ---------------------------------------------------------------------------

def _find_keyword_word_timing(
    seg: SubtitleSegment, keyword: str,
) -> Optional[Tuple[int, int]]:
    """在 seg.words 中定位关键词的精确起止时间"""
    if not seg.words:
        return None
    # 精确匹配
    for w in seg.words:
        if w["text"] == keyword or w["text"].strip() == keyword.strip():
            return (w["start_ms"], w["end_ms"])
    # 子串匹配：关键词在某个 word 内
    for w in seg.words:
        if keyword in w["text"]:
            ratio = w["text"].index(keyword) / max(len(w["text"]), 1)
            kw_dur = w["end_ms"] - w["start_ms"]
            kw_start = int(w["start_ms"] + ratio * kw_dur)
            return (kw_start, int(kw_start + kw_dur * len(keyword) / max(len(w["text"]), 1)))
    # 跨 word 匹配：关键词跨越多个 word
    words_text = "".join(w["text"] for w in seg.words)
    pos = words_text.find(keyword)
    if pos >= 0:
        char_offset = 0
        for i, w in enumerate(seg.words):
            w_end_offset = char_offset + len(w["text"])
            if char_offset <= pos < w_end_offset:
                start_ms = w["start_ms"]
                # 找到关键词结束所在的 word
                end_offset = pos + len(keyword)
                for j in range(i, len(seg.words)):
                    wj_end = sum(len(seg.words[k]["text"]) for k in range(j + 1))
                    if wj_end >= end_offset:
                        return (start_ms, seg.words[j]["end_ms"])
            char_offset = w_end_offset
    return None


# ---------------------------------------------------------------------------
# ASS 文件生成入口
# ---------------------------------------------------------------------------

def generate_ass_file(
    segments: List[SubtitleSegment],
    style_config: ASSStyleConfig,
    output_path: str,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    language: str = "zh-CN",
    title: str = "AI Effects Subtitles",
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
    kinetic_config: Optional[KineticTypographyConfig] = None,
) -> str:
    font_name = resolve_font_for_language(language, style_config.font_name)
    sections = [
        _build_script_info(style_config, play_res_x, play_res_y, title),
        _build_styles_section(style_config, font_name, keyword_emphases),
        _build_events_section(segments, style_config, keyword_emphases, play_res_x, play_res_y, kinetic_config),
    ]
    content = "\n\n".join(sections) + "\n"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


def parse_srt_to_segments(srt_path: str) -> List[SubtitleSegment]:
    segments = []
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", content.strip())
    for i, block in enumerate(blocks):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        time_match = re.match(
            r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)", lines[1].strip()
        )
        if not time_match:
            continue
        start_ms = parse_srt_time(time_match.group(1))
        end_ms = parse_srt_time(time_match.group(2))
        text = "\n".join(lines[2:]).strip()
        if not text:
            continue
        segments.append(SubtitleSegment(index=i, start_ms=start_ms, end_ms=end_ms, text=text))
    return segments


def parse_json_subtitles(json_path: str) -> List[SubtitleSegment]:
    import json
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    segments = []
    for i, item in enumerate(data):
        text = item.get("text", "").strip()
        if not text:
            continue
        start_ms = int(item.get("start", 0) * 1000)
        end_ms = int(item.get("end", 0) * 1000)
        words = None
        if "words" in item:
            words = [
                {
                    "text": w.get("text", ""),
                    "start_ms": int(w.get("start", 0) * 1000),
                    "end_ms": int(w.get("end", 0) * 1000),
                }
                for w in item["words"]
            ]
        segments.append(
            SubtitleSegment(index=i, start_ms=start_ms, end_ms=end_ms, text=text, words=words)
        )
    return segments


# ---------------------------------------------------------------------------
# ASS文件各段构建
# ---------------------------------------------------------------------------

def _build_script_info(style_config: ASSStyleConfig, res_x: int, res_y: int, title: str) -> str:
    return (
        "[Script Info]\n"
        f"Title: {title}\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {res_x}\n"
        f"PlayResY: {res_y}\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
    )


def _build_styles_section(
    style_config: ASSStyleConfig,
    font_name: str,
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
) -> str:
    styles = _format_ass_style("Default", style_config, font_name)
    if style_config.karaoke_highlight_colour:
        highlight = _build_highlight_style(style_config, font_name)
        styles += f"\n{_format_ass_style_from_raw('Highlight', highlight)}"
    if keyword_emphases:
        seen_presets = set()
        for emp in keyword_emphases:
            preset_key = f"{emp.preset}_{emp.color}"
            if preset_key not in seen_presets:
                seen_presets.add(preset_key)
                huazi_style = _build_huazi_style(emp, style_config, font_name)
                if huazi_style:
                    styles += f"\n{_format_ass_style_from_raw(f'Huazi_{preset_key}', huazi_style)}"
    header = "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    return f"[V4+ Styles]\n{header}\n{styles}"


def _build_huazi_style(emp: KeywordEmphasis, base: ASSStyleConfig, font_name: str) -> Optional[dict]:
    scale = int(emp.scale * 100)
    return {
        "font_name": font_name,
        "font_size": base.font_size,
        "primary_colour": emp.color,
        "secondary_colour": base.secondary_colour,
        "outline_colour": emp.outline_color or base.outline_colour,
        "back_colour": emp.bg_color or base.back_colour,
        "bold": base.bold,
        "italic": base.italic,
        "underline": base.underline,
        "strike_out": base.strike_out,
        "scale_x": float(scale),
        "scale_y": float(scale),
        "spacing": base.spacing,
        "angle": base.angle,
        "border_style": base.border_style,
        "outline": emp.outline_width or base.outline,
        "shadow": base.shadow,
        "alignment": base.alignment,
        "margin_l": base.margin_l,
        "margin_r": base.margin_r,
        "margin_v": base.margin_v,
        "encoding": base.encoding,
    }


def _format_ass_style(name: str, cfg: ASSStyleConfig, font_name: str) -> str:
    return (
        f"Style: {name},{font_name},{cfg.font_size},"
        f"{cfg.primary_colour},{cfg.secondary_colour},{cfg.outline_colour},{cfg.back_colour},"
        f"{-1 if cfg.bold else 0},{-1 if cfg.italic else 0},"
        f"{-1 if cfg.underline else 0},{-1 if cfg.strike_out else 0},"
        f"{cfg.scale_x},{cfg.scale_y},{cfg.spacing},{cfg.angle},"
        f"{cfg.border_style},{cfg.outline},{cfg.shadow},{cfg.alignment},"
        f"{cfg.margin_l},{cfg.margin_r},{cfg.margin_v},{cfg.encoding}"
    )


def _build_highlight_style(cfg: ASSStyleConfig, font_name: str) -> dict:
    return {
        "font_name": font_name,
        "font_size": cfg.karaoke_highlight_size or cfg.font_size,
        "primary_colour": cfg.karaoke_highlight_colour or cfg.primary_colour,
        "secondary_colour": cfg.secondary_colour,
        "outline_colour": cfg.karaoke_highlight_outline or cfg.outline_colour,
        "back_colour": cfg.back_colour,
        "bold": cfg.bold,
        "italic": cfg.italic,
        "underline": cfg.underline,
        "strike_out": cfg.strike_out,
        "scale_x": cfg.scale_x,
        "scale_y": cfg.scale_y,
        "spacing": cfg.spacing,
        "angle": cfg.angle,
        "border_style": cfg.border_style,
        "outline": cfg.outline,
        "shadow": cfg.shadow,
        "alignment": cfg.alignment,
        "margin_l": cfg.margin_l,
        "margin_r": cfg.margin_r,
        "margin_v": cfg.margin_v,
        "encoding": cfg.encoding,
    }


def _format_ass_style_from_raw(name: str, r: dict) -> str:
    return (
        f"Style: {name},{r['font_name']},{r['font_size']},"
        f"{r['primary_colour']},{r['secondary_colour']},{r['outline_colour']},{r['back_colour']},"
        f"{-1 if r['bold'] else 0},{-1 if r['italic'] else 0},"
        f"{-1 if r['underline'] else 0},{-1 if r['strike_out'] else 0},"
        f"{r['scale_x']},{r['scale_y']},{r['spacing']},{r['angle']},"
        f"{r['border_style']},{r['outline']},{r['shadow']},{r['alignment']},"
        f"{r['margin_l']},{r['margin_r']},{r['margin_v']},{r['encoding']}"
    )


# ---------------------------------------------------------------------------
# Events段 — 核心改动区域
# ---------------------------------------------------------------------------

def _build_events_section(
    segments: List[SubtitleSegment],
    cfg: ASSStyleConfig,
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
    play_res_x: int = 1080,
    play_res_y: int = 1920,
    kinetic_config: Optional[KineticTypographyConfig] = None,
) -> str:
    dialogues = []
    use_kinetic = kinetic_config and kinetic_config.enabled

    for seg in segments:
        # 改进1: 无 word timing 时生成伪时间（在副本上操作避免修改原数据）
        if not seg.words and not cfg.disable_karaoke_highlight:
            seg = SubtitleSegment(
                index=seg.index, start_ms=seg.start_ms, end_ms=seg.end_ms,
                text=seg.text, words=_generate_pseudo_word_timing(seg),
            )

        start = format_ass_time(seg.start_ms)
        end = format_ass_time(seg.end_ms)
        dur = seg.end_ms - seg.start_ms

        # F3: 动态排版模式
        if use_kinetic and seg.words and not cfg.disable_karaoke_highlight:
            text = build_kinetic_word_sequence(
                words=seg.words,
                keyword_emphases=keyword_emphases,
                preset_name=kinetic_config.emphasis_preset,
                color_by_type=kinetic_config.color_by_word_type,
                variable_size=kinetic_config.variable_word_size,
                size_range=kinetic_config.size_range,
            )
            # 用默认高亮色上下文包裹
            highlight_color = cfg.karaoke_highlight_colour or "&H0000FFFF&"
            text = f"{{\\c{highlight_color}\\2c{cfg.primary_colour}}}{text}"
        else:
            text = _build_dialogue_text(seg, cfg, keyword_emphases)

        overrides = _build_animation_overrides(seg, cfg, play_res_x, play_res_y)
        # 无动画时默认添加淡入淡出，让字幕前后行自然过渡
        if not overrides and cfg.animation == ASSAnimationType.NONE:
            fade_dur = min(100, dur // 4)
            overrides = [f"\\fad({fade_dur},{fade_dur})"]
        override_str = ""
        if overrides:
            override_str = "{" + " ".join(overrides) + "}"
        if cfg.dialogue_overrides:
            if override_str:
                override_str = override_str.rstrip("}") + cfg.dialogue_overrides + "}"
            else:
                override_str = "{" + cfg.dialogue_overrides + "}"

        # F3: 多位置字幕
        position_tag = ""
        if use_kinetic and kinetic_config.multi_position:
            alignment, pos = get_caption_position(seg.index, keyword_emphases, kinetic_config.position_weights)
            if alignment != 2:  # 不是默认的底部居中
                position_tag = f"{{\\an{alignment}}}"
                if pos:
                    position_tag = f"{{\\an{alignment}\\pos({pos[0]},{pos[1]})}}"

        # 自动缩放防止溢出
        est_width = _estimate_text_pixel_width(seg.text, cfg.font_size, cfg.scale_x)
        avail_width = play_res_x - cfg.margin_l - cfg.margin_r
        if est_width > avail_width and avail_width > 0:
            auto_scale = max(55, int(avail_width * cfg.scale_x / est_width))
            scale_tag = f"\\fscx{auto_scale}\\fscy{auto_scale}"
            if override_str:
                override_str = override_str.rstrip("}") + scale_tag + "}"
            else:
                override_str = "{" + scale_tag + "}"

        dialogues.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{position_tag}{override_str}{text}")

    all_dialogues = dialogues
    header = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    return header + "\n" + "\n".join(all_dialogues)


def _build_keyword_overlay_dialogues(
    seg: SubtitleSegment,
    cfg: ASSStyleConfig,
    keyword_emphases: List[KeywordEmphasis],
    play_res_x: int,
    play_res_y: int,
) -> List[str]:
    """为关键词生成 layer=1 的覆盖 Dialogue，精准对齐到词级时刻"""
    from .effects.huazi_presets import apply_huazi
    overlays = []
    overlay_y = max(50, play_res_y - cfg.margin_v - 120)
    cx = play_res_x // 2

    sorted_emphases = sorted(keyword_emphases, key=lambda e: len(e.keyword), reverse=True)
    matched_keywords = set()

    for emp in sorted_emphases:
        keyword = emp.keyword
        if not keyword or keyword not in seg.text:
            continue
        if keyword in matched_keywords:
            continue
        matched_keywords.add(keyword)

        # 精准时间定位
        word_timing = _find_keyword_word_timing(seg, keyword)
        if word_timing:
            kw_start_ms, kw_end_ms = word_timing
        else:
            # 降级：按关键词在文本中的位置比例估算
            pos = seg.text.find(keyword)
            ratio = pos / max(len(seg.text), 1)
            total_dur = seg.end_ms - seg.start_ms
            kw_start_ms = int(seg.start_ms + ratio * total_dur)
            kw_end_ms = min(kw_start_ms + emp.duration_ms, seg.end_ms)

        # 记录到 emphasis 供外部使用（SFX/zoom 对齐）
        emp.word_start_ms = kw_start_ms
        emp.word_end_ms = kw_end_ms

        overlay_start = format_ass_time(kw_start_ms)
        overlay_end = format_ass_time(min(kw_start_ms + emp.duration_ms, seg.end_ms))
        keyword_escaped = escape_ass_text(keyword)
        tagged = apply_huazi(keyword_escaped, emp, kw_start_ms, kw_end_ms)

        pos_tag = f"{{\\an2\\pos({cx},{overlay_y})}}"
        overlays.append(
            f"Dialogue: 1,{overlay_start},{overlay_end},Default,,0,0,0,,{pos_tag}{tagged}"
        )
    return overlays


# ---------------------------------------------------------------------------
# 对话文本构建 — 改进1: 逐词高亮为默认
# ---------------------------------------------------------------------------

def _build_dialogue_text(
    seg: SubtitleSegment,
    cfg: ASSStyleConfig,
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
) -> str:
    """构建字幕文本：逐词高亮为默认行为，关键词内联强调"""
    # 显式卡拉OK动画模式（向后兼容）
    if cfg.animation == ASSAnimationType.KARAOKE_WORD and seg.words:
        return _apply_karaoke_word_tags(seg, cfg)
    if cfg.animation == ASSAnimationType.KARAOKE_CHAR and seg.words:
        return _apply_karaoke_char_tags(seg, cfg)
    # 所有样式默认启用逐词高亮
    if seg.words and not cfg.disable_karaoke_highlight:
        return _apply_per_word_highlight(seg, cfg, keyword_emphases)
    return escape_ass_text(seg.text)


def _apply_per_word_highlight(
    seg: SubtitleSegment,
    cfg: ASSStyleConfig,
    keyword_emphases: Optional[List[KeywordEmphasis]] = None,
) -> str:
    """逐词平滑填色高亮：关键词用特殊颜色+缩放动画，其余用默认高亮色"""
    default_highlight = cfg.karaoke_highlight_colour or "&H0000FFFF"
    base = cfg.primary_colour
    keyword_color = "&H0000FF00"  # 绿色用于关键词强调

    # 构建关键词匹配集合
    kw_texts = set()
    if keyword_emphases:
        for emp in keyword_emphases:
            if emp.keyword:
                kw_texts.add(emp.keyword)

    parts = []
    for word in seg.words:
        word_text = escape_ass_text(word["text"])
        duration_cs = max(1, (word["end_ms"] - word["start_ms"]) // 10)

        # 检查当前词是否命中关键词
        is_keyword = False
        if kw_texts:
            for kw in kw_texts:
                if kw == word_text or kw in word_text:
                    is_keyword = True
                    break

        if is_keyword:
            # 关键词：绿色高亮 + 短暂放大弹回动画
            parts.append(
                f"{{\\c{keyword_color}\\2c{base}"
                f"\\t(0,150,\\fscx110\\fscy110)"
                f"\\t(150,300,\\fscx100\\fscy100)}}"
                f"{{\\kf{duration_cs}}}{word_text}"
                f"{{\\c{default_highlight}\\2c{base}\\r}}"
            )
        else:
            parts.append(f"{{\\kf{duration_cs}}}{word_text}")

    return f"{{\\c{default_highlight}\\2c{base}}}" + "".join(parts)


def _apply_keyword_emphasis(
    text: str,
    emphases: List[KeywordEmphasis],
    seg_start_ms: int,
    seg_end_ms: int,
) -> str:
    """内联关键词强调（仅当 disable_karaoke_highlight 时使用）"""
    if not emphases:
        return text
    from .effects.huazi_presets import apply_huazi
    sorted_emphases = sorted(emphases, key=lambda e: len(e.keyword), reverse=True)
    result = text
    for emp in sorted_emphases:
        keyword = emp.keyword
        if not keyword:
            continue
        keyword_escaped = escape_ass_text(keyword)
        if keyword_escaped not in result:
            idx = result.lower().find(keyword.lower()) if keyword.isascii() else -1
            if idx < 0:
                continue
            actual_keyword = result[idx:idx + len(keyword)]
            tagged = apply_huazi(actual_keyword, emp, seg_start_ms, seg_end_ms)
            result = result[:idx] + tagged + result[idx + len(keyword):]
        else:
            tagged = apply_huazi(keyword_escaped, emp, seg_start_ms, seg_end_ms)
            result = result.replace(keyword_escaped, tagged, 1)
    return result


# ---------------------------------------------------------------------------
# 动画覆盖标签（整行动画，与逐词高亮共存）
# ---------------------------------------------------------------------------

def _build_animation_overrides(seg: SubtitleSegment, cfg: ASSStyleConfig,
                               play_res_x: int = 1080, play_res_y: int = 1920) -> List[str]:
    overrides = []
    dur = seg.end_ms - seg.start_ms
    anim_dur = cfg.animation_duration_ms
    anim = cfg.animation
    cx = play_res_x // 2
    cy = play_res_y // 2

    # KARAOKE_WORD/CHAR 不需要额外 override（已在文本中处理）
    if anim in (ASSAnimationType.KARAOKE_WORD, ASSAnimationType.KARAOKE_CHAR):
        return overrides

    if anim == ASSAnimationType.FADE_IN:
        overrides.append(f"\\fad({anim_dur},0)")
    elif anim == ASSAnimationType.FADE_OUT:
        overrides.append(f"\\fad(0,{anim_dur})")
    elif anim == ASSAnimationType.FADE_IN_OUT:
        overrides.append(f"\\fad({min(anim_dur, dur // 3)},{min(anim_dur, dur // 3)})")
    elif anim == ASSAnimationType.BOUNCE:
        half = anim_dur // 2
        peak = 120
        overrides.append(f"\\t(0,{half},\\fscx{peak}\\fscy{peak})")
        overrides.append(f"\\t({half},{anim_dur},\\fscx100\\fscy100)")
    elif anim == ASSAnimationType.GLOW_PULSE:
        half = anim_dur // 2
        overrides.append(f"\\t(0,{half},\\blur3)")
        overrides.append(f"\\t({half},{anim_dur},\\blur1)")
    elif anim == ASSAnimationType.SHAKE:
        for offset in range(0, min(anim_dur, 300), 50):
            dx = 3 if (offset // 50) % 2 == 0 else -3
            overrides.append(f"\\t({offset},{offset + 50},\\pos({dx},0))")
    elif anim == ASSAnimationType.POP:
        third = anim_dur // 3
        peak = 110
        overrides.append(f"\\t(0,{third},\\fscx80\\fscy80)")
        overrides.append(f"\\t({third},{third * 2},\\fscx{peak}\\fscy{peak})")
        overrides.append(f"\\t({third * 2},{anim_dur},\\fscx100\\fscy100)")
    elif anim == ASSAnimationType.SCALE_UP:
        overrides.append("\\fscx50\\fscy50")
        overrides.append(f"\\t(0,{anim_dur},\\fscx100\\fscy100)")
    elif anim == ASSAnimationType.SLIDE_UP:
        overrides.append(f"\\move({cx},{cy + 100},{cx},{cy},0,{anim_dur})")
    elif anim == ASSAnimationType.SLIDE_DOWN:
        overrides.append(f"\\move({cx},{cy - 100},{cx},{cy},0,{anim_dur})")
    elif anim == ASSAnimationType.SLIDE_LEFT:
        overrides.append(f"\\move({cx + 200},{cy},{cx},{cy},0,{anim_dur})")
    elif anim == ASSAnimationType.SLIDE_RIGHT:
        overrides.append(f"\\move({cx - 200},{cy},{cx},{cy},0,{anim_dur})")
    elif anim == ASSAnimationType.RAINBOW:
        colors = ["&H000000FF", "&H0000FF00", "&H00FF0000", "&H0000FFFF", "&H00FF00FF", "&H00FFFF00"]
        step = anim_dur // len(colors)
        for ci, color in enumerate(colors):
            start_t = ci * step
            end_t = (ci + 1) * step
            overrides.append(f"\\t({start_t},{end_t},\\c{color})")
    elif anim == ASSAnimationType.ELASTIC:
        q = anim_dur // 4
        overrides.append(f"\\t(0,{q},\\fscx80\\fscy80)")
        overrides.append(f"\\t({q},{q * 2},\\fscx125\\fscy125)")
        overrides.append(f"\\t({q * 2},{q * 3},\\fscx95\\fscy95)")
        overrides.append(f"\\t({q * 3},{anim_dur},\\fscx100\\fscy100)")
    elif anim == ASSAnimationType.WAVE:
        for offset in range(0, min(anim_dur, 500), 80):
            dy = 8 if (offset // 80) % 2 == 0 else -8
            overrides.append(f"\\t({offset},{offset + 80},\\fscy{100 + dy})")
    elif anim == ASSAnimationType.FLASH:
        half = anim_dur // 2
        overrides.append(f"\\t(0,{half // 2},\\alpha&HFF&)")
        overrides.append(f"\\t({half // 2},{half},\\alpha&H00&)")
        overrides.append(f"\\t({half},{half + half // 2},\\alpha&HFF&)")
        overrides.append(f"\\t({half + half // 2},{anim_dur},\\alpha&H00&)")
    elif anim == ASSAnimationType.SPIRAL:
        overrides.append(f"\\t(0,{anim_dur},\\frz360)")
    elif anim == ASSAnimationType.DROP:
        overrides.append(f"\\move({cx},0,{cx},{cy},0,{anim_dur // 2})")
    return overrides


# ---------------------------------------------------------------------------
# 卡拉OK标签（向后兼容）
# ---------------------------------------------------------------------------

def _apply_karaoke_word_tags(seg: SubtitleSegment, cfg: ASSStyleConfig) -> str:
    if not seg.words:
        return escape_ass_text(seg.text)
    parts = []
    for word in seg.words:
        word_text = escape_ass_text(word["text"])
        duration_cs = max(1, (word["end_ms"] - word["start_ms"]) // 10)
        if cfg.karaoke_highlight_colour:
            parts.append(f"{{\\K{duration_cs}}}{word_text}")
        else:
            parts.append(f"{{\\k{duration_cs}}}{word_text}")
    return "".join(parts)


def _apply_karaoke_char_tags(seg: SubtitleSegment, cfg: ASSStyleConfig) -> str:
    if not seg.words:
        text = seg.text
        chars = list(text)
        total_dur = seg.end_ms - seg.start_ms
        per_char = max(1, total_dur // max(len(chars), 1) // 10)
        parts = []
        for ch in chars:
            ch_esc = escape_ass_text(ch)
            if cfg.karaoke_highlight_colour:
                parts.append(f"{{\\K{per_char}}}{ch_esc}")
            else:
                parts.append(f"{{\\k{per_char}}}{ch_esc}")
        return "".join(parts)
    parts = []
    for word in seg.words:
        word_text = word["text"]
        word_dur = word["end_ms"] - word["start_ms"]
        chars = list(word_text)
        per_char = max(1, word_dur // max(len(chars), 1) // 10)
        for ch in chars:
            ch_esc = escape_ass_text(ch)
            if cfg.karaoke_highlight_colour:
                parts.append(f"{{\\K{per_char}}}{ch_esc}")
            else:
                parts.append(f"{{\\k{per_char}}}{ch_esc}")
    return "".join(parts)
