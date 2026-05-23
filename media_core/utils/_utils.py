import os
import re
import json
import uuid


def get_project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_ffmpeg_path() -> str:
    return "ffmpeg"


def print2(msg: str) -> None:
    print(msg)


def get_uuid() -> str:
    return uuid.uuid4().hex[:12]


def extract_json_from_response(text: str) -> dict:
    if not text:
        return {}
    # 尝试直接解析原始JSON
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # 尝试从markdown中提取JSON代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    # 尝试在文本中查找JSON对象
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return {}
