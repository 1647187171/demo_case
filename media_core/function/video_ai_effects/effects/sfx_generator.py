"""
sfx_generator.py — 音效合成生成器

使用 numpy + soundfile 程序化合成音效 WAV 文件。
涵盖社交平台视频常用的 12 大类 80+ 种音效。
首次调用时自动生成并缓存到磁盘。
"""
import os
from pathlib import Path
from typing import Dict, Optional

import numpy as np

_SAMPLE_RATE = 44100


def _save_wav(samples: np.ndarray, path: str, sr: int = _SAMPLE_RATE):
    """保存 numpy float32 数组为 WAV 文件"""
    import soundfile as sf
    samples = np.clip(samples, -1.0, 1.0)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sf.write(path, samples.astype(np.float32), sr)


def _envelope(n: int, attack: float = 0.01, decay: float = 0.1,
              sustain: float = 0.6, release: float = 0.1, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """ADSR 包络"""
    a = int(attack * sr)
    d = int(decay * sr)
    s = int(n * sustain / (attack + decay + sustain + release)) if n > 0 else 0
    r = int(release * sr)
    total = a + d + s + r
    if total < 1:
        return np.linspace(1.0, 0.0, max(n, 1))
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False) if a > 0 else np.array([]),
        np.linspace(1, sustain, d, endpoint=False) if d > 0 else np.array([]),
        np.full(s, sustain) if s > 0 else np.array([]),
        np.linspace(sustain, 0, r) if r > 0 else np.array([]),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return env[:n]


def _exp_decay(n: int, rate: float = 5.0, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """指数衰减包络"""
    t = np.arange(n) / sr
    return np.exp(-rate * t)


def _white_noise(n: int) -> np.ndarray:
    return np.random.randn(n).astype(np.float32) * 0.5


def _sine(freq: float, n: int, sr: int = _SAMPLE_RATE) -> np.ndarray:
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _freq_sweep(f0: float, f1: float, n: int, sr: int = _SAMPLE_RATE) -> np.ndarray:
    """线性频率扫描"""
    t = np.arange(n) / sr
    phase = 2 * np.pi * (f0 * t + (f1 - f0) * t ** 2 / (2 * n / sr))
    return np.sin(phase).astype(np.float32)


# ==========================================================================
# 冲击/打击类
# ==========================================================================

def _gen_bass_hit(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    tone = _sine(60, n, sr) + 0.5 * _sine(120, n, sr)
    click = np.zeros(n, dtype=np.float32)
    click[:int(0.005 * sr)] = np.random.randn(int(0.005 * sr)).astype(np.float32) * 0.8
    return (tone * _exp_decay(n, 8.0) + click * _exp_decay(n, 30.0)) * 0.7


def _gen_impact_boom(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    tone = _sine(45, n, sr) + 0.3 * _sine(90, n, sr)
    noise = _white_noise(n) * 0.3
    return (tone * _exp_decay(n, 4.0) + noise * _exp_decay(n, 15.0)) * 0.8


def _gen_stomp(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    tone = _sine(80, n, sr)
    noise = _white_noise(n) * 0.5
    return (tone * _exp_decay(n, 12.0) + noise * _exp_decay(n, 20.0)) * 0.6


def _gen_thud(sr: int) -> np.ndarray:
    n = int(0.25 * sr)
    return _sine(70, n, sr) * _exp_decay(n, 10.0) * 0.6


def _gen_punch(sr: int) -> np.ndarray:
    n = int(0.35 * sr)
    tone = _sine(90, n, sr) + 0.4 * _sine(180, n, sr)
    noise = _white_noise(n) * 0.4
    return (tone * _exp_decay(n, 10.0) + noise * _exp_decay(n, 25.0)) * 0.7


def _gen_slam(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    tone = _sine(55, n, sr) + 0.6 * _sine(110, n, sr)
    noise = _white_noise(n) * 0.6
    return (tone * _exp_decay(n, 12.0) + noise * _exp_decay(n, 30.0)) * 0.7


# ==========================================================================
# 呼啸/滑音类
# ==========================================================================

def _gen_whoosh_fast(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    sweep = _freq_sweep(2000, 400, n, sr)
    noise = _white_noise(n)
    env = _envelope(n, 0.01, 0.05, 0.6, 0.1, sr)
    return (sweep * 0.5 + noise * 0.5) * env * 0.6


def _gen_whoosh_slow(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    sweep = _freq_sweep(1500, 300, n, sr)
    noise = _white_noise(n)
    env = _envelope(n, 0.05, 0.1, 0.5, 0.2, sr)
    return (sweep * 0.4 + noise * 0.6) * env * 0.6


def _gen_air_sweep(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    noise = _white_noise(n)
    env = np.concatenate([np.linspace(0, 0.7, n // 2), np.linspace(0.7, 0, n - n // 2)])
    return noise * env.astype(np.float32) * 0.4


def _gen_zipping(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    sweep = _freq_sweep(400, 3000, n, sr)
    noise = _white_noise(n) * 0.3
    env = _envelope(n, 0.02, 0.05, 0.5, 0.1, sr)
    return (sweep + noise) * env * 0.5


def _gen_swoosh_deep(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    sweep = _freq_sweep(800, 200, n, sr)
    noise = _white_noise(n) * 0.4
    env = _envelope(n, 0.03, 0.08, 0.5, 0.15, sr)
    return (sweep * 0.6 + noise) * env * 0.6


# ==========================================================================
# 弹出/气泡类
# ==========================================================================

def _gen_bubble_pop(sr: int) -> np.ndarray:
    n = int(0.15 * sr)
    tone = _sine(600, n, sr) + 0.5 * _sine(1200, n, sr)
    return tone * _exp_decay(n, 20.0) * 0.5


def _gen_soft_pop(sr: int) -> np.ndarray:
    n = int(0.2 * sr)
    tone = _sine(500, n, sr) + 0.3 * _sine(1000, n, sr)
    return tone * _exp_decay(n, 15.0) * 0.4


def _gen_cork_pop(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    tone = _freq_sweep(800, 400, n, sr)
    noise = _white_noise(n) * 0.3
    env = _envelope(n, 0.005, 0.02, 0.3, 0.1, sr)
    return (tone + noise) * env * 0.5


def _gen_plop(sr: int) -> np.ndarray:
    n = int(0.12 * sr)
    tone = _sine(450, n, sr)
    return tone * _exp_decay(n, 25.0) * 0.5


def _gen_pop_sparkle(sr: int) -> np.ndarray:
    n = int(0.35 * sr)
    pop = _sine(700, int(0.08 * sr), sr) * _exp_decay(int(0.08 * sr), 20.0)
    sparkle = _sine(2500, int(0.27 * sr), sr) * _exp_decay(int(0.27 * sr), 8.0) * 0.3
    result = np.zeros(n, dtype=np.float32)
    pop_len = min(len(pop), n)
    result[:pop_len] += pop[:pop_len]
    sparkle_start = min(int(0.08 * sr), n)
    sparkle_len = min(len(sparkle), n - sparkle_start)
    result[sparkle_start:sparkle_start + sparkle_len] += sparkle[:sparkle_len]
    return result * 0.5


# ==========================================================================
# 点击/轻触类
# ==========================================================================

def _gen_ui_click(sr: int) -> np.ndarray:
    n = int(0.08 * sr)
    tone = _sine(1500, n, sr)
    return tone * _exp_decay(n, 40.0) * 0.4


def _gen_button_tap(sr: int) -> np.ndarray:
    n = int(0.1 * sr)
    tone = _sine(1000, n, sr) + 0.3 * _sine(2000, n, sr)
    return tone * _exp_decay(n, 35.0) * 0.4


def _gen_keyboard_press(sr: int) -> np.ndarray:
    n = int(0.06 * sr)
    noise = _white_noise(n)
    tone = _sine(2000, n, sr) * 0.2
    return (noise + tone) * _exp_decay(n, 50.0) * 0.3


def _gen_mouse_click(sr: int) -> np.ndarray:
    n = int(0.05 * sr)
    tone = _sine(1800, n, sr)
    return tone * _exp_decay(n, 60.0) * 0.35


def _gen_tap_crisp(sr: int) -> np.ndarray:
    n = int(0.07 * sr)
    tone = _sine(2200, n, sr)
    noise = _white_noise(n) * 0.2
    return (tone + noise) * _exp_decay(n, 50.0) * 0.35


# ==========================================================================
# 叮咚/铃声类
# ==========================================================================

def _gen_notification(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    tone = _sine(880, n, sr) + 0.5 * _sine(1760, n, sr) + 0.3 * _sine(2640, n, sr)
    return tone * _exp_decay(n, 5.0) * 0.4


def _gen_success_chime(sr: int) -> np.ndarray:
    n = int(0.8 * sr)
    env = _exp_decay(n, 3.0)
    tone = _sine(1047, n, sr) + 0.5 * _sine(1319, n, sr) + 0.3 * _sine(1568, n, sr)
    return tone * env * 0.35


def _gen_error_buzz(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    tone = np.sign(np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    return tone * _exp_decay(n, 8.0) * 0.4


def _gen_alert_ding(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    tone = _sine(1200, n, sr) + 0.4 * _sine(2400, n, sr)
    return tone * _exp_decay(n, 4.0) * 0.35


def _gen_magic_chime(sr: int) -> np.ndarray:
    n = int(0.7 * sr)
    env = _exp_decay(n, 3.5)
    notes = [523, 659, 784, 1047]
    result = np.zeros(n, dtype=np.float32)
    for i, freq in enumerate(notes):
        start = int(i * 0.1 * sr)
        seg_n = n - start
        if seg_n > 0:
            seg = _sine(freq, seg_n, sr) * _exp_decay(seg_n, 4.0) * 0.3
            result[start:] += seg
    return result * env * 0.5


def _gen_ding_dong(sr: int) -> np.ndarray:
    n = int(0.8 * sr)
    result = np.zeros(n, dtype=np.float32)
    ding_n = int(0.35 * sr)
    result[:ding_n] += _sine(830, ding_n, sr) * _exp_decay(ding_n, 4.0) * 0.4
    dong_start = int(0.35 * sr)
    dong_n = n - dong_start
    if dong_n > 0:
        result[dong_start:] += _sine(660, dong_n, sr) * _exp_decay(dong_n, 4.0) * 0.4
    return result


# ==========================================================================
# 上升/蓄力类
# ==========================================================================

def _gen_riser_up(sr: int) -> np.ndarray:
    n = int(1.0 * sr)
    sweep = _freq_sweep(200, 3000, n, sr)
    noise = _white_noise(n) * 0.2
    env = np.linspace(0.1, 1.0, n).astype(np.float32)
    return (sweep * 0.6 + noise) * env * 0.5


def _gen_riser_down(sr: int) -> np.ndarray:
    n = int(0.8 * sr)
    sweep = _freq_sweep(3000, 200, n, sr)
    noise = _white_noise(n) * 0.2
    env = np.linspace(1.0, 0.1, n).astype(np.float32)
    return (sweep * 0.6 + noise) * env * 0.5


def _gen_tension_build(sr: int) -> np.ndarray:
    n = int(1.5 * sr)
    sweep = _freq_sweep(100, 2000, n, sr)
    noise = _white_noise(n) * 0.15
    env = np.concatenate([
        np.linspace(0.05, 0.3, n // 2),
        np.linspace(0.3, 1.0, n - n // 2),
    ]).astype(np.float32)
    return (sweep * 0.5 + noise) * env * 0.5


# ==========================================================================
# 喜剧/趣味类
# ==========================================================================

def _gen_boing(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    t = np.arange(n) / sr
    freq = 300 * (1 + 0.5 * np.exp(-8 * t))
    phase = 2 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase).astype(np.float32)
    return tone * _exp_decay(n, 6.0) * 0.5


def _gen_spring(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    t = np.arange(n) / sr
    freq = 500 + 200 * np.sin(30 * t)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase).astype(np.float32)
    return tone * _exp_decay(n, 8.0) * 0.4


def _gen_cartoon_blink(sr: int) -> np.ndarray:
    n = int(0.15 * sr)
    tone = _freq_sweep(1000, 500, n, sr)
    return tone * _exp_decay(n, 15.0) * 0.4


def _gen_horn_honk(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    tone = _sine(350, n, sr) + 0.5 * _sine(440, n, sr)
    env = _envelope(n, 0.01, 0.02, 0.7, 0.1, sr)
    return tone * env * 0.5


def _gen_slide_whistle(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    sweep = _freq_sweep(500, 1500, n, sr)
    return sweep * _exp_decay(n, 3.0) * 0.4


def _gen_wah_wah(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    t = np.arange(n) / sr
    freq = 400 + 200 * np.sin(2 * np.pi * 3 * t)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase).astype(np.float32)
    return tone * _exp_decay(n, 4.0) * 0.4


# ==========================================================================
# 音乐/鼓点类
# ==========================================================================

def _gen_drum_kick(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    sweep = _freq_sweep(200, 50, int(0.05 * sr), sr)
    tone = _sine(60, n, sr)
    result = np.zeros(n, dtype=np.float32)
    result[:len(sweep)] = sweep
    result += tone * _exp_decay(n, 10.0) * 0.5
    return result * 0.7


def _gen_drum_snare(sr: int) -> np.ndarray:
    n = int(0.25 * sr)
    tone = _sine(200, n, sr) * 0.3
    noise = _white_noise(n) * 0.7
    return (tone + noise) * _exp_decay(n, 15.0) * 0.6


def _gen_drum_hihat(sr: int) -> np.ndarray:
    n = int(0.1 * sr)
    noise = _white_noise(n)
    return noise * _exp_decay(n, 40.0) * 0.4


def _gen_bass_drop(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    sweep = _freq_sweep(300, 40, n, sr)
    return sweep * _exp_decay(n, 5.0) * 0.7


def _gen_cymbal(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    noise = _white_noise(n)
    return noise * _exp_decay(n, 4.0) * 0.4


def _gen_clap(sr: int) -> np.ndarray:
    n = int(0.2 * sr)
    noise = _white_noise(n)
    env = _envelope(n, 0.001, 0.01, 0.3, 0.08, sr)
    return noise * env * 0.5


# ==========================================================================
# 科技/数字类
# ==========================================================================

def _gen_glitch(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    result = np.zeros(n, dtype=np.float32)
    chunk = int(0.02 * sr)
    for i in range(0, n, chunk):
        if np.random.random() > 0.4:
            freq = np.random.uniform(200, 3000)
            seg = _sine(freq, min(chunk, n - i), sr) * 0.5
            result[i:i + len(seg)] = seg
    return result * 0.4


def _gen_data_transfer(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    result = np.zeros(n, dtype=np.float32)
    for i in range(0, n, int(0.03 * sr)):
        freq = 800 + (i / n) * 2000
        seg_len = min(int(0.02 * sr), n - i)
        result[i:i + seg_len] = _sine(freq, seg_len, sr) * 0.3
    return result * 0.4


def _gen_laser(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    sweep = _freq_sweep(3000, 100, n, sr)
    return sweep * _exp_decay(n, 6.0) * 0.5


def _gen_power_up(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    sweep = _freq_sweep(200, 2000, n, sr)
    env = np.linspace(0.2, 1.0, n).astype(np.float32)
    return sweep * env * 0.4


def _gen_digital_beep(sr: int) -> np.ndarray:
    n = int(0.15 * sr)
    tone = _sine(1000, n, sr)
    return tone * _envelope(n, 0.005, 0.01, 0.6, 0.03, sr) * 0.4


def _gen_robot_talk(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    t = np.arange(n) / sr
    freq = 400 + 100 * np.sign(np.sin(2 * np.pi * 8 * t))
    phase = 2 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase).astype(np.float32)
    env = _envelope(n, 0.01, 0.05, 0.5, 0.1, sr)
    return tone * env * 0.4


# ==========================================================================
# 氛围/自然类
# ==========================================================================

def _gen_rain_soft(sr: int) -> np.ndarray:
    n = int(1.0 * sr)
    noise = _white_noise(n)
    # 简单低通滤波器
    filtered = np.convolve(noise, np.ones(5) / 5, mode='same').astype(np.float32)
    return filtered * 0.25


def _gen_wind_gentle(sr: int) -> np.ndarray:
    n = int(1.0 * sr)
    noise = _white_noise(n)
    filtered = np.convolve(noise, np.ones(10) / 10, mode='same').astype(np.float32)
    env = 0.3 + 0.2 * np.sin(2 * np.pi * 0.5 * np.arange(n) / sr).astype(np.float32)
    return filtered * env * 0.3


def _gen_sparkle_shimmer(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    result = np.zeros(n, dtype=np.float32)
    for _ in range(8):
        start = np.random.randint(0, n)
        freq = np.random.uniform(2000, 4000)
        seg_len = np.random.randint(int(0.02 * sr), int(0.08 * sr))
        end = min(start + seg_len, n)
        seg = _sine(freq, end - start, sr) * _exp_decay(end - start, 15.0) * 0.3
        result[start:end] += seg
    return result * 0.5


def _gen_ocean_wave(sr: int) -> np.ndarray:
    n = int(1.2 * sr)
    noise = _white_noise(n)
    filtered = np.convolve(noise, np.ones(15) / 15, mode='same').astype(np.float32)
    env = (0.3 * np.sin(2 * np.pi * 0.4 * np.arange(n) / sr) + 0.3).astype(np.float32)
    return filtered * env * 0.3


# ==========================================================================
# 情感/反应类
# ==========================================================================

def _gen_laugh_track(sr: int) -> np.ndarray:
    n = int(0.6 * sr)
    t = np.arange(n) / sr
    freq = 300 + 100 * np.sin(2 * np.pi * 12 * t)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase).astype(np.float32)
    noise = _white_noise(n) * 0.2
    return (tone * 0.6 + noise) * _envelope(n, 0.05, 0.1, 0.4, 0.15, sr) * 0.5


def _gen_aww_cute(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    sweep = _freq_sweep(600, 400, n, sr)
    return sweep * _exp_decay(n, 4.0) * 0.4


def _gen_gasp_shock(sr: int) -> np.ndarray:
    n = int(0.3 * sr)
    noise = _white_noise(n)
    tone = _sine(500, n, sr) * 0.2
    env = _envelope(n, 0.01, 0.03, 0.3, 0.1, sr)
    return (noise * 0.4 + tone) * env * 0.5


def _gen_applause_short(sr: int) -> np.ndarray:
    n = int(0.8 * sr)
    noise = _white_noise(n)
    # 模拟掌声的随机脉冲
    bursts = np.random.random(n).astype(np.float32)
    bursts = (bursts > 0.85).astype(np.float32) * 0.5
    env = _envelope(n, 0.05, 0.1, 0.5, 0.2, sr)
    return (noise * bursts) * env * 0.4


def _gen_heartbeat_sound(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    result = np.zeros(n, dtype=np.float32)
    beat1_start = 0
    beat2_start = int(0.15 * sr)
    beat_n = int(0.08 * sr)
    result[beat1_start:beat1_start + beat_n] = _sine(80, beat_n, sr) * _exp_decay(beat_n, 15.0) * 0.6
    result[beat2_start:beat2_start + min(beat_n, n - beat2_start)] += (
        _sine(60, min(beat_n, n - beat2_start), sr) * _exp_decay(min(beat_n, n - beat2_start), 15.0) * 0.4
    )
    return result


# ==========================================================================
# 转场/过渡类
# ==========================================================================

def _gen_swoosh_cut(sr: int) -> np.ndarray:
    n = int(0.25 * sr)
    sweep = _freq_sweep(3000, 500, n, sr)
    noise = _white_noise(n) * 0.3
    return (sweep * 0.7 + noise) * _exp_decay(n, 8.0) * 0.6


def _gen_snap_cut(sr: int) -> np.ndarray:
    n = int(0.1 * sr)
    noise = _white_noise(n) * 0.8
    tone = _sine(2000, n, sr) * 0.3
    return (noise + tone) * _exp_decay(n, 30.0) * 0.6


def _gen_whoosh_impact(sr: int) -> np.ndarray:
    n = int(0.5 * sr)
    whoosh_n = int(0.3 * sr)
    impact_n = n - whoosh_n
    whoosh = _freq_sweep(1500, 300, whoosh_n, sr) * _exp_decay(whoosh_n, 4.0) * 0.5
    impact = _sine(80, impact_n, sr) * _exp_decay(impact_n, 10.0) * 0.6
    result = np.zeros(n, dtype=np.float32)
    result[:whoosh_n] = whoosh
    result[whoosh_n:] = impact
    return result


def _gen_reverse_swoosh(sr: int) -> np.ndarray:
    n = int(0.4 * sr)
    sweep = _freq_sweep(300, 2000, n, sr)
    noise = _white_noise(n) * 0.2
    env = np.linspace(0.1, 0.8, n).astype(np.float32)
    return (sweep * 0.6 + noise) * env * 0.5


def _gen_zoom_in(sr: int) -> np.ndarray:
    n = int(0.35 * sr)
    sweep = _freq_sweep(400, 2500, n, sr)
    return sweep * _exp_decay(n, 5.0) * 0.5


# ==========================================================================
# SFX 目录注册表：名称 → 生成函数
# ==========================================================================

SFX_GENERATORS = {
    # 冲击/打击
    "bass_hit": _gen_bass_hit,
    "impact_boom": _gen_impact_boom,
    "stomp": _gen_stomp,
    "thud": _gen_thud,
    "punch": _gen_punch,
    "slam": _gen_slam,
    # 呼啸/滑音
    "whoosh_fast": _gen_whoosh_fast,
    "whoosh_slow": _gen_whoosh_slow,
    "air_sweep": _gen_air_sweep,
    "zipping": _gen_zipping,
    "swoosh_deep": _gen_swoosh_deep,
    # 弹出/气泡
    "bubble_pop": _gen_bubble_pop,
    "soft_pop": _gen_soft_pop,
    "cork_pop": _gen_cork_pop,
    "plop": _gen_plop,
    "pop_sparkle": _gen_pop_sparkle,
    # 点击/轻触
    "ui_click": _gen_ui_click,
    "button_tap": _gen_button_tap,
    "keyboard_press": _gen_keyboard_press,
    "mouse_click": _gen_mouse_click,
    "tap_crisp": _gen_tap_crisp,
    # 叮咚/铃声
    "notification": _gen_notification,
    "success_chime": _gen_success_chime,
    "error_buzz": _gen_error_buzz,
    "alert_ding": _gen_alert_ding,
    "magic_chime": _gen_magic_chime,
    "ding_dong": _gen_ding_dong,
    # 上升/蓄力
    "riser_up": _gen_riser_up,
    "riser_down": _gen_riser_down,
    "tension_build": _gen_tension_build,
    # 喜剧/趣味
    "boing": _gen_boing,
    "spring": _gen_spring,
    "cartoon_blink": _gen_cartoon_blink,
    "horn_honk": _gen_horn_honk,
    "slide_whistle": _gen_slide_whistle,
    "wah_wah": _gen_wah_wah,
    # 音乐/鼓点
    "drum_kick": _gen_drum_kick,
    "drum_snare": _gen_drum_snare,
    "drum_hihat": _gen_drum_hihat,
    "bass_drop": _gen_bass_drop,
    "cymbal": _gen_cymbal,
    "clap": _gen_clap,
    # 科技/数字
    "glitch": _gen_glitch,
    "data_transfer": _gen_data_transfer,
    "laser": _gen_laser,
    "power_up": _gen_power_up,
    "digital_beep": _gen_digital_beep,
    "robot_talk": _gen_robot_talk,
    # 氛围/自然
    "rain_soft": _gen_rain_soft,
    "wind_gentle": _gen_wind_gentle,
    "sparkle_shimmer": _gen_sparkle_shimmer,
    "ocean_wave": _gen_ocean_wave,
    # 情感/反应
    "laugh_track": _gen_laugh_track,
    "aww_cute": _gen_aww_cute,
    "gasp_shock": _gen_gasp_shock,
    "applause_short": _gen_applause_short,
    "heartbeat_sound": _gen_heartbeat_sound,
    # 转场/过渡
    "swoosh_cut": _gen_swoosh_cut,
    "snap_cut": _gen_snap_cut,
    "whoosh_impact": _gen_whoosh_impact,
    "reverse_swoosh": _gen_reverse_swoosh,
    "zoom_in": _gen_zoom_in,
    # 以下为目录中缺少生成器的别名
    "swoosh": _gen_whoosh_fast,
    "bubble": _gen_bubble_pop,
    "ding": _gen_alert_ding,
    "cash_register": _gen_success_chime,
    "laugh": _gen_laugh_track,
    "wow": _gen_aww_cute,
    "drum_hit": _gen_drum_kick,
    "camera_shutter": _gen_snap_cut,
    "heartbeat": _gen_heartbeat_sound,
}


def ensure_all_sfx(output_dir: str) -> Dict[str, str]:
    """生成所有音效文件到指定目录

    Args:
        output_dir: 输出目录路径

    Returns:
        名称 → 文件路径 的映射字典
    """
    os.makedirs(output_dir, exist_ok=True)
    result = {}
    for name, gen_fn in SFX_GENERATORS.items():
        path = os.path.join(output_dir, f"{name}.wav")
        if not os.path.exists(path):
            samples = gen_fn(_SAMPLE_RATE)
            _save_wav(samples, path)
        result[name] = path
    return result


def generate_sfx(name: str, output_dir: str) -> Optional[str]:
    """生成单个音效文件

    Args:
        name: 音效名称
        output_dir: 输出目录

    Returns:
        生成的 WAV 文件路径，名称不存在则返回 None
    """
    gen_fn = SFX_GENERATORS.get(name)
    if not gen_fn:
        return None
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{name}.wav")
    if not os.path.exists(path):
        samples = gen_fn(_SAMPLE_RATE)
        _save_wav(samples, path)
    return path
