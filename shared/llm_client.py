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
            groq_models_to_try = [self.groq_model, "llama-3.1-8b-instant", "qwen/qwen3.6-27b"]
            groq_headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json"
            }

            for g_model in groq_models_to_try:
                groq_payload: Dict[str, Any] = {
                    "model": g_model,
                    "messages": messages,
                    "temperature": temperature
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
                        res = requests.post(GROQ_URL, headers=groq_headers, json=groq_payload, timeout=15)
                        if res.status_code == 200:
                            data = res.json()
                            if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                                content = data["choices"][0]["message"]["content"]
                                logger.info(f"Groq API ({g_model}) LLM call SUCCESS!")
                                return content

                        if res.status_code == 429:
                            retry_after = 2.0
                            try:
                                hdr = res.headers.get("retry-after")
                                if hdr:
                                    retry_after = float(hdr)
                            except Exception:
                                pass
                            if retry_after > 5.0:
                                logger.warning(f"Groq API 429 rate limit ({retry_after}s) on {g_model}. Trying next Groq model...")
                                break
                            logger.warning(f"Groq API 429 rate limit on {g_model}. Backoff {retry_after}s...")
                            time.sleep(min(retry_after, 2.0))
                            continue

                        if res.status_code == 400 and "response_format" in groq_payload:
                            del groq_payload["response_format"]
                            continue

                        logger.warning(f"Groq API ({g_model}) status {res.status_code}: {res.text[:150]}")
                    except Exception as ge:
                        logger.warning(f"Groq API ({g_model}) attempt failed: {ge}")

        # Priority 2: OpenRouter API Fallback Execution
        if self.openrouter_key and self.openrouter_key.strip() and self.openrouter_key != "your_openrouter_api_key_here":
            selected_model = model or self.default_model
            openrouter_headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/Halyk-AI-Challenge-2026",
                "X-Title": "Halyk AI Challenge Covenant Agent"
            }

            openrouter_payload: Dict[str, Any] = {
                "model": selected_model,
                "messages": messages,
                "temperature": temperature
            }
            if response_format:
                openrouter_payload["response_format"] = response_format

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"Calling OpenRouter API ({selected_model})...")
                    res = requests.post(OPENROUTER_URL, headers=openrouter_headers, json=openrouter_payload, timeout=15)
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0]["message"]["content"]
                            logger.info("OpenRouter API LLM call SUCCESS!")
                            return content

                    if res.status_code == 429:
                        logger.warning(f"OpenRouter 429 rate limit. Retrying after 2s...")
                        time.sleep(2)
                        continue

                    logger.warning(f"OpenRouter attempt {attempt} status {res.status_code}: {res.text[:150]}")
                except Exception as oe:
                    logger.warning(f"OpenRouter attempt {attempt} failed: {oe}")

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
