# 视频AI智能特效项目 — 完整架构与调用流程说明

## 一、项目概览

本项目是一个**全自动视频AI特效处理系统**。输入一个视频文件，系统会自动完成：语音转字幕、视觉内容分析、音频节拍检测、LLM智能导演决策、字幕样式选择、花字关键词强调、音效编排、动态变速、场景转场、调色、贴纸叠加、动态图形生成，最后通过FFmpeg渲染输出带全部特效的成品视频。

**核心流水线**：

```
字幕加载 → 视觉分析+节拍检测(并发) → LLM导演 → 特效编排 → ASS生成 → FFmpeg渲染
```

---

## 二、入口文件：`test_ai_effects.py`

### 调用链起点

```python
if __name__ == "__main__":
    asyncio.run(main())
```

### `main()` 函数

- **位置**: `test_ai_effects.py:12`
- **逻辑**: 调用 `video_ai_effect()` 并传入以下参数：
  - `input_path`: 输入视频路径
  - `output_path`: 输出视频路径
  - `genre_hint`: 视频类型提示（如 `"vlog"`）
  - `task_id`: 任务标识
  - `progress_callback`: 进度回调函数 `progress()`

### `progress()` 函数

- **位置**: `test_ai_effects.py:8`
- **逻辑**: 简单的进度打印回调，打印 `"进度: {p}%"`

---

## 三、API层：`media_core/media_core_api.py`

### `video_ai_effect()` 函数

- **位置**: `media_core_api.py:4`
- **逻辑**: 直接委托给 `VideoAiEffectsCore.video_ai_effect()`，将所有参数透传。这是对外暴露的公开API入口。

---

## 四、核心引擎：`media_core/function/video_ai_effects/video_ai_effects_core.py`

### 类 `VideoAiEffectsCore`（单例模式）

#### 4.1 `video_ai_effect()` 静态方法

- **位置**: `video_ai_effects_core.py:219`
- **逻辑**:
  1. 生成 `task_id`（如果未提供则用UUID）
  2. 创建 `internal_callback` 包装用户提供的进度回调，处理异步/同步兼容
  3. 构建 `RenderingConfig` 配置对象，默认启用全部功能模块
  4. 获取 `VideoAiEffectsCore` 单例实例
  5. 通过 `run_in_executor` 在线程池中执行 `_apply_sync_impl()`，避免阻塞异步事件循环

#### 4.2 `_apply_sync_impl()` 核心同步实现

- **位置**: `video_ai_effects_core.py:286`
- **逻辑**: 这是整个系统的核心流水线，分为以下步骤：

---

### 流水线详细步骤

#### Step 0：初始化（行 297-332）

- 创建 `EffectsPathManager` 管理临时目录结构（`ass/`, `srt/`, `audio/`, `output/`, `temp/`）
- 定义 `check_cancel()` 内部函数，检查任务是否被取消（通过内存集合 + 取消标志文件双重检查）
- 定义 `report()` 内部函数，安全调用进度回调
- **F9：爆款模板**：如果 `config.template_name` 已指定，调用 `apply_template()` 应用预设模板配置

---

#### Step 1：字幕加载/生成与拆行（行 336-362）

- **调用**: `_load_subtitles(config, path_mgr)` → 第974行
  - 如果提供了SRT路径且为JSON格式 → 调用 `parse_json_subtitles()`（`ass_engine.py:376`）
  - 如果提供了SRT路径且为SRT格式 → 调用 `parse_srt_to_segments()`（`ass_engine.py:353`）
  - 都没有则返回空列表

- **调用**: `_auto_transcribe(config, path_mgr)` → 第983行（当上面没有字幕时）
  - 调用 `VideoSubtitleTranscribe.video_subtitle_transcribe()` → `video_subtitle_transcribe.py:8`
  - 目前是stub实现，返回硬编码的SRT路径
  - 转录成功后调用 `parse_srt_to_segments()` 解析SRT

- **`parse_srt_to_segments()`** — `ass_engine.py:353`
  - 用正则分割SRT文本块
  - 解析时间戳（`HH:MM:SS,mmm --> HH:MM:SS,mmm`）
  - 转换为毫秒并构建 `SubtitleSegment` 列表

- **`parse_json_subtitles()`** — `ass_engine.py:376`
  - 读取JSON文件，每项包含 `text`, `start`, `end`, `words`（可选词级时间）
  - 构建带词级时间信息的 `SubtitleSegment` 列表

- **拆行**: `auto_split_segments()` — `ass_engine.py:41`
  - 获取视频分辨率，计算可用像素宽度
  - 使用 `_estimate_text_pixel_width()` 估算文本像素宽度
  - 如果超出1.3倍则按像素宽度拆分 → `_split_text_by_pixel_width()`（在自然断点处切割，不在英文单词中间断开）
  - 无像素信息时退化为按字符数拆分 → `_split_text_at_breaks()`
  - 拆分后重新分配时间 → `_redistribute_timing()`

---

#### Step 1.5：视觉分析与节拍检测（并发）（行 365-394）

使用 `ThreadPoolExecutor(max_workers=2)` 并发执行两个分析任务。

##### 视觉分析: `_run_visual_analysis()` → 第925行

- **调用**: `analyze_video_visuals()` → `visual_analyzer.py:100`
  1. **`extract_frames()`** — `visual_analyzer.py:19`
     - 用 FFmpeg 按 `fps=1/interval_sec` 从视频中提取关键帧图像（JPG格式）
     - 默认间隔2秒，最多30帧
  2. **`detect_scene_transitions()`** — `visual_analyzer.py:68`
     - 用 FFmpeg 的 `select='gt(scene,threshold)'` 滤镜检测场景切换时间点
  3. **`_analyze_frames()`** — `visual_analyzer.py:139`
     - 获取VL配置管理器 → `get_config_manager()`
     - 创建视觉分析器 → `create_vision_analyzer(config)`
     - 调用 VL 模型分析每帧图像（发送描述提示词，要求返回JSON）
     - 解析每帧响应 → `_parse_frame_response()`：提取 `scene_type`, `objects`, `actions`, `mood`, `style`
     - 汇总：统计最常见的情绪、场景类型、去重后的物体和动作
     - 生成摘要 → `_generate_summary()`
     - 返回 `VisualAnalysisResult`

##### 节拍检测: `_run_beat_detection()` → 第937行

- **调用**: `detect_beats()` → `beat_sync.py:19`
  1. **`_extract_audio()`** — `beat_sync.py:165`：用 FFmpeg 提取视频音轨为 WAV 文件
  2. 使用 `librosa` 库加载音频（采样率22050Hz）
  3. **`librosa.beat.beat_track()`**：检测节拍位置和 BPM
  4. **`librosa.onset.onset_detect()`**：检测音频起始点（onset）
  5. 返回 `BeatInfo`（包含 `tempo`, `beat_times`, `onset_times`, `onset_strengths`）

---

#### Step 2：LLM导演决策（行 397-456）

##### 如果用户未指定样式，调用LLM导演:

- **调用**: `analyze_and_recommend()` → `llm_director.py:26`
  1. **`build_director_user_prompt()`** — `effect_director_prompt.py:92`
     - 构建包含视频信息、转录文本、视觉分析结果、节拍信息、可用样式列表的完整提示词
  2. **`llm.call_qwen_model()`** — `_llm.py:6`
     - 调用阿里云 DashScope 的千问模型（`qwen3.6-plus`）
     - 使用 OpenAI 兼容接口，通过 `httpx` 发送POST请求
     - 成功返回文本内容，失败返回空字符串
  3. **`_parse_director_response()`** — `llm_director.py:127`
     - 解析LLM返回的JSON，提取：
       - `style_id`：推荐的样式ID
       - `genre`：视频类型
       - `keyword_emphases`：关键词花字强调（通过 `_parse_keyword_emphases()`）
       - `effects`：音效编排计划（为每个效果查找真实文件路径）
       - `bgm_recommendation`：BGM推荐
     - 调用 `_validate_style_for_platform()` 确保社交平台不使用企业/新闻类正式风格
     - 调用 `_align_effects_to_beats()` 将音效时间戳对齐到最近节拍
     - 调用 `_enforce_min_gap()` 确保同类特效间隔≥0.5秒
  4. **降级方案**: `_fallback_selection()` — `llm_director.py:276`
     - 当LLM不可用时，通过关键词匹配+视觉分析选择样式和音效
     - 通过 `_genre_from_visual()` 从视觉分析检测到的物体推断视频类型
     - 通过 `_select_style_by_genre_and_platform()` 选择样式
     - 通过 `get_sfx_for_mood()` 按情绪推荐音效

##### LLM失败时的增强降级:

- **调用**: `_extract_keyword_emphases()` → `llm_director.py:379`
  1. 从 `KEYWORD_EMOJI_MAP`（huazi_presets.py:298）中匹配关键词→表情映射
  2. 匹配数字+单位模式（如"3倍"、"100%"）
  3. 不足时调用 `_fill_keywords_from_text()` 通过TF-IDF式打分补充中文实词
  4. 轮转分配花字预设（pop_highlight → emoji_pop → scale_pulse → ...）

---

#### Step 2.2：关键词音效对齐 + 缩放脉冲收集（行 458-507）

##### 频率上限控制:

- 根据视频时长计算上限：
  - `max_keywords`: 每5秒1个，3-8个
  - `max_sfx_count`: 每5秒1个，3-8个
  - `max_zoom_count`: 每8秒1个，2-6个

##### 关键词SFX生成: `_generate_keyword_sfx()` → 第796行

- 为每个关键词找到所在字幕段
- 通过 `_find_keyword_word_timing()` 精确定位关键词在音频中的时间位置
- 通过 `match_sfx_to_keyword()` 匹配音效文件
- 生成对应该时间点的 `EffectPlan` 列表

##### SFX合并去重: `_deduplicate_effects()` → 第910行

- 按时间排序，间隔<0.4秒的只保留第一个

##### 缩放脉冲收集: `_collect_zoom_pulses()` → renderer.py:129

- **调用**: `get_strong_beats()` → `beat_sync.py:124`
  - 筛选 onset_strength 超过指定百分位的强拍
  - 最多返回12个
- 合并强拍时间 + 关键词出现时间
- 按时间排序，去重（最小间隔0.3秒），截断到上限

---

#### Step 2.4：智能开头Hook检测（F1）（行 513-540）

- **调用**: `detect_best_hook_moment()` → `hook_engine.py:47`
  - 滑动窗口（默认0.5秒步长）扫描整个视频
  - 每个窗口打三个维度的分：
    - **节拍密度** (权重0.40)：通过 `_score_beat_density()` 评分
    - **关键词密度** (权重0.30)：通过 `_score_keyword_density()` 评分
    - **Onset强度** (权重0.30)：通过 `_score_onset_strength()` 评分
  - 返回能量最高且>0.05的窗口起始时间
- 如果未找到高能量片段且Hook模式为"auto"，则将模式设为"none"跳过Hook
- **调用**: `select_hook_text()` → `hook_engine.py:165`
  - 从转录文本提取第一句有意义的话
  - 或从HOOK_TEMPLATES模板库中随机选择（question/statistic/wow/countdown四种风格）

---

#### Step 2.5：动态变速分析（F2）（行 543-583）

- **调用**: `generate_speed_ramp_segments()` → `speed_ramper.py:77`
  1. 按固定窗口（默认2秒）分析每个段的能量：`analyze_segment_energy()` 评估节拍密度(0.40) + 关键词密度(0.30) + 字幕活跃度(0.30)
  2. 合并相邻且能量差<0.15的段
  3. 去除过短段（<1.5秒）
  4. 分配速度：低能量段加速(1.2-1.5x)，高能量段慢放(0.7-0.9x)，普通段1.0x
  5. 首尾段强制正常速度
- **调用**: `apply_speed_ramp_prepass()` → `speed_ramper.py:237`
  - 通过 `build_speed_ramp_filters()` 构建FFmpeg分段变速滤镜
  - 用FFmpeg预处理出变速后视频，后续流水线使用该文件
- **调用**: `_remap_effects_for_speed()` → 第862行
  - 将所有已计划的特效时间戳按变速段重新映射到新时间轴

---

#### Step 2.6：背景音乐推荐（行 586-604）

- **调用**: `recommend_bgm()` → `bgm_library.py:108`
  - 三层优先级匹配：
    1. LLM推荐的情绪直接匹配
    2. 视频类型匹配（每种类型有对应的BGM风格）
    3. 视觉分析的情绪匹配（energetic→快节奏, calm→舒缓等）
  - 返回BGM文件路径，设置默认音量为0.1

---

#### Step 2.7：场景转场（F4）（行 610-624）

- **调用**: `generate_transition_plan()` → `transition_engine.py:122`
  - 过滤场景切换时间点（去重、去首尾1秒内、最小间隔2秒）
  - 通过节拍密度差评估场景间能量变化
  - `select_transition_type()`：根据能量差选择转场类型
    - 差<0.05: crossfade（交叉溶解）
    - 差<0.15: zoom_blur（缩放模糊）
    - 差<0.25: slide_push（滑动推开）
    - 差<0.35: whip_pan（快速摇镜模糊）
    - 差>=0.35: glitch（数字故障）
  - 确保相邻转场类型不重复

---

#### Step 2.75：传播力评分（F10）（行 628-648）

- **调用**: `score_engagement()` → `engagement_scorer.py:21`
  - 六个维度打分（0-100）：
    - **Hook强度** (25%)：`_score_hook()` — 有teaser加40分，有文字叠加加20分
    - **节奏感** (20%)：`_score_pacing()` — 有变速段比例加分，有节拍信息加分
    - **特效密度** (15%)：`_score_density()` — 理想密度0.5-2.0个特效/秒
    - **多样性** (15%)：`_score_variety()` — 变速+转场类型数+关键词数+SFX数
    - **排版质量** (15%)：`_score_typography()` — 动态排版启用+变量字号+词性配色+多位置
    - **音频质量** (10%)：`_score_audio()` — SFX数+BGM+节拍信息
  - 生成改进建议：`_generate_suggestions()`

---

#### Step 2.8：贴纸 + 调色 + 动态图形（行 660-697）

##### 自动调色（F6）:

- **调用**: `select_color_preset()` → `color_grading.py:75`
  - 优先级：手动提示 > 视觉分析情绪 > 视频类型映射
  - 四种预设：warm(暖色), cool(冷色), cinematic_desat(电影感), vibrant(鲜艳)

##### 动态图形叠加（F7）:

- **调用**: `generate_motion_graphics_from_keywords()` → `motion_graphics.py:206`
  - 数字/步骤关键词 → progress_bar（进度条，用drawbox画）
  - 指向性关键词（看/注意/重点）→ arrow（动态箭头，用drawtext绘制）
  - 感叹/惊讶关键词 → particle_burst（粒子爆发，6个方向扩散的小方块）
  - 3字以上名词 → lower_third（下三分之一字幕条）

##### 贴纸匹配:

- **调用**: `_select_stickers_for_keywords()` → 第92行
  - 从 `res/effects/catalog.json` 加载贴纸目录
  - 按关键词→贴纸映射匹配，最多3个，间隔≥3秒

---

#### Step 3：生成ASS字幕文件（行 699-734）

##### 获取视频分辨率 → 应用高级样式:

- **`_apply_premium_subtitle_style()`** → 第47行
  - 设置 `BorderStyle=1`（描边+投影），替代硬边框
  - 描边宽度7.0，阴影2.5，背景色半透明黑
  - 追加边缘模糊 `\be1`
  - 横屏时字号按比例放大（最大1.3倍）

- **`_apply_orientation_margins()`** → 第72行
  - 横屏：边距≥120
  - 方形：边距≥80
  - 竖屏：按平台安全边距（TikTok 180, Instagram 170, YouTube 150）

##### 生成ASS文件: `generate_ass_file()` → `ass_engine.py:331`

1. **字体解析**: `resolve_font_for_language()` → 根据语言选择合适字体

2. **`_build_script_info()`** → 第406行
   - 生成 `[Script Info]` 段：标题、分辨率、ASS版本

3. **`_build_styles_section()`** → 第418行
   - 生成 `[V4+ Styles]` 段
   - 包含 Default 样式、Highlight 高亮样式（如果配置了卡拉OK高亮色）
   - 为每个花字关键词生成独立的 `Huazi_*` 样式（通过 `_build_huazi_style()`）

4. **`_build_events_section()`** → 第523行（核心字幕事件生成）
   - 对每个字幕片段：
     - **无词级时间时自动生成**: `_generate_pseudo_word_timing()` — 第259行
       - CJK文字：逐字均分时间
       - 拉丁文字：逐词均分时间
     - **F3动态排版模式**: `build_kinetic_word_sequence()` → 来自 `kinetic_presets.py`
       - 按词性配色（名词=暖色, 动词=冷色, 形容词=亮色）
       - 变量字号
     - **默认逐词高亮模式**: `_build_dialogue_text()` → 第659行
       - 调用 `_apply_per_word_highlight()` — 第676行
       - 对每个词生成 `\kf` 卡拉OK填充标签
       - 命中关键词的词：绿色高亮 + 放大弹回动画
       - 未命中：默认高亮色
     - **自动缩放**: 文本像素宽度超过可用宽度时，自动缩小字体（最小55%）
     - **动画覆盖**: `_build_animation_overrides()` — 第755行
       - 支持20+种动画类型：FADE_IN, BOUNCE, SHAKE, POP, RAINBOW, ELASTIC, WAVE, FLASH, SPIRAL等
     - **多位置**: `get_caption_position()` 根据权重分配到不同屏幕位置
   - **花字关键词覆盖层**: `_build_keyword_overlay_dialogues()` — 第603行
     - 在关键词出现的精确时间生成 `layer=1` 的覆盖Dialogue
     - 通过 `_find_keyword_word_timing()` 精准定位
     - 调用 `apply_huazi()` 应用花字预设效果

5. **写入文件**: 将所有段拼接写入 `.ass` 文件

---

#### Step 4：FFmpeg渲染（行 737-760）

##### `FFmpegRenderer.render()` → `renderer.py:22`

判断是否有音频混合需求（音效或BGM），选择渲染路径：

##### 路径A：纯字幕渲染 `_render_subtitles_only()` → 第236行

1. 构建滤镜链：
   - **F11自动裁切**: `build_crop_filter()` → 从 `crop_engine.py`
   - **F6自动调色**: `build_color_grading_filter()` → 从 `color_grading.py`
   - **字幕烧录**: `subtitles='...ass'` 滤镜
   - **Zoompan缩放脉冲**: `_build_zoompan_expression()` → 第91行
     - 构建正弦钟形脉冲表达式：`1 + Σ delta*sin(PI*(time-t0)/dur) * gate(t0, t0+dur)`
   - **F4转场滤镜**: `_build_variety_transitions()` → 第189行
     - 调用 `build_all_transition_filters()` → `transition_engine.py:190`
     - 为每个转场构建对应FFmpeg滤镜（fade/zoompan/gblur/geq等）
   - **F7动态图形**: `_build_motion_graphics_vf()` → 第206行
     - 调用 `build_all_motion_graphics_filters()` → `motion_graphics.py:179`
2. 有贴纸时走 `_render_subtitles_with_stickers()` → 第328行
   - 使用 `filter_complex` 将贴纸图片缩放、淡入淡出后叠加到视频
3. 执行FFmpeg命令 → `_run_ffmpeg()` → 第686行

##### 路径B：完整音频混合渲染 `_render_with_audio()` → 第392行

- 输入包含：原始视频 + 每个SFX音效文件 + BGM文件 + 贴纸图片
- 视频链：裁切→调色→字幕→zoompan→转场→动态图形→贴纸叠加
- 音频链（两阶段混合）：
  - 阶段1：混合所有效果音（SFX + BGM），使用 `adelay` 设置延迟，`volume` 控制音量
  - 阶段2：`amix` 将效果音叠加到提升1.3倍音量的原始音频上
  - 支持 **F5音频闪避**（ducking）：当启用时用 `sidechaincompress` 在SFX/BGM响起时压缩原始音频
- 输出：H.264视频 + AAC音频，`-movflags +faststart` 优化网页播放

##### 后处理：

- **F1 Hook片头拼接**: `_prepend_hook()` → 第750行
  - text_overlay模式：生成纯色背景+动画文字片段
  - extract_teaser模式：从原视频提取指定时间段片段
  - 用concat协议拼接 Hook + 正片
- **F8 结尾CTA画面**: `_append_end_screen()` → 第866行
  - 提取最后一帧做模糊背景
  - 叠加频道名和CTA文字（如"Follow for more!"）
  - 淡入淡出动画 → concat拼接

##### 输出校验：`_validate_output()` → 第172行

- 检查输出文件大小≥10KB

---

## 五、数据模型总览

所有数据模型定义在 `models.py` 中：

| 模型 | 用途 |
|------|------|
| `ASSStyleConfig` | ASS字幕样式配置（字体、颜色、描边、动画等20+属性） |
| `SubtitleSegment` | 字幕片段（时间范围+文本+词级时间） |
| `VisualAnalysisResult` | 视觉分析结果（帧分析+情绪+场景切换+物体/动作） |
| `BeatInfo` | 音频节拍信息（BPM+节拍时间+onset） |
| `KeywordEmphasis` | 花字关键词配置（预设+颜色+缩放+emoji+位置） |
| `EffectPlan` | 特效计划（SFX/花字/贴纸/转场） |
| `EffectDirectorOutput` | LLM导演输出（样式+特效+关键词+BGM推荐） |
| `RenderingConfig` | 渲染总配置（包含全部F1-F11功能开关） |
| `HookConfig` | Hook片头配置 |
| `SpeedRampConfig` | 动态变速配置 |
| `KineticTypographyConfig` | 动态排版配置 |
| `TransitionConfig` | 转场配置 |
| `ColorGradingConfig` | 调色配置 |
| `MotionGraphicsConfig` | 动态图形配置 |
| `EngagementScore` | 传播力评分 |

---

## 六、辅助模块索引

| 文件 | 核心功能 |
|------|---------|
| `utils/_utils.py` | 项目根目录获取、UUID生成、FFmpeg路径、JSON提取工具函数 |
| `utils/_llm.py` | 千问模型API调用（DashScope OpenAI兼容接口） |
| `utils/path_manager.py` | 任务目录结构管理（ass/srt/audio/output/temp） |
| `ass_styles/__init__.py` | 121种字幕样式的注册与查询（16个分类） |
| `effects/beat_sync.py` | librosa节拍检测、强拍筛选 |
| `effects/sfx_library.py` | 80+音效库、关键词→音效映射、情绪→音效推荐 |
| `effects/bgm_library.py` | 7种BGM风格库、多维度推荐 |
| `effects/hook_engine.py` | Hook片段检测（能量评分）、文字模板库 |
| `effects/speed_ramper.py` | 分段能量分析、变速方案生成、FFmpeg变速滤镜 |
| `effects/transition_engine.py` | 6种转场类型、能量差自动选择、FFmpeg滤镜构建 |
| `effects/color_grading.py` | 4种调色预设、情绪/类型→预设映射 |
| `effects/motion_graphics.py` | 5种动态图形（进度条/箭头/圈选/粒子/字幕条）的FFmpeg滤镜生成 |
| `effects/huazi_presets.py` | 12种花字视觉预设、关键词→Emoji映射(150+)、颜色方案 |
| `effects/engagement_scorer.py` | 6维度传播力评分、改进建议生成 |
| `prompts/effect_director_prompt.py` | LLM导演系统提示词（含音效分类、花字预设说明、输出格式） |
| `video_subtitle_transcribe.py` | ASR语音转字幕（目前为stub，返回固定SRT路径） |

---

## 七、完整调用关系图

```text
test_ai_effects.py::main()
  └─ media_core_api.py::video_ai_effect()
       └─ VideoAiEffectsCore.video_ai_effect()          [静态方法，创建配置]
            └─ VideoAiEffectsCore._apply_sync_impl()     [核心同步流水线]
                 │
                 ├─ [Step 0] EffectsPathManager()        [目录管理]
                 ├─ [Step 0] apply_template()             [F9: 爆款模板]
                 │
                 ├─ [Step 1] _load_subtitles()
                 │    ├─ parse_srt_to_segments()          [SRT解析]
                 │    └─ parse_json_subtitles()           [JSON字幕解析]
                 ├─ [Step 1] _auto_transcribe()
                 │    └─ VideoSubtitleTranscribe.video_subtitle_transcribe()
                 ├─ [Step 1] auto_split_segments()        [长字幕拆行]
                 │
                 ├─ [Step 1.5] _run_visual_analysis()  ─┐ [并发]
                 │    └─ analyze_video_visuals()          │
                 │         ├─ extract_frames()            │
                 │         ├─ detect_scene_transitions()  │
                 │         └─ _analyze_frames()           │ [VL模型分析]
                 │                                        │
                 ├─ [Step 1.5] _run_beat_detection()   ──┘
                 │    └─ detect_beats()                   [librosa节拍检测]
                 │
                 ├─ [Step 2] analyze_and_recommend()      [LLM导演]
                 │    ├─ build_director_user_prompt()
                 │    ├─ llm.call_qwen_model()            [千问模型调用]
                 │    ├─ _parse_director_response()
                 │    │    ├─ _parse_keyword_emphases()
                 │    │    ├─ _validate_style_for_platform()
                 │    │    ├─ _align_effects_to_beats()
                 │    │    └─ _enforce_min_gap()
                 │    └─ _fallback_selection()            [降级方案]
                 │         └─ _extract_keyword_emphases() [增强降级]
                 │
                 ├─ [Step 2.2] _generate_keyword_sfx()    [关键词→音效]
                 │    ├─ _find_keyword_word_timing()
                 │    └─ match_sfx_to_keyword()
                 ├─ [Step 2.2] _deduplicate_effects()
                 ├─ [Step 2.2] _collect_zoom_pulses()
                 │    └─ get_strong_beats()
                 │
                 ├─ [Step 2.4] detect_best_hook_moment()  [F1: Hook检测]
                 ├─ [Step 2.4] select_hook_text()
                 │
                 ├─ [Step 2.5] generate_speed_ramp_segments() [F2: 变速]
                 ├─ [Step 2.5] apply_speed_ramp_prepass()
                 ├─ [Step 2.5] _remap_effects_for_speed()
                 │
                 ├─ [Step 2.6] recommend_bgm()            [BGM推荐]
                 │
                 ├─ [Step 2.7] generate_transition_plan() [F4: 转场]
                 │
                 ├─ [Step 2.75] score_engagement()        [F10: 传播力评分]
                 │
                 ├─ [Step 2.8] select_color_preset()      [F6: 调色]
                 ├─ [Step 2.8] generate_motion_graphics_from_keywords() [F7: 动态图形]
                 ├─ [Step 2.8] _select_stickers_for_keywords() [贴纸匹配]
                 │
                 ├─ [Step 3] _apply_premium_subtitle_style()  [高级字幕样式]
                 ├─ [Step 3] _apply_orientation_margins()     [方向感知边距]
                 ├─ [Step 3] generate_ass_file()              [ASS生成]
                 │    ├─ _build_script_info()
                 │    ├─ _build_styles_section()
                 │    └─ _build_events_section()
                 │         ├─ _generate_pseudo_word_timing()
                 │         ├─ _apply_per_word_highlight()
                 │         ├─ _build_animation_overrides()
                 │         └─ _build_keyword_overlay_dialogues()
                 │              └─ apply_huazi()              [12种花字预设]
                 │
                 └─ [Step 4] FFmpegRenderer.render()          [FFmpeg渲染]
                      ├─ _render_subtitles_only() 或 _render_with_audio()
                      │    ├─ _build_zoompan_expression()     [缩放脉冲滤镜]
                      │    ├─ _build_variety_transitions()    [转场滤镜]
                      │    └─ _build_motion_graphics_vf()     [动态图形滤镜]
                      ├─ _prepend_hook()                      [F1: 片头拼接]
                      ├─ _append_end_screen()                 [F8: 片尾CTA]
                      └─ _validate_output()                   [输出校验]
```
