# -*- coding: utf-8 -*-
"""Reusable Groq chat-completion client (UA fix + JSON-safe UTF-8 + retries)."""
import json
import os
import re
import time
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_raw_keys = os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY", "")
API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
if not API_KEYS:
    raise RuntimeError(
        "No Groq API key found. Set GROQ_API_KEY (or comma-separated GROQ_API_KEYS) "
        "in your environment or a .env file (see .env.example)."
    )
_key_index = 0
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


def _current_key() -> str:
    return API_KEYS[_key_index % len(API_KEYS)]


def _rotate_key() -> str:
    global _key_index
    _key_index += 1
    key = _current_key()
    print(f"    [key-rotate] switching to key #{_key_index % len(API_KEYS) + 1}/{len(API_KEYS)}", flush=True)
    return key


def chat(system: str, user: str, model: str = MODEL, temperature: float = 0, max_retries: int = None, max_tokens: int = 1500) -> dict:
    n_keys = len(API_KEYS)
    if max_retries is None:
        max_retries = n_keys * 2 + 2  # try every key at least twice before giving up
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err = None
    exhausted_keys = set()
    for attempt in range(max_retries):
        req = urllib.request.Request(URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {_current_key()}")
        req.add_header("Content-Type", "application/json; charset=utf-8")
        req.add_header("User-Agent", "curl/8.7.1")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return {"content": content, "usage": usage}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            last_err = f"HTTP {e.code}: {err_body[:300]}"
            if e.code == 429:
                exhausted_keys.add(_current_key())
                if len(exhausted_keys) < n_keys:
                    _rotate_key()
                    continue
                # all keys exhausted this cycle -> actually wait it out
                m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", err_body)
                if m:
                    h = float(m.group(1) or 0)
                    mi = float(m.group(2) or 0)
                    s = float(m.group(3) or 0)
                    wait = h * 3600 + mi * 60 + s + 5
                else:
                    wait = 15 * (attempt + 1)
                print(f"    [429] all {n_keys} key(s) exhausted, waiting {wait:.0f}s...", flush=True)
                time.sleep(wait)
                exhausted_keys.clear()
                continue
            if e.code == 413:
                raise RuntimeError(last_err)  # prompt too large, retrying won't help
            if e.code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(last_err)
        except Exception as e:
            last_err = str(e)
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Groq call failed after {max_retries} retries: {last_err}")


def chat_json(system: str, user: str, model: str = MODEL) -> dict:
    result = chat(system, user, model=model)
    try:
        return json.loads(result["content"])
    except json.JSONDecodeError:
        # strip markdown fences if present
        text = result["content"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
