import os
import json
from typing import Optional


def call_qwen_model(
    user_content: str,
    system_content: str = "",
    model_name: str = "qwen3.6-plus",
    temperature: float = 0.7,
    max_tokens: int = 65536,
) -> str:
    """调用阿里云 DashScope 兼容 OpenAI 接口的千问模型。

    约定：
    - 成功时返回模型文本内容
    - 失败时返回空字符串，让上层逻辑自动走 fallback
    """
    api_key = os.getenv("ALIYUN_LLM_KEY")

    if not api_key:
        print("[LLM] ALIYUN_LLM_KEY is not set, skip remote LLM call")
        return ""

    try:
        import httpx

        messages = []
        if system_content:
            messages.append({"role": "system", "content": system_content})
        messages.append({"role": "user", "content": user_content})

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
            if resp.status_code != 200:
                print(f"[LLM] API returned {resp.status_code}: {resp.text[:200]}")
                return ""
            data = resp.json()

        return _extract_message_text(data)
    except Exception as e:
        print(f"[LLM] call failed: {e}")
        return ""


def _extract_message_text(data: dict) -> str:
    """兼容不同 SDK 返回结构，尽量提取首条文本。"""
    try:
        choices = data.get("choices")
        if choices:
            message = choices[0].get("message")
            if message:
                content = message.get("content", "")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
                        if text:
                            parts.append(text)
                    if parts:
                        return "\n".join(parts)
    except Exception:
        pass
    return ""
