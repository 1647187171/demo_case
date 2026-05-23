"""
renderer.py — FFmpeg渲染器

负责将ASS字幕文件、zoompan缩放脉冲和音效通过FFmpeg合成到视频。
支持纯字幕渲染、字幕+音效+zoompan混合渲染、贴纸叠加三种模式。
"""
import subprocess
import json
import time
from typing import Optional, List, Tuple, Callable, Dict, Any
from pathlib import Path

from libs.media_core.utils import utils
from libs.api.error_codes import ErrorCodes

from .models import RenderingConfig, EffectPlan


class FFmpegRenderer:
    """FFmpeg渲染器：字幕硬烧、zoompan脉冲、音效混合"""

    def render(
        self,
        config: RenderingConfig,
        ass_path: str,
        effects: Optional[List[EffectPlan]] = None,
        check_cancel: Optional[Callable] = None,
    ) -> Tuple[int, str]:
        try:
            if check_cancel and check_cancel(config.task_id):
                return ErrorCodes.USER_CANCELLED[0], "Task cancelled"

            valid_sfx = []
            if effects:
                for eff in effects:
                    if eff.effect_type == "sfx" and eff.sfx_path and Path(eff.sfx_path).exists():
                        valid_sfx.append(eff)

            has_sfx = bool(valid_sfx)
            has_bgm = bool(config.bgm_path and Path(config.bgm_path).exists())
            has_zoom = bool(config.zoom_pulses)
            needs_audio_mix = has_sfx or has_bgm

            # 无音频混合需求时走纯字幕路径（支持 zoompan + 音频 copy）
            if not needs_audio_mix:
                result = self._render_subtitles_only(config, ass_path, check_cancel)
                result = self._validate_output(result, config.output_path)
            else:
                # 有音频混合需求时检查视频是否有音轨
                if not self._has_audio_stream(config.input_path):
                    utils.print2("[FFmpegRenderer] No audio stream, falling back to subtitles-only")
                    result = self._render_subtitles_only(config, ass_path, check_cancel)
                    result = self._validate_output(result, config.output_path)
                else:
                    result = self._render_with_audio(config, ass_path, valid_sfx, check_cancel)

                    # 降级处理：如果zoompan导致失败，移除后重试
                    if result[0] != ErrorCodes.SUCCESS[0] and has_zoom:
                        utils.print2("[FFmpegRenderer] Retrying without zoompan...")
                        saved_pulses = config.zoom_pulses
                        config.zoom_pulses = None
                        try:
                            result = self._render_with_audio(config, ass_path, valid_sfx, check_cancel)
                        finally:
                            config.zoom_pulses = saved_pulses

                    result = self._validate_output(result, config.output_path)

            if result[0] != ErrorCodes.SUCCESS[0]:
                return result

            # F1: 后处理 — 在片头添加Hook介绍
            has_hook = (config.enable_smart_hook and config.hook_config and
                        config.hook_config.mode != "none" and
                        (config.hook_config.teaser_start_time is not None or config.hook_config.overlay_text))
            if has_hook:
                result = self._prepend_hook(config, check_cancel)

            # F8: 后处理 — 在片尾添加CTA画面
            if config.enable_end_screen and config.end_screen_config:
                result = self._append_end_screen(config, check_cancel)

            return result
        except Exception as e:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], f"Render failed: {str(e)}"

    # ------------------------------------------------------------------
    # Zoompan缩放脉冲表达式构建
    # ------------------------------------------------------------------

    def _build_zoompan_expression(
        self,
        duration: float,
        pulses: List[Dict[str, float]],
        peak_zoom: float = 1.06,
        pulse_dur: float = 0.8,
    ) -> Optional[str]:
        """从 pulse 列表构建 FFmpeg zoompan 的 zoom= 表达式

        每个 pulse 生成正弦曲线钟形脉冲，平滑地 zoom in 再 zoom out。
        使用 sin(PI*(time-t0)/dur) 在 [t0, t0+dur] 区间内产生平滑缩放。
        注意: FFmpeg zoompan 使用 'time' 变量，不是 't'。
        """
        if not pulses:
            return None

        pulses = sorted(pulses, key=lambda p: p["time"])[:15]

        parts = []
        for p in pulses:
            t = p["time"]
            strength = p.get("strength", 0.5)
            delta = round((peak_zoom - 1.0) * strength, 4)
            if delta < 0.005:
                continue
            t_start = round(max(0, t), 3)
            t_end = round(t_start + pulse_dur, 3)
            parts.append(
                f"{delta}*sin(PI*(time-{t_start})/{pulse_dur})"
                f"*if(gt(time,{t_start})*lt(time,{t_end}),1,0)"
            )

        if not parts:
            return None

        expr = "1+" + "+".join(parts)
        return expr

    def _collect_zoom_pulses(
        self,
        beat_times: Optional[List[float]],
        onset_strengths: Optional[List[float]],
        keyword_emphases: Optional[List] = None,
        segments: Optional[List] = None,
        max_pulses: int = 4,
    ) -> List[Dict[str, float]]:
        """合并强拍 + 关键词时刻为统一的 zoom pulse 列表"""
        pulses = []

        # 强拍
        if beat_times:
            from .effects.beat_sync import get_strong_beats
            strong = get_strong_beats(beat_times, onset_strengths or [], percentile=60, max_beats=10)
            pulses.extend(strong)

        # 关键词时刻
        if keyword_emphases and segments:
            for emp in keyword_emphases:
                kw_time = None
                if emp.word_start_ms:
                    kw_time = emp.word_start_ms / 1000.0
                elif segments:
                    for seg in segments:
                        if emp.keyword in seg.text:
                            kw_time = seg.start_ms / 1000.0
                            break
                if kw_time is not None and kw_time > 0:
                    pulses.append({"time": kw_time, "strength": 0.8})

        # 按时间排序 + 去重 (最小间隔 0.3s)
        pulses.sort(key=lambda p: p["time"])
        deduped = []
        for p in pulses:
            if not deduped or p["time"] - deduped[-1]["time"] >= 0.3:
                deduped.append(p)
        return deduped[:max_pulses]

    # ------------------------------------------------------------------
    # 渲染方法
    # ------------------------------------------------------------------

    def _validate_output(self, result: Tuple[int, str], output_path: str) -> Tuple[int, str]:
        """渲染后校验输出文件有效性"""
        if result[0] != ErrorCodes.SUCCESS[0]:
            return result
        try:
            size = Path(output_path).stat().st_size
            if size < 10_000:
                utils.print2(f"[FFmpegRenderer] Output too small: {size} bytes")
                return ErrorCodes.FFMPEG_RENDER_FAILED[0], f"Output file too small ({size} bytes), render may have failed"
        except FileNotFoundError:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], "Output file not found after render"
        return result

    def _build_fade_transitions(self, timestamps: List[float]) -> str:
        """DEPRECATED: 使用 _build_variety_transitions 替代"""
        return self._build_variety_transitions(timestamps, None)

    def _build_variety_transitions(
        self,
        transition_plan: Optional[List[Dict[str, Any]]] = None,
        video_resolution: Optional[Tuple[int, int]] = None,
    ) -> str:
        """构建丰富转场滤镜链（F4）

        根据转场计划中每个转场的类型生成对应FFmpeg滤镜。
        如果没有计划则退回经典fade-to-black。
        """
        if not transition_plan:
            return ""

        from .effects.transition_engine import build_all_transition_filters
        w, h = video_resolution or (1080, 1920)
        return build_all_transition_filters(transition_plan, w, h)

    def _build_motion_graphics_vf(
        self,
        config: RenderingConfig,
        resolution: Tuple[int, int],
    ) -> str:
        """构建动态图形滤镜（进度条、箭头等）"""
        if not config.motion_graphics_config or not config.motion_graphics_config.enabled:
            return ""
        if not config.motion_graphics_config.graphics:
            return ""
        try:
            from .effects.motion_graphics import build_all_motion_graphics_filters
            mg_data = []
            for g in config.motion_graphics_config.graphics:
                mg_data.append({
                    "graphic_type": g.graphic_type,
                    "timestamp": g.timestamp,
                    "duration": g.duration,
                    "position": g.position,
                    "color": g.color,
                    "label": g.label,
                    "target_pos": g.target_pos,
                })
            return build_all_motion_graphics_filters(
                mg_data, resolution[0], resolution[1],
            )
        except Exception as e:
            utils.print2(f"[FFmpegRenderer] Motion graphics failed: {e}")
            return ""

    def _render_subtitles_only(
        self,
        config: RenderingConfig,
        ass_path: str,
        check_cancel: Optional[Callable],
    ) -> Tuple[int, str]:
        ffmpeg = utils.get_ffmpeg_path()
        fonts_dir = self._get_fonts_dir()
        resolution = self.get_video_resolution(config.input_path)

        # F11: 自动裁切 — 滤镜链中首个滤镜
        crop_vf = ""
        if config.enable_auto_crop and config.crop_config:
            from .effects.crop_engine import build_crop_filter
            crop_vf = build_crop_filter(
                src_width=resolution[0],
                src_height=resolution[1],
                config=config.crop_config,
                visual_analysis=getattr(config, '_visual_result', None),
            )

        # F6: 自动调色 — 在字幕之前应用
        color_vf = ""
        if config.enable_color_grading and config.color_grading_config:
            from .effects.color_grading import build_color_grading_filter
            color_vf = build_color_grading_filter(
                config.color_grading_config,
                getattr(config, '_visual_result', None),
                config.genre,
            )

        # 合并裁切与调色滤镜
        pre_filters = ",".join(f for f in [crop_vf, color_vf] if f)

        sub_path = str(Path(ass_path).resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        vf = f"subtitles='{sub_path}'"
        if fonts_dir:
            fonts_dir_esc = str(fonts_dir).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
            vf = f"subtitles='{sub_path}':fontsdir='{fonts_dir_esc}'"
        if pre_filters:
            vf = pre_filters + "," + vf

        # Zoompan缩放脉冲滤镜
        if config.zoom_pulses:
            duration = self.get_video_duration(config.input_path)
            zoompan_expr = self._build_zoompan_expression(duration, config.zoom_pulses)
            if zoompan_expr:
                w, h = resolution
                vf += f",zoompan=z='{zoompan_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:fps=30:s={w}x{h}"

        # 场景转场 (F4: 丰富转场或降级淡入淡出)
        if config.transition_config and config.transition_config.transitions:
            variety_filters = self._build_variety_transitions(
                config.transition_config.transitions, resolution,
            )
            if variety_filters:
                vf += "," + variety_filters
        elif config.scene_transitions:
            fade_filters = self._build_fade_transitions(config.scene_transitions)
            if fade_filters:
                vf += "," + fade_filters

        # 动态图形覆盖 (进度条、箭头等)
        mg_vf = self._build_motion_graphics_vf(config, resolution)
        if mg_vf:
            vf += "," + mg_vf

        # 有贴纸时改用 filter_complex
        stickers = config.sticker_overlays or []
        sticker_inputs = [stk for stk in stickers if Path(stk["sticker_path"]).exists()]

        if sticker_inputs:
            return self._render_subtitles_with_stickers(
                config, vf, sticker_inputs, check_cancel,
            )

        cmd = [
            ffmpeg, "-y",
            "-i", config.input_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            config.output_path,
        ]

        result = self._run_ffmpeg(cmd, check_cancel, config.task_id)
        if result != 0:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], "FFmpeg subtitle render failed"
        return ErrorCodes.SUCCESS[0], "Success"

    def _render_subtitles_with_stickers(
        self,
        config: RenderingConfig,
        vf: str,
        sticker_inputs: list,
        check_cancel: Optional[Callable],
    ) -> Tuple[int, str]:
        """纯字幕路径 + 贴纸叠加（无音频混合时使用）"""
        ffmpeg = utils.get_ffmpeg_path()
        resolution = self.get_video_resolution(config.input_path)
        w, h = resolution

        inputs = ["-i", config.input_path]
        for stk in sticker_inputs:
            inputs.extend(["-i", stk["sticker_path"]])

        filter_parts = [f"[0:v]{vf}[basev]"]
        current_label = "basev"

        for i, stk in enumerate(sticker_inputs):
            scale_w = int(w * stk.get("scale", 0.15))
            ts = stk["timestamp"]
            dur = stk.get("duration", 1.5)
            end_t = ts + dur
            pos = stk.get("position", "top_right")
            if pos == "top_left":
                ox, oy = int(w * 0.05), int(h * 0.05)
            else:
                ox, oy = int(w * 0.80), int(h * 0.05)

            stk_label = f"stk{i}"
            next_label = f"vstk{i}" if i < len(sticker_inputs) - 1 else "outv"
            filter_parts.append(
                f"[{i + 1}:v]scale={scale_w}:-1,format=yuva420p"
                f",fade=t=in:st={ts:.3f}:d=0.2:alpha=1"
                f",fade=t=out:st={max(0, end_t - 0.3):.3f}:d=0.3:alpha=1"
                f"[{stk_label}]"
            )
            filter_parts.append(
                f"[{current_label}][{stk_label}]overlay={ox}:{oy}"
                f":enable='between(t,{ts:.3f},{end_t:.3f})'"
                f"[{next_label}]"
            )
            current_label = next_label

        filter_complex = ";".join(filter_parts)

        cmd = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{current_label}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            config.output_path,
        ]

        result = self._run_ffmpeg(cmd, check_cancel, config.task_id)
        if result != 0:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], "FFmpeg subtitle+sticker render failed"
        return ErrorCodes.SUCCESS[0], "Success"

    def _render_with_audio(
        self,
        config: RenderingConfig,
        ass_path: str,
        sfx_effects: List[EffectPlan],
        check_cancel: Optional[Callable],
    ) -> Tuple[int, str]:
        ffmpeg = utils.get_ffmpeg_path()
        fonts_dir = self._get_fonts_dir()

        max_sfx = 20
        sfx_effects = sfx_effects[:max_sfx]

        inputs = ["-i", config.input_path]
        for effect in sfx_effects:
            inputs.extend(["-i", effect.sfx_path])

        bgm_idx = None
        sfx_count = len(sfx_effects)
        if config.bgm_path and Path(config.bgm_path).exists():
            bgm_idx = 1 + sfx_count
            inputs.extend(["-i", config.bgm_path])

        # 贴纸输入
        stickers = config.sticker_overlays or []
        sticker_inputs = []
        for stk in stickers:
            if Path(stk["sticker_path"]).exists():
                inputs.extend(["-i", stk["sticker_path"]])
                sticker_inputs.append(stk)

        filter_parts = []

        resolution = self.get_video_resolution(config.input_path)

        # F11 + F6: 裁切与调色前置滤镜
        pre_filters = []
        if config.enable_auto_crop and config.crop_config:
            from .effects.crop_engine import build_crop_filter
            crop_f = build_crop_filter(
                src_width=resolution[0], src_height=resolution[1],
                config=config.crop_config,
                visual_analysis=getattr(config, '_visual_result', None),
            )
            if crop_f:
                pre_filters.append(crop_f)
        if config.enable_color_grading and config.color_grading_config:
            from .effects.color_grading import build_color_grading_filter
            color_f = build_color_grading_filter(
                config.color_grading_config,
                getattr(config, '_visual_result', None),
                config.genre,
            )
            if color_f:
                pre_filters.append(color_f)
        pre_filter_str = ",".join(pre_filters)

        # 视频：字幕 + zoompan（在 filter_complex 中用 ; 分开避免逗号冲突）
        sub_path = str(Path(ass_path).resolve()).replace(":", r"\:").replace("'", r"\'")
        vf = f"subtitles='{sub_path}'"
        if fonts_dir:
            fonts_dir_esc = str(fonts_dir).replace(":", r"\:").replace("'", r"\'")
            vf = f"subtitles='{sub_path}':fontsdir='{fonts_dir_esc}'"

        if config.zoom_pulses:
            duration = self.get_video_duration(config.input_path)
            zoompan_expr = self._build_zoompan_expression(duration, config.zoom_pulses)
            if zoompan_expr:
                w, h = resolution
                # 调色 → 字幕 → zoompan
                vf_full = pre_filter_str + "," + vf if pre_filter_str else vf
                filter_parts.append(f"[0:v]{vf_full}[subbed]")
                filter_parts.append(
                    f"[subbed]zoompan=z='{zoompan_expr}'"
                    f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":d=1:fps=30:s={w}x{h}[outv]"
                )
            else:
                vf_full = pre_filter_str + "," + vf if pre_filter_str else vf
                filter_parts.append(f"[0:v]{vf_full}[outv]")
        else:
            vf_full = pre_filter_str + "," + vf if pre_filter_str else vf
            filter_parts.append(f"[0:v]{vf_full}[outv]")

        # 场景转场 (F4)：在 [outv] 上叠加转场效果
        out_label = "outv"
        if config.transition_config and config.transition_config.transitions:
            variety_filters = self._build_variety_transitions(
                config.transition_config.transitions, resolution,
            )
            if variety_filters:
                filter_parts.append(f"[outv]{variety_filters}[outvf]")
                out_label = "outvf"
        elif config.scene_transitions:
            fade_filters = self._build_fade_transitions(config.scene_transitions)
            if fade_filters:
                filter_parts.append(f"[outv]{fade_filters}[outvf]")
                out_label = "outvf"

        # 动态图形覆盖 (进度条、箭头等)
        mg_vf = self._build_motion_graphics_vf(config, resolution)
        if mg_vf:
            filter_parts.append(f"[{out_label}]{mg_vf}[outvmg]")
            out_label = "outvmg"

        # 贴纸叠加
        if sticker_inputs:
            resolution = self.get_video_resolution(config.input_path)
            w, h = resolution
            base_input_idx = 1 + sfx_count + (1 if bgm_idx else 0)
            current_label = out_label
            for i, stk in enumerate(sticker_inputs):
                stk_idx = base_input_idx + i
                scale_w = int(w * stk.get("scale", 0.15))
                ts = stk["timestamp"]
                dur = stk.get("duration", 1.5)
                end_t = ts + dur
                pos = stk.get("position", "top_right")
                if pos == "top_left":
                    ox, oy = int(w * 0.05), int(h * 0.05)
                else:
                    ox, oy = int(w * 0.80), int(h * 0.05)

                stk_label = f"stk{i}"
                next_label = f"vstk{i}" if i < len(sticker_inputs) - 1 else "finalv"
                # 缩放贴纸 + 淡入淡出
                filter_parts.append(
                    f"[{stk_idx}:v]scale={scale_w}:-1,format=yuva420p"
                    f",fade=t=in:st={ts:.3f}:d=0.2:alpha=1"
                    f",fade=t=out:st={max(0, end_t - 0.3):.3f}:d=0.3:alpha=1"
                    f"[{stk_label}]"
                )
                filter_parts.append(
                    f"[{current_label}][{stk_label}]overlay={ox}:{oy}"
                    f":enable='between(t,{ts:.3f},{end_t:.3f})'"
                    f"[{next_label}]"
                )
                current_label = next_label
            out_label = current_label

        # 音频混合 (F5: 带侧链闪避)
        ducking_enabled = (config.enable_ducking and config.ducking_config and
                           config.ducking_config.enabled)
        audio_parts = []

        if ducking_enabled and (sfx_effects or bgm_idx is not None):
            # 构建侧链闪避：SFX+BGM混合 → 作为sidechain信号 → 压缩原始音频
            dcfg = config.ducking_config
            audio_parts.append("[0:a]volume=1.3[base_pre]")

            sfx_mix_labels = []
            for i in range(len(sfx_effects)):
                input_idx = i + 1
                delay_ms = max(0, int(sfx_effects[i].timestamp * 1000))
                vol = max(0.1, min(1.0, sfx_effects[i].intensity * config.sfx_volume))
                label = f"sfx_duc{i}"
                audio_parts.append(
                    f"[{input_idx}:a]adelay={delay_ms}|{delay_ms},volume={vol:.2f}[{label}]"
                )
                sfx_mix_labels.append(f"[{label}]")

            if bgm_idx is not None:
                bgm_vol = max(0.01, min(0.5, config.bgm_volume))
                audio_parts.append(f"[{bgm_idx}:a]volume={bgm_vol:.2f}[bgm_duc]")
                sfx_mix_labels.append("[bgm_duc]")

            all_sc = "".join(sfx_mix_labels)
            sc_count = len(sfx_mix_labels)
            if sc_count > 0:
                audio_parts.append(
                    f"{all_sc}amix=inputs={sc_count}:duration=first[sc_signal]"
                )
                audio_parts.append(
                    f"[base_pre]sidechaincompress=threshold={dcfg.threshold_db / 100:.3f}:"
                    f"ratio=4:attack={dcfg.attack_ms}:release={dcfg.release_ms}:"
                    f"makeup=1:knee=3:link=average[ducked_base]"
                )
                audio_parts.append(
                    f"[ducked_base][sc_signal]amix=inputs=2:"
                    f"duration=first:dropout_transition=2[aout]"
                )
            else:
                audio_parts.append("[base_pre]anull[aout]")
        else:
            # 两阶段音频混合：保持原始语音质量
            # 阶段1: 混合所有效果音 (SFX + BGM)
            # 阶段2: 将效果音叠加到原始音频上，语音占主导
            audio_parts = ["[0:a]volume=1.3[base_boosted]"]

            sfx_labels_orig = []
            for i, effect in enumerate(sfx_effects):
                input_idx = i + 1
                delay_ms = max(0, int(effect.timestamp * 1000))
                vol = max(0.1, min(1.0, effect.intensity * config.sfx_volume))
                label = f"sfx{i}"
                audio_parts.append(
                    f"[{input_idx}:a]adelay={delay_ms}|{delay_ms},volume={vol:.2f}[{label}]"
                )
                sfx_labels_orig.append(f"[{label}]")

            bgm_label_orig = ""
            if bgm_idx is not None:
                bgm_label_orig = "bgm"
                bgm_vol = max(0.01, min(0.5, config.bgm_volume))
                audio_parts.append(
                    f"[{bgm_idx}:a]volume={bgm_vol:.2f}[{bgm_label_orig}]"
                )

            effect_count = len(sfx_labels_orig) + (1 if bgm_label_orig else 0)
            if effect_count > 0:
                effect_inputs = "".join(sfx_labels_orig) + (f"[{bgm_label_orig}]" if bgm_label_orig else "")
                audio_parts.append(
                    f"{effect_inputs}amix=inputs={effect_count}:duration=first:normalize=1[effects_mix]"
                )
                audio_parts.append(
                    f"[base_boosted][effects_mix]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
            else:
                audio_parts.append("[base_boosted]anull[aout]")

        filter_complex = ";".join(filter_parts + audio_parts)

        cmd = [
            ffmpeg, "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", f"[{out_label}]",
            "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            config.output_path,
        ]

        result = self._run_ffmpeg(cmd, check_cancel, config.task_id)
        if result != 0:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], "FFmpeg render with audio failed"
        return ErrorCodes.SUCCESS[0], "Success"

    def _render_soft_sub(
        self,
        config: RenderingConfig,
        ass_path: str,
    ) -> Tuple[int, str]:
        ffmpeg = utils.get_ffmpeg_path()
        cmd = [
            ffmpeg, "-y",
            "-i", config.input_path,
            "-i", ass_path,
            "-c", "copy",
            "-c:s", "copy",
            config.output_path,
        ]
        result = self._run_ffmpeg(cmd, None, "")
        if result != 0:
            return ErrorCodes.FFMPEG_RENDER_FAILED[0], "FFmpeg soft-sub failed"
        return ErrorCodes.SUCCESS[0], "Success"

    def get_video_resolution(self, video_path: str) -> Tuple[int, int]:
        try:
            ffprobe = self._get_ffprobe_path()
            cmd = [
                ffprobe,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            stream = data.get("streams", [{}])[0]
            return int(stream.get("width", 1080)), int(stream.get("height", 1920))
        except Exception:
            return 1080, 1920

    def get_video_duration(self, video_path: str) -> float:
        try:
            ffprobe = self._get_ffprobe_path()
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def _run_ffmpeg(
        self,
        cmd: List[str],
        check_cancel: Optional[Callable],
        task_id: str,
    ) -> int:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        while True:
            if check_cancel and task_id and check_cancel(task_id):
                process.kill()
                return -1
            try:
                ret = process.poll()
                if ret is not None:
                    if ret != 0:
                        try:
                            stderr_output = process.stderr.read()
                            utils.print2(f"[FFmpegRenderer] FFmpeg failed (code={ret}), stderr:\n{stderr_output[:3000]}")
                        except Exception:
                            pass
                    return ret
            except Exception:
                process.kill()
                return -1
            time.sleep(0.1)

    def _get_fonts_dir(self) -> Optional[Path]:
        try:
            project_root = Path(utils.get_project_root())
            fonts_dir = project_root / "res" / "fonts"
            if fonts_dir.exists():
                return fonts_dir
        except Exception:
            pass
        return None

    def _get_ffprobe_path(self) -> str:
        return str(Path(utils.get_ffmpeg_path()).parent / "ffprobe")

    def _has_audio_stream(self, video_path: str) -> bool:
        """检查视频文件是否包含音轨"""
        try:
            ffprobe = self._get_ffprobe_path()
            cmd = [
                ffprobe, "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                video_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return bool(result.stdout.strip())
        except Exception:
            return True

    # ------------------------------------------------------------------
    # F1: Hook片头拼接
    # ------------------------------------------------------------------

    def _prepend_hook(
        self,
        config: RenderingConfig,
        check_cancel: Optional[Callable],
    ) -> Tuple[int, str]:
        """将Hook片头（teaser或文字覆盖）拼接到渲染输出之前"""
        hook_cfg = config.hook_config
        if not hook_cfg:
            return ErrorCodes.SUCCESS[0], "Success"

        ffmpeg = utils.get_ffmpeg_path()
        output_path = config.output_path
        tmp_main = output_path + ".main_tmp.mp4"
        tmp_hook = output_path + ".hook_tmp.mp4"
        concat_list = output_path + ".concat.txt"

        try:
            Path(output_path).rename(tmp_main)
            w, h = self.get_video_resolution(tmp_main)

            if hook_cfg.mode == "text_overlay" and hook_cfg.overlay_text:
                # 生成文字叠加Hook片段
                text = hook_cfg.overlay_text.replace("'", r"\'").replace(":", r"\:")
                dur = min(hook_cfg.teaser_duration, hook_cfg.max_duration)
                font_size = max(28, min(64, int(w * 0.06)))
                cmd_hook = [
                    ffmpeg, "-y",
                    "-f", "lavfi", "-i",
                    f"color=c=0x1a1a2e:s={w}x{h}:d={dur:.3f}:r=30",
                    "-f", "lavfi", "-i",
                    f"anullsrc=r=44100:cl=stereo",
                    "-vf",
                    f"drawtext=text='{text}':fontcolor=white:fontsize={font_size}:"
                    f"x=(w-text_w)/2:y=(h-text_h)/2-30:"
                    f"box=1:boxcolor=black@0.4:boxborderw=20:"
                    f"enable='between(t,0,{dur:.2f})'",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k",
                    "-t", f"{dur:.3f}",
                    "-pix_fmt", "yuv420p",
                    tmp_hook,
                ]
                if check_cancel and config.task_id and check_cancel(config.task_id):
                    return ErrorCodes.USER_CANCELLED[0], "Task cancelled"
                result = self._run_ffmpeg(cmd_hook, check_cancel, config.task_id)
                if result != 0:
                    # 失败时恢复原始输出
                    Path(tmp_main).rename(output_path)
                    return ErrorCodes.SUCCESS[0], "Success (hook skipped)"

            elif hook_cfg.teaser_start_time is not None:
                # 从原始视频中提取teaser片段
                ts = hook_cfg.teaser_start_time
                dur = min(hook_cfg.teaser_duration, hook_cfg.max_duration)
                cmd_hook = [
                    ffmpeg, "-y",
                    "-i", config.input_path,
                    "-ss", f"{ts:.3f}",
                    "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "128k",
                    "-pix_fmt", "yuv420p",
                    tmp_hook,
                ]
                if check_cancel and config.task_id and check_cancel(config.task_id):
                    return ErrorCodes.USER_CANCELLED[0], "Task cancelled"
                result = self._run_ffmpeg(cmd_hook, check_cancel, config.task_id)
                if result != 0:
                    Path(tmp_main).rename(output_path)
                    return ErrorCodes.SUCCESS[0], "Success (hook skipped)"
            else:
                Path(tmp_main).rename(output_path)
                return ErrorCodes.SUCCESS[0], "Success"

            # 拼接Hook + 正片
            concat_content = f"file '{Path(tmp_hook).resolve()}'\nfile '{Path(tmp_main).resolve()}'\n"
            Path(concat_list).write_text(concat_content)

            cmd_concat = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path,
            ]
            if check_cancel and config.task_id and check_cancel(config.task_id):
                return ErrorCodes.USER_CANCELLED[0], "Task cancelled"
            result = self._run_ffmpeg(cmd_concat, check_cancel, config.task_id)
            if result != 0:
                Path(tmp_main).rename(output_path)
                return ErrorCodes.SUCCESS[0], "Success (hook concat failed, using original)"

            utils.print2(f"[FFmpegRenderer] Hook prepended: mode={hook_cfg.mode}")
            return ErrorCodes.SUCCESS[0], "Success"

        except Exception as e:
            utils.print2(f"[FFmpegRenderer] Hook error: {e}")
            try:
                if Path(tmp_main).exists() and not Path(output_path).exists():
                    Path(tmp_main).rename(output_path)
            except Exception:
                pass
            return ErrorCodes.SUCCESS[0], "Success (hook failed, original preserved)"
        finally:
            for p in [tmp_hook, tmp_main, concat_list]:
                try:
                    if Path(p).exists():
                        Path(p).unlink()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # F8: 结尾CTA画面拼接
    # ------------------------------------------------------------------

    def _append_end_screen(
        self,
        config: RenderingConfig,
        check_cancel: Optional[Callable],
    ) -> Tuple[int, str]:
        """将结尾CTA画面拼接到渲染输出之后"""
        end_cfg = config.end_screen_config
        if not end_cfg or not end_cfg.enabled:
            return ErrorCodes.SUCCESS[0], "Success"

        ffmpeg = utils.get_ffmpeg_path()
        output_path = config.output_path
        tmp_main = output_path + ".main_tmp.mp4"
        tmp_end = output_path + ".end_tmp.mp4"
        concat_list = output_path + ".concat.txt"

        try:
            Path(output_path).rename(tmp_main)
            w, h = self.get_video_resolution(tmp_main)
            dur = end_cfg.duration
            font_size_main = max(18, min(48, int(w * 0.045)))
            font_size_sub = max(14, min(32, int(w * 0.03)))
            cx = w // 2

            cta = end_cfg.cta_text.replace("'", r"\'").replace(":", r"\:")
            channel = (end_cfg.channel_name or "").replace("'", r"\'").replace(":", r"\:")

            # 构建drawtext文字滤镜
            text_filters = []
            if channel:
                text_filters.append(
                    f"drawtext=text='{channel}':fontcolor=white:fontsize={font_size_main}:"
                    f"x=(w-text_w)/2:y=h*0.35:"
                    f"alpha='if(lt(t,0.3), t/0.3, 1)'"
                )
            text_filters.append(
                f"drawtext=text='{cta}':fontcolor=yellow:fontsize={font_size_sub}:"
                f"x=(w-text_w)/2:y=h*0.55:"
                f"alpha='if(lt(t,0.6), (t-0.3)/0.3, if(lt(t,{dur-0.3:.2f}), 1, ({dur:.2f}-t)/0.3))'"
            )

            vf = ",".join(text_filters)

            # 提取最后一帧作为模糊背景
            cmd_end = [
                ffmpeg, "-y",
                "-i", tmp_main,
                "-filter_complex",
                f"[0:v]trim=start=999999,loop=loop={int(dur * 30)}:size=1:start=0,"
                f"gblur=sigma={end_cfg.background_blur},"
                f"fade=t=in:d=0.3,{vf}[outv];"
                f"anullsrc=r=44100:cl=stereo[outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                "-t", f"{dur:.3f}",
                "-pix_fmt", "yuv420p",
                tmp_end,
            ]
            if check_cancel and config.task_id and check_cancel(config.task_id):
                return ErrorCodes.USER_CANCELLED[0], "Task cancelled"
            result = self._run_ffmpeg(cmd_end, check_cancel, config.task_id)
            if result != 0:
                Path(tmp_main).rename(output_path)
                return ErrorCodes.SUCCESS[0], "Success (end screen skipped)"

            # 拼接正片 + 结尾画面
            concat_content = f"file '{Path(tmp_main).resolve()}'\nfile '{Path(tmp_end).resolve()}'\n"
            Path(concat_list).write_text(concat_content)

            cmd_concat = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                "-movflags", "+faststart",
                output_path,
            ]
            if check_cancel and config.task_id and check_cancel(config.task_id):
                return ErrorCodes.USER_CANCELLED[0], "Task cancelled"
            result = self._run_ffmpeg(cmd_concat, check_cancel, config.task_id)
            if result != 0:
                Path(tmp_main).rename(output_path)
                return ErrorCodes.SUCCESS[0], "Success (end screen concat failed)"

            utils.print2("[FFmpegRenderer] End screen appended")
            return ErrorCodes.SUCCESS[0], "Success"

        except Exception as e:
            utils.print2(f"[FFmpegRenderer] End screen error: {e}")
            try:
                if Path(tmp_main).exists() and not Path(output_path).exists():
                    Path(tmp_main).rename(output_path)
            except Exception:
                pass
            return ErrorCodes.SUCCESS[0], "Success (end screen failed, original preserved)"
        finally:
            for p in [tmp_end, tmp_main, concat_list]:
                try:
                    if Path(p).exists():
                        Path(p).unlink()
                except Exception:
                    pass
