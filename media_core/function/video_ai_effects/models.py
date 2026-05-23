"""
models.py — 视频AI特效数据模型

定义字幕样式配置、动画类型、渲染配置、特效计划等核心数据结构。
包含视觉分析、节拍检测、花字强调等扩展模型。
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple


class VideoPlatform(Enum):
    """视频发布平台枚举"""
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    GENERIC = "generic"


class VideoGenre(Enum):
    """视频内容类型枚举"""
    CINEMATIC = "cinematic"
    GAMING = "gaming"
    MUSIC_LYRICS = "music_lyrics"
    MEME_COMEDY = "meme_comedy"
    EDUCATION = "education"
    CORPORATE = "corporate"
    VLOG = "vlog"
    FOOD = "food"
    FITNESS = "fitness"
    TRAVEL = "travel"
    FASHION = "fashion"
    NEWS = "news"
    KIDS = "kids"
    TECH = "tech"
    SPORTS = "sports"
    PETS = "pets"
    MOTIVATION = "motivation"
    HORROR = "horror"
    ROMANCE = "romance"


class ASSAnimationType(Enum):
    """ASS字幕动画类型"""
    NONE = "none"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    FADE_IN_OUT = "fade_in_out"
    KARAOKE_WORD = "karaoke_word"
    KARAOKE_CHAR = "karaoke_char"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    BOUNCE = "bounce"
    GLOW_PULSE = "glow_pulse"
    TYPEWRITER = "typewriter"
    POP = "pop"
    SHAKE = "shake"
    SCALE_UP = "scale_up"
    ROTATE = "rotate"
    RAINBOW = "rainbow"
    ELASTIC = "elastic"
    WAVE = "wave"
    FLASH = "flash"
    SPIRAL = "spiral"
    DROP = "drop"


# ---------------------------------------------------------------------------
# 转场类型枚举 (功能模块F4)
# ---------------------------------------------------------------------------

class TransitionType(Enum):
    """转场类型枚举"""
    FADE_BLACK = "fade_black"
    ZOOM_BLUR = "zoom_blur"
    SLIDE_PUSH = "slide_push"
    ROTATION_FLIP = "rotation_flip"
    GLITCH = "glitch"
    WHIP_PAN = "whip_pan"
    CROSSFADE = "crossfade"


# ---------------------------------------------------------------------------
# 核心ASS样式配置
# ---------------------------------------------------------------------------

@dataclass
class ASSStyleConfig:
    """ASS字幕样式配置"""
    style_id: str
    style_name: str
    category: str
    platform: str
    font_name: str = "SourceHanSansSC-Bold"
    font_size: int = 52
    primary_colour: str = "&H00FFFFFF"
    secondary_colour: str = "&H000000FF"
    outline_colour: str = "&H00000000"
    back_colour: str = "&H80000000"
    bold: bool = True
    italic: bool = False
    underline: bool = False
    strike_out: bool = False
    border_style: int = 1
    outline: float = 3.0
    shadow: float = 1.0
    alignment: int = 2
    margin_l: int = 60
    margin_r: int = 60
    margin_v: int = 90
    scale_x: float = 100.0
    scale_y: float = 100.0
    spacing: float = 0.0
    angle: float = 0.0
    encoding: int = 1
    animation: ASSAnimationType = ASSAnimationType.NONE
    animation_duration_ms: int = 300
    dialogue_overrides: str = ""
    karaoke_highlight_colour: Optional[str] = None
    karaoke_highlight_outline: Optional[str] = None
    karaoke_highlight_size: Optional[int] = None
    word_animation_template: Optional[str] = None
    font_map: Optional[Dict[str, str]] = None
    description: str = ""
    tags: List[str] = field(default_factory=list)
    disable_karaoke_highlight: bool = False


# ---------------------------------------------------------------------------
# 字幕片段
# ---------------------------------------------------------------------------

@dataclass
class SubtitleSegment:
    """字幕片段：一条字幕的时间范围和文本"""
    index: int
    start_ms: int
    end_ms: int
    text: str
    words: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# 视觉分析模型
# ---------------------------------------------------------------------------

@dataclass
class VisualFrameAnalysis:
    """单帧视觉分析结果"""
    timestamp: float
    description: str = ""
    objects: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    style_tags: List[str] = field(default_factory=list)
    mood: str = ""
    scene_type: str = ""
    dominant_colors: List[Tuple[int, int, int]] = field(default_factory=list)


@dataclass
class VisualAnalysisResult:
    """完整视频视觉分析结果"""
    frames: List[VisualFrameAnalysis] = field(default_factory=list)
    dominant_colors: List[Tuple[int, int, int]] = field(default_factory=list)
    overall_mood: str = ""
    scene_changes: List[float] = field(default_factory=list)
    dominant_scene_type: str = ""
    detected_objects: List[str] = field(default_factory=list)
    detected_actions: List[str] = field(default_factory=list)
    visual_style: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# 节拍检测模型
# ---------------------------------------------------------------------------

@dataclass
class BeatInfo:
    """音频节拍检测结果"""
    tempo: float = 0.0
    beat_times: List[float] = field(default_factory=list)
    onset_times: List[float] = field(default_factory=list)
    onset_strengths: List[float] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 花字/关键词强调模型
# ---------------------------------------------------------------------------

@dataclass
class KeywordEmphasis:
    """花字强调配置：对关键词施加特定视觉效果"""
    keyword: str
    preset: str = "pop_highlight"
    color: str = "&H0000FFFF"
    scale: float = 1.2
    outline_color: Optional[str] = None
    outline_width: Optional[float] = None
    bg_color: Optional[str] = None
    bg_padding: int = 4
    duration_ms: int = 400
    emoji: Optional[str] = None
    layer: int = 1
    start_offset_ms: int = 0
    word_start_ms: Optional[int] = None
    word_end_ms: Optional[int] = None
    # F3: 动态排版扩展字段
    position: Optional[str] = None  # 位置: center / top / left / right / bottom
    size_multiplier: float = 1.0
    animation_in: str = ""  # 入场动画: bounce / slide / fade / grow


# ---------------------------------------------------------------------------
# 特效计划
# ---------------------------------------------------------------------------

@dataclass
class EffectPlan:
    """特效计划：一个音效或视觉特效的触发安排"""
    timestamp: float
    effect_type: str  # 特效类型: sfx / huazi / sticker / transition / text_animation
    sfx_path: Optional[str] = None
    animation_data: Optional[Dict] = None
    duration: float = 1.0
    intensity: float = 0.5
    position: Optional[Tuple[float, float]] = None
    keyword_emphasis: Optional[KeywordEmphasis] = None
    sticker_path: Optional[str] = None
    transition_type: Optional[str] = None
    beat_aligned: bool = False
    segment_index: int = -1


# ---------------------------------------------------------------------------
# LLM导演输出模型
# ---------------------------------------------------------------------------

@dataclass
class EffectDirectorOutput:
    """LLM导演输出：样式选择和特效编排结果"""
    style_id: str
    genre: VideoGenre
    platform: VideoPlatform
    confidence: float
    effects: List[EffectPlan] = field(default_factory=list)
    key_terms: List[str] = field(default_factory=list)
    reasoning: str = ""
    visual_analysis: Optional[VisualAnalysisResult] = None
    beat_info: Optional[BeatInfo] = None
    keyword_emphases: List[KeywordEmphasis] = field(default_factory=list)
    bgm_recommendation: Optional[Dict] = None
    # F1: LLM推荐的Hook配置
    hook_recommendation: Optional[Dict] = None


# ===========================================================================
# 新增数据结构 — 阶段1-3
# ===========================================================================

# ---------------------------------------------------------------------------
# F1: 智能开头Hook检测
# ---------------------------------------------------------------------------

@dataclass
class HookConfig:
    """智能开头Hook配置"""
    mode: str = "auto"  # "extract_teaser", "text_overlay", "auto"
    teaser_duration: float = 2.0
    teaser_start_time: Optional[float] = None  # 为None时自动检测
    overlay_text: str = ""
    overlay_style: str = "question"  # countdown / question / statistic / wow
    max_duration: float = 2.5  # Hook最大总时长(秒)
    transition_in: bool = True  # Hook结束后是否添加过渡转场


# ---------------------------------------------------------------------------
# F2: 动态变速
# ---------------------------------------------------------------------------

@dataclass
class SpeedRampSegment:
    """单个变速段定义"""
    start_time: float
    end_time: float
    speed: float  # 1.0=normal, <1.0=slow-mo, >1.0=sped up
    reason: str = ""


@dataclass
class SpeedRampConfig:
    """动态变速配置"""
    enabled: bool = False
    segments: List[SpeedRampSegment] = field(default_factory=list)
    min_speed: float = 0.70
    max_speed: float = 1.50
    energy_threshold_low: float = 0.25
    energy_threshold_high: float = 0.70
    transition_frames: int = 6  # 变速过渡平滑帧数


# ---------------------------------------------------------------------------
# F3: 动态排版
# ---------------------------------------------------------------------------

@dataclass
class KineticTypographyConfig:
    """动态排版配置"""
    enabled: bool = False
    variable_word_size: bool = True
    size_range: Tuple[float, float] = (0.8, 1.5)
    multi_position: bool = True  # 字幕在不同位置出现
    position_weights: Dict[str, float] = field(default_factory=lambda: {
        "bottom_center": 0.55, "top_center": 0.15, "center": 0.15,
        "left_third": 0.08, "right_third": 0.07,
    })
    reveal_style: str = "word_by_word"  # 揭示方式: word_by_word / char_by_char / line_slide / stagger
    color_by_word_type: bool = True  # 按词性配色: 名词=暖色, 动词=冷色, 形容词=亮色
    emphasis_preset: str = "viral"  # 强调预设: viral / kinetic / subtle / none


# ---------------------------------------------------------------------------
# F4: 丰富转场
# ---------------------------------------------------------------------------

@dataclass
class TransitionConfig:
    """转场配置"""
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    # 每项格式: {"time": float, "type": str, "duration": float, "direction": str}
    min_gap: float = 2.0  # 转场之间最小间隔(秒)
    max_count: int = 6
    default_duration: float = 0.4
    energy_delta_weights: Dict[str, float] = field(default_factory=lambda: {
        "fade_black": 0.0, "crossfade": 0.05, "zoom_blur": 0.15,
        "slide_push": 0.15, "rotation_flip": 0.20, "glitch": 0.25, "whip_pan": 0.30,
    })


# ---------------------------------------------------------------------------
# F5: 音频闪避（侧链压缩）
# ---------------------------------------------------------------------------

@dataclass
class AudioDuckingConfig:
    """音频闪避（侧链压缩）配置"""
    enabled: bool = True
    duck_amount_db: float = -8.0
    attack_ms: int = 20
    release_ms: int = 200
    threshold_db: float = -25.0


# ---------------------------------------------------------------------------
# F6: 自动调色
# ---------------------------------------------------------------------------

@dataclass
class ColorGradingConfig:
    """自动调色配置"""
    enabled: bool = True
    preset: str = "auto"  # auto / warm / cool / cinematic_desat / vibrant / none
    intensity: float = 0.7
    custom_curves: Optional[str] = None


# ---------------------------------------------------------------------------
# F7: 动态图形叠加
# ---------------------------------------------------------------------------

@dataclass
class MotionGraphic:
    """单个动态图形定义"""
    graphic_type: str  # 图形类型: progress_bar / arrow / circle_highlight / particle_burst / lower_third
    timestamp: float
    duration: float
    position: Tuple[float, float] = (0.5, 0.5)  # 归一化坐标（相对视频尺寸比例）
    color: str = "&H0000FFFF"
    label: str = ""
    target_pos: Optional[Tuple[float, float]] = None  # 箭头指向的目标位置
    scale: float = 1.0
    segments: int = 5  # 进度条总步数
    segment_current: int = 1


@dataclass
class MotionGraphicsConfig:
    """动态图形叠加配置"""
    enabled: bool = True
    graphics: List[MotionGraphic] = field(default_factory=list)
    max_graphics: int = 6


# ---------------------------------------------------------------------------
# F8: 结尾CTA画面
# ---------------------------------------------------------------------------

@dataclass
class EndScreenConfig:
    """结尾CTA画面配置"""
    enabled: bool = True
    duration: float = 3.0
    cta_text: str = "Follow for more!"
    channel_name: str = ""
    subscribe_icon: bool = True
    like_icon: bool = True
    background_blur: int = 20
    background_from_last_frame: bool = True
    next_video_text: str = ""
    template: str = "centered"  # centered / split / minimal
    primary_color: str = "white"
    accent_color: str = "yellow"


# ---------------------------------------------------------------------------
# F10: 传播力评分
# ---------------------------------------------------------------------------

@dataclass
class EngagementScore:
    """传播力评分"""
    overall: float = 0.0  # 0-100
    hook_strength: float = 0.0
    pacing_score: float = 0.0
    effect_density: float = 0.0
    variety_score: float = 0.0
    typography_score: float = 0.0
    audio_score: float = 0.0
    suggestions: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# F11: 自动画幅适配
# ---------------------------------------------------------------------------

@dataclass
class CropConfig:
    """自动画幅适配配置"""
    target_aspect: str = "9:16"  # "9:16", "16:9", "1:1", "4:5"
    strategy: str = "smart_center"  # smart_center / center / top
    use_visual_analysis: bool = True
    padding_color: str = "black"  # 需要填充时的背景色


# ===========================================================================
# 渲染配置（包含所有功能模块字段）
# ===========================================================================

@dataclass
class RenderingConfig:
    """渲染配置：输入输出路径、样式、平台、语言等参数"""
    input_path: str
    output_path: str
    srt_path: Optional[str] = None
    task_id: str = ""
    style_id: str = ""
    platform: str = "tiktok"
    genre: str = ""
    language: str = "zh-CN"
    hard_sub: bool = True
    sfx_enabled: bool = True
    bgm_path: str = ""
    bgm_volume: float = 0.15
    sfx_volume: float = 0.35
    progress_callback: Optional[Any] = None
    # 扩展配置
    enable_visual_analysis: bool = True
    enable_beat_sync: bool = True
    enable_huazi: bool = True
    max_effects_per_minute: int = 20
    min_sfx_gap: float = 0.5
    visual_analysis_interval: float = 2.0
    zoom_pulses: Optional[List[Dict[str, float]]] = None
    scene_transitions: Optional[List[float]] = None
    sticker_overlays: Optional[List[Any]] = None

    # --- 新增：阶段1-3功能模块 ---
    # F9: 爆款模板名称
    template_name: str = ""

    # F1: 智能Hook配置
    hook_config: Optional[HookConfig] = None
    enable_smart_hook: bool = False

    # F2: 动态变速配置
    speed_ramp_config: Optional[SpeedRampConfig] = None
    enable_speed_ramp: bool = True

    # F3: 动态排版配置
    kinetic_typo_config: Optional[KineticTypographyConfig] = None
    enable_kinetic_typo: bool = True

    # F4: 丰富转场配置
    transition_config: Optional[TransitionConfig] = None
    enable_variety_transitions: bool = True

    # F5: 音频闪避配置
    ducking_config: Optional[AudioDuckingConfig] = None
    enable_ducking: bool = True

    # F6: 自动调色配置
    color_grading_config: Optional[ColorGradingConfig] = None
    enable_color_grading: bool = True

    # F7: 动态图形配置
    motion_graphics_config: Optional[MotionGraphicsConfig] = None
    enable_motion_graphics: bool = True

    # F8: 结尾画面配置
    end_screen_config: Optional[EndScreenConfig] = None
    enable_end_screen: bool = False

    # F11: 自动裁剪配置
    crop_config: Optional[CropConfig] = None
    enable_auto_crop: bool = False

    # 内部追踪字段
    _visual_result: Optional[Any] = None
    _beat_info: Optional[Any] = None
    _director_output: Optional[Any] = None
    _effects: Optional[List[Any]] = None
    _engagement_score: Optional[EngagementScore] = None
