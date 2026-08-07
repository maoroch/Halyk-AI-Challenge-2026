import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_PRIMARY_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMClient:
    """
    Unified production-grade LLM client with multi-provider failover.
    Supports Groq API (Primary) and OpenRouter API (Secondary) with rate-limit handling,
    structured JSON parsing, and automatic fallback.
    """

    def __init__(
        self,
        openrouter_key: Optional[str] = None,
        groq_key: Optional[str] = None,
        default_model: Optional[str] = None
    ):
        self.openrouter_key = openrouter_key or OPENROUTER_API_KEY
        self.groq_key = groq_key or GROQ_API_KEY
        self.default_model = default_model or OPENROUTER_DEFAULT_MODEL
        self.groq_model = GROQ_PRIMARY_MODEL
        self.disabled = False
        # Per-model rate-limit cooldown: model_name -> unix timestamp when it becomes available
        self._groq_cooldown: Dict[str, float] = {}

    def is_configured(self) -> bool:
        if self.disabled:
            return False
        has_openrouter = bool(self.openrouter_key and self.openrouter_key.strip() and self.openrouter_key != "your_openrouter_api_key_here")
        has_groq = bool(self.groq_key and self.groq_key.strip())
        return has_openrouter or has_groq

    def completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[Dict[str, str]] = None,
        max_retries: int = 3
    ) -> str:
        if not self.is_configured():
            raise ValueError("No valid LLM API key configured.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Priority 1: Groq API Execution (Multi-model failover across 3 active Groq models)
        if self.groq_key and self.groq_key.strip():
            groq_models_to_try = [self.groq_model, "qwen/qwen3.6-27b", "llama-3.1-8b-instant"]
            groq_headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json"
            }

            for g_model in groq_models_to_try:
                # Skip model if still in rate-limit cooldown
                cooldown_until = self._groq_cooldown.get(g_model, 0)
                if time.time() < cooldown_until:
                    remaining = cooldown_until - time.time()
                    logger.warning(f"Groq ({g_model}) in cooldown for {remaining:.0f}s more. Skipping.")
                    continue

                groq_payload: Dict[str, Any] = {
                    "model": g_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 2048
                }
                if response_format and response_format.get("type") == "json_object":
                    sys_content = system_prompt or ""
                    if "json" not in sys_content.lower() and "json" not in prompt.lower():
                        messages_copy = list(messages)
                        if messages_copy and messages_copy[0]["role"] == "system":
                            messages_copy[0] = {"role": "system", "content": messages_copy[0]["content"] + "\nReturn valid JSON."}
                        else:
                            messages_copy.insert(0, {"role": "system", "content": "Return valid JSON."})
                        groq_payload["messages"] = messages_copy
                    groq_payload["response_format"] = response_format

                for attempt in range(1, 3):
                    try:
                        logger.info(f"Calling Groq API ({g_model})...")
                        res = requests.post(GROQ_URL, headers=groq_headers, json=groq_payload, timeout=60)
                        if res.status_code == 200:
                            data = res.json()
                            if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0]["message"]["content"]
                                logger.info(f"Groq API ({g_model}) LLM call SUCCESS!")
                                return content

                        if res.status_code == 429:
                            retry_after = 5.0
                            try:
                                hdr = res.headers.get("retry-after")
                                if hdr:
                                    retry_after = float(hdr)
                            except Exception:
                                pass
                            # Record cooldown regardless of duration
                            self._groq_cooldown[g_model] = time.time() + retry_after
                            logger.warning(f"Groq API 429 on {g_model}. Cooldown set for {retry_after:.0f}s. Trying next model.")
                            break  # Always move to next model immediately

                        if res.status_code == 400 and "response_format" in groq_payload:
                            del groq_payload["response_format"]
                            continue

                        logger.warning(f"Groq API ({g_model}) status {res.status_code}: {res.text[:150]}")
                    except Exception as ge:
                        logger.warning(f"Groq API ({g_model}) attempt failed: {ge}")

        # Priority 2: OpenRouter API Fallback Execution
        # Try multiple free-tier models in order of quality
        OPENROUTER_FREE_MODELS = [
            "qwen/qwen3-8b:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "microsoft/phi-3-mini-128k-instruct:free",
        ]
        if self.openrouter_key and self.openrouter_key.strip() and self.openrouter_key != "your_openrouter_api_key_here":
            # Prefer the configured default model first, then free fallbacks
            models_to_try = [model or self.default_model] + [
                m for m in OPENROUTER_FREE_MODELS if m != (model or self.default_model)
            ]
            openrouter_headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Halyk-AI-Challenge-2026",
                "X-Title": "Halyk AI Challenge Covenant Agent"
            }

            for or_model in models_to_try:
                openrouter_payload: Dict[str, Any] = {
                    "model": or_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 2048
                }
                if response_format:
                    openrouter_payload["response_format"] = response_format

                for attempt in range(1, max_retries + 1):
                    try:
                        logger.info(f"Calling OpenRouter API ({or_model})...")
                        res = requests.post(OPENROUTER_URL, headers=openrouter_headers, json=openrouter_payload, timeout=60)
                        if res.status_code == 200:
                            data = res.json()
                            if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0]["message"]["content"]
                                logger.info(f"OpenRouter API ({or_model}) LLM call SUCCESS!")
                                return content

                        if res.status_code == 429:
                            logger.warning(f"OpenRouter ({or_model}) 429 rate limit. Trying next model...")
                            break  # Try next model instead of waiting

                        logger.warning(f"OpenRouter ({or_model}) attempt {attempt} status {res.status_code}: {res.text[:150]}")
                    except Exception as oe:
                        logger.warning(f"OpenRouter ({or_model}) attempt {attempt} failed: {oe}")

        raise RuntimeError("ALL_LLM_PROVIDERS_FAILED")

    def completion_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0
    ) -> Union[Dict[str, Any], list]:
        fmt = {"type": "json_object"}
        raw_text = self.completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            response_format=fmt
        )
        return self._parse_json_response(raw_text)

    def _parse_json_response(self, raw_text: str) -> Union[Dict[str, Any], list]:
        cleaned = raw_text.strip()

        if "<think>" in cleaned:
            if "</think>" in cleaned:
                cleaned = cleaned.split("</think>", 1)[-1].strip()
            else:
                raise ValueError(f"Reasoning response truncated before closing </think>: {raw_text[:200]}")

        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start_dict = cleaned.find("{")
            end_dict = cleaned.rfind("}")
            if start_dict != -1 and end_dict != -1 and end_dict > start_dict:
                try:
                    return json.loads(cleaned[start_dict:end_dict + 1])
                except json.JSONDecodeError:
                    pass

            start_arr = cleaned.find("[")
            end_arr = cleaned.rfind("]")
            if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
                try:
                    return json.loads(cleaned[start_arr:end_arr + 1])
                except json.JSONDecodeError:
                    pass

            raise ValueError(f"Could not parse valid JSON from LLM output: {raw_text[:200]}")

    def completion_list_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0
    ) -> list:
        """Call LLM without json_object format constraint — for prompts expecting a raw JSON array.
        Falls back to completion_json if the response happens to be a dict with a list value."""
        raw_text = self.completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            # No response_format here — avoids json_object wrapper forcing
        )
        parsed = self._parse_json_response(raw_text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # e.g. {"txn_ids": [...]} — extract the first list value
            for v in parsed.values():
                if isinstance(v, list):
                    return v
        return []

