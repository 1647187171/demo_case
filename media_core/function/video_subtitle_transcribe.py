"""ASR 语音转字幕 stub 模块"""

import os


class VideoSubtitleTranscribe:
    @staticmethod
    def video_subtitle_transcribe(
        input_path: str,
        target_language: str = "zh-CN",
        output_dir: str = "",
    ):
        print(f"[ASR Stub] Transcribe called: {input_path}")
        srt_path = r"C:\Users\25828\Desktop\source\bdb4edc1_video_translate.srt"
        if os.path.exists(srt_path):
            return ((0, "Success"), srt_path)
        return ((9999, "SRT file not found"), "")
