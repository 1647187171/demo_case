#!/usr/bin/env python3
"""
Video Transcribe 客户端

用法:
  python scripts/video_transcribe_client.py
"""

import base64
import hashlib
import json
import os as _os
import socket as _socket
import ssl
import struct
import sys
import threading
import time
from urllib.parse import urlparse

import requests


# ---- WebSocket client (raw socket, stdlib only) ----
_OP_TEXT = 0x1
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _ws_connect(url: str, timeout: float = 30):
    u = urlparse(url)
    host = u.hostname
    port = u.port or (443 if u.scheme == "wss" else 80)
    path = u.path + ("?" + u.query if u.query else "")

    sock = _socket.create_connection((host, port), timeout=timeout)
    if u.scheme == "wss":
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(sock, server_hostname=host)

    ws_key = base64.b64encode(_os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    sock.sendall(req.encode())

    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("WebSocket 握手时连接断开")
        buf += chunk

    head, rest = buf.split(b"\r\n\r\n", 1)
    head_str = head.decode(errors="ignore")
    first_line = head_str.split("\r\n", 1)[0]
    print(f"[WS] 握手响应: {first_line}")

    if " 101 " not in first_line:
        body_preview = rest[:500].decode(errors="ignore") if rest else ""
        raise RuntimeError(f"WebSocket 握手失败，响应体: {body_preview}")

    expected_accept = base64.b64encode(
        hashlib.sha1((ws_key + _WS_GUID).encode()).digest()
    ).decode()
    for line in head_str.split("\r\n"):
        if line.lower().startswith("sec-websocket-accept:"):
            got = line.split(":", 1)[1].strip()
            if got == expected_accept:
                print("[WS] 握手成功 (Accept Key 验证通过)")
            break

    return sock


def _read_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("WebSocket 连接断开")
        buf += chunk
    return buf


def _send_frame(sock, opcode: int, payload: bytes):
    length = len(payload)
    header = bytes([0x80 | opcode, 0x80 | (length if length < 126 else (126 if length < 65536 else 127))])
    if length >= 65536:
        header += struct.pack("!Q", length)
    elif length >= 126:
        header += struct.pack("!H", length)
    mask_key = _os.urandom(4)
    masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask_key + masked_payload)


def _ws_recv(sock, timeout: float = 30) -> str | None:
    while True:
        sock.settimeout(timeout)
        b1, b2 = struct.unpack("!BB", _read_exact(sock, 2))
        opcode = b1 & 0xF
        masked = (b2 >> 7) & 1
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack("!H", _read_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _read_exact(sock, 8))[0]
        mask_key = _read_exact(sock, 4) if masked else None
        payload = _read_exact(sock, length)
        if mask_key:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        if opcode == _OP_TEXT:
            return payload.decode("utf-8")
        elif opcode == _OP_CLOSE:
            return None
        elif opcode == _OP_PING:
            _send_frame(sock, _OP_PONG, payload)


# ---- Client ----
class VideoTranscribeClient:
    """视频转录客户端"""

    def __init__(self, base_url: str, ws_host: str = "", timeout: float = 600):
        self.base_url = base_url.rstrip("/")
        self.ws_host = ws_host
        self.timeout = timeout
        self._token = ""

    # ---------- auth ----------
    def login(self, phone: str, password: str) -> dict:
        """手机号密码登录，返回 user_info"""
        resp = requests.post(
            f"{self.base_url}/api/sms/password-login",
            json={"phone": phone, "password": password, "frontend": "web"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"登录失败: {body.get('message')} (code={body.get('error_code')})")
        data = body["data"]
        self._token = data["access_token"]
        user = data.get("user_info", {})
        print(f"[登录] 成功, 用户: {user.get('username') or user.get('phone_number')}")
        return user

    @property
    def token(self) -> str:
        return self._token

    # ---------- submit ----------
    def submit(self, input_path: str, output_path: str, language: str = "zh_cn") -> str:
        """提交视频转录任务，返回 task_id"""
        if not self._token:
            raise RuntimeError("请先调用 login() 登录")
        resp = requests.post(
            f"{self.base_url}/api/tasks/video_transcribe_task",
            json={
                "input_path": input_path,
                "output_path": output_path,
                "target_language": language,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            raise RuntimeError(f"提交任务失败: {body.get('message')} (code={body.get('error_code')})")
        task_id = body["data"]["task_id"]
        print(f"[任务] 已提交, task_id={task_id}")
        return task_id

    # ---------- wait via WebSocket ----------
    def wait_result(self, task_id: str) -> dict | None:
        """通过 WebSocket 等待任务完成，返回 result"""
        ws_url = self._build_ws_url(task_id)
        print(f"[WS] 连接 {ws_url}")

        result = None
        finished = False

        def _listen():
            nonlocal result, finished
            sock = None
            try:
                sock = _ws_connect(ws_url, timeout=self.timeout)
                while not finished:
                    message = _ws_recv(sock, timeout=30)
                    if message is None:
                        break
                    data = json.loads(message)
                    if data.get("type") != "task_update":
                        continue
                    payload = data["data"]
                    status = payload.get("task_status", "")
                    progress = payload.get("progress", 0)
                    msg_text = payload.get("msg", "")
                    print(f"[进度] status={status} progress={progress}%  msg={msg_text}")
                    if status.upper() in ("SUCCESS", "FAILURE", "TIMEOUT", "CANCELED"):
                        result = payload.get("result")
                        finished = True
            except Exception as exc:
                print(f"[WS] 连接错误: {exc}")
            finally:
                finished = True
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

        t = threading.Thread(target=_listen, daemon=True)
        t.start()

        deadline = time.time() + self.timeout
        while not finished and time.time() < deadline:
            time.sleep(1)

        if not finished:
            print("[WS] 等待超时")
        t.join(timeout=5)
        return result

    def _build_ws_url(self, task_id: str) -> str:
        if self.ws_host:
            proto = "wss" if self.base_url.startswith("https") else "ws"
            return f"{proto}://{self.ws_host}/ws/aimedia/task/{task_id}/"
        ws_base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{ws_base}/ws/aimedia/task/{task_id}/"

    # ---------- one-shot ----------
    def transcribe(self, input_path: str, output_path: str, language: str = "zh_cn") -> dict:
        """登录 → 提交 → 等待 → 返回转录结果"""
        task_id = self.submit(input_path, output_path, language)
        result = self.wait_result(task_id)
        if result is None:
            raise RuntimeError("未能获取到转录结果")
        return result


# ---- main ----
def main():
    client = VideoTranscribeClient(
        base_url="https://aimediarest.cn",
        ws_host="ai.aimediarest.cn",
        timeout=600,
    )
    client.login(phone="18088888888", password="123456!")

    result = client.transcribe(
        input_path="https://media.aimediarest.cn/video_effects/input/video_translate.mp4",
        output_path="https://media.aimediarest.cn/video_effects/output/",
    )

    print()
    print("=" * 60)
    print("转录结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()


"""
============================================================
转录结果:
{
  "srt_file": "https://media.aimediarest.cn/video_effects/output/bdb4edc1_video_translate.srt",
  "text_file": "https://media.aimediarest.cn/video_effects/output/bdb4edc1_video_translate.txt",
  "speaker_samples_dict": {},
  "vocals_path": "https://media.aimediarest.cn/video_effects/output/bdb4edc1_video_translate_vocals.wav",
  "accompaniment_path": "https://media.aimediarest.cn/video_effects/output/bdb4edc1_video_translate_no_vocals.wav",
  "state_path": "https://media.aimediarest.cn/video_effects/output/bdb4edc1_video_translate.json",
  "cost_time": 4.29,
  "generatedPath": "https://media.aimediarest.cn/video_effects/output/"
}
============================================================
"""