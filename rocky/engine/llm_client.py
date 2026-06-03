import os
import httpx
import json
import logging
from typing import Any
from rocky.config import get_config

logger = logging.getLogger("rocky.llm_client")

class GroqEngine:
    def __init__(self, host: str, timeout: int, models: dict[str, str]):
        self.host = host
        self.timeout = timeout
        self.models = models
        self.api_key = os.getenv("GROQ_API_KEY", "")

    async def chat(self, worker_type: str, messages: list[dict], format_schema: Any = None) -> str:
        """Query Groq API via HTTP POST."""
        self.api_key = os.getenv("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
            
        model = self.models.get(worker_type, "llama-3.1-8b-instant")
        url = f"{self.host.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.0 if format_schema else 0.7
        }
        
        if format_schema:
            payload["response_format"] = {"type": "json_object"}
            
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                res_data = response.json()
                content = res_data["choices"][0]["message"]["content"]
                return content
            except Exception as e:
                logger.error(f"Groq API call failed: {e}")
                raise e

    async def generate(self, worker_type: str, prompt: str, system: str = None, format_schema: Any = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return await self.chat(worker_type, messages, format_schema)

class OllamaEngine:
    def __init__(self, host: str, timeout: int, models: dict[str, str]):
        self.host = host
        self.timeout = timeout
        self.models = models

    async def chat(self, worker_type: str, messages: list[dict], format_schema: Any = None) -> str:
        """Query local Ollama server."""
        model = self.models.get(worker_type)
        if not model:
            model = "qwen3:8b" if worker_type == "coder" else "gemma3:4b"
            
        url = f"{self.host.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0 if format_schema else 0.7}
        }
        
        if format_schema:
            payload["format"] = format_schema.model_json_schema()
            
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                res_data = response.json()
                content = res_data["message"]["content"]
                return content
            except Exception as e:
                logger.error(f"Ollama local call failed: {e}")
                raise e

    async def generate(self, worker_type: str, prompt: str, system: str = None, format_schema: Any = None) -> str:
        model = self.models.get(worker_type, "gemma3:4b")
        url = f"{self.host.rstrip('/')}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0 if format_schema else 0.7}
        }
        if system:
            payload["system"] = system
        if format_schema:
            payload["format"] = format_schema.model_json_schema()
            
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                res_data = response.json()
                content = res_data["response"]
                return content
            except Exception as e:
                logger.error(f"Ollama local generate failed: {e}")
                raise e

class LLMClient:
    """Unified factory client that switches between Groq API and local Ollama fallback."""
    def __init__(self):
        config = get_config()
        self.provider = config.engine.provider
        
        self.groq = GroqEngine(config.groq.host, config.groq.timeout, config.groq.models)
        self.ollama = OllamaEngine(config.ollama.host, config.ollama.timeout, config.ollama.models)

    async def health_check(self) -> bool:
        """Check connection state of configured provider."""
        config = get_config()
        if self.provider == "groq":
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                logger.warning("GROQ_API_KEY environment variable is missing.")
                return False
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    res = await client.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"})
                    return res.status_code == 200
            except Exception:
                return False
        else:
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    res = await client.get(f"{config.ollama.host.rstrip('/')}/")
                    return res.status_code == 200
            except Exception:
                return False

    async def chat(self, worker_type: str, messages: list[dict], format_schema: Any = None) -> str:
        config = get_config()
        self.api_key = os.getenv("GROQ_API_KEY", "")
        if self.provider == "groq" and self.api_key:
            try:
                return await self.groq.chat(worker_type, messages, format_schema)
            except Exception as e:
                logger.warning(f"Groq API call failed. Falling back to local Ollama. Error: {e}")
                return await self.ollama.chat(worker_type, messages, format_schema)
        else:
            return await self.ollama.chat(worker_type, messages, format_schema)

    async def generate(self, worker_type: str, prompt: str, system: str = None, format_schema: Any = None) -> str:
        config = get_config()
        self.api_key = os.getenv("GROQ_API_KEY", "")
        if self.provider == "groq" and self.api_key:
            try:
                return await self.groq.generate(worker_type, prompt, system, format_schema)
            except Exception as e:
                logger.warning(f"Groq API generate failed. Falling back to local Ollama. Error: {e}")
                return await self.ollama.generate(worker_type, prompt, system, format_schema)
        else:
            return await self.ollama.generate(worker_type, prompt, system, format_schema)
