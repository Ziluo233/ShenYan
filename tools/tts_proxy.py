#!/usr/bin/env python3
"""MiMo TTS VoiceDesign 代理 · 给 RikkaHub 补上音色描述
用法：python3 tts_proxy.py
密钥：优先读环境变量 MIMO_KEY；否则读同目录 .mimo_key 文件（一行，sk- 开头）
音色：若同目录有 voice_style.txt，优先用它的内容（改音色只需改这个文件）
"""
import json, os, http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIMO_HOST = "api.xiaomimimo.com"
MODEL = "mimo-v2.5-tts-voicedesign"

BASE = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get("MIMO_KEY", "").strip()
if not KEY:
    kf = os.path.join(BASE, ".mimo_key")
    if os.path.exists(kf):
        KEY = open(kf, encoding="utf-8").read().strip()

# 音色描述：voice_style.txt 优先（改音色只需改这个文件）
SF = os.path.join(BASE, "voice_style.txt")
STYLE_FILE = open(SF, encoding="utf-8").read().strip() if os.path.exists(SF) else ""

# 内置音色表（没有 voice_style.txt 时用；RikkaHub「语音」填左边的名字）
VOICE_MAP = {
    "守夜人": (
        "一位二十多岁的霸道总裁，音色沉稳有气场。吐字清晰语速稍快，"
        "语气温和，偶尔带一丝很轻的笑意，对着恋人说话。"
    ),
    "晚安": (
        "一位年轻男性，嗓音温柔低缓，音量不大，像在床边轻声说话。"
        "语速很慢，语气柔软耐心，气息平稳，尾音轻轻收着。"
    ),
    "清朗": (
        "一位二十多岁的年轻男性，中低音，清朗干净，语速自然偏慢，"
        "语气平静松弛，像熟人之间不紧不慢地聊天。"
    ),
}
DEFAULT_VOICE = "守夜人"

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_POST(self):
        try:
            if not self.path.endswith("/chat/completions"):
                self.send_error(404); return
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln))
            voice = (body.get("audio") or {}).get("voice") or DEFAULT_VOICE
            style = STYLE_FILE or VOICE_MAP.get(voice, VOICE_MAP[DEFAULT_VOICE])
            messages = list(body.get("messages") or [])
            if not messages or messages[0].get("role") != "user":
                messages = [{"role": "user", "content": style}] + messages
            fwd = {
                "model": body.get("model") or MODEL,
                "messages": messages,
                "audio": {"format": "pcm16", "optimize_text_preview": False},
                "stream": True,
            }
            print(f"[req] voice={voice} messages={len(messages)}", flush=True)
            conn = http.client.HTTPSConnection(MIMO_HOST, timeout=180)
            conn.request("POST", "/v1/chat/completions",
                         body=json.dumps(fwd, ensure_ascii=False).encode("utf-8"),
                         headers={"Content-Type": "application/json",
                                  "api-key": KEY,
                                  "Accept": "text/event-stream"})
            resp = conn.getresponse()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.getheader("Content-Type") or "text/event-stream")
            self.end_headers()
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
            conn.close()
        except Exception as e:
            print(f"[err] {e}", flush=True)
            try:
                self.send_error(500, str(e))
            except Exception:
                pass


if __name__ == "__main__":
    if not KEY:
        raise SystemExit("[!] 没找到密钥：把 sk- 开头的 key 写进同目录 .mimo_key（或设环境变量 MIMO_KEY）")
    print("描述来源：" + ("voice_style.txt" if STYLE_FILE else "脚本内置"))
    print("tts_proxy 听着 9263，把 RikkaHub 的 base URL 指到 http://127.0.0.1:9263")
    ThreadingHTTPServer(("127.0.0.1", 9263), Handler).serve_forever()
