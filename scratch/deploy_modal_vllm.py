import modal
from fastapi import FastAPI, Request

app = modal.App("halyk-covenant-llm")

# Clean, robust PyTorch GPU container image without vllm/DTensor conflicts
llm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("torch==2.4.0", "transformers>=4.44.0", "accelerate", "bitsandbytes", "fastapi")
)

MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
web_app = FastAPI()

@app.cls(
    image=llm_image,
    gpu="A10G",
    max_containers=1,
    scaledown_window=300,
    timeout=300,
)
class ModelServer:
    @modal.enter()
    def load_model(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        
        print(f"Loading {MODEL_NAME} on NVIDIA A10G GPU...")
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto"
        )
        print("Model loaded successfully on GPU!")

    @modal.method()
    def generate_text(self, prompt: str, temperature: float = 0.0):
        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda")
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=1024,
            do_sample=(temperature > 0.0),
            temperature=max(temperature, 0.01) if temperature > 0 else None
        )
        res_text = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return res_text

@web_app.post("/v1/chat/completions")
@web_app.post("/generate")
@web_app.post("/")
async def chat_completions(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    prompt = ""
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        prompt += f"<|im_start|>{role}\n{content}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    
    temperature = data.get("temperature", 0.0)
    
    server = ModelServer()
    text = await server.generate_text.remote.aio(prompt, temperature)
    
    return {
        "id": "chatcmpl-modal",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": text
                }
            }
        ]
    }

@app.function(image=llm_image)
@modal.asgi_app()
def serve():
    return web_app
