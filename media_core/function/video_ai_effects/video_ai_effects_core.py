"""
video_ai_effects_core.py — 视频AI特效核心模块

提供视频字幕样式选择、ASS字幕生成、花字强调、音效编排、FFmpeg渲染的完整流水线。
支持通过 VL 视觉分析和 LLM 自动分析视频内容并推荐最佳样式与特效编排。
流水线：字幕加载 → 视觉分析+节拍检测(并发) → LLM导演 → ASS生成 → FFmpeg渲染
"""
import os
import threading
import asyncio
from typing import Tuple, Optional, Callable, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from media_core.utils import utils
from api.error_codes import ErrorCodes

from .models import (RenderingConfig, SubtitleSegment, EffectPlan, BeatInfo,
    HookConfig, SpeedRampConfig, KineticTypographyConfig,
    ColorGradingConfig, MotionGraphicsConfig, MotionGraphic,
    TransitionConfig)
from .ass_styles import get_style, get_all_style_ids, get_all_categories, get_style_count
from .ass_engine import generate_ass_file, parse_srt_to_segments, parse_json_subtitles, auto_split_segments, _find_keyword_word_timing
from .renderer import FFmpegRenderer
from .llm_director import analyze_and_recommend, _extract_keyword_emphases
from .visual_analyzer import analyze_video_visuals
from .effects.beat_sync import detect_beats, get_strong_beats
from .effects.bgm_library import recommend_bgm
from .effects.sfx_library import match_sfx_to_keyword, get_sfx
from .effects.hook_engine import detect_best_hook_moment, select_hook_text
from .effects.speed_ramper import generate_speed_ramp_segments, apply_speed_ramp_prepass
from .utils.path_manager import EffectsPathManager


# ---------------------------------------------------------------------------
# 字幕样式与定位辅助函数
# ---------------------------------------------------------------------------

def _detect_orientation(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio < 0.85:
        return "portrait"
    elif ratio > 1.15:
        return "landscape"
    return "square"


def _apply_premium_subtitle_style(style_config, video_resolution: tuple) -> None:
    """应用高级字幕样式：描边+投影+边缘模糊，替代 BorderStyle=3 矩形底框"""
    # 如果样式本身已设置 border_style=3 且有自定义 back_colour，保留原设置
    if style_config.border_style == 3 and style_config.back_colour not in ("&H80000000", "&H00000000", ""):
        return

    style_config.border_style = 1
    style_config.outline = 7.0
    style_config.shadow = 2.5
    style_config.back_colour = "&H80000000"

    # 追加边缘模糊到 dialogue_overrides（如果还没有）
    overrides = style_config.dialogue_overrides or ""
    if "\\be" not in overrides:
        overrides += "\\be1"
    style_config.dialogue_overrides = overrides

    # 横屏时字号按比例放大
    width = video_resolution[0]
    base_width = 1080
    if width > base_width * 1.3:
        factor = min(width / base_width, 1.3)
        style_config.font_size = int(style_config.font_size * factor)


def _apply_orientation_margins(style_config, platform: str, video_resolution: tuple) -> None:
    """根据视频方向和平台调整边距"""
    orientation = _detect_orientation(video_resolution[0], video_resolution[1])

    if orientation == "landscape":
        style_config.margin_l = max(style_config.margin_l, 120)
        style_config.margin_r = max(style_config.margin_r, 120)
        style_config.margin_v = max(style_config.margin_v, 80)
    elif orientation == "square":
        style_config.margin_l = max(style_config.margin_l, 80)
        style_config.margin_r = max(style_config.margin_r, 80)
        style_config.margin_v = max(style_config.margin_v, 120)
    else:
        # 竖屏：平台安全边距
        PLATFORM_SAFE_MARGIN = {"tiktok": 180, "instagram": 170, "youtube": 150}
        safe_v = PLATFORM_SAFE_MARGIN.get(platform, 150)
        if style_config.margin_v < safe_v:
            style_config.margin_v = safe_v


def _select_stickers_for_keywords(keyword_emphases, video_duration: float):
    """从 catalog.json 的 keyword_triggers 匹配贴纸"""
    import json
    from pathlib import Path
    from .models import KeywordEmphasis

    catalog_path = Path(utils.get_project_root()) / "res" / "effects" / "catalog.json"
    if not catalog_path.exists():
        return []

    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    triggers = catalog.get("keyword_triggers", {})
    if not triggers:
        return []

    # 构建关键词→贴纸路径映射
    kw_to_sticker = {}
    for _trigger_name, trigger_data in triggers.items():
        keywords = trigger_data.get("keywords", [])
        asset_id = trigger_data.get("primary_asset")
        if not asset_id:
            continue
        sticker_path = _resolve_sticker_asset(asset_id, catalog)
        if sticker_path:
            for kw in keywords:
                kw_to_sticker[kw.lower()] = sticker_path

    # 匹配 keyword_emphases
    stickers = []
    used_times = []
    for emp in keyword_emphases:
        if len(stickers) >= 3:
            break
        kw_lower = emp.keyword.lower()
        sticker_path = kw_to_sticker.get(kw_lower)
        if not sticker_path:
            # 尝试部分匹配
            for kw_key, path in kw_to_sticker.items():
                if kw_key in kw_lower or kw_lower in kw_key:
                    sticker_path = path
                    break
        if not sticker_path or not Path(sticker_path).exists():
            continue

        ts = emp.word_start_ms / 1000.0 if emp.word_start_ms else 0
        if ts <= 0:
            continue
        # 间隔 ≥ 3s
        if any(abs(ts - ut) < 3.0 for ut in used_times):
            continue

        stickers.append({
            "sticker_path": sticker_path,
            "timestamp": ts,
            "duration": 1.5,
            "position": "top_right" if len(stickers) % 2 == 0 else "top_left",
            "scale": 0.15,
        })
        used_times.append(ts)

    return stickers


def _resolve_sticker_asset(asset_id: str, catalog: dict):
    """在 catalog kits 中搜索贴纸文件路径"""
    from pathlib import Path
    for kit_name, kit_data in catalog.get("kits", {}).items():
        stickers = kit_data.get("stickers", [])
        if isinstance(stickers, list):
            for s in stickers:
                if isinstance(s, dict) and s.get("id") == asset_id:
                    return str(Path(utils.get_project_root()) / "res" / "effects" / s["path"])
    return None


class VideoAiEffectsCore:
    """视频AI特效核心类（单例模式）

    协调字幕加载、视觉分析、节拍检测、LLM导演、ASS生成、FFmpeg渲染各环节。
    支持任务取消和进度回调。
    """
    _singleton = None
    _lock = threading.Lock()
    _cancelled_tasks = set()
    _cancel_lock = threading.Lock()

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self._executor = ThreadPoolExecutor(max_workers=3)
        self._count_lock = threading.Lock()
        self._task_counter = 0
        self._initialized = True

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._singleton is None:
            with cls._lock:
                if cls._singleton is None:
                    cls._singleton = cls()
        return cls._singleton

    @classmethod
    def cancel_task(cls, task_id: str) -> Tuple[int, str]:
        """取消指定任务"""
        if not task_id:
            return ErrorCodes.INVALID_INPUT[0], "Task ID 不能为空"
        with cls._cancel_lock:
            cls._cancelled_tasks.add(task_id)
        utils.print2(f"[VideoAiEffects] 收到取消请求: {task_id}")
        try:
            flag_path = os.path.join(utils.get_project_root(), "workflow_output", f"{task_id}.cancel")
            with open(flag_path, 'w') as f:
                f.write('1')
        except Exception:
            pass
        return ErrorCodes.SUCCESS[0], "取消请求已提交"

    # ------------------------------------------------------------------
    # 兼容旧接口: 保持原有 video_ai_effect 签名
    # ------------------------------------------------------------------
    @staticmethod
    async def video_ai_effect(
        input_path: str,
        output_path: str,
        genre_hint: str = "",
        task_id: str = "",
        progress_callback: Optional[Callable[[int], None]] = None,
        master_name: str = "",
    ) -> Tuple[int, str]:
        """旧版兼容接口：对视频施加AI特效"""
        _task_id = task_id if task_id else utils.get_uuid()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        # 创建 internal_callback 包装用户提供的进度回调，处理异步/同步兼容
        def internal_callback(p: int):
            if not progress_callback:
                return
            try:
                if asyncio.iscoroutinefunction(progress_callback):
                    if loop and not loop.is_closed():
                        asyncio.run_coroutine_threadsafe(progress_callback(p), loop)
                else:
                    try:
                        progress_callback(p)
                    except Exception:
                        pass
            except Exception:
                pass

        # 构建 RenderingConfig 配置对象，默认启用全部功能模块
        config = RenderingConfig(
            input_path=input_path,
            output_path=output_path,
            task_id=_task_id,
            genre=genre_hint,
            sfx_enabled=True,
            progress_callback=internal_callback,
        )

        instance = VideoAiEffectsCore.get_instance()
        return await loop.run_in_executor(
            instance._executor,
            instance._apply_sync_impl,
            config,
        )

    # ------------------------------------------------------------------
    # 新接口: 通过 RenderingConfig 调用
    # ------------------------------------------------------------------
    @staticmethod
    async def apply_effects(config: RenderingConfig) -> Tuple[int, str]:
        """通过 RenderingConfig 配置对象施加特效（推荐使用此接口）"""
        instance = VideoAiEffectsCore.get_instance()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            instance._executor,
            instance._apply_sync_impl,
            config,
        )

    # ------------------------------------------------------------------
    # 核心同步实现
    # ------------------------------------------------------------------
    def _apply_sync_impl(self, config: RenderingConfig) -> Tuple[int, str]:
        """特效应用的核心同步实现

        流水线：
        Step 1:   加载/生成字幕 → auto_split 拆行
        Step 1.5: 视觉分析 + 节拍检测（并发）→ 筛选强拍
        Step 2:   LLM导演决策 → keyword_sfx 对齐 + zoom_pulses 合并
        Step 2.5: BGM推荐
        Step 3:   生成ASS文件（逐词高亮 + 关键词overlay）
        Step 4:   FFmpeg渲染（zoompan + 音效混合）
        """
        task_id = config.task_id
        path_mgr = None
        project_root = utils.get_project_root()

        def check_cancel():
            with self._cancel_lock:
                if task_id in self._cancelled_tasks:
                    raise RuntimeError("FLOW_CANCELLED")
            flag_path = os.path.join(project_root, "workflow_output", f"{task_id}.cancel")
            if os.path.exists(flag_path):
                raise RuntimeError("FLOW_CANCELLED")

        def report(p: int, message: str = ""):
            cb = config.progress_callback
            if not cb:
                return
            try:
                cb(p)
            except Exception:
                pass

        try:
            if not config.task_id:
                with self._count_lock:
                    self._task_counter += 1
                task_id = f"fx_{self._task_counter}"
                config.task_id = task_id

            path_mgr = EffectsPathManager(task_id)

            # F9: 应用爆款模板（如已指定）
            if config.template_name:
                from .templates.viral_templates import apply_template
                apply_template(config.template_name, config)
                utils.print2(f"[VideoAiEffects] Template applied: {config.template_name}")

            report(5, "准备处理...")

            # ==============================================================
            # 第一步：加载或生成字幕并拆行
            # ==============================================================
            check_cancel()
            segments = self._load_subtitles(config, path_mgr)
            if not segments:
                segments = self._auto_transcribe(config, path_mgr)
            if not segments:
                return ErrorCodes.ASS_GENERATION_FAILED[0], "No subtitle data found"

            # 改进5: 获取分辨率后用像素宽度判定是否需要拆行长字幕
            try:
                renderer_tmp = FFmpegRenderer()
                video_resolution = renderer_tmp.get_video_resolution(config.input_path)
                style_config_tmp = get_style(config.style_id) if config.style_id else None
                split_font_size = style_config_tmp.font_size if style_config_tmp else 52
                split_scale_x = style_config_tmp.scale_x if style_config_tmp else 100.0
                margin_lr = 60 + 60
                max_px = video_resolution[0] - margin_lr
                segments = auto_split_segments(
                    segments,
                    max_pixel_width=max_px,
                    font_size=split_font_size,
                    scale_x=split_scale_x,
                )
            except Exception:
                segments = auto_split_segments(segments)

            report(15, "字幕已就绪")

            # ==============================================================
            # 第1.5步：视觉分析与节拍检测并发执行
            # ==============================================================
            check_cancel()
            visual_result = None
            beat_info = None

            if config.enable_visual_analysis or config.enable_beat_sync:
                with ThreadPoolExecutor(max_workers=2) as analysis_pool:
                    futures = {}

                    if config.enable_visual_analysis:
                        futures["visual"] = analysis_pool.submit(
                            self._run_visual_analysis, config, task_id,
                        )
                    if config.enable_beat_sync:
                        futures["beat"] = analysis_pool.submit(
                            self._run_beat_detection, config,
                        )

                    for key, future in futures.items():
                        try:
                            if key == "visual":
                                visual_result = future.result(timeout=120)
                            elif key == "beat":
                                beat_info = future.result(timeout=60)
                        except Exception as e:
                            utils.print2(f"[VideoAiEffects] {key} analysis failed: {e}")

            report(35, "分析完成")

            # ==============================================================
            # 第二步：LLM导演决策
            # ==============================================================
            check_cancel()
            style_id = config.style_id
            style_config = None
            keyword_emphases = []
            # effects = getattr(config, '_effects', [])
            effects = getattr(config, '_effects', None) or []

            if style_id:
                style_config = get_style(style_id)

            if not style_config:
                video_duration = 0.0
                video_resolution = (1080, 1920)
                try:
                    renderer = FFmpegRenderer()
                    video_duration = renderer.get_video_duration(config.input_path)
                    video_resolution = renderer.get_video_resolution(config.input_path)
                except Exception:
                    pass

                transcript_text = " ".join(seg.text for seg in segments)
                director_output = analyze_and_recommend(
                    transcript_text=transcript_text,
                    srt_segments=segments,
                    video_duration=video_duration,
                    video_resolution=video_resolution,
                    platform_hint=config.platform,
                    genre_hint=config.genre,
                    visual_analysis=visual_result,
                    beat_info=beat_info,
                )
                if director_output and director_output.style_id:
                    utils.print2(f"[VideoAiEffects] LLM director: style={director_output.style_id}, "
                                 f"effects={len(director_output.effects or [])}, "
                                 f"keywords={len(director_output.keyword_emphases or [])}")
                    style_id = director_output.style_id
                    style_config = get_style(style_id)
                    if config.sfx_enabled and director_output.effects:
                        effects = director_output.effects
                    if config.enable_huazi and director_output.keyword_emphases:
                        keyword_emphases = director_output.keyword_emphases
                    config._visual_result = visual_result
                    config._beat_info = beat_info
                    config._director_output = director_output
                else:
                    utils.print2("[VideoAiEffects] LLM director returned no result, using fallback")

                if not style_config:
                    style_config = get_style("tiktok_pop_yellow")
                    if not style_config:
                        return ErrorCodes.ASS_STYLE_NOT_FOUND[0], "No style available"

            # 兜底：如果LLM没有返回花字关键词，使用增强版降级提取
            if config.enable_huazi and not keyword_emphases:
                transcript_text = " ".join(seg.text for seg in segments)
                genre_str = config.genre or "vlog"
                keyword_emphases = _extract_keyword_emphases(transcript_text, genre_str)
                utils.print2(f"[VideoAiEffects] Fallback keywords: {len(keyword_emphases)} extracted")

            # ==============================================================
            # 第2步（新增）：关键词对齐音效 + 缩放脉冲收集（频率上限控制）
            # ==============================================================
            check_cancel()

            # 效果频率上限：以视频时长为基准
            try:
                renderer_dur = FFmpegRenderer()
                video_duration = renderer_dur.get_video_duration(config.input_path)
            except Exception:
                video_duration = 0.0

            max_keywords = max(3, min(int(video_duration / 5), 8)) if video_duration > 0 else 3
            max_sfx_count = max(3, min(int(video_duration / 5), 8)) if video_duration > 0 else 3
            max_zoom_count = max(2, min(int(video_duration / 8), 6)) if video_duration > 0 else 2

            if keyword_emphases and len(keyword_emphases) > max_keywords:
                keyword_emphases = keyword_emphases[:max_keywords]

            # 关键词触发 SFX
            keyword_sfx = []
            if config.sfx_enabled and keyword_emphases:
                keyword_sfx = self._generate_keyword_sfx(
                    keyword_emphases, segments, config.sfx_volume,
                )

            # 合并 SFX：关键词 SFX + LLM SFX，去重，截断到频率上限
            all_effects = keyword_sfx + effects
            all_effects = self._deduplicate_effects(all_effects, min_gap=0.4)
            all_effects = all_effects[:max_sfx_count]
            utils.print2(f"[VideoAiEffects] SFX: keyword_sfx={len(keyword_sfx)}, "
                         f"total_effects={len(all_effects)}, beat_info={beat_info is not None}")

            # 收集 zoom 脉冲（强拍 + 关键词时刻），截断到频率上限
            if config.enable_beat_sync:
                beat_times = beat_info.beat_times if beat_info else []
                onset_strengths = beat_info.onset_strengths if beat_info else []
                renderer_tmp = FFmpegRenderer()
                config.zoom_pulses = renderer_tmp._collect_zoom_pulses(
                    beat_times, onset_strengths, keyword_emphases, segments,
                    max_pulses=max_zoom_count,
                )
            elif keyword_emphases:
                renderer_tmp = FFmpegRenderer()
                config.zoom_pulses = renderer_tmp._collect_zoom_pulses(
                    None, None, keyword_emphases, segments,
                    max_pulses=max_zoom_count,
                )
            utils.print2(f"[VideoAiEffects] Zoom pulses: {len(config.zoom_pulses or [])}, "
                         f"visual_result={visual_result is not None}")

            report(50, f"样式: {style_config.style_name}")

            # ==============================================================
            # 第2.4步：智能开头Hook检测 (功能模块F1)
            # ==============================================================
            check_cancel()
            if config.enable_smart_hook and not config.hook_config:
                config.hook_config = HookConfig(mode="auto")
            if config.enable_smart_hook and config.hook_config:
                hook_cfg = config.hook_config
                if hook_cfg.mode in ("auto", "extract_teaser"):
                    hook_cfg.teaser_start_time = detect_best_hook_moment(
                        beat_info=beat_info,
                        keyword_emphases=keyword_emphases,
                        segments=segments,
                        video_duration=video_duration,
                        hook_duration=hook_cfg.teaser_duration,
                    )
                    if hook_cfg.teaser_start_time is not None:
                        utils.print2(f"[VideoAiEffects] Hook teaser at {hook_cfg.teaser_start_time:.1f}s, "
                                     f"duration={hook_cfg.teaser_duration}s")
                    elif hook_cfg.mode == "auto":
                        # 未找到高能量片段 — 完全跳过Hook
                        # 避免添加黑屏文字覆盖层浪费观众时间
                        hook_cfg.mode = "none"
                        utils.print2("[VideoAiEffects] No hook moment found, skipping hook")
                if hook_cfg.mode == "text_overlay" and not hook_cfg.overlay_text:
                    transcript_text = " ".join(seg.text for seg in segments)
                    hook_cfg.overlay_text = select_hook_text(
                        hook_cfg, transcript_text, config.genre,
                    )
                config.hook_config = hook_cfg

            # ==============================================================
            # 第2.5步：动态变速分析 (功能模块F2)
            # ==============================================================
            check_cancel()
            speed_ramped_input = None
            original_input_path = config.input_path
            if config.enable_speed_ramp:
                if not config.speed_ramp_config:
                    config.speed_ramp_config = SpeedRampConfig(enabled=True)
                ramp_cfg = config.speed_ramp_config
                ramp_segments = generate_speed_ramp_segments(
                    video_duration=video_duration,
                    beat_info=beat_info,
                    keyword_emphases=keyword_emphases,
                    segments=segments,
                    config=ramp_cfg,
                )
                if ramp_segments and any(s.speed != 1.0 for s in ramp_segments):
                    ramp_cfg.segments = ramp_segments
                    # 预处理：生成变速后的视频文件
                    speed_ramped_input = str(path_mgr.get_path("speed_ramped.mp4"))
                    utils.print2(f"[VideoAiEffects] Speed ramp: {len(ramp_segments)} segments, "
                                 f"speeds={[f'{s.speed:.2f}x' for s in ramp_segments]}")
                    success = apply_speed_ramp_prepass(
                        input_path=original_input_path,
                        output_path=speed_ramped_input,
                        ramp_segments=ramp_segments,
                        video_duration=video_duration,
                        ffmpeg_path=utils.get_ffmpeg_path(),
                    )
                    if success:
                        config.input_path = speed_ramped_input
                        # 将所有特效时间戳重新映射到变速后的时间轴
                        if all_effects:
                            all_effects = self._remap_effects_for_speed(all_effects, ramp_segments)
                        utils.print2(f"[VideoAiEffects] Speed ramp applied: {speed_ramped_input}")
                    else:
                        utils.print2("[VideoAiEffects] Speed ramp prepass failed, using original")
                else:
                    utils.print2("[VideoAiEffects] Speed ramp: no significant energy variation detected")
            config._speed_ramped_input = speed_ramped_input
            config._original_input_path = original_input_path

            # ==============================================================
            # 第2.6步：背景音乐推荐
            # ==============================================================
            check_cancel()
            if not config.bgm_path:
                try:
                    director_out = getattr(config, '_director_output', None)
                    mood = ""
                    if director_out and director_out.bgm_recommendation:
                        mood = director_out.bgm_recommendation.get("mood", "")
                    bgm_path = recommend_bgm(
                        visual_analysis=visual_result,
                        genre=config.genre,
                        mood=mood,
                    )
                    if bgm_path:
                        config.bgm_path = bgm_path
                        config.bgm_volume = 0.1
                except Exception as e:
                    utils.print2(f"[VideoAiEffects] BGM recommendation failed: {e}")

            report(55, "特效编排完成")

            # ==============================================================
            # 第2.7步：场景转场 (功能模块F4: 丰富转场效果)
            # ==============================================================
            if visual_result and visual_result.scene_changes and video_duration > 2.0:
                from .effects.transition_engine import generate_transition_plan
                if not config.transition_config:
                    config.transition_config = TransitionConfig()
                config.transition_config.transitions = generate_transition_plan(
                    scene_changes=visual_result.scene_changes,
                    beat_info=beat_info,
                    video_duration=video_duration,
                    config=config.transition_config,
                )
                # 同时保留兼容的 timestamps 列表
                config.scene_transitions = [t["time"] for t in config.transition_config.transitions]
                utils.print2(f"[VideoAiEffects] Rich transitions: {len(config.transition_config.transitions)} "
                             f"types={[t['type'] for t in config.transition_config.transitions]}")

            # ==============================================================
            # 第2.75步：传播力评分 (功能模块F10)
            # ==============================================================
            from .effects.engagement_scorer import score_engagement
            config._engagement_score = score_engagement(
                hook_config=config.hook_config,
                speed_ramp_config=config.speed_ramp_config,
                kinetic_config=config.kinetic_typo_config,
                transition_config=getattr(config, 'transition_config', None),
                beat_info=beat_info,
                keyword_emphases=keyword_emphases,
                segments=segments,
                video_duration=video_duration,
                sfx_count=len(all_effects),
                zoom_pulse_count=len(config.zoom_pulses or []),
                bgm_enabled=bool(config.bgm_path),
            )
            utils.print2(f"[VideoAiEffects] Engagement score: {config._engagement_score.overall}/100, "
                         f"hook={config._engagement_score.hook_strength}, "
                         f"pacing={config._engagement_score.pacing_score}")

            # 转场音效
            if config.sfx_enabled and config.scene_transitions:
                for t in config.scene_transitions[:3]:
                    sfx_path = get_sfx("swoosh_cut")
                    if sfx_path:
                        all_effects.append(EffectPlan(
                            timestamp=t,
                            effect_type="sfx",
                            sfx_path=sfx_path,
                            duration=0.25,
                            intensity=0.4,
                        ))
                all_effects = self._deduplicate_effects(all_effects, min_gap=0.4)

            # ==============================================================
            # 第2.8步：贴纸选择 + 调色 + 动态图形
            # ==============================================================
            # 自动调色配置 (功能模块F6)
            if config.enable_color_grading and not config.color_grading_config:
                from .effects.color_grading import select_color_preset
                preset = select_color_preset(
                    visual_analysis=visual_result,
                    genre=config.genre,
                )
                config.color_grading_config = ColorGradingConfig(enabled=True, preset=preset)
                utils.print2(f"[VideoAiEffects] Color grading: preset={preset}")

            # 动态图形叠加 (功能模块F7)
            if config.enable_motion_graphics and keyword_emphases:
                if not config.motion_graphics_config:
                    config.motion_graphics_config = MotionGraphicsConfig(enabled=True)
                if not config.motion_graphics_config.graphics:
                    from .effects.motion_graphics import generate_motion_graphics_from_keywords
                    graphics = generate_motion_graphics_from_keywords(
                        keyword_emphases=keyword_emphases,
                        segments=segments,
                        video_duration=video_duration,
                        max_count=config.motion_graphics_config.max_graphics,
                    )
                    config.motion_graphics_config.graphics = [
                        MotionGraphic(**g) for g in graphics
                    ]
                    utils.print2(f"[VideoAiEffects] Motion graphics: {len(graphics)} generated")

            # 贴纸匹配
            if config.enable_huazi and keyword_emphases:
                config.sticker_overlays = _select_stickers_for_keywords(
                    keyword_emphases, video_duration,
                )
                utils.print2(f"[VideoAiEffects] Stickers: {len(config.sticker_overlays or [])} matched, "
                             f"keywords={[e.keyword for e in keyword_emphases[:5]]}")

            # ==============================================================
            # 第三步：生成ASS文件
            # ==============================================================
            check_cancel()
            try:
                renderer = FFmpegRenderer()
                video_resolution = renderer.get_video_resolution(config.input_path)
            except Exception:
                video_resolution = (1080, 1920)

            # 高级字幕样式：描边+投影+边缘模糊（"文字浮在画面上"效果）
            _apply_premium_subtitle_style(style_config, video_resolution)

            # 方向感知边距：根据视频方向和平台调整安全区
            _apply_orientation_margins(style_config, config.platform, video_resolution)

            ass_path = str(path_mgr.get_ass_path(f"{style_id}.ass"))
            # F3: 确定动态排版配置
            kinetic_cfg = None
            if config.enable_kinetic_typo:
                if config.kinetic_typo_config:
                    kinetic_cfg = config.kinetic_typo_config
                else:
                    kinetic_cfg = KineticTypographyConfig(enabled=True, emphasis_preset="viral")
            generate_ass_file(
                segments=segments,
                style_config=style_config,
                output_path=ass_path,
                play_res_x=video_resolution[0],
                play_res_y=video_resolution[1],
                language=config.language,
                keyword_emphases=keyword_emphases if config.enable_huazi else None,
                kinetic_config=kinetic_cfg,
            )

            report(70, "ASS字幕已生成")

            # ==============================================================
            # 第四步：FFmpeg渲染
            # ==============================================================
            check_cancel()
            output_path = config.output_path or str(path_mgr.get_output_path("output.mp4"))
            config.output_path = output_path

            utils.print2(f"[VideoAiEffects] Rendering: sfx={len(all_effects)}, "
                         f"zoom={len(config.zoom_pulses or [])}, "
                         f"transitions={len(config.scene_transitions or [])}, "
                         f"stickers={len(config.sticker_overlays or [])}, "
                         f"bgm={bool(config.bgm_path)}")

            renderer = FFmpegRenderer()
            result_code, result_msg = renderer.render(
                config=config,
                ass_path=ass_path,
                effects=all_effects,
                check_cancel=lambda tid: self._is_cancelled(tid),
            )

            if result_code == ErrorCodes.SUCCESS[0]:
                report(95, "渲染完成")

            return result_code, result_msg

        except RuntimeError as e:
            if str(e) == "FLOW_CANCELLED":
                utils.print2(f"[VideoAiEffects] 任务被取消: {task_id}")
                return ErrorCodes.USER_CANCELLED[0], "任务被取消"
            return ErrorCodes.UNKNOWN_ERROR[0], str(e)

        except Exception as e:
            utils.print2(f"[VideoAiEffects] Error: {e}")
            import traceback
            traceback.print_exc()
            return ErrorCodes.UNKNOWN_ERROR[0], str(e)
        finally:
            with self._cancel_lock:
                self._cancelled_tasks.discard(task_id)
            try:
                flag_path = os.path.join(project_root, "workflow_output", f"{task_id}.cancel")
                if os.path.exists(flag_path):
                    os.remove(flag_path)
            except Exception:
                pass
            if path_mgr:
                path_mgr.cleanup()
            # 清理变速临时文件
            ramped_input = getattr(config, '_speed_ramped_input', None)
            if ramped_input and os.path.exists(ramped_input):
                try:
                    os.remove(ramped_input)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 改进4: 关键词对齐 SFX 生成
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_keyword_sfx(
        keyword_emphases: list,
        segments: list,
        sfx_volume: float = 0.6,
    ) -> List[EffectPlan]:
        """为每个关键词生成对齐到其说话时刻的音效"""
        # 花字预设 → 默认音效映射
        preset_sfx_map = {
            "pop_highlight": "pop",
            "emoji_pop": "pop_sparkle",
            "scale_pulse": "pop",
            "bounce_letter": "boing",
            "glow_emphasis": "magic_chime",
            "color_flash": "click_sharp",
            "box_highlight": "tap",
            "neon_flash": "digital_beep",
            "shake_word": "impact_boom",
            "gradient_fill": "magic_chime",
            "underline_sweep": "whoosh",
            "typewriter_reveal": "keyboard_press",
        }

        effects = []
        for emp in keyword_emphases:
            keyword = emp.keyword
            if not keyword:
                continue

            # 找关键词所在 segment
            target_seg = None
            for seg in segments:
                if keyword in seg.text:
                    target_seg = seg
                    break
            if not target_seg:
                continue

            # 精准时间定位
            timing = _find_keyword_word_timing(target_seg, keyword)
            if timing:
                timestamp = timing[0] / 1000.0
            else:
                pos = target_seg.text.find(keyword)
                ratio = pos / max(len(target_seg.text), 1)
                timestamp = target_seg.start_ms / 1000.0 + ratio * (target_seg.end_ms - target_seg.start_ms) / 1000.0

            # 找匹配的 SFX
            sfx_path = match_sfx_to_keyword(keyword)
            if not sfx_path:
                default_name = preset_sfx_map.get(emp.preset, "pop")
                sfx_path = get_sfx(default_name)
            if not sfx_path:
                continue

            effects.append(EffectPlan(
                timestamp=timestamp,
                effect_type="sfx",
                sfx_path=sfx_path,
                duration=0.4,
                intensity=0.7,
                segment_index=target_seg.index,
            ))
        return effects

    @staticmethod
    def _remap_effects_for_speed(
        effects: List[EffectPlan],
        ramp_segments: list,
    ) -> List[EffectPlan]:
        """将特效时间戳按变速映射重新计算"""
        if not ramp_segments or not effects:
            return effects
        # 对每个变速段计算累积偏移
        cumulative_offset = 0.0
        breakpoints = []
        for seg in ramp_segments:
            dur = seg.end_time - seg.start_time
            if dur <= 0:
                continue
            if seg.speed != 1.0:
                new_dur = dur / seg.speed
                cumulative_offset += (new_dur - dur)
            breakpoints.append((seg.end_time, cumulative_offset))
        if not breakpoints:
            return effects
        remapped = []
        for eff in effects:
            ts = eff.timestamp
            offset = 0.0
            for bp_time, bp_offset in breakpoints:
                if ts <= bp_time:
                    for seg in ramp_segments:
                        if seg.start_time <= ts < seg.end_time:
                            offset = (ts - seg.start_time) * (1.0 / max(seg.speed, 0.1) - 1.0)
                            break
                    break
                offset = bp_offset
            remapped.append(EffectPlan(
                timestamp=round(ts + offset, 3),
                effect_type=eff.effect_type,
                sfx_path=eff.sfx_path,
                duration=eff.duration,
                intensity=eff.intensity,
                position=eff.position,
                keyword_emphasis=eff.keyword_emphasis,
                sticker_path=eff.sticker_path,
                transition_type=eff.transition_type,
                beat_aligned=eff.beat_aligned,
                segment_index=eff.segment_index,
            ))
        return remapped

    @staticmethod
    def _deduplicate_effects(effects: List[EffectPlan], min_gap: float = 0.4) -> List[EffectPlan]:
        """按时间排序去重：时间间隔 < min_gap 的只保留第一个"""
        if not effects:
            return []
        effects.sort(key=lambda e: e.timestamp)
        result = [effects[0]]
        for eff in effects[1:]:
            if eff.timestamp - result[-1].timestamp >= min_gap:
                result.append(eff)
        return result

    # ------------------------------------------------------------------
    # 并发分析辅助方法
    # ------------------------------------------------------------------

    def _run_visual_analysis(self, config: RenderingConfig, task_id: str):
        """在子线程中执行视觉分析"""
        try:
            return analyze_video_visuals(
                video_path=config.input_path,
                task_id=task_id,
                interval_sec=config.visual_analysis_interval,
            )
        except Exception as e:
            utils.print2(f"[VideoAiEffects] Visual analysis error: {e}")
            return None

    def _run_beat_detection(self, config: RenderingConfig):
        """在子线程中执行节拍检测"""
        try:
            beat_data = detect_beats(config.input_path)
            if beat_data:
                return BeatInfo(
                    tempo=beat_data.get("tempo", 0),
                    beat_times=beat_data.get("beat_times", []),
                    onset_times=beat_data.get("onset_times", []),
                    onset_strengths=beat_data.get("onset_strengths", []),
                )
            return None
        except Exception as e:
            utils.print2(f"[VideoAiEffects] Beat detection error: {e}")
            return None

    # ------------------------------------------------------------------
    # 取消检查
    # ------------------------------------------------------------------

    def _is_cancelled(self, task_id: str) -> bool:
        """供渲染器回调使用的取消检查"""
        with self._cancel_lock:
            if task_id in self._cancelled_tasks:
                return True
        try:
            flag_path = os.path.join(utils.get_project_root(), "workflow_output", f"{task_id}.cancel")
            if os.path.exists(flag_path):
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # 字幕加载
    # ------------------------------------------------------------------

    def _load_subtitles(self, config: RenderingConfig, path_mgr: EffectsPathManager) -> list:
        """加载字幕文件（支持 SRT 和 JSON 格式）"""
        if config.srt_path:
            srt_path = config.srt_path
            if srt_path.endswith(".json"):
                return parse_json_subtitles(srt_path)
            return parse_srt_to_segments(srt_path)
        return []

    def _auto_transcribe(self, config: RenderingConfig, path_mgr: EffectsPathManager) -> list:
        """自动转录：当没有字幕文件时，通过 ASR 生成字幕"""
        try:
            # from libs.media_core.function.video_subtitle_transcribe import VideoSubtitleTranscribe
            from ..video_subtitle_transcribe import VideoSubtitleTranscribe
            audio_dir = str(path_mgr.get_path("srt_dir"))
            result = VideoSubtitleTranscribe.video_subtitle_transcribe(
                input_path=config.input_path,
                target_language=config.language,
                output_dir=audio_dir,
            )
            asr_code = result[0][0]
            srt_path = result[1]
            if asr_code != ErrorCodes.SUCCESS[0] or not srt_path or not os.path.exists(srt_path):
                utils.print2(f"[VideoAiEffects] ASR failed: {result[0]}")
                return []
            config.srt_path = srt_path
            return parse_srt_to_segments(srt_path)
        except Exception as e:
            utils.print2(f"[VideoAiEffects] Auto-transcribe error: {e}")
            return []

    # ------------------------------------------------------------------
    # 公共查询接口
    # ------------------------------------------------------------------

    @staticmethod
    def get_available_styles() -> dict:
        """获取所有可用样式，按分类分组返回"""
        result = {}
        for style_info in get_all_style_ids():
            cat = style_info["category"]
            if cat not in result:
                result[cat] = {"title": cat, "styles": []}
            result[cat]["styles"].append(style_info)
        return result

    @staticmethod
    def get_categories() -> list:
        """获取所有样式分类"""
        return get_all_categories()

    @staticmethod
    def get_style_info(style_id: str) -> Optional[dict]:
        """获取指定样式的详细信息"""
        style = get_style(style_id)
        if not style:
            return None
        return {
            "id": style.style_id,
            "name": style.style_name,
            "category": style.category,
            "platform": style.platform,
            "description": style.description,
            "tags": style.tags,
            "animation": style.animation.value,
            "font_size": style.font_size,
        }

    @staticmethod
    def get_style_count() -> int:
        """获取样式总数"""
        return get_style_count()
