import os
import json
import time
import logging
import requests
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Configurable Local LLM settings from environment variables (.env)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1/chat/completions")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))
LLM_API_KEY = os.getenv("LLM_API_KEY", "")


class LLMClient:
    """
    Production-grade LLM client connected exclusively to the local LLM endpoint (Ollama / vLLM / Local Docker).
    No cloud fallbacks. Fully configurable via environment variables (.env).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        self.base_url = base_url or LLM_BASE_URL
        self.model_name = model_name or LLM_MODEL_NAME
        self.timeout = timeout or LLM_TIMEOUT
        self.api_key = LLM_API_KEY
        self.disabled = False

    def is_configured(self) -> bool:
        if self.disabled:
            return False
        return bool(self.base_url and self.base_url.strip())

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
            raise ValueError("LLMClient is disabled or base_url is unconfigured.")

        target_model = model or self.model_name
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096
        }

        if response_format and response_format.get("type") == "json_object":
            payload["response_format"] = response_format

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Calling Local LLM ({target_model} @ {self.base_url}) [Attempt {attempt}/{max_retries}]...")
                res = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
                
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict) and "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        logger.info(f"Local LLM call SUCCESS!")
                        return content
                
                # If response_format json_object is unsupported by local endpoint, retry without it
                if res.status_code == 400 and "response_format" in payload:
                    logger.warning(f"Local LLM 400 on response_format, retrying without response_format...")
                    del payload["response_format"]
                    continue

                last_error = f"HTTP Status {res.status_code}: {res.text[:200]}"
                logger.warning(f"Local LLM attempt {attempt} failed: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Local LLM attempt {attempt} connection exception: {e}")

            time.sleep(1.0)

        raise RuntimeError(f"Local LLM execution failed after {max_retries} attempts: {last_error}")

    def completion_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        Guarantees structured JSON dictionary output from local LLM.
        Strips <think> reasoning tags and markdown code blocks.
        """
        full_sys_prompt = (
            (system_prompt or "") +
            "\nOutput ONLY valid JSON. Do not include markdown code block backticks (like ```json), commentary, or reasoning tags."
        ).strip()

        raw_text = self.completion(
            prompt=prompt,
            system_prompt=full_sys_prompt,
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"}
        )

        # Strip reasoning tags (e.g. <think>...</think> from DeepSeek R1 models)
        clean_text = re_strip_think(raw_text)

        # Strip markdown ```json ``` markers
        if "```" in clean_text:
            match = re_search_codeblock(clean_text)
            if match:
                clean_text = match
            else:
                clean_text = clean_text.replace("```json", "").replace("```", "").strip()

        # Parse JSON
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback regex search for JSON object inside braces
            brace_match = re_search_braces(clean_text)
            if brace_match:
                try:
                    return json.loads(brace_match)
                except json.JSONDecodeError:
                    pass
            logger.error(f"Failed to parse JSON from Local LLM response: {raw_text[:300]}")
            raise ValueError(f"Local LLM response is not valid JSON: {clean_text[:200]}")


def re_strip_think(text: str) -> str:
    import re
    return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

def re_search_codeblock(text: str) -> Optional[str]:
    import re
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    return m.group(1).strip() if m else None

def re_search_braces(text: str) -> Optional[str]:
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    return m.group(0).strip() if m else None
