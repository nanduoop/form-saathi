"""Thin wrapper over the Meta Model API (OpenAI-compatible)."""

import base64
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
    api_key=os.getenv("MODEL_API_KEY"),
)

CHAT_MODEL = os.getenv("CHAT_MODEL", "muse-spark-1.3")
SEGMENT_MODEL = os.getenv("SEGMENT_MODEL", "sam-3.1")
VOICE_MODEL = os.getenv("VOICE_MODEL", "muse-voice-transcribe")


def _data_url(image_path):
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def chat(prompt, image_path=None, tools=None, model=CHAT_MODEL, system=None, images=None):
    content = [{"type": "text", "text": prompt}]
    for p in ([image_path] if image_path else []) + list(images or []):
        content.append({"type": "image_url", "image_url": {"url": _data_url(p)}})
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    kwargs = {}
    if tools:
        # The Meta API only accepts tool_choice="auto".
        kwargs = {"tools": tools, "tool_choice": "auto"}
    resp = client.chat.completions.create(model=model, messages=messages, **kwargs)
    return resp.choices[0].message


def parse_json(text):
    t = re.sub(r"^```(json)?", "", (text or "").strip()).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0) if m else t)


def chat_json(prompt, image_path=None, system=None):
    msg = chat(prompt, image_path=image_path, system=system)
    return parse_json(getattr(msg, "content", "") or "")


def segment(image_path, prompt, model=SEGMENT_MODEL):
    """SAM 3.1: returns boxes in source-pixel coordinates."""
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": _data_url(image_path)},
        ]}],
    )
    text = getattr(resp, "output_text", "") or str(resp)
    boxes = []
    for m in re.finditer(r"<\|box;(.*?)\|>", text):
        box = {}
        for part in m.group(1).split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    box[k] = int(v)
                except ValueError:
                    try:
                        box[k] = float(v)
                    except ValueError:
                        box[k] = v
        if all(k in box for k in ("x1", "y1", "x2", "y2")):
            boxes.append(box)
    return boxes


def transcribe(audio_path, language=None, model=VOICE_MODEL):
    """Muse Voice Transcribe through the OpenAI-compatible audio endpoint."""
    kwargs = {"model": model}
    if language:
        kwargs["language"] = language
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(file=f, **kwargs)
    return getattr(resp, "text", None) or str(resp)
