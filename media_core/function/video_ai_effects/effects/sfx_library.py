"""
sfx_library.py — 音效库

管理可用音效资源，提供按名称查询、关键词匹配、情绪匹配音效的功能。
支持预置 WAV 文件和程序化生成的音效。
"""
from typing import Optional, Dict, List
from pathlib import Path
from libs.media_core.utils import utils

# 音效目录：名称 → 文件信息
# 包含预置文件和程序化生成文件
SFX_CATALOG = {
    # --- Impact / Hit ---
    "bass_hit": {"file": "bass_hit.wav", "duration": 0.4, "tags": ["impact", "bass", "heavy", "boom"], "category": "impact"},
    "impact_boom": {"file": "impact_boom.wav", "duration": 0.6, "tags": ["impact", "boom", "dramatic"], "category": "impact"},
    "stomp": {"file": "stomp.wav", "duration": 0.3, "tags": ["impact", "stomp", "heavy"], "category": "impact"},
    "thud": {"file": "thud.wav", "duration": 0.25, "tags": ["impact", "thud", "dull"], "category": "impact"},
    "punch": {"file": "punch.wav", "duration": 0.35, "tags": ["impact", "punch", "hit", "fight"], "category": "impact"},
    "slam": {"file": "slam.wav", "duration": 0.3, "tags": ["impact", "slam", "door"], "category": "impact"},
    "hit": {"file": "hit_01.wav", "duration": 0.4, "tags": ["impact", "emphasis", "punch"], "category": "impact"},
    "hit_heavy": {"file": "hit_02.wav", "duration": 0.3, "tags": ["impact", "heavy", "emphasis"], "category": "impact"},

    # --- Whoosh / Swoosh ---
    "whoosh": {"file": "whoosh_01.wav", "duration": 0.5, "tags": ["transition", "move", "slide", "fast"], "category": "whoosh"},
    "whoosh_fast": {"file": "whoosh_fast.wav", "duration": 0.3, "tags": ["transition", "fast", "quick"], "category": "whoosh"},
    "whoosh_slow": {"file": "whoosh_slow.wav", "duration": 0.6, "tags": ["transition", "slow", "smooth"], "category": "whoosh"},
    "air_sweep": {"file": "air_sweep.wav", "duration": 0.5, "tags": ["transition", "air", "sweep"], "category": "whoosh"},
    "zipping": {"file": "zipping.wav", "duration": 0.4, "tags": ["fast", "zip", "quick"], "category": "whoosh"},
    "swoosh": {"file": "swoosh_01.wav", "duration": 0.4, "tags": ["fast", "quick", "pass"], "category": "whoosh"},
    "swoosh_deep": {"file": "swoosh_deep.wav", "duration": 0.5, "tags": ["deep", "transition", "cinematic"], "category": "whoosh"},

    # --- Pop / Bubble ---
    "pop": {"file": "pop_01.wav", "duration": 0.3, "tags": ["appear", "show", "reveal", "pop"], "category": "pop"},
    "pop_soft": {"file": "pop_02.wav", "duration": 0.15, "tags": ["soft", "gentle", "appear"], "category": "pop"},
    "bubble_pop": {"file": "bubble_pop.wav", "duration": 0.15, "tags": ["bubble", "cute", "pop"], "category": "pop"},
    "soft_pop": {"file": "soft_pop.wav", "duration": 0.2, "tags": ["soft", "gentle"], "category": "pop"},
    "cork_pop": {"file": "cork_pop.wav", "duration": 0.3, "tags": ["celebration", "open", "pop"], "category": "pop"},
    "plop": {"file": "plop.wav", "duration": 0.12, "tags": ["drop", "plop", "cute"], "category": "pop"},
    "pop_sparkle": {"file": "pop_sparkle.wav", "duration": 0.35, "tags": ["sparkle", "magic", "appear"], "category": "pop"},
    "bubble": {"file": "bubble_01.wav", "duration": 0.3, "tags": ["cute", "fun", "playful"], "category": "pop"},

    # --- Click / Tap ---
    "click": {"file": "click_01.wav", "duration": 0.2, "tags": ["select", "confirm", "click"], "category": "click"},
    "click_sharp": {"file": "click_02.wav", "duration": 0.1, "tags": ["sharp", "click", "clean"], "category": "click"},
    "tap": {"file": "tap_01.wav", "duration": 0.15, "tags": ["click", "press", "touch"], "category": "click"},
    "ui_click": {"file": "ui_click.wav", "duration": 0.08, "tags": ["ui", "click", "interface"], "category": "click"},
    "button_tap": {"file": "button_tap.wav", "duration": 0.1, "tags": ["button", "tap", "press"], "category": "click"},
    "keyboard_press": {"file": "keyboard_press.wav", "duration": 0.06, "tags": ["typing", "keyboard", "tech"], "category": "click"},
    "mouse_click": {"file": "mouse_click.wav", "duration": 0.05, "tags": ["mouse", "click", "computer"], "category": "click"},
    "tap_crisp": {"file": "tap_crisp.wav", "duration": 0.07, "tags": ["crisp", "tap", "clean"], "category": "click"},

    # --- Chime / Ding ---
    "chime": {"file": "chime_01.wav", "duration": 0.6, "tags": ["notification", "success", "complete"], "category": "chime"},
    "ding": {"file": "ding_01.wav", "duration": 0.5, "tags": ["correct", "right", "alert"], "category": "chime"},
    "notification": {"file": "notification.wav", "duration": 0.5, "tags": ["notification", "alert", "phone"], "category": "chime"},
    "success_chime": {"file": "success_chime.wav", "duration": 0.8, "tags": ["success", "complete", "celebration"], "category": "chime"},
    "error_buzz": {"file": "error_buzz.wav", "duration": 0.3, "tags": ["error", "wrong", "fail", "buzz"], "category": "chime"},
    "alert_ding": {"file": "alert_ding.wav", "duration": 0.6, "tags": ["alert", "warning", "ding"], "category": "chime"},
    "magic_chime": {"file": "magic_chime.wav", "duration": 0.7, "tags": ["magic", "sparkle", "wonder"], "category": "chime"},
    "ding_dong": {"file": "ding_dong.wav", "duration": 0.8, "tags": ["doorbell", "ding", "dong"], "category": "chime"},
    "cash_register": {"file": "cash_01.wav", "duration": 0.5, "tags": ["money", "sale", "price", "cash"], "category": "chime"},

    # --- Riser / Build ---
    "riser_up": {"file": "riser_up.wav", "duration": 1.0, "tags": ["riser", "build", "tension", "up"], "category": "riser"},
    "riser_down": {"file": "riser_down.wav", "duration": 0.8, "tags": ["riser", "down", "fall"], "category": "riser"},
    "tension_build": {"file": "tension_build.wav", "duration": 1.5, "tags": ["tension", "build", "dramatic"], "category": "riser"},

    # --- Comedy / Fun ---
    "laugh": {"file": "laugh_01.wav", "duration": 0.8, "tags": ["funny", "comedy", "joke", "laugh"], "category": "comedy"},
    "boing": {"file": "boing.wav", "duration": 0.4, "tags": ["comedy", "bounce", "funny", "cartoon"], "category": "comedy"},
    "spring": {"file": "spring.wav", "duration": 0.3, "tags": ["comedy", "spring", "bounce"], "category": "comedy"},
    "cartoon_blink": {"file": "cartoon_blink.wav", "duration": 0.15, "tags": ["cartoon", "blink", "cute"], "category": "comedy"},
    "horn_honk": {"file": "horn_honk.wav", "duration": 0.5, "tags": ["horn", "funny", "honk", "car"], "category": "comedy"},
    "slide_whistle": {"file": "slide_whistle.wav", "duration": 0.6, "tags": ["comedy", "whistle", "slide", "fail"], "category": "comedy"},
    "wah_wah": {"file": "wah_wah.wav", "duration": 0.5, "tags": ["fail", "comedy", "wah", "sad"], "category": "comedy"},
    "wow": {"file": "wow_01.wav", "duration": 0.6, "tags": ["surprise", "amazing", "wow"], "category": "comedy"},

    # --- Musical / Drum ---
    "drum_hit": {"file": "drum_01.wav", "duration": 0.3, "tags": ["beat", "rhythm", "music"], "category": "musical"},
    "drum_kick": {"file": "drum_kick.wav", "duration": 0.3, "tags": ["kick", "drum", "beat", "bass"], "category": "musical"},
    "drum_snare": {"file": "drum_snare.wav", "duration": 0.25, "tags": ["snare", "drum", "beat"], "category": "musical"},
    "drum_hihat": {"file": "drum_hihat.wav", "duration": 0.1, "tags": ["hihat", "drum", "beat", "tick"], "category": "musical"},
    "bass_drop": {"file": "bass_drop.wav", "duration": 0.5, "tags": ["bass", "drop", "electronic", "edm"], "category": "musical"},
    "cymbal": {"file": "cymbal.wav", "duration": 0.6, "tags": ["cymbal", "crash", "drama"], "category": "musical"},
    "clap": {"file": "clap.wav", "duration": 0.2, "tags": ["clap", "applause", "beat"], "category": "musical"},

    # --- Tech / Digital ---
    "glitch": {"file": "glitch.wav", "duration": 0.3, "tags": ["glitch", "tech", "digital", "error"], "category": "tech"},
    "data_transfer": {"file": "data_transfer.wav", "duration": 0.4, "tags": ["data", "transfer", "tech", "loading"], "category": "tech"},
    "laser": {"file": "laser.wav", "duration": 0.3, "tags": ["laser", "sci-fi", "shoot", "space"], "category": "tech"},
    "power_up": {"file": "power_up.wav", "duration": 0.6, "tags": ["power", "up", "game", "level"], "category": "tech"},
    "digital_beep": {"file": "digital_beep.wav", "duration": 0.15, "tags": ["beep", "digital", "tech"], "category": "tech"},
    "robot_talk": {"file": "robot_talk.wav", "duration": 0.4, "tags": ["robot", "ai", "tech", "voice"], "category": "tech"},

    # --- Ambient / Nature ---
    "rain_soft": {"file": "rain_soft.wav", "duration": 1.0, "tags": ["rain", "ambient", "nature", "calm"], "category": "ambient"},
    "wind_gentle": {"file": "wind_gentle.wav", "duration": 1.0, "tags": ["wind", "ambient", "nature"], "category": "ambient"},
    "sparkle_shimmer": {"file": "sparkle_shimmer.wav", "duration": 0.5, "tags": ["sparkle", "shimmer", "magic", "twinkle"], "category": "ambient"},
    "ocean_wave": {"file": "ocean_wave.wav", "duration": 1.2, "tags": ["ocean", "wave", "nature", "calm"], "category": "ambient"},
    "camera_shutter": {"file": "shutter_01.wav", "duration": 0.3, "tags": ["photo", "camera", "snap"], "category": "ambient"},

    # --- Emotion / Reaction ---
    "heartbeat": {"file": "heartbeat_01.wav", "duration": 0.5, "tags": ["love", "heart", "emotion"], "category": "emotion"},
    "laugh_track": {"file": "laugh_track.wav", "duration": 0.6, "tags": ["laugh", "audience", "comedy"], "category": "emotion"},
    "aww_cute": {"file": "aww_cute.wav", "duration": 0.4, "tags": ["cute", "aww", "adorable"], "category": "emotion"},
    "gasp_shock": {"file": "gasp_shock.wav", "duration": 0.3, "tags": ["gasp", "shock", "surprise"], "category": "emotion"},
    "applause_short": {"file": "applause_short.wav", "duration": 0.8, "tags": ["applause", "cheer", "success"], "category": "emotion"},
    "heartbeat_sound": {"file": "heartbeat_sound.wav", "duration": 0.5, "tags": ["heartbeat", "tension", "drama"], "category": "emotion"},

    # --- Transition ---
    "swoosh_cut": {"file": "swoosh_cut.wav", "duration": 0.25, "tags": ["cut", "transition", "edit"], "category": "transition"},
    "snap_cut": {"file": "snap_cut.wav", "duration": 0.1, "tags": ["snap", "cut", "quick"], "category": "transition"},
    "whoosh_impact": {"file": "whoosh_impact.wav", "duration": 0.5, "tags": ["whoosh", "impact", "transition"], "category": "transition"},
    "reverse_swoosh": {"file": "reverse_swoosh.wav", "duration": 0.4, "tags": ["reverse", "swoosh", "rewind"], "category": "transition"},
    "zoom_in": {"file": "zoom_in.wav", "duration": 0.35, "tags": ["zoom", "focus", "emphasis"], "category": "transition"},
}

# 关键词 → 音效名称映射（150+ 关键词）
_KEYWORD_MAP = {
    # 金钱/商业
    "buy": "cash_register", "price": "cash_register", "sale": "cash_register",
    "discount": "cash_register", "money": "cash_register", "cost": "cash_register",
    "利润": "cash_register", "赚钱": "cash_register", "价格": "cash_register",
    "打折": "cash_register", "优惠": "cash_register", "红包": "cash_register",
    "coin": "cash_register", "dollar": "cash_register", "currency": "cash_register",
    # 成功/完成
    "free": "success_chime", "win": "success_chime", "success": "success_chime",
    "done": "success_chime", "complete": "success_chime", "achieve": "success_chime",
    "成功": "success_chime", "完成": "success_chime", "胜利": "success_chime",
    "赢了": "success_chime", "恭喜": "success_chime",
    # 惊讶
    "wow": "wow", "amazing": "wow", "incredible": "wow", "unbelievable": "wow",
    "哇": "wow", "太棒了": "wow", "震惊": "wow", "竟然": "wow",
    "surprise": "gasp_shock", "omg": "gasp_shock", "shock": "gasp_shock",
    "天哪": "gasp_shock", "不可思议": "gasp_shock",
    # 爱情/情感
    "love": "heartbeat", "heart": "heartbeat", "like": "heartbeat",
    "爱": "heartbeat", "喜欢": "heartbeat", "心动": "heartbeat",
    "kiss": "heartbeat", "baby": "heartbeat", "sweet": "heartbeat",
    "可爱": "aww_cute", "萌": "aww_cute", "cute": "aww_cute",
    # 搞笑
    "funny": "laugh", "lol": "laugh", "haha": "laugh", "joke": "laugh",
    "搞笑": "laugh", "段子": "laugh", "哈哈": "laugh", "笑死": "laugh",
    "fun": "laugh_track", "comedy": "laugh_track", "喜剧": "laugh_track",
    "fail": "wah_wah", "失败": "wah_wah", "尴尬": "wah_wah",
    # 开始/选择
    "click": "click", "start": "click", "begin": "click",
    "开始": "click", "选择": "click", "确认": "ui_click",
    "select": "button_tap", "choose": "button_tap",
    # 出现/展示
    "new": "pop", "reveal": "pop", "show": "pop", "look": "pop",
    "新": "pop", "展示": "pop", "看": "pop", "发现": "pop",
    "appear": "pop_sparkle", "magic": "magic_chime", "魔法": "magic_chime",
    # 快速/移动
    "fast": "swoosh", "quick": "swoosh", "go": "swoosh",
    "快": "swoosh", "冲": "swoosh", "速度": "swoosh",
    "run": "whoosh_fast", "fly": "whoosh_fast", "跑": "whoosh_fast", "飞": "whoosh_fast",
    # 冲击/强调
    "boom": "impact_boom", "explosion": "impact_boom", "爆炸": "impact_boom",
    "hit": "punch", "fight": "punch", "打": "punch", "击": "punch",
    "smash": "slam", "break": "slam", "碎": "slam",
    # 音乐/节奏
    "music": "drum_kick", "beat": "drum_kick", "音乐": "drum_kick",
    "节奏": "drum_kick", "dance": "drum_kick", "跳舞": "drum_kick",
    "drop": "bass_drop", "重低音": "bass_drop",
    # 科技
    "tech": "digital_beep", "digital": "digital_beep", "科技": "digital_beep",
    "数据": "data_transfer", "ai": "robot_talk", "机器人": "robot_talk",
    "game": "power_up", "游戏": "power_up", "升级": "power_up", "level": "power_up",
    "glitch": "glitch", "bug": "glitch", "故障": "glitch",
    # 食物
    "food": "cork_pop", "eat": "bubble_pop", "cook": "cork_pop",
    "美食": "cork_pop", "好吃": "soft_pop", "烹饪": "cork_pop",
    "recipe": "pop", "chef": "pop", "菜": "pop",
    "delicious": "soft_pop", "taste": "bubble_pop",
    # 运动/健身
    "workout": "drum_kick", "exercise": "punch", "gym": "impact_boom",
    "训练": "punch", "健身": "drum_kick", "运动": "whoosh_fast",
    # 通知/提醒
    "notification": "notification", "alert": "alert_ding", "提醒": "alert_ding",
    "消息": "notification", "注意": "alert_ding",
    "warning": "error_buzz", "wrong": "error_buzz", "错误": "error_buzz",
    # 鼓掌/喝彩
    "applause": "applause_short", "cheer": "applause_short", "鼓掌": "applause_short",
    "bravo": "applause_short", "encore": "applause_short",
    # 拍照
    "photo": "camera_shutter", "camera": "camera_shutter", "拍照": "camera_shutter",
    "selfie": "camera_shutter", "自拍": "camera_shutter",
    # 转场
    "next": "swoosh_cut", "then": "swoosh_cut", "接下来": "swoosh_cut",
    "transition": "whoosh_impact", "change": "snap_cut", "换": "snap_cut",
    # 强调
    "important": "bass_hit", "key": "bass_hit", "重点": "bass_hit",
    "注意": "alert_ding", "必看": "bass_hit", "绝密": "bass_hit",
    # 自然
    "rain": "rain_soft", "雨": "rain_soft",
    "wind": "wind_gentle", "风": "wind_gentle",
    "ocean": "ocean_wave", "海": "ocean_wave",
    "sparkle": "sparkle_shimmer", "闪": "sparkle_shimmer",
}

# 情绪 → 推荐音效列表
_MOOD_SFX_MAP = {
    "energetic": ["drum_kick", "bass_hit", "whoosh_fast", "swoosh_cut", "clap", "power_up"],
    "happy": ["pop", "success_chime", "bubble_pop", "applause_short", "pop_sparkle", "ding_dong"],
    "calm": ["soft_pop", "notification", "wind_gentle", "sparkle_shimmer", "ding", "tap_crisp"],
    "dramatic": ["impact_boom", "bass_drop", "tension_build", "riser_up", "thud", "slam"],
    "funny": ["boing", "spring", "laugh", "wah_wah", "slide_whistle", "cartoon_blink", "horn_honk"],
    "tech": ["digital_beep", "data_transfer", "laser", "glitch", "robot_talk", "power_up"],
    "romantic": ["heartbeat", "magic_chime", "aww_cute", "sparkle_shimmer", "cork_pop"],
    "scary": ["tension_build", "heartbeat_sound", "impact_boom", "glitch", "riser_up"],
    "epic": ["impact_boom", "bass_drop", "riser_up", "drum_kick", "cymbal", "whoosh_impact"],
    "cute": ["bubble_pop", "aww_cute", "plop", "soft_pop", "pop_sparkle", "boing"],
}


def _get_sfx_dir() -> Path:
    """获取音效资源目录路径"""
    try:
        project_root = Path(utils.get_project_root())
        sfx_dir = project_root / "res" / "effects" / "sfx"
        if sfx_dir.exists():
            return sfx_dir
    except Exception:
        pass
    return Path("res/effects/sfx")


def _get_gen_dir() -> Path:
    """获取程序化生成音效目录（直接生成到 res/effects/sfx/ 和预置文件放一起）"""
    return _get_sfx_dir()


def _ensure_sfx_file(name: str, catalog_entry: dict) -> Optional[str]:
    """确保音效文件存在，预置文件不存在时从生成器生成"""
    sfx_dir = _get_sfx_dir()
    path = sfx_dir / catalog_entry["file"]
    if path.exists():
        return str(path)

    # 尝试其他扩展名
    for ext in [".wav", ".mp3", ".ogg"]:
        alt = sfx_dir / f"{name}{ext}"
        if alt.exists():
            return str(alt)

    # 尝试程序化生成
    gen_dir = _get_gen_dir()
    gen_dir.mkdir(parents=True, exist_ok=True)
    gen_path = gen_dir / catalog_entry["file"]

    if gen_path.exists():
        return str(gen_path)

    try:
        from .sfx_generator import generate_sfx
        result = generate_sfx(name, str(gen_dir))
        if result:
            return result
    except Exception:
        pass

    return None


def get_sfx(name: str) -> Optional[str]:
    """根据音效名称获取音效文件路径"""
    entry = SFX_CATALOG.get(name)
    if not entry:
        return None
    return _ensure_sfx_file(name, entry)


def get_all_sfx() -> Dict[str, str]:
    """获取所有可用音效的名称→路径映射"""
    result = {}
    for name in SFX_CATALOG:
        path = get_sfx(name)
        if path:
            result[name] = path
    return result


def get_sfx_by_category(category: str) -> Dict[str, str]:
    """按分类获取音效"""
    result = {}
    for name, entry in SFX_CATALOG.items():
        if entry.get("category") == category:
            path = get_sfx(name)
            if path:
                result[name] = path
    return result


def match_sfx_to_keyword(keyword: str) -> Optional[str]:
    """根据关键词匹配最相关的音效文件路径"""
    keyword_lower = keyword.lower()
    sfx_name = _KEYWORD_MAP.get(keyword_lower)
    if sfx_name:
        return get_sfx(sfx_name)
    for kw, sfx in _KEYWORD_MAP.items():
        if kw in keyword_lower or keyword_lower in kw:
            return get_sfx(sfx)
    return None


def match_sfx_to_visual(visual_tags: List[str]) -> Optional[str]:
    """根据视觉分析标签匹配音效"""
    tag_to_sfx = {
        "jump": "whoosh_fast", "run": "whoosh_fast", "dance": "drum_kick",
        "cook": "cork_pop", "eat": "bubble_pop", "exercise": "punch",
        "smile": "pop", "laugh": "laugh", "cry": "wah_wah",
        "explosion": "impact_boom", "fire": "whoosh_impact",
        "water": "ocean_wave", "rain": "rain_soft",
        "machine": "digital_beep", "computer": "keyboard_press",
        "car": "whoosh_fast", "food": "soft_pop",
        "product": "pop_sparkle", "money": "cash_register",
        "sport": "drum_kick", "fight": "punch",
        "celebrate": "applause_short", "clap": "clap",
        "sing": "success_chime", "music": "drum_kick",
    }
    for tag in visual_tags:
        tag_lower = tag.lower()
        if tag_lower in tag_to_sfx:
            return get_sfx(tag_to_sfx[tag_lower])
        for key, sfx_name in tag_to_sfx.items():
            if key in tag_lower or tag_lower in key:
                return get_sfx(sfx_name)
    return None


def get_sfx_for_mood(mood: str) -> List[str]:
    """根据情绪获取推荐音效列表"""
    mood_lower = mood.lower()
    for key, sfx_list in _MOOD_SFX_MAP.items():
        if key in mood_lower or mood_lower in key:
            return sfx_list
    return ["pop", "whoosh", "click"]


def ensure_sfx_generated():
    """预生成所有不存在的音效文件"""
    from .sfx_generator import ensure_all_sfx
    gen_dir = _get_gen_dir()
    ensure_all_sfx(str(gen_dir))
