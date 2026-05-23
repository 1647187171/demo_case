import asyncio
import sys
sys.path.insert(0, r"D:\Project\特效")

from media_core.media_core_api import video_ai_effect


def progress(p: int):
    print(f"进度: {p}%")


async def main():
    code, msg = await video_ai_effect(
        input_path=r"C:\Users\25828\Desktop\source\video_translate.mp4",
        output_path=r"C:\Users\25828\Desktop\source\output\output.mp4",
        genre_hint="vlog", # 视频类型提示
        task_id="test_001",
        progress_callback=progress,
    )
    print(f"结果: code={code}, msg={msg}")


if __name__ == "__main__":
    asyncio.run(main())
