# -*- coding: utf-8 -*-
"""Local Ollama client (assumes an SSH tunnel/local forward to a remote Ollama instance on port 11434),
same interface as groq_client.chat_json. Fallback path — was not reliable enough for this task's
covenant-computation prompts (see README)."""
import json
import urllib.request

URL = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen2.5:7b-instruct"


def chat_json(system: str, user: str, model: str = MODEL, temperature: float = 0) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
