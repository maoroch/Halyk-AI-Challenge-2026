import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from shared.llm_client import LLMClient

load_dotenv()

def main():
    print("=" * 65)
    print("  HALYK AI CHALLENGE — LLM PROVIDER & MODEL DIAGNOSTIC TEST")
    print("=" * 65)

    client = LLMClient()
    if not client.is_configured():
        print("❌ ERROR: No valid GROQ_API_KEY or OPENROUTER_API_KEY found in .env")
        sys.exit(1)

    print(f"Groq API Key configured       : {'YES (' + client.groq_key[:12] + '...)' if client.groq_key else 'NO'}")
    print(f"OpenRouter API Key configured : {'YES (' + client.openrouter_key[:12] + '...)' if client.openrouter_key else 'NO'}")
    print("-" * 65)

    prompt = "Return valid JSON: {\"status\": \"ok\", \"model\": \"test\"}"
    system_prompt = "You are a financial verification assistant. Return valid JSON."

    # Test 1: Full LLMClient completion_json call
    print("\n[TEST 1] Testing LLMClient.completion_json() failover execution...")
    start_time = time.time()
    try:
        res = client.completion_json(prompt, system_prompt=system_prompt)
        elapsed = round(time.time() - start_time, 2)
        print(f"🟢 SUCCESS ({elapsed}s)! LLM returned JSON output:")
        print(f"   {res}")
    except Exception as e:
        print(f"🔴 FAILED: {e}")

    # Test 2: Direct model availability check
    print("\n[TEST 2] Testing individual Groq models...")
    groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3.6-27b"]

    if client.groq_key:
        import requests
        headers = {"Authorization": f"Bearer {client.groq_key}", "Content-Type": "application/json"}
        for m in groq_models:
            t0 = time.time()
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json={"model": m, "messages": [{"role": "user", "content": prompt}]},
                    timeout=10
                )
                dt = round(time.time() - t0, 2)
                if r.status_code == 200:
                    print(f"  - Groq Model [{m:<25}]: 🟢 OK (Status 200, {dt}s)")
                else:
                    print(f"  - Groq Model [{m:<25}]: 🟡 WARNING (Status {r.status_code}: {r.text[:80]})")
            except Exception as ex:
                print(f"  - Groq Model [{m:<25}]: 🔴 ERROR ({ex})")

    print("=" * 65)

if __name__ == "__main__":
    main()
