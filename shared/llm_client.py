import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL", "inclusionai/ling-3.0-flash:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class LLMClient:
    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.default_model = default_model or DEFAULT_MODEL
        self.fallback_model = FALLBACK_MODEL
        self.disabled = False

    def is_configured(self) -> bool:
        if self.disabled:
            return False
        return bool(self.api_key and self.api_key.strip() and self.api_key != "your_openrouter_api_key_here")

    def completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[Dict[str, str]] = None,
        max_retries: int = 2
    ) -> str:
        if not self.is_configured():
            raise ValueError("OPENROUTER_API_KEY is not configured or client disabled.")

        selected_model = model or self.default_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Halyk-AI-Challenge-2026",
            "X-Title": "Halyk AI Challenge Covenant Agent"
        }

        payload: Dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature
        }

        if response_format:
            payload["response_format"] = response_format

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                        choice = data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            return choice["message"]["content"]

                    logger.warning(f"OpenRouter response missing choices field: {response.text[:150]}")
                    if attempt < max_retries:
                        payload["model"] = self.fallback_model
                        time.sleep(1)
                        continue

                if response.status_code in (401, 402):
                    logger.warning("Attempting automatic retry with openrouter/free model...")
                    payload["model"] = "openrouter/free"
                    free_res = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=10)
                    if free_res.status_code == 200:
                        free_data = free_res.json()
                        if isinstance(free_data, dict) and "choices" in free_data and len(free_data["choices"]) > 0:
                            return free_data["choices"][0]["message"]["content"]

                    logger.warning("OpenRouter API auth/credits error. Falling back to heuristic parsing.")
                    raise RuntimeError("OPENROUTER_AUTH_OR_CREDITS_ERROR")

                logger.warning(
                    f"Attempt {attempt}/{max_retries} failed with status {response.status_code}: {response.text[:150]}"
                )
                if response.status_code in (404, 429, 500, 502, 503, 504) and attempt < max_retries:
                    payload["model"] = self.fallback_model
                    time.sleep(1)
                    continue

                response.raise_for_status()

            except RuntimeError as re_err:
                self.disabled = True
                raise re_err
            except Exception as e:
                logger.error(f"Error calling OpenRouter API on attempt {attempt}: {e}")
                if attempt == max_retries:
                    self.disabled = True
                    raise e
                time.sleep(1)

        raise RuntimeError("Failed to complete OpenRouter request after max retries")

    def completion_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        fmt = None if ("free" in (model or self.default_model)) else {"type": "json_object"}
        raw_text = self.completion(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            temperature=temperature,
            response_format=fmt
        )
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            raise
